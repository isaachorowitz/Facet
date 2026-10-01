"""Clef-flash with its Qwen3.5 backbone on MLX and its joint schema head on PyTorch.

The released code runs the whole model in PyTorch. On Apple Silicon that path has
no fused kernels for Qwen3.5's gated delta-net layers and falls back to plain
torch. mlx-vlm ships Metal kernels for them, so the backbone (vision encoder and
language model, 99.9% of the compute) runs in MLX. The small head that turns
hidden states into per-option logits stays in PyTorch, unchanged, so outputs
match the release (checked by scripts/compare_backends.py).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import mlx.core as mx
import numpy as np
import torch


def _mx(value: Any) -> mx.array:
    """The processor may hand back torch tensors or, once mlx-vlm is imported, MLX arrays."""
    if isinstance(value, mx.array):
        return value
    if isinstance(value, torch.Tensor):
        value = value.float().numpy() if value.is_floating_point() else value.numpy()
    return mx.array(np.asarray(value))


class _LexicalTable:
    """Stands in for the output-embedding matrix the head indexes.

    The head only ever reads the rows for option tokens, and the schema is fixed,
    so rows are fetched from the MLX weights once and cached.
    """

    def __init__(self, weight: mx.array, device: torch.device, dtype: torch.dtype) -> None:
        self.weight, self.device, self.dtype = weight, device, dtype
        self.cache: dict[tuple[int, ...], torch.Tensor] = {}

    def __getitem__(self, token_ids: torch.Tensor) -> torch.Tensor:
        key = tuple(int(t) for t in token_ids.tolist())
        rows = self.cache.get(key)
        if rows is None:
            picked = self.weight[mx.array(key, dtype=mx.int32)].astype(mx.float32)
            rows = torch.from_numpy(np.array(picked)).to(self.device, self.dtype)
            self.cache[key] = rows
        return rows


class ClefMLX:
    def __init__(self, path: str | Path, device: str = "mps", quantize_bits: int | None = None) -> None:
        from mlx_vlm import load
        from safetensors.torch import load_file
        from transformers import AutoProcessor

        path = Path(path)
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
        import joint_schema_model as jsm

        self.jsm = jsm
        self.model, _ = load(str(path))
        if quantize_bits:
            import mlx.nn as nn

            nn.quantize(self.model.language_model, group_size=64, bits=quantize_bits)
        self.processor = AutoProcessor.from_pretrained(path)
        self.device = torch.device(device)
        self.dtype = torch.bfloat16
        import json

        head_config = json.loads((path / "joint_head_config.json").read_text())
        self.head = jsm.JointSchemaHead(**head_config)
        self.head.load_state_dict(load_file(path / "joint_head.safetensors"), strict=True)
        self.head = self.head.to(self.device, self.dtype).eval()
        lm_head = getattr(self.model.language_model, "lm_head", None)
        weight = lm_head.weight if lm_head is not None else self.model.language_model.model.embed_tokens.weight
        if quantize_bits and lm_head is not None and hasattr(lm_head, "scales"):
            weight = mx.dequantize(lm_head.weight, lm_head.scales, lm_head.biases, group_size=64, bits=quantize_bits)
        self.lexical = _LexicalTable(weight, self.device, self.dtype)

    def _hidden(self, encoded) -> mx.array:
        ids = mx.array([list(encoded.input_ids)], dtype=mx.int32)
        media = encoded.media or {}
        kwargs: dict[str, Any] = {}
        pixel_values = None
        if "pixel_values" in media:
            pixel_values = _mx(media["pixel_values"])
            kwargs["image_grid_thw"] = _mx(media["image_grid_thw"])
        elif "pixel_values_videos" in media:
            pixel_values = _mx(media["pixel_values_videos"])
            kwargs["video_grid_thw"] = _mx(media["video_grid_thw"])
        features = self.model.get_input_embeddings(ids, pixel_values, **kwargs)
        hidden = self.model.language_model.model(
            ids, inputs_embeds=features.inputs_embeds, position_ids=features.position_ids
        )
        mx.eval(hidden)
        return hidden

    @torch.inference_mode()
    def logits(self, record: dict[str, Any], max_length: int = 16384) -> tuple[Any, list[torch.Tensor]]:
        encoded = self.jsm.encode_record(self.processor.tokenizer, record, max_length=max_length, processor=self.processor)
        hidden = self._hidden(encoded)
        hidden_t = torch.from_numpy(np.array(hidden.astype(mx.float32))).to(self.device, self.dtype)
        input_ids = torch.tensor([list(encoded.input_ids)], device=self.device)
        mask = torch.ones_like(input_ids)
        return encoded, self.head(hidden_t, input_ids, mask, [encoded], self.lexical)[0]

    def systemone(self, request: dict[str, Any]) -> dict[str, Any]:
        """Same contract as joint_schema_model.systemone."""
        questions = request["questions"]
        encoded, logits = self.logits(request)
        answers = {
            q.question_id: self.jsm.systemone_answer(
                questions[q.question_id], dict(zip(q.option_ids, ql.float().softmax(-1).tolist()))
            )
            for q, ql in zip(encoded.questions, logits)
        }
        return {"model": request.get("model", "clef-flash"), "answers": answers, "usage": {"input_tokens": len(encoded.input_ids), "output_tokens": 0}}
