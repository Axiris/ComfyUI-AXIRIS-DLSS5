# -*- coding: utf-8 -*-
"""AXIRIS DLSS 5 — Neural Rendering in ComfyUI through Merserk's Visual Enhancer (v15, native controls; image and video).

Three things worth knowing before reading the code:
  · the look comes from the SETTINGS, not from a depth map — the engine ignores depth entirely;
  · the controls are DLSS's own (v15): style, intensity, local tone, local structure, skin structure, and a control
    mask whose red / green / blue channels drive intensity / local tone / structure separately;
  · on video, the temporal pipeline brings stability (no added shimmer), not extra detail.
Hence: a light default preset, an explorer that renders every variant at once with its settings written under
each tile, and a video finishing node for a whole shot.
"""
import json
import os
import re
import time
import uuid

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

import folder_paths

from .merserk_engine import ffmpeg_exe, merserk_dir, run_pilot

SCALES = {"source (100 %)": 1.0, "125 %": 1.25, "150 %": 1.5, "175 %": 1.75, "200 %": 2.0,
          "75 %": 0.75, "50 %": 0.5, "25 %": 0.25}
STYLES = ["Style 0", "Style 1", "Style 2"]
OPTICAL_FLOW = ["High", "Medium", "Low"]

# Our setting names -> Merserk's option fields (ImageConversionOptions / ConversionOptions, v15)
TO_ENGINE = {"passes": ("nr_passes", int), "style": ("nr_style", str), "intensity": ("nr_intensity", float),
             "local_tone": ("local_tone_strength", float), "local_structure": ("local_structure_strength", float),
             "skin_structure": ("skin_structure_strength", float), "auto_mask": ("automatic_mask", bool)}

# The engine's own defaults (what an unspecified setting falls back to in a preset or a variant line).
DEFAULTS = {"passes": 1, "style": "Style 0", "intensity": 1.0, "local_tone": 1.0, "local_structure": 1.0,
            "skin_structure": 1.0, "auto_mask": False, "scale": "source (100 %)"}

# The look we validated by eye — on portraits, "plastic AI" images and cinematic video shots — carried over to v15:
# ONE pass, moderate intensity and local tone, skin driven. On the same sources it lands at ~37 dB from the v9 look,
# and keeps the source brightness without any compensation (v15 no longer darkens).
AXIRIS_LOOK = {"passes": 1, "style": "Style 0", "intensity": 0.85, "local_tone": 0.595, "local_structure": 1.0,
               "skin_structure": 0.6, "auto_mask": True}

# Each preset is a DIRECTION we rendered side by side on the same sources; the Explorer shows them together.
PRESETS = {
    "AXIRIS look (validated)":             dict(AXIRIS_LOOK),
    "Engine defaults":                     {},
    "Style 1":                             dict(AXIRIS_LOOK, style="Style 1"),
    "Style 2":                             dict(AXIRIS_LOOK, style="Style 2"),
    "Two passes":                          dict(AXIRIS_LOOK, passes=2),
    "Stronger (intensity 1.2, tone 0.8)":  dict(AXIRIS_LOOK, intensity=1.2, local_tone=0.8),
    "Softer (0.6, tone 0.4, skin 0.4)":    dict(AXIRIS_LOOK, intensity=0.6, local_tone=0.4, skin_structure=0.4),
    "Full local tone (1.0)":               dict(AXIRIS_LOOK, local_tone=1.0),
}

# Every tile of the board SAYS its values: the three that always matter, then those that differ from the defaults.
_ALWAYS = ("style", "intensity", "local_tone")


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
    """A preset name, or « my test: intensity=1.1 local_tone=0.7 style=Style 1 ». None = ignored (empty or #)."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line in PRESETS:
        return line, dict(DEFAULTS, **PRESETS[line])
    name, _, rest = line.partition(":")
    if not rest.strip():
        raise ValueError(f"[AXIRIS DLSS5] line not understood: « {line} » — an exact preset name, or « name: intensity=1.1 local_tone=0.7 »")
    s = dict(DEFAULTS)
    rest = re.sub(r"style=Style\s+(\d)", r"style=Style_\1", rest)
    for word in rest.split():
        k, _, v = word.partition("=")
        if k not in DEFAULTS:
            raise ValueError(f"[AXIRIS DLSS5] unknown setting « {k} » in « {line} » (known: {', '.join(DEFAULTS)})")
        d = DEFAULTS[k]
        s[k] = (v.lower() in ("1", "true", "yes", "on")) if isinstance(d, bool) else type(d)(v.replace("Style_", "Style "))
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


def _control_png(image, folder):
    a = (image[0, ..., :3].detach().cpu().float().clamp(0, 1).numpy() * 255 + 0.5).astype(np.uint8)
    p = os.path.join(folder, "control_mask.png")
    Image.fromarray(a, "RGB").save(p)
    return p


def _render(images, variants, mask=None, control=None):
    """Renders len(variants) option sets of the batch `images` in ONE engine process.
    -> (list of [N,H,W,3] tensors in the order of the variants, pilot result)."""
    work = _work_dir("images")
    inputs = []
    for i in range(images.shape[0]):
        p = os.path.join(work, f"in_{i:05d}.png")
        _to_png(images[i], p)
        inputs.append(p)
    if control is not None:
        pm = _control_png(control, work)
        variants = [dict(v, nr_mask=pm) for v in variants]
    elif mask is not None:
        pm = _mask_png(mask, work)
        variants = [dict(v, nr_mask=pm) for v in variants]
    req = os.path.join(work, "request.json")
    json.dump({"inputs": inputs, "output_dir": os.path.join(work, "out"), "variants": variants}, open(req, "w", encoding="utf-8"))
    res = run_pilot("render_images.py", req, timeout=600 + 30 * len(inputs) * len(variants))
    return [torch.stack([_from_png(p) for p in v]) for v in res["variants"]], res


def _float(d, lo, hi, tip, step=0.05):
    return ("FLOAT", {"default": d, "min": lo, "max": hi, "step": step, "tooltip": tip})


_MASK_TIP = "where Neural Rendering applies — white = full, black = protected, grey = in between"
_CONTROL_TIP = ("a COLOUR control mask (DLSS's own, v15): red = intensity, green = local tone, blue = local structure, "
                "each channel 0-255 = 0-100 % of the slider. Wins over « mask » when both are plugged")


class AXDLSS5Render:
    CATEGORY = "AXIRIS DLSS5"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "report")
    FUNCTION = "render"
    DESCRIPTION = ("DLSS 5 Neural Rendering on an image or a batch (Merserk Visual Enhancer v15). The sliders start on the "
                   "AXIRIS look — a deliberately light starting point, not a universal setting: expect to tune per image. "
                   "'preset' (last) replaces every slider with a preset.")

    @classmethod
    def INPUT_TYPES(cls):
        L = AXIRIS_LOOK
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "an image or a batch"}),
                "passes": ("INT", {"default": L["passes"], "min": 1, "max": 4,
                                   "tooltip": "Neural Rendering passes on the same image — more = stronger effect"}),
                "style": (STYLES, {"default": L["style"], "tooltip": "DLSS's three native styles (Style 0 = the former Default, "
                                                                    "1 = Natural, 2 = Cinematic)"}),
                "intensity": _float(L["intensity"], 0.0, 2.0, "strength of each pass — the master dial"),
                "local_tone": _float(L["local_tone"], 0.0, 1.0, "broad local lighting — the light that carves the volumes"),
                "local_structure": _float(L["local_structure"], 0.0, 1.0, "high frequencies: material, micro-shadows"),
                "skin_structure": _float(L["skin_structure"], 0.0, 1.0, "pores / skin"),
                "auto_mask": ("BOOLEAN", {"default": L["auto_mask"], "tooltip": "the model's automatic mask"}),
                "scale": (list(SCALES), {"default": "source (100 %)",
                                         "tooltip": "render resolution: above 100 % the image is enlarged (Lanczos) BEFORE "
                                                    "Neural Rendering, below it is reduced"}),
            },
            "optional": {
                "mask": ("MASK", {"tooltip": _MASK_TIP}),
                "control_mask": ("IMAGE", {"tooltip": _CONTROL_TIP}),
                "preset": (["custom (sliders)"] + list(PRESETS), {"default": "custom (sliders)",
                           "tooltip": "a preset REPLACES every slider; « custom » = the sliders. The Explorer shows them side by side."}),
            },
        }

    def render(self, images, passes, style, intensity, local_tone, local_structure, skin_structure, auto_mask, scale,
               mask=None, control_mask=None, preset="custom (sliders)"):
        t0 = time.time()
        if preset in PRESETS:
            s, name = dict(DEFAULTS, **PRESETS[preset]), preset
        else:
            s = dict(passes=passes, style=style, intensity=intensity, local_tone=local_tone, local_structure=local_structure,
                     skin_structure=skin_structure, auto_mask=auto_mask, scale=scale)
            name = "custom"
        (out,), res = _render(images, [_engine_options(s)], mask, control_mask)
        m = "colour control" if control_mask is not None else ("yes" if mask is not None else "no")
        report = (f"[AXIRIS DLSS5 · {res.get('engine', 'Merserk')}] {images.shape[0]} image(s) · {name} · "
                  + " · ".join(f"{k} {v}" for k, v in s.items())
                  + f" · mask {m} · {res['output_px'][0]}×{res['output_px'][1]}"
                  + f" · engine {res['seconds']} s (total {time.time() - t0:.1f} s)"
                  + ("" if not res.get("adapted") else " · " + " ; ".join(res["adapted"])))
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
    DESCRIPTION = ("One image → every variant of the list (one per line: a preset name, or « name: intensity=1.1 local_tone=0.7 … ») "
                   "in ONE engine session. « board » = the source then each variant, at 100 % on the chosen zone, with its number "
                   "and its settings; « variants » = the full images. Click a tile of the board: the Before/After node shows it.")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "the image to try (the first of a batch)"}),
                "variants": ("STRING", {"multiline": True, "default": _default_list(),
                             "tooltip": "one variant per line: a preset name, or « my test: intensity=1.1 local_tone=0.7 "
                                        "skin_structure=0.4 style=Style 1 ». A line starting with # is ignored."}),
                "zone_x": ("INT", {"default": 50, "min": 0, "max": 100, "tooltip": "center of the zone shown at 100 %, % of the width"}),
                "zone_y": ("INT", {"default": 40, "min": 0, "max": 100, "tooltip": "center of the zone shown at 100 %, % of the height (40 ≈ a portrait's face)"}),
                "zone_size": ("INT", {"default": 512, "min": 128, "max": 2048, "step": 32, "tooltip": "side of the zone shown at 100 % — never reduced"}),
                "columns": ("INT", {"default": 4, "min": 1, "max": 8}),
            },
            "optional": {
                "mask": ("MASK", {"tooltip": _MASK_TIP + " (for every variant)"}),
                "control_mask": ("IMAGE", {"tooltip": _CONTROL_TIP}),
            },
        }

    def explore(self, image, variants, zone_x, zone_y, zone_size, columns, mask=None, control_mask=None):
        t0 = time.time()
        read = [x for x in (_read_line(l) for l in variants.splitlines()) if x]
        if not read:
            raise ValueError("[AXIRIS DLSS5] no variant to render (empty list)")
        src = image[:1]
        outs, res = _render(src, [_engine_options(s) for _, s in read], mask, control_mask)
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
    """DLSS 5 finishing of a SHOT: Merserk's video pipeline — temporal history, scene cuts, motion computed by the
    engine (optical flow). Frames in (VAE Decode, Load Video…), the same frames out, finished."""
    CATEGORY = "AXIRIS DLSS5"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "report")
    FUNCTION = "finish"
    DESCRIPTION = ("DLSS 5 finishing of a shot (Merserk Visual Enhancer v15 video pipeline). Defaults = the AXIRIS look. The "
                   "temporal pipeline brings stability — no added shimmer, brightness kept — rather than extra detail. The "
                   "whole shot goes through RAM as a ComfyUI image batch: fine for shots, not for minutes-long films.")

    @classmethod
    def INPUT_TYPES(cls):
        L = AXIRIS_LOOK
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "the frames of the shot, in order"}),
                "fps": _float(24.0, 1.0, 120.0, "frame rate of the shot (motion is computed between two frames)", 0.5),
                "intensity": _float(L["intensity"], 0.0, 2.0, "Neural Rendering strength"),
                "local_tone": _float(L["local_tone"], 0.0, 1.0, "the light that carves the volumes"),
                "local_structure": _float(L["local_structure"], 0.0, 1.0, "material, micro-shadows"),
                "skin_structure": _float(L["skin_structure"], 0.0, 1.0, "pores / skin"),
                "auto_mask": ("BOOLEAN", {"default": L["auto_mask"], "tooltip": "the model's automatic mask"}),
                "optical_flow": (OPTICAL_FLOW, {"default": "High", "tooltip": "quality of the motion the engine computes between "
                                                                              "frames — High = steadiest, Low = fastest"}),
                "passes": ("INT", {"default": L["passes"], "min": 1, "max": 4, "tooltip": "passes per frame"}),
                "style": (STYLES, {"default": L["style"]}),
            },
            "optional": {
                "mask": ("MASK", {"tooltip": _MASK_TIP + " — the same for the whole shot"}),
                "control_mask": ("IMAGE", {"tooltip": _CONTROL_TIP + " — the same for the whole shot"}),
            },
        }

    def finish(self, images, fps, intensity, local_tone, local_structure, skin_structure, auto_mask, optical_flow,
               passes, style, mask=None, control_mask=None):
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
                    "skin_structure_strength": float(skin_structure), "automatic_mask": bool(auto_mask),
                    "nr_optical_flow_quality": optical_flow, "codec": "H.265 (NVIDIA NVENC)", "quality": "Max",
                    "rename_mode": "Custom", "custom_suffix": "_finished"}
            if control_mask is not None:
                opts["nr_mask"] = _control_png(control_mask, work)
            elif mask is not None:
                opts["nr_mask"] = _mask_png(mask, work)
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
        report = (f"[AXIRIS DLSS5 video · {res.get('engine', 'Merserk')}] {n} frames {W}×{H} → {ow}×{oh} · intensity {intensity} · "
                  f"local_tone {local_tone} · structure {local_structure} · skin {skin_structure} · passes {passes} · {style} · "
                  f"optical flow {optical_flow} · mask {'colour control' if control_mask is not None else ('yes' if mask is not None else 'no')} · "
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
    "AXDLSS5Render": "AXIRIS DLSS 5 · Render",
    "AXDLSS5Explorer": "AXIRIS DLSS 5 · Explorer (every variant at once)",
    "AXDLSS5PickVariant": "AXIRIS DLSS 5 · Pick a variant",
    "AXDLSS5VideoFinish": "AXIRIS DLSS 5 · Video finishing (a shot)",
}
