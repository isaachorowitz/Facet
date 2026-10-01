"""Time Clef-flash on Apple Silicon (MPS) for text-only and image records."""
import sys, time
import numpy as np
import torch
from huggingface_hub import snapshot_download
from PIL import Image

path = snapshot_download("Cloudflare/clef-flash")
sys.path.insert(0, path)
from joint_schema_model import systemone, load_release_model  # noqa: E402

t = time.time()
model, processor = load_release_model(path, device="mps")
print(f"load {time.time()-t:.1f}s", flush=True)

Q = {
    "expression": {"type": "choice", "instructions": "Facial expression of the person",
                   "criteria": {"happy": "smiling", "neutral": "relaxed", "sad": "sad", "angry": "angry"}},
    "stressed": {"type": "noul", "instructions": "Does the person look stressed?"},
}
img = Image.fromarray((np.random.rand(480, 640, 3) * 255).astype("uint8"))
reqs = {
    "text": {"model": "clef-flash", "state": "I am so tired of this, nothing works.", "questions": Q},
    "image": {"model": "clef-flash", "state": "Webcam frame.", "images": [img], "questions": Q,
              "media_kwargs": {"images_kwargs": {"max_pixels": 448 * 448}}},
}
for name, r in reqs.items():
    for i in range(3):
        t = time.time()
        out = systemone(model, processor, r)
        torch.mps.synchronize()
        print(name, i, f"{(time.time()-t)*1000:.0f}ms", out["usage"], out["answers"]["expression"]["choice"], flush=True)
