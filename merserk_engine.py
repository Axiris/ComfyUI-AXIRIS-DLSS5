# -*- coding: utf-8 -*-
"""Where the Merserk v9 engine lives, and how we call it.

The DLSS 5 Neural Rendering engine is **Merserk's dlss5-visual-enhancer v9** (MIT) — it is NOT shipped
in this repository. Install it from its source, then tell this pack where it is (first match wins):

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
    candidats += [os.path.join(ICI, "merserk"), os.path.join(ICI, "merserk", "v9.0")]
    for c in candidats:
        if c and os.path.isfile(os.path.join(c, "app.py")) and os.path.isdir(os.path.join(c, "src")):
            return c
    raise RuntimeError(
        "[AXIRIS DLSS5] Merserk v9 engine not found. Download Merserk's dlss5-visual-enhancer v9 release, unzip it "
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


def run_pilot(pilot, request_path, timeout):
    """Runs one of our pilots (bin/*.py) with Merserk's Python. Returns the parsed AXIRIS_RESULT json."""
    racine = merserk_dir()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONNOUSERSITE="1")
    r = subprocess.run([merserk_python(racine), os.path.join(ICI, "bin", pilot), request_path, racine],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lignes = (r.stdout or "").strip().splitlines()
    fin = next((l for l in reversed(lignes) if l.startswith("AXIRIS_")), "")
    if not fin.startswith("AXIRIS_RESULT "):
        detail = fin[len("AXIRIS_ERROR "):] if fin.startswith("AXIRIS_ERROR ") else (r.stderr or r.stdout or "")[-800:]
        raise RuntimeError(f"[AXIRIS DLSS5] the engine failed (exit {r.returncode}): {detail}")
    return json.loads(fin[len("AXIRIS_RESULT "):])
