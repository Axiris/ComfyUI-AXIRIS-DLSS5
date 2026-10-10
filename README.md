# AXIRIS DLSS 5 for ComfyUI

DLSS 5 Neural Rendering on images and video, inside ComfyUI: a tuned render, an Explorer that shows
every variant at once, video finishing for a shot, and a before/after slider — image and video.

The engine is **Merserk's** [dlss5-visual-enhancer](https://github.com/Merserk/dlss5-visual-enhancer)
(v9, MIT). This pack calls it; it does not ship it. *[Version française plus bas.](#francais)*

## Install

1. In `ComfyUI/custom_nodes/`: `git clone https://github.com/Axiris/ComfyUI-AXIRIS-DLSS5`
2. Download Merserk's **v9** release ([releases](https://github.com/Merserk/dlss5-visual-enhancer/releases))
   and unzip it into `custom_nodes/ComfyUI-AXIRIS-DLSS5/merserk/` — the folder holding `app.py`, `src/`, `bin/`.
   Already installed elsewhere? Copy `config.example.json` to `config.json` and point it there
   (or set `MERSERK_DLSS5_DIR`).
3. Restart ComfyUI. The nodes are under **AXIRIS DLSS5**.

A recent RTX card is required. The DLSS 5 runtime (`nvngx_dlssnr.dll`) comes with Merserk: a
community-adapted, unsigned NVIDIA library. **This repository contains no NVIDIA file and no NVIDIA code.**

## Nodes

| Node | What it does |
| :--- | :--- |
| **Render (Merserk v9)** | DLSS 5 on an image or a batch. Sliders open on the AXIRIS look; `preset` swaps in a preset. Optional mask. |
| **Explorer** | One image → every variant of a list, in a single engine session. The board shows the same zone at 100 %, each tile with its settings. |
| **Pick a variant** | A board number → that variant alone, without re-running the Explorer. |
| **Video finishing** | A shot through Merserk's video pipeline (frame-to-frame memory, cuts, anti-shimmer). The shot is held in memory: for shots, not for feature-length files. |
| **Before / After slider** | Before/after under a slider, inside the node — image or video. Follows the image picked in Save Image, and a click on a board tile. |

## Settings: there is no universal one

**A setting that fits every image does not exist.** What DLSS 5 does depends on what is in the
picture — skin, stone, foliage and metal do not want the same amount of work, and the same value
that rescues one image flattens the next. **Expect to tune per image.**

The look shipped here is deliberately **light**: not the strongest result on any given picture, but
the one with the best odds of being acceptable on the widest range of them. Treat it as a starting
point, not an answer.

### What each setting buys you

| Setting | Range | What it buys | Reach for it when |
| :--- | :--- | :--- | :--- |
| `passes` | 1 – 4 | Repeats the pass. Stronger effect — **and darker each time**. | The image barely moves at one pass. Raise `tone_preservation` alongside. |
| `style` | Default · Natural · Cinematic | `Default` contrasted · `Natural` closest to the source *(can shift green eyes to blue-grey)* · `Cinematic` strongest. | The render drifts from the original mood. |
| `intensity` | 0 – 2 | Strength of each pass — the master dial. | You want more or less of everything at once. |
| `local_tone` | 0 – 2 | Broad local lighting: **the light that carves the volumes**. 1.5–2.0 digs deeper. | The image is flat, unlit, "cardboard". |
| `local_structure` | 0 – 2 | High frequencies: **material and micro-shadows**. | Stone, bark, fabric, foliage look smooth. |
| `skin_structure` | −1 – 2 | Pores and skin. **`-1` means *left to the engine*, not minimum** — and the engine tends to overdo it. | Always worth setting yourself on anything with skin. |
| `face_protection` | 0 – 1 | Holds the rendering back **on faces** while the rest is treated normally. | Portraits, crowds, anything where a face turns plastic. |
| `tone_preservation` | 0 – 1 | **Keeps the source brightness** — the counterweight of passes. | The render came out darker than the original. |
| `color_strength` | 0 – 1 | Share of the rendered colour. `0` keeps the source colours untouched. | Colours drift, skin turns orange. |
| `grain` | 0 – 1 | Keeps the source grain instead of polishing it away. | Film look, or an image that shouldn't look digital. |
| `auto_mask` | on/off | The engine's own mask — it decides where to work. | Leave on; turn off to treat the frame uniformly. |
| `mask` *(optional)* | — | **You** decide where it applies: white = treated, black = protected. | One subject to protect, or one area to push. |
| `scale` | — | Render resolution. **The v9 engine does not upscale** — this only changes what it works on. | Rarely. Upscale outside, then run DLSS 5. |

Two of them do **nothing** at their default, and they are the two that matter most:
**`skin_structure` at `-1`** (left to the engine) and **`tone_preservation` at `0`** (no brightness
held). Set them yourself.

To judge any setting, change **one slider at a time** and read it twice: against the previous
render — *what did this slider change?* — and against the source — *is the effect still there?*
The Explorer does both at once: it renders a list of variants in a single session and lays them
side by side at 100 %.

**For detail: upscale first** — the upscale adds matter — **then run DLSS 5.**

## Workflows

In `workflows/`, drag into ComfyUI:

- `AXIRIS_DLSS5_Reglage_AXIRIS.json` — one image, the AXIRIS look, every setting editable by hand;
- `AXIRIS_DLSS5_Explorer.json` — every variant, the clickable board, the slider following along;
- `AXIRIS_DLSS5_Video.json` — a finished shot saved to mp4, with the video slider.

Copy `examples/` into `ComfyUI/input/` to run them as they are.

## Credits and licences

This pack: MIT (see `LICENSE`). Engine: [Merserk/dlss5-visual-enhancer](https://github.com/Merserk/dlss5-visual-enhancer),
MIT, called as is — none of its code is copied here. DLSS is NVIDIA technology; the runtime Merserk
uses comes from the community. The slider is written from scratch.

---

<a id="francais"></a>
# AXIRIS DLSS 5 pour ComfyUI

DLSS 5 Neural Rendering sur images et vidéos, dans ComfyUI : un rendu réglé, un explorateur qui montre
toutes les variantes d'un coup, une finition vidéo pour un plan, et un comparateur avant/après à
curseur — image et vidéo. Le moteur est celui de **Merserk** (v9, MIT) : ce pack l'appelle, il ne le
contient pas.

**Installation** — clonez ce dépôt dans `ComfyUI/custom_nodes/`, décompressez la release v9 de Merserk
dans `custom_nodes/ComfyUI-AXIRIS-DLSS5/merserk/` (ou pointez `config.json` / `MERSERK_DLSS5_DIR` vers
une installation existante), redémarrez ComfyUI. Les nodes sont dans **AXIRIS DLSS5**. Une carte RTX
récente est nécessaire ; ce dépôt ne contient **aucun** fichier ni code NVIDIA.

**Le réglage universel n'existe pas** — ce que DLSS 5 fait dépend de ce qu'il y a dans l'image : peau,
pierre, feuillage et métal ne demandent pas le même travail, et la valeur qui sauve une image en écrase
une autre. **Prévoyez de régler image par image.** Le look livré ici est volontairement **léger** : pas
le meilleur résultat sur une image donnée, mais celui qui a le plus de chances de convenir au plus grand
nombre. C'est un point de départ, pas une réponse.

**Deux réglages à connaître** — leur valeur par défaut ne fait rien : `skin_structure = -1` ne veut pas
dire « minimum » mais « laissé au moteur », qui a tendance à trop travailler la peau ; et
`tone_preservation = 0` ne retient pas la luminosité de la source. Pilotez-les. `face_protection`
retient le même travail sur les visages. Pour juger un réglage : **un seul curseur à la fois**, lu deux
fois — contre le rendu précédent, et contre la source. **Pour du détail : agrandir d'abord, DLSS 5 ensuite.**

**Licences** — ce pack : MIT. Moteur : Merserk/dlss5-visual-enhancer, MIT, appelé tel quel. DLSS est une
technologie NVIDIA ; le runtime vient de la communauté. Le comparateur est écrit de zéro.
