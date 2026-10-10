# -*- coding: utf-8 -*-
"""Pilot for Merserk's Visual Enhancer VIDEO pipeline (src/neural_rendering/video/processor.convert_video), called as is.

The video pipeline keeps a temporal history, detects scene cuts, has a shimmer suppression and computes the
motion itself. Run with Merserk's embedded Python:
  <merserk>/bin/python-*-embed-amd64/python.exe render_video.py <request.json> <merserk dir>
request.json = { "input": "<video>", "output_dir": "<dir>", "options": { <ConversionOptions fields> } }
Last line on stdout: AXIRIS_RESULT {json}  — or AXIRIS_ERROR {json}.
"""
import json
import os
import sys
import time
import traceback


def main():
    req = json.load(open(sys.argv[1], encoding="utf-8"))
    root = sys.argv[2]
    os.chdir(root)
    sys.path.insert(0, root)
    from src.neural_rendering.video.models import ConversionOptions
    from src.neural_rendering.video.processor import convert_video

    known = set(ConversionOptions.__dataclass_fields__)
    raw = req.get("options") or {}
    os.makedirs(req["output_dir"], exist_ok=True)
    t0 = time.time()
    r = convert_video(req["input"], ConversionOptions(**{k: v for k, v in raw.items() if k in known}), output_dir=req["output_dir"])
    print("AXIRIS_RESULT " + json.dumps({
        "output": r.output_path, "frames": r.frames, "nr_frames": r.nr_count_evidence, "seconds": round(time.time() - t0, 2),
        "gpu": r.gpu, "output_px": [r.output_width, r.output_height], "ignored": sorted(set(raw) - known),
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("AXIRIS_ERROR " + json.dumps({"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]},
                                           ensure_ascii=False))
        sys.exit(1)
