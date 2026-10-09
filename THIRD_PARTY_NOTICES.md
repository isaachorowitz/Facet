# Third-party notices

Facet's own code is MIT licensed (see `LICENSE`). Facet does not ship any model
weights. The models below are downloaded on first run from their publishers and
stay under their own licenses, which you accept by running Facet.

| Model | Used for | Source | License |
|---|---|---|---|
| Clef-flash (Cloudflare), post-trained from Qwen3.5-9B | Face, voice and overall judgments | [Cloudflare/clef-flash](https://huggingface.co/Cloudflare/clef-flash) | Apache 2.0 |
| Qwen3.5-9B, MLX 4-bit conversion | Vision narrator and story of the day | [mlx-community/Qwen3.5-9B-MLX-4bit](https://huggingface.co/mlx-community/Qwen3.5-9B-MLX-4bit), from [Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | Apache 2.0 |
| Parakeet TDT 0.6B v3 (NVIDIA), MLX conversion | Speech to text | [mlx-community/parakeet-tdt-0.6b-v3](https://huggingface.co/mlx-community/parakeet-tdt-0.6b-v3), from [nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | CC BY 4.0 |
| HuBERT Large, SUPERB emotion recognition | Voice emotion scores | [superb/hubert-large-superb-er](https://huggingface.co/superb/hubert-large-superb-er) | Apache 2.0 |
| MediaPipe Face Landmarker, Pose Landmarker (lite), Gesture Recognizer | Face, posture and hand tracking | [Google MediaPipe models](https://ai.google.dev/edge/mediapipe/solutions/guide) | Apache 2.0 |

Parakeet is used under CC BY 4.0: speech recognition by NVIDIA's Parakeet TDT
0.6B v3, converted to MLX by the mlx-community.

`facet/clef_mlx.py` loads `joint_schema_model.py` from the Clef-flash download
(Apache 2.0, Cloudflare) at run time and does not copy it.

Python, JavaScript and Swift dependencies are listed in `uv.lock`,
`web/pnpm-lock.yaml` and `macos/Package.swift`, each under its own license. The
dashboard loads the Geist, Geist Mono and Instrument Serif typefaces from Google
Fonts (SIL Open Font License 1.1).
