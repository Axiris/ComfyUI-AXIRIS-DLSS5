# -*- coding: utf-8 -*-
"""AXIRIS DLSS 5 — Neural Rendering in ComfyUI through Merserk's v9 engine (image and video).

Three things worth knowing before reading the code:
  · the look comes from the SETTINGS, not from a depth map — the engine ignores depth entirely;
  · several passes add effect but darken and turn orange unless tone preservation / color strength compensate;
  · on video, the temporal pipeline brings stability (no added shimmer), not extra detail.
Hence: a light default preset, an explorer that renders every variant at once with its settings written under
each tile, and a video finishing node for a whole shot.
"""
import json
import os
import time
import uuid

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

import folder_paths

from .merserk_engine import ffmpeg_exe, merserk_dir, run_pilot

SCALES = {"source (100 %)": 1.0, "75 %": 0.75, "50 %": 0.5, "25 %": 0.25}
STYLES = ["Default", "Natural", "Cinematic"]

# Our setting names -> Merserk's option fields (ImageConversionOptions / ConversionOptions)
TO_ENGINE = {"passes": ("nr_passes", int), "style": ("nr_style", str), "intensity": ("nr_intensity", float),
             "local_tone": ("local_tone_strength", float), "local_structure": ("local_structure_strength", float),
             "skin_structure": ("skin_structure_strength", float), "auto_mask": ("automatic_mask", bool),
             "color_strength": ("nr_color_strength", float), "tone_preservation": ("tone_preservation", float),
             "face_protection": ("face_skin_protection", float), "grain": ("grain_preservation", float)}

# The engine's own defaults (what an unspecified setting falls back to in a preset or a variant line).
DEFAULTS = {"passes": 2, "style": "Default", "intensity": 1.0, "local_tone": 1.0, "local_structure": 1.0,
            "skin_structure": -1.0, "auto_mask": False, "color_strength": 1.0, "tone_preservation": 0.0,
            "face_protection": 0.0, "grain": 0.0, "scale": "source (100 %)"}

# The look we validated by eye on portraits, "plastic AI" images and cinematic video shots: ONE pass, moderate
# intensity and local tone. It keeps brightness and eye color where the engine's defaults darken by ~20-30 %.
#
# [2026-09-17] SKIN IS NOW DRIVEN, NOT LEFT TO THE ENGINE.
# skin_structure = -1 does NOT mean "minimum": it means "left to the model" (see the field's own
# description below). So this look never drove skin at all, and face_protection stayed at 0 — no
# restraint on faces. That is where the artefacts came from.
# Judged side by side on the same source, one knob at a time: skin left to the engine is the worst
# case; driven at a moderate value it stops damaging without flattening the render.
#
# [2026-09-17, same day] AND THE BRIGHTNESS IS NOW HELD TOO. "we still have a loss of brightness"
# — tone_preservation ("keeps the source brightness", field description below) was ALSO left at 0,
# while every measured preset that keeps its tone raises it (Faithful 1.0, Worked skin 0.9,
# Cinematic 0.7). Same oversight as skin, one hour apart: the look was never bad, it was
# INCOMPLETE — two knobs at zero that exist for the exact defects being reported.
AXIRIS_LOOK = {"passes": 1, "style": "Default", "intensity": 0.85, "local_tone": 0.595, "local_structure": 1.0,
               "skin_structure": 0.6, "auto_mask": True, "color_strength": 1.0, "tone_preservation": 0.6,
               "face_protection": 0.5, "grain": 0.0}

# Each preset is a DIRECTION we measured; the explorer shows them side by side.
PRESETS = {
    "AXIRIS look (validated)":              dict(AXIRIS_LOOK),
    "AXIRIS look, deeper volumes (tone 1.5)": dict(AXIRIS_LOOK, local_tone=1.5),
    "Soft single pass":                     {"passes": 1, "tone_preservation": 0.5, "color_strength": 0.5},
    "Faithful (2 passes, tone kept)":       {"passes": 2, "tone_preservation": 1.0, "color_strength": 0.0},
    "Strong material (4 passes, tone kept)": {"passes": 4, "tone_preservation": 1.0, "color_strength": 0.0},
    "Material + color (3 passes)":          {"passes": 3, "tone_preservation": 1.0, "color_strength": 0.5},
    "Game-like light (3 passes, tone 0.4)": {"passes": 3, "tone_preservation": 0.4},
    "Cinematic (2 passes)":                 {"passes": 2, "style": "Cinematic", "tone_preservation": 0.7, "color_strength": 0.7},
    "Pure detail (structure 1.8)":          {"passes": 2, "tone_preservation": 1.0, "color_strength": 0.0,
                                             "local_structure": 1.8, "local_tone": 0.5},
    "Worked skin (3 passes, skin 1.5)":     {"passes": 3, "tone_preservation": 0.9, "color_strength": 0.3,
                                             "skin_structure": 1.5, "auto_mask": True},
    "Raw (3 passes, no correction)":        {"passes": 3},
}

# Every tile of the board SAYS its values: the three that always matter, then those that differ from the defaults.
_ALWAYS = ("passes", "tone_preservation", "color_strength")


def _summary(s):
    parts = [f"{k}={s[k]}" for k in _ALWAYS]
    parts += [f"{k}={v}" for k, v in s.items() if k not in _ALWAYS and k != "scale" and v != DEFAULTS[k]]
    return " ".join(parts)


def _default_list():
    return "\n".join(f"{name.split(' (')[0]}: {_summary(dict(DEFAULTS, **p))}" for name, p in PRESETS.items())


def _to_png(t, path):
    a = (t.detach().cpu().float().clamp(0, 1).numpy() * 255.0 + 0.5).astype(np.uint8)
    Image.fromarray(a[..., :3]).save(path, compress_level=1)


def _from_png(path):
    return torch.from_numpy(np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0)


def _engine_options(s):
    o = {key: conv(s[name]) for name, (key, conv) in TO_ENGINE.items() if name in s}
    o["upscaling_factor"] = SCALES.get(s.get("scale", "source (100 %)"), 1.0)
    o["output_format"], o["preserve_metadata"] = "PNG", False
    return o


def _read_line(line):
    """A preset name, or « my test: passes=3 tone_preservation=0.8 style=Natural ». None = ignored (empty or #)."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line in PRESETS:
        return line, dict(DEFAULTS, **PRESETS[line])
    name, _, rest = line.partition(":")
    if not rest.strip():
        raise ValueError(f"[AXIRIS DLSS5] line not understood: « {line} » — an exact preset name, or « name: passes=3 tone_preservation=0.8 »")
    s = dict(DEFAULTS)
    for word in rest.split():
        k, _, v = word.partition("=")
        if k not in DEFAULTS:
            raise ValueError(f"[AXIRIS DLSS5] unknown setting « {k} » in « {line} » (known: {', '.join(DEFAULTS)})")
        d = DEFAULTS[k]
        s[k] = (v.lower() in ("1", "true", "yes", "on")) if isinstance(d, bool) else type(d)(v)
    return name.strip(), s


def _work_dir(kind):
    d = os.path.join(folder_paths.get_temp_directory(), "axiris_dlss5", kind, uuid.uuid4().hex[:12])
    os.makedirs(d, exist_ok=True)
    return d


def _mask_png(mask, folder):
    m = mask[0] if mask.dim() == 3 else mask
    p = os.path.join(folder, "mask.png")
    Image.fromarray((m.detach().cpu().float().clamp(0, 1).numpy() * 255 + 0.5).astype(np.uint8), "L").save(p)
    return p


def _render(images, variants, mask=None, feather=8):
    """Renders len(variants) option sets of the batch `images` in ONE engine process.
    -> (list of [N,H,W,3] tensors in the order of the variants, pilot result)."""
    work = _work_dir("images")
    inputs = []
    for i in range(images.shape[0]):
        p = os.path.join(work, f"in_{i:05d}.png")
        _to_png(images[i], p)
        inputs.append(p)
    if mask is not None:
        pm = _mask_png(mask, work)
        variants = [dict(v, nr_mask=pm, mask_feather=int(feather)) for v in variants]
    req = os.path.join(work, "request.json")
    json.dump({"inputs": inputs, "output_dir": os.path.join(work, "out"), "variants": variants}, open(req, "w", encoding="utf-8"))
    res = run_pilot("render_images.py", req, timeout=600 + 30 * len(inputs) * len(variants))
    return [torch.stack([_from_png(p) for p in v]) for v in res["variants"]], res


def _float(d, lo, hi, tip, step=0.05):
    return ("FLOAT", {"default": d, "min": lo, "max": hi, "step": step, "tooltip": tip})


class AXDLSS5Render:
    CATEGORY = "AXIRIS DLSS5"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "report")
    FUNCTION = "render"
    DESCRIPTION = ("DLSS 5 Neural Rendering on an image or a batch (Merserk v9 engine). The sliders start on the AXIRIS look — "
                   "a deliberately light starting point, not a universal setting: expect to tune per image. "
                   "'preset' (last) replaces every slider with a preset.")

    @classmethod
    def INPUT_TYPES(cls):
        L = AXIRIS_LOOK
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "an image or a batch"}),
                "passes": ("INT", {"default": L["passes"], "min": 1, "max": 4,
                                   "tooltip": "Neural Rendering passes on the same image. More = stronger effect, and darker "
                                              "(compensate with tone_preservation)"}),
                "style": (STYLES, {"default": L["style"], "tooltip": "Default = contrasted · Natural = closest to the source "
                                                                    "(can shift green eyes to blue-grey) · Cinematic = strongest"}),
                "intensity": _float(L["intensity"], 0.0, 2.0, "strength of each pass"),
                "local_tone": _float(L["local_tone"], 0.0, 2.0, "broad local lighting — the light that carves the volumes (1.5-2.0 = deeper)"),
                "local_structure": _float(L["local_structure"], 0.0, 2.0, "high frequencies: material, micro-shadows"),
                "skin_structure": _float(L["skin_structure"], -1.0, 2.0, "pores / skin; -1 = left to the model"),
                "auto_mask": ("BOOLEAN", {"default": L["auto_mask"], "tooltip": "the model's automatic mask"}),
                "color_strength": _float(L["color_strength"], 0.0, 1.0, "share of the rendered color (0 = keep the source colors)"),
                "tone_preservation": _float(L["tone_preservation"], 0.0, 1.0, "keeps the source brightness — the counterweight of passes"),
                "face_protection": _float(L["face_protection"], 0.0, 1.0, "holds the rendering back on faces and skin"),
                "grain": _float(L["grain"], 0.0, 1.0, "keeps the source grain"),
                "scale": (list(SCALES), {"default": "source (100 %)", "tooltip": "render resolution (the v9 engine does not upscale)"}),
            },
            "optional": {
                "mask": ("MASK", {"tooltip": "where Neural Rendering applies (white = yes, black = protected)"}),
                "mask_feather": ("INT", {"default": 8, "min": 0, "max": 128, "tooltip": "mask edge blur, in pixels"}),
                "preset": (["custom (sliders)"] + list(PRESETS), {"default": "custom (sliders)",
                           "tooltip": "a measured preset REPLACES every slider; « custom » = the sliders. The Explorer shows them side by side."}),
            },
        }

    def render(self, images, passes, style, intensity, local_tone, local_structure, skin_structure, auto_mask,
               color_strength, tone_preservation, face_protection, grain, scale, mask=None, mask_feather=8,
               preset="custom (sliders)"):
        t0 = time.time()
        if preset in PRESETS:
            s, name = dict(DEFAULTS, **PRESETS[preset]), preset
        else:
            s = dict(passes=passes, style=style, intensity=intensity, local_tone=local_tone, local_structure=local_structure,
                     skin_structure=skin_structure, auto_mask=auto_mask, color_strength=color_strength,
                     tone_preservation=tone_preservation, face_protection=face_protection, grain=grain, scale=scale)
            name = "custom"
        (out,), res = _render(images, [_engine_options(s)], mask, mask_feather)
        report = (f"[AXIRIS DLSS5] {images.shape[0]} image(s) · {name} · " + " · ".join(f"{k} {v}" for k, v in s.items())
                  + f" · mask {'yes' if mask is not None else 'no'} · {res['output_px'][0]}×{res['output_px'][1]}"
                  + f" · engine {res['seconds']} s (total {time.time() - t0:.1f} s)")
        print(report)
        return (out, report)


def _board(tiles, zone_x, zone_y, zone_size, columns):
    """tiles = [(title, subtitle, tensor [H,W,3])], the first one is the source. Every tile shows the SAME zone at 100 %.
    -> ([1,H,W,3] board, (side, x0, y0)). The grid (8 px gaps, a title band of max(40, side/10) above each tile) is
    what web/axiris-dlss5-before-after.js uses to turn a click on the board into a variant."""
    src = tiles[0][2]
    H, W = int(src.shape[0]), int(src.shape[1])
    c = min(int(zone_size), W, H)
    x0 = max(0, min(W - c, int(W * zone_x / 100) - c // 2))
    y0 = max(0, min(H - c, int(H * zone_y / 100) - c // 2))
    try:
        font = ImageFont.truetype("arial.ttf", max(14, c // 26))
    except Exception:
        font = ImageFont.load_default()
    band = max(40, c // 10)
    cols = max(1, int(columns))
    rows = -(-len(tiles) // cols)
    board = Image.new("RGB", (cols * c + (cols - 1) * 8, rows * (c + band) + (rows - 1) * 8), (20, 20, 20))
    d = ImageDraw.Draw(board)
    for i, (title, subtitle, t) in enumerate(tiles):
        a = (t.detach().cpu().float().clamp(0, 1).numpy() * 255 + 0.5).astype(np.uint8)
        fx, fy = a.shape[1] / W, a.shape[0] / H
        piece = Image.fromarray(a[int(y0 * fy):int((y0 + c) * fy), int(x0 * fx):int((x0 + c) * fx), :3])
        if piece.size != (c, c):
            piece = piece.resize((c, c), Image.LANCZOS)
        x, y = (i % cols) * (c + 8), (i // cols) * (c + band + 8)
        board.paste(piece, (x, y + band))
        d.text((x + 6, y + 2), f"{i}. {title}" if i else title, fill=(255, 255, 255), font=font)
        if subtitle:
            # the settings line shrinks to fit its tile, then is cut — it never runs over the neighbour
            p, text = font, subtitle
            for size in range(max(11, c // 40), 7, -1):
                try:
                    p = ImageFont.truetype("arial.ttf", size)
                except Exception:
                    p = ImageFont.load_default()
                    break
                if d.textlength(text, font=p) <= c - 12:
                    break
            while len(text) > 4 and d.textlength(text, font=p) > c - 12:
                text = text[:-2].rstrip() + "…"
            d.text((x + 6, y + band // 2 + 2), text, fill=(170, 200, 255), font=p)
    return torch.from_numpy(np.asarray(board, dtype=np.float32) / 255.0)[None], (c, x0, y0)


class AXDLSS5Explorer:
    """Every variant at once, side by side: choose by eye, without touching a slider."""
    CATEGORY = "AXIRIS DLSS5"
    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("board", "variants", "report")
    FUNCTION = "explore"
    DESCRIPTION = ("One image → every variant of the list (one per line: a preset name, or « name: passes=3 tone_preservation=0.8 … ») "
                   "in ONE engine session. « board » = the source then each variant, at 100 % on the chosen zone, with its number "
                   "and its settings; « variants » = the full images. Click a tile of the board: the Before/After node shows it.")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "the image to try (the first of a batch)"}),
                "variants": ("STRING", {"multiline": True, "default": _default_list(),
                             "tooltip": "one variant per line: a preset name, or « my test: passes=3 tone_preservation=0.8 "
                                        "color_strength=0.2 style=Natural ». A line starting with # is ignored."}),
                "zone_x": ("INT", {"default": 50, "min": 0, "max": 100, "tooltip": "center of the zone shown at 100 %, % of the width"}),
                "zone_y": ("INT", {"default": 40, "min": 0, "max": 100, "tooltip": "center of the zone shown at 100 %, % of the height (40 ≈ a portrait's face)"}),
                "zone_size": ("INT", {"default": 512, "min": 128, "max": 2048, "step": 32, "tooltip": "side of the zone shown at 100 % — never reduced"}),
                "columns": ("INT", {"default": 4, "min": 1, "max": 8}),
            },
            "optional": {
                "mask": ("MASK", {"tooltip": "white = DLSS 5 applied, black = protected (for every variant)"}),
                "mask_feather": ("INT", {"default": 8, "min": 0, "max": 128}),
            },
        }

    def explore(self, image, variants, zone_x, zone_y, zone_size, columns, mask=None, mask_feather=8):
        t0 = time.time()
        read = [x for x in (_read_line(l) for l in variants.splitlines()) if x]
        if not read:
            raise ValueError("[AXIRIS DLSS5] no variant to render (empty list)")
        src = image[:1]
        outs, res = _render(src, [_engine_options(s) for _, s in read], mask, mask_feather)
        tiles = [("source", "", src[0])] + [(name, _summary(s), v[0]) for (name, s), v in zip(read, outs)]
        board, (c, x0, y0) = _board(tiles, zone_x, zone_y, zone_size, columns)
        report = (f"[AXIRIS DLSS5 Explorer] {len(read)} variant(s) in {time.time() - t0:.1f} s (engine {res['seconds']} s) · "
                  f"zone {c}px at ({x0},{y0}):\n" + "\n".join(f"  {i + 1}. {name} — {_summary(s)}" for i, (name, s) in enumerate(read)))
        print(report)
        return (board, torch.cat([v[:1] for v in outs]), report)


class AXDLSS5PickVariant:
    """The number written on the board → that variant alone. Changing the number does NOT rerun the Explorer
    (ComfyUI keeps its renders in cache): only this node and what follows are redone."""
    CATEGORY = "AXIRIS DLSS5"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("variant", "which")
    FUNCTION = "pick"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "variants": ("IMAGE", {"tooltip": "the Explorer's « variants » output"}),
            "number": ("INT", {"default": 1, "min": 1, "max": 64, "tooltip": "the number written on the board (1 = the first variant)"}),
        }, "optional": {
            "report": ("STRING", {"forceInput": True, "tooltip": "the Explorer's report, to name the variant"}),
        }}

    def pick(self, variants, number, report=None):
        n = variants.shape[0]
        if not 1 <= number <= n:
            raise ValueError(f"[AXIRIS DLSS5] variant #{number}: there are only {n} (numbers 1 to {n})")
        name = f"variant {number}"
        if report:
            name = next((l.strip() for l in report.splitlines() if l.strip().startswith(f"{number}. ")), name)
        return (variants[number - 1:number], name)


class AXDLSS5VideoFinish:
    """DLSS 5 finishing of a SHOT: Merserk v9's video pipeline — temporal history, scene cuts, shimmer suppression,
    motion computed by the engine. Frames in (VAE Decode, Load Video…), the same frames out, finished."""
    CATEGORY = "AXIRIS DLSS5"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "report")
    FUNCTION = "finish"
    DESCRIPTION = ("DLSS 5 finishing of a shot (Merserk v9 video pipeline). Defaults = the AXIRIS look. The temporal pipeline "
                   "brings stability — no added shimmer, brightness kept — rather than extra detail. The whole shot goes "
                   "through RAM as a ComfyUI image batch: fine for shots, not for minutes-long films.")

    @classmethod
    def INPUT_TYPES(cls):
        L = AXIRIS_LOOK
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "the frames of the shot, in order"}),
                "fps": _float(24.0, 1.0, 120.0, "frame rate of the shot (motion is computed between two frames)", 0.5),
                "intensity": _float(L["intensity"], 0.0, 2.0, "Neural Rendering strength"),
                "local_tone": _float(L["local_tone"], 0.0, 2.0, "the light that carves the volumes (1.5-2.0 = deeper)"),
                "local_structure": _float(L["local_structure"], 0.0, 2.0, "material, micro-shadows"),
                "skin_structure": _float(L["skin_structure"], -1.0, 2.0, "pores / skin; -1 = left to the model"),
                "auto_mask": ("BOOLEAN", {"default": L["auto_mask"], "tooltip": "the model's automatic mask"}),
                "color_strength": _float(L["color_strength"], 0.0, 1.0, "share of the rendered color (0 = keep the shot's colors)"),
                "tone_preservation": _float(L["tone_preservation"], 0.0, 1.0, "keeps the shot's brightness"),
                "shimmer_suppression": _float(0.70, 0.0, 1.0, "calms the effect from one frame to the next (0.70 = Merserk default; 0 = raw)"),
                "passes": ("INT", {"default": L["passes"], "min": 1, "max": 4, "tooltip": "passes per frame"}),
                "style": (STYLES, {"default": L["style"]}),
            },
            "optional": {
                "mask": ("MASK", {"tooltip": "where the finishing applies (white = yes, black = protected) — the same for the whole shot"}),
                "mask_feather": ("INT", {"default": 8, "min": 0, "max": 128}),
                # last, on purpose: a widget added in the middle would shift the values saved in existing workflows
                "face_protection": _float(L["face_protection"], 0.0, 1.0, "holds the rendering back on faces and skin"),
                "grain": _float(L["grain"], 0.0, 1.0, "keeps the shot's grain"),
            },
        }

    def finish(self, images, fps, intensity, local_tone, local_structure, skin_structure, auto_mask, color_strength,
               tone_preservation, shimmer_suppression, passes, style, mask=None, mask_feather=8, face_protection=0.0, grain=0.0):
        import shutil
        import subprocess
        t0 = time.time()
        ff = ffmpeg_exe(merserk_dir())
        n, H, W = int(images.shape[0]), int(images.shape[1]), int(images.shape[2])
        work = _work_dir("video")
        try:
            # round trip: lossless FFV1 in, H.265 NVENC « Max » out
            src = os.path.join(work, "shot.mkv")
            raw = (images[..., :3].detach().cpu().float().clamp(0, 1).numpy() * 255.0 + 0.5).astype(np.uint8)
            w = subprocess.run([ff, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", f"{fps:g}",
                                "-i", "-", "-c:v", "ffv1", "-pix_fmt", "bgr0", src], input=raw.tobytes(), capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if w.returncode:
                raise RuntimeError(f"[AXIRIS DLSS5 video] writing the shot: {w.stderr.decode(errors='replace')[-400:]}")
            opts = {"nr_style": style, "nr_intensity": float(intensity), "nr_passes": int(passes),
                    "local_tone_strength": float(local_tone), "local_structure_strength": float(local_structure),
                    "skin_structure_strength": float(skin_structure), "nr_color_strength": float(color_strength),
                    "tone_preservation": float(tone_preservation), "automatic_mask": bool(auto_mask),
                    "shimmer_suppression": float(shimmer_suppression), "face_skin_protection": float(face_protection),
                    "grain_preservation": float(grain), "codec": "H.265 (NVIDIA NVENC)", "quality": "Max",
                    "rename_mode": "Custom", "custom_suffix": "_finished"}
            if mask is not None:
                opts.update(nr_mask=_mask_png(mask, work), mask_feather=int(mask_feather))
            req = os.path.join(work, "request.json")
            json.dump({"input": src, "output_dir": os.path.join(work, "out"), "options": opts}, open(req, "w", encoding="utf-8"))
            res = run_pilot("render_video.py", req, timeout=600 + 2 * n)
            ow, oh = res["output_px"]
            rd = subprocess.run([ff, "-v", "error", "-i", res["output"], "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if rd.returncode:
                raise RuntimeError(f"[AXIRIS DLSS5 video] reading the render: {rd.stderr.decode(errors='replace')[-400:]}")
            out = torch.from_numpy(np.frombuffer(rd.stdout, np.uint8).reshape(-1, oh, ow, 3).astype(np.float32) / 255.0)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        gap = "" if out.shape[0] == n else f" · ⚠ {out.shape[0]} frames rendered for {n} in"   # said, never silently cut
        report = (f"[AXIRIS DLSS5 video] {n} frames {W}×{H} → {ow}×{oh} · intensity {intensity} · local_tone {local_tone} · "
                  f"passes {passes} · {style} · shimmer {shimmer_suppression} · face {face_protection} · grain {grain} · "
                  f"mask {'yes' if mask is not None else 'no'} · "
                  f"Neural Rendering on {res['nr_frames']} frames · engine {res['seconds']} s (total {time.time() - t0:.1f} s){gap}")
        print(report)
        return (out, report)


NODE_CLASS_MAPPINGS = {
    "AXDLSS5Render": AXDLSS5Render,
    "AXDLSS5Explorer": AXDLSS5Explorer,
    "AXDLSS5PickVariant": AXDLSS5PickVariant,
    "AXDLSS5VideoFinish": AXDLSS5VideoFinish,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AXDLSS5Render": "AXIRIS DLSS 5 · Render (Merserk v9)",
    "AXDLSS5Explorer": "AXIRIS DLSS 5 · Explorer (every variant at once)",
    "AXDLSS5PickVariant": "AXIRIS DLSS 5 · Pick a variant",
    "AXDLSS5VideoFinish": "AXIRIS DLSS 5 · Video finishing (a shot)",
}
