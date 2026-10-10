# -*- coding: utf-8 -*-
"""BEFORE / AFTER under a slider — see what a treatment (DLSS 5, upscale, inpaint…) changed, image or video.

A number (PSNR, frame diff) says an image was reworked; it does not say whether it is better. The slider you hold,
on the image or on the playing video, lets the eye judge.

- Two IMAGE batches, `before` and `after`. A batch of 1 = an image; a batch of N = a video (batch order = time).
  Both batches are read under ONE index by the front end: the sync is structural, not a setting.
- ONE image against a BATCH (the source against the Explorer's variants): it is repeated against each image of the
  batch — not a video, a choice among N. The front end then follows the image selected in Save Image / Preview Image,
  and a click on the Explorer's board.
- The node computes nothing: it writes the frames as JPEG in temp/ (served by /view, like Preview Image) and returns
  a `ui`; the display lives in web/axiris-dlss5-before-after.js. Different sizes are fine (upscales): both images use
  the same box on screen, the before is shown at the after's scale.
"""
import os
import uuid

import numpy as np
import torch
from PIL import Image

import folder_paths

_SUBFOLDER = "axiris_before_after"


def _save_batch(images, folder, prefix, fmt, quality, max_frames):
    n = int(images.shape[0])
    if max_frames > 0:
        n = min(n, max_frames)
    entries = []
    h, w = int(images.shape[1]), int(images.shape[2])
    ext = "png" if fmt == "png" else "jpg"
    for i in range(n):
        arr = (images[i].detach().to("cpu", torch.float32).clamp(0.0, 1.0).numpy()[..., :3] * 255.0 + 0.5).astype(np.uint8)
        im = Image.fromarray(arr, "RGB")
        name = "%s_%05d.%s" % (prefix, i, ext)
        if ext == "png":
            im.save(os.path.join(folder, name), format="PNG", compress_level=1)
        else:
            im.save(os.path.join(folder, name), format="JPEG", quality=int(quality), subsampling=0)
        entries.append({"filename": name, "subfolder": _SUBFOLDER, "type": "temp"})
    return entries, (w, h)


class AXBeforeAfter:
    CATEGORY = "AXIRIS DLSS5"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("report",)
    FUNCTION = "show"
    OUTPUT_NODE = True
    DESCRIPTION = ("BEFORE / AFTER under a slider, inside the node: an image (batch of 1) or a video (batch of N frames, played "
                   "in sync under one index). Drag, or click to send the slider there; editable labels; the before is shown "
                   "at the after's scale. Computes nothing.")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "before": ("IMAGE", {"tooltip": "the batch BEFORE the treatment (the loaded image, the source video's frames)"}),
                "after": ("IMAGE", {"tooltip": "the batch AFTER the treatment — same order as before"}),
            },
            "optional": {
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 0.5, "tooltip": "playback speed of a batch of N frames"}),
                "label_before": ("STRING", {"default": "BEFORE"}),
                "label_after": ("STRING", {"default": "AFTER — DLSS 5"}),
                "direction": (["vertical", "horizontal"], {"default": "vertical",
                              "tooltip": "vertical = before on the left, after on the right; horizontal = before on top"}),
                "format": (["jpeg", "png"], {"default": "jpeg", "tooltip": "preview files in temp/: jpeg (light) or png (lossless, heavy on a video)"}),
                "jpeg_quality": ("INT", {"default": 92, "min": 50, "max": 100}),
                "max_frames": ("INT", {"default": 600, "min": 0, "max": 100000, "tooltip": "safety bound on a batch's length (0 = all)"}),
            },
        }

    def show(self, before, after, fps=24.0, label_before="BEFORE", label_after="AFTER — DLSS 5", direction="vertical",
             format="jpeg", jpeg_quality=92, max_frames=600):
        for name, t in (("before", before), ("after", after)):
            if not isinstance(t, torch.Tensor) or t.ndim != 4:
                raise ValueError("`%s` must be an IMAGE batch [B,H,W,C]" % name)
        folder = os.path.join(folder_paths.get_temp_directory(), _SUBFOLDER)
        os.makedirs(folder, exist_ok=True)
        token = uuid.uuid4().hex[:8]
        choice = False
        if int(before.shape[0]) == 1 and int(after.shape[0]) > 1:
            before, choice = before.expand(int(after.shape[0]), -1, -1, -1), True
        elif int(after.shape[0]) == 1 and int(before.shape[0]) > 1:
            after, choice = after.expand(int(before.shape[0]), -1, -1, -1), True
        n = min(int(before.shape[0]), int(after.shape[0]))
        if max_frames > 0:
            n = min(n, int(max_frames))
        e_before, s_before = _save_batch(before, folder, "axba_%s_before" % token, format, jpeg_quality, n)
        e_after, s_after = _save_batch(after, folder, "axba_%s_after" % token, format, jpeg_quality, n)
        lines = ["BEFORE / AFTER — %d frame(s)" % n + (" (video at %.3g fps)" % fps if n > 1 and not choice else ""),
                 "before: %d frame(s) %dx%d · after: %d frame(s) %dx%d" % (int(before.shape[0]), s_before[0], s_before[1],
                                                                           int(after.shape[0]), s_after[0], s_after[1])]
        if int(before.shape[0]) != int(after.shape[0]):
            lines.append("⚠ different lengths: compared on the first %d frames" % n)
        if s_before != s_after:
            lines.append("different sizes (×%.3g in width): the before is shown at the after's scale" % (s_after[0] / max(1, s_before[0])))
        report = "\n".join(lines)
        return {"ui": {"axba": [{"before": e_before, "after": e_after, "n": n, "fps": float(fps), "choice": choice,
                                 "label_before": label_before, "label_after": label_after, "direction": direction,
                                 "sizes": {"before": list(s_before), "after": list(s_after)}, "report": report}]},
                "result": (report,)}


NODE_CLASS_MAPPINGS = {"AXBeforeAfter": AXBeforeAfter}
NODE_DISPLAY_NAME_MAPPINGS = {"AXBeforeAfter": "AXIRIS · Before / After slider (image & video)"}
