# -*- coding: utf-8 -*-
"""AXIRIS DLSS 5 for ComfyUI — Neural Rendering through Merserk's v9 engine, an Explorer, video finishing,
and a Before / After slider. See README.md."""
from .nodes_before_after import NODE_CLASS_MAPPINGS as _BA, NODE_DISPLAY_NAME_MAPPINGS as _BA_NAMES
from .nodes_dlss5 import NODE_CLASS_MAPPINGS as _D5, NODE_DISPLAY_NAME_MAPPINGS as _D5_NAMES

NODE_CLASS_MAPPINGS = {**_D5, **_BA}
NODE_DISPLAY_NAME_MAPPINGS = {**_D5_NAMES, **_BA_NAMES}
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
