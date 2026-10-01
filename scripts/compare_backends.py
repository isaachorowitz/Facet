"""Check the MLX backbone against the released PyTorch path: same answers, how much faster.

uv run python scripts/compare_backends.py [image.jpg]
"""
import sys
import time

import torch
from huggingface_hub import snapshot_download
from PIL import Image

from facet.clef_mlx import ClefMLX
from facet.judge import FACE_QUESTIONS, OVERALL_QUESTIONS, VOICE_QUESTIONS

path = snapshot_download("Cloudflare/clef-flash")
img = Image.open(sys.argv[1]).convert("RGB").resize((384, 384)) if len(sys.argv) > 1 else Image.new("RGB", (384, 384), (128, 120, 110))
records = {
    "face": {"model": "clef-flash", "state": {"context": "Webcam image of a person at their desk during the workday."}, "images": [img], "questions": FACE_QUESTIONS},
    "voice": {"model": "clef-flash", "state": {"transcript": "I can't believe the deploy failed again, this is the third time today.", "prosody": {"words_per_minute": 207, "pitch_hz": 172}}, "questions": VOICE_QUESTIONS},
    "overall": {"model": "clef-flash", "state": {"camera": {"avg_stress": 1.2, "expressions_seen": {"serious": 20, "focused": 8}}, "posture": {"score": 66, "issues": ["Head dropping forward"]}}, "questions": OVERALL_QUESTIONS},
}


def timed(fn, n=4):
    fn()  # warm the shape
    times = []
    for _ in range(n):
        t = time.time()
        out = fn()
        if torch.backends.mps.is_available():
            torch.mps.synchronize()
        times.append((time.time() - t) * 1000)
    return out, sorted(times)[len(times) // 2]


def probs(answers):
    flat = {}
    for q, a in answers.items():
        if a["type"] == "noul":
            flat[q] = {"true": a["noul"]}
        else:
            flat[q] = a["probabilities"]
    return flat


def compare(a, b):
    worst, flips = 0.0, []
    for q in a:
        for k in a[q]:
            worst = max(worst, abs(a[q][k] - b[q][k]))
        if len(a[q]) > 1 and max(a[q], key=a[q].get) != max(b[q], key=b[q].get):
            flips.append(q)
    return worst, flips


results = {}
mode = sys.argv[2] if len(sys.argv) > 2 else "all"
if mode in ("all", "torch"):
    sys.path.insert(0, path)
    from joint_schema_model import load_release_model, systemone

    model, processor = load_release_model(path, device="mps")
    for name, r in records.items():
        out, ms = timed(lambda: systemone(model, processor, r))
        results[("torch", name)] = (probs(out["answers"]), ms)
        print(f"torch  {name:8s} {ms:7.0f} ms  tokens={out['usage']['input_tokens']}", flush=True)
    del model
    torch.mps.empty_cache()

for bits in (None, 8):
    clef = ClefMLX(path, quantize_bits=bits)
    label = "mlx-bf16" if bits is None else f"mlx-q{bits}"
    for name, r in records.items():
        out, ms = timed(lambda: clef.systemone(r))
        results[(label, name)] = (probs(out["answers"]), ms)
        line = f"{label:8s} {name:8s} {ms:7.0f} ms"
        if ("torch", name) in results:
            worst, flips = compare(results[("torch", name)][0], results[(label, name)][0])
            line += f"  max prob diff vs torch={worst:.3f}  top-choice flips={flips or 'none'}"
        print(line, flush=True)
    del clef
