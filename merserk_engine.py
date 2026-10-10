# -*- coding: utf-8 -*-
"""Where Merserk's engine lives, and how we call it.

The DLSS 5 Neural Rendering engine is **Merserk's dlss5-visual-enhancer** (v15 recommended, v9 still works) —
it is NOT shipped in this repository. Install it from its source, then tell this pack where it is (first match wins):

  1. the environment variable  MERSERK_DLSS5_DIR
  2. "merserk_dir" in  config.json  (next to this file — copy config.example.json)
  3. the folder  merserk/  inside this pack

The folder is the one that contains Merserk's `app.py`, `src/` and `bin/`.
We call Merserk's own pipelines with Merserk's own embedded Python, in a separate process:
no line of their code is copied here.
"""
import glob
import json
import os
import shutil
import subprocess

ICI = os.path.dirname(os.path.abspath(__file__))


def merserk_dir():
    candidats = [os.environ.get("MERSERK_DLSS5_DIR", "")]
    try:
        with open(os.path.join(ICI, "config.json"), encoding="utf-8") as f:
            candidats.append(str(json.load(f).get("merserk_dir", "")))
    except (OSError, ValueError):
        pass
    candidats.append(os.path.join(ICI, "merserk"))
    for c in candidats:
        if c and os.path.isfile(os.path.join(c, "app.py")) and os.path.isdir(os.path.join(c, "src")):
            return c
        # a folder holding several releases side by side (v9.0, v15.0, ...): the newest one
        if c and os.path.isdir(c):
            import re
            rel = []
            for d in os.listdir(c):
                m = re.match(r"^v(\d+)(?:\.(\d+))?$", d)
                if m and os.path.isfile(os.path.join(c, d, "app.py")):
                    rel.append(((int(m.group(1)), int(m.group(2) or 0)), os.path.join(c, d)))
            if rel:
                return max(rel)[1]
    raise RuntimeError(
        "[AXIRIS DLSS5] Merserk's engine not found. Download Merserk's dlss5-visual-enhancer release (v15), unzip it "
        "into custom_nodes/ComfyUI-AXIRIS-DLSS5/merserk/ (the folder with app.py), or set MERSERK_DLSS5_DIR, or put "
        "\"merserk_dir\" in config.json. See README.")


def merserk_python(racine):
    trouves = sorted(glob.glob(os.path.join(racine, "bin", "python-*-embed-amd64", "python.exe")))
    if not trouves:
        raise RuntimeError(f"[AXIRIS DLSS5] Merserk's embedded Python not found in {racine}\\bin (python-*-embed-amd64)")
    return trouves[-1]


def ffmpeg_exe(racine=None):
    candidats = []
    if racine:
        candidats.append(os.path.join(racine, "bin", "ffmpeg", "bin", "ffmpeg.exe"))
    candidats.append(shutil.which("ffmpeg") or "")
    for c in candidats:
        if c and os.path.isfile(c):
            return c
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError("[AXIRIS DLSS5] ffmpeg not found (Merserk's bundled one, PATH, or imageio_ffmpeg)")


# Merserk v15 (08/10/2026) keeps the same NVIDIA library but drives it through its NATIVE controls: styles « Style 0/1/2 »,
# ranges 0-1, and no more composition layer (color strength, tone preservation, face protection, grain, shimmer
# suppression, mask feather). The pack speaks v9 words; this translates them for the engine actually installed.
NATIVE_STYLES = {"Default": "Style 0", "Natural": "Style 1", "Cinematic": "Style 2"}
GONE_IN_V15 = {"nr_color_strength": 1.0, "tone_preservation": 0.0, "face_skin_protection": 0.0, "grain_preservation": 0.0,
               "shimmer_suppression": 0.7, "mask_feather": 8, "nr_gpu_mode": True, "preview_compat": True}


def is_native(racine):
    return os.path.isfile(os.path.join(racine, "src", "core", "nr_control_mask.py"))


def adapt(options, racine):
    """Options in the pack's (v9) vocabulary -> the installed engine's. Returns (options, notes)."""
    if not is_native(racine):
        return options, []
    o, notes = dict(options), []
    if o.get("nr_style") in NATIVE_STYLES:
        o["nr_style"] = NATIVE_STYLES[o["nr_style"]]
    for k in ("local_tone_strength", "local_structure_strength", "skin_structure_strength"):
        if k in o:
            v = float(o[k])
            if k == "skin_structure_strength" and v < 0:
                o[k] = 1.0                                   # v9: -1 = left to the model; v15: 1 = the model's default
            elif v > 1.0:
                o[k] = 1.0; notes.append(f"{k} {v:g} clamped to 1 (v15 range 0-1)")
    for k, neutral in GONE_IN_V15.items():
        if k in o:
            v = o.pop(k)
            if v is not None and v != neutral:
                notes.append(f"{k}={v} no longer exists in v15")
    return o, sorted(set(notes))


def engine_name(racine):
    return os.path.basename(os.path.normpath(racine))


def run_pilot(pilot, request_path, timeout):
    """Runs one of our pilots (bin/*.py) with Merserk's Python. Returns the parsed AXIRIS_RESULT json."""
    racine = merserk_dir()
    with open(request_path, encoding="utf-8") as f:
        req = json.load(f)
    notes = []
    for key in ("variants", "variantes"):
        if isinstance(req.get(key), list):
            pairs = [adapt(v, racine) for v in req[key]]
            req[key] = [p[0] for p in pairs]; notes += [n for p in pairs for n in p[1]]
    if isinstance(req.get("options"), dict):
        req["options"], n = adapt(req["options"], racine); notes += n
        if is_native(racine):
            req["options"].setdefault("nr_optical_flow_quality", "High")
    with open(request_path, "w", encoding="utf-8") as f:
        json.dump(req, f)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONNOUSERSITE="1")
    r = subprocess.run([merserk_python(racine), os.path.join(ICI, "bin", pilot), request_path, racine],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lignes = (r.stdout or "").strip().splitlines()
    fin = next((l for l in reversed(lignes) if l.startswith("AXIRIS_")), "")
    if not fin.startswith("AXIRIS_RESULT "):
        detail = fin[len("AXIRIS_ERROR "):] if fin.startswith("AXIRIS_ERROR ") else (r.stderr or r.stdout or "")[-800:]
        raise RuntimeError(f"[AXIRIS DLSS5] the engine failed (exit {r.returncode}): {detail}")
    res = json.loads(fin[len("AXIRIS_RESULT "):])
    res["engine"], res["adapted"] = engine_name(racine), sorted(set(notes))
    if res["adapted"]:
        print("[AXIRIS DLSS5] " + res["engine"] + " · " + " ; ".join(res["adapted"]))
    return res
