# -*- coding: utf-8 -*-
"""Pilot for Merserk v9's IMAGE pipeline (src/neural_rendering/image/batch.convert_images), called as is.

Run by the ComfyUI nodes with Merserk's embedded Python:
  <merserk>/bin/python-*-embed-amd64/python.exe render_images.py <request.json> <merserk dir>
request.json = { "inputs": ["<png>", ...], "output_dir": "<dir>", "variants": [ { <ImageConversionOptions fields> }, ... ] }
Last line on stdout: AXIRIS_RESULT {json}  — or AXIRIS_ERROR {json}.
Several variants on the same inputs run in ONE process: the engine is not reloaded between them.
"""
import json
import os
import sys
import traceback


def main():
    req = json.load(open(sys.argv[1], encoding="utf-8"))
    root = sys.argv[2]
    os.chdir(root)
    sys.path.insert(0, root)
    from src.neural_rendering.image.models import ImageConversionOptions
    from src.neural_rendering.image.batch import convert_images

    known = set(ImageConversionOptions.__dataclass_fields__)
    inputs = req["inputs"]
    results, ignored = [], set()
    for i, variant in enumerate(req.get("variants") or [{}]):
        opts = {k: v for k, v in variant.items() if k in known}
        ignored |= set(variant) - known
        batch = convert_images(inputs, ImageConversionOptions(**opts), output_dir=os.path.join(req["output_dir"], f"v{i:02d}"),
                               generate_previews=False, create_zip=False)
        if batch.failures:
            raise RuntimeError(f"variant {i}: " + "; ".join(f"{f.input_path}: {f.error}" for f in batch.failures)[:500])
        # one output per input, in the ORDER of the inputs (the batch may return them in another order)
        by_input = {os.path.normcase(os.path.abspath(r.input_path)): r for r in batch.successes}
        results.append([by_input[os.path.normcase(os.path.abspath(p))] for p in inputs])
    r0 = results[0][0]
    print("AXIRIS_RESULT " + json.dumps({
        "variants": [[r.output_path for r in v] for v in results],
        "seconds": round(sum(r.elapsed_seconds for v in results for r in v), 2), "gpu": r0.gpu,
        "input_px": [r0.input_width, r0.input_height], "output_px": [r0.output_width, r0.output_height],
        "warnings": sorted({w for v in results for r in v for w in r.warnings}), "ignored": sorted(ignored),
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("AXIRIS_ERROR " + json.dumps({"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]},
                                           ensure_ascii=False))
        sys.exit(1)
