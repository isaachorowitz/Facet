"""Reproducible local benchmark: python -m facet.benchmark_narrator IMAGE --model REPO."""

import argparse
import json
import time


def main():
    from huggingface_hub import snapshot_download
    from PIL import Image

    from .narrator import NarratorModel

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--model", required=True)
    parser.add_argument("--worker-smoke", action="store_true", help="Exercise the production process with caption and text recap")
    args = parser.parse_args()
    if args.worker_smoke:
        import numpy as np
        from . import config
        from .narrator import NarratorWorker

        config.NARRATOR_REPO = args.model
        worker = NarratorWorker()
        try:
            worker.wait_ready()
            image = Image.open(args.image).convert("RGB")
            image.thumbnail((640, 360))
            print(json.dumps({"caption": worker(("caption", np.asarray(image)))}), flush=True)
            evidence = {"summary": {"date": "2026-09-30", "minutes_present": 90,
                        "avg_focus": 3, "avg_stress": 1.5, "avg_posture": 78,
                        "minutes_talking": 3, "sips": 2, "face_touches": 1,
                        "eyes_breaks_taken": 1, "eyes_breaks_due": 1,
                        "focus_sessions": [{"started": 1790760000, "minutes": 25}]},
                        "marks": [{"kind": "win", "note": None}],
                        "notable_captions": [{"text": "You write beside your laptop, holding a pen."}],
                        "nudges": [{"kind": "eyes", "text": "Look away for 20 seconds."}]}
            text = worker(("recap", evidence))
            print(json.dumps({"recap": text, "words": len(text.split()), "pid": worker.process.pid}), flush=True)
        finally:
            worker.close()
        print(json.dumps({"worker_stopped": not worker.process.is_alive(), "exitcode": worker.process.exitcode}), flush=True)
        return
    started = time.perf_counter()
    path = snapshot_download(args.model)
    download = time.perf_counter() - started
    started = time.perf_counter()
    model = NarratorModel(path)
    load_seconds = time.perf_counter() - started
    image = Image.open(args.image).convert("RGB")
    image.thumbnail((640, 360))
    samples = []
    for _ in range(3):
        started = time.perf_counter()
        caption = model.caption(image)
        samples.append({"seconds": time.perf_counter() - started, "caption": caption})
        print(json.dumps({"progress": samples[-1]}), flush=True)
    print(json.dumps({"model": args.model, "download_seconds": download, "load_seconds": load_seconds,
                      "image_size": image.size, "captions": samples,
                      "mean_seconds": sum(x["seconds"] for x in samples) / len(samples),
                      "warm_mean_seconds": sum(x["seconds"] for x in samples[1:]) / (len(samples) - 1)}), flush=True)


if __name__ == "__main__":
    main()
