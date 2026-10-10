# AXIRIS DLSS 5 for ComfyUI

DLSS 5 Neural Rendering on images and video, inside ComfyUI: a tuned render, an Explorer that shows
every variant at once, video finishing for a shot, and a before/after slider — image and video.

The engine is **Merserk's** [Visual Enhancer](https://github.com/Merserk/dlss5-visual-enhancer) (v15).
This pack calls it; it does not ship it. *[Version française plus bas.](#francais)*

## What we learned (measured, RTX PRO 6000 Blackwell, Windows 11)

Portraits, "plastic AI" images and video shots. Each point is a measurement, not an impression.

- **The settings make the look.** One pass, intensity 0.85, local tone ≈ 0.6 — the look we validated by eye. We first
  credited a depth map for that render; the same settings **without any depth** reproduce it at 53.8 dB (beyond ~40 dB
  the eye sees no difference). The depth map was not what made it.
- **The engine ignores depth.** Flat, white, noisy or inverted depth: the same image to the pixel; on video, 124/124 frames
  identical with a flat depth. The runtime has no input for normals or materials: it reads the image and the motion and
  **infers** the volumes, then lights them (the **local tone** drives that light).
- **Time brings stability, not detail.** A synthetic sequence built from one photo (sub-pixel jitter, exact motion) gives no
  more detail than a single pass. On real video: no added shimmer, brightness kept.
- **It transforms more than it enhances.** It pulls the image towards its own realism: striking on drawn or "plastic AI"
  images, riskier on photo-real portraits (it guesses materials — a ring can stop looking like metal).
- **v15 keeps the brightness.** With v9, extra passes darkened the image (skin 167 → 114 → 94 for source / 2 / 4 passes) and
  had to be compensated. On the same sources, v15 holds the source brightness without any compensation.

## Install

1. In `ComfyUI/custom_nodes/`: `git clone https://github.com/Axiris/ComfyUI-AXIRIS-DLSS5`
2. A working installation of **Merserk's Visual Enhancer v15** is required — see
   [their project](https://github.com/Merserk/dlss5-visual-enhancer). Point this pack to it: copy `config.example.json`
   to `config.json` and set `merserk_dir`, or set `MERSERK_DLSS5_DIR`. A folder holding several releases side by side
   (`v9.0`, `v15.0`…) works too: the newest one is used.
3. Restart ComfyUI. The nodes are under **AXIRIS DLSS5**.

A recent RTX card is required. DLSS 5 Neural Rendering runs on `nvngx_dlssnr.dll`, a proprietary NVIDIA binary,
unmodified and unsigned, that NVIDIA does not distribute outside games and that the community reuses.
**This repository contains none of it, and no NVIDIA code.**

## Nodes

| Node | What it does |
| :--- | :--- |
| **Render** | DLSS 5 on an image or a batch. Sliders open on the AXIRIS look; `preset` swaps in a preset. Optional mask or colour control mask. |
| **Explorer** | One image → every variant of a list, in a single engine session. The board shows the same zone at 100 %, each tile with its settings. |
| **Pick a variant** | A board number → that variant alone, without re-running the Explorer. |
| **Video finishing** | A shot through Merserk's video pipeline (temporal history, scene cuts, motion computed by the engine). The shot is held in memory: for shots, not for feature-length files. |
| **Before / After slider** | Before/after under a slider, inside the node — image or video. Follows the image picked in Save Image, and a click on a board tile. |

## Settings: there is no universal one

**A setting that fits every image does not exist.** What DLSS 5 does depends on what is in the
picture — skin, stone, foliage and metal do not want the same amount of work, and the same value
that rescues one image flattens the next. **Expect to tune per image.**

The look shipped here is deliberately **light**: not the strongest result on any given picture, but
the one with the best odds of being acceptable on the widest range of them. Treat it as a starting
point, not an answer.

### What each setting buys you

These are DLSS's own controls (v15).

| Setting | Range | What it buys | Reach for it when |
| :--- | :--- | :--- | :--- |
| `passes` | 1 – 4 | Repeats the pass: a stronger effect. | The image barely moves at one pass. |
| `style` | Style 0 · 1 · 2 | DLSS's three native styles (formerly Default, Natural, Cinematic). | The render drifts from the original mood. |
| `intensity` | 0 – 2 | Strength of each pass — the master dial. | You want more or less of everything at once. |
| `local_tone` | 0 – 1 | Broad local lighting: **the light that carves the volumes**. | The image is flat, unlit, "cardboard". |
| `local_structure` | 0 – 1 | High frequencies: **material and micro-shadows**. | Stone, bark, fabric, foliage look smooth. |
| `skin_structure` | 0 – 1 | Pores and skin. | Always worth setting yourself on anything with skin. |
| `auto_mask` | on/off | The engine's own mask — it decides where to work. | Leave on; turn off to treat the frame uniformly. |
| `mask` *(optional)* | — | **You** decide where it applies: white = full, black = protected, grey = in between. | One subject to protect, or one area to push. |
| `control_mask` *(optional)* | — | A colour mask: **red = intensity, green = local tone, blue = local structure**, each channel separately. | Different amounts of work in different areas. |
| `scale` | — | Render resolution. Above 100 % the image is enlarged (Lanczos) **before** Neural Rendering. | You need more pixels for the engine to work on. |
| `optical_flow` *(video)* | High · Medium · Low | Quality of the motion the engine computes between frames. | High = steadiest; Low = fastest. |

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

This pack: MIT (see `LICENSE`). Engine: [Merserk's Visual Enhancer](https://github.com/Merserk/dlss5-visual-enhancer),
under its own licence (the Merserk Source License: personal, professional and commercial use; no redistribution) —
called as is, none of its code is copied or shipped here. DLSS is NVIDIA technology; `nvngx_dlssnr.dll` is NVIDIA's.
The slider is written from scratch.

---

<a id="francais"></a>
# AXIRIS DLSS 5 pour ComfyUI

DLSS 5 Neural Rendering sur images et vidéos, dans ComfyUI : un rendu réglé, un explorateur qui montre
toutes les variantes d'un coup, une finition vidéo pour un plan, et un comparateur avant/après à
curseur — image et vidéo. Le moteur est le **Visual Enhancer de Merserk** (v15) : ce pack l'appelle,
il ne le contient pas.

## Ce qu'on a compris (mesuré, RTX PRO 6000 Blackwell, Windows 11)

- **C'est le réglage qui fait le rendu.** Une passe, intensité 0.85, ton local ≈ 0.6 : le look validé à l'œil. On l'avait
  d'abord attribué à une carte de profondeur ; les mêmes réglages **sans aucune profondeur** le reproduisent à 53,8 dB
  (au-delà de ~40 dB, l'œil ne voit plus de différence). Ce n'était pas la profondeur.
- **Le moteur ignore la profondeur.** Plate, blanche, bruitée ou inversée : même image au pixel ; en vidéo, 124 images sur 124
  identiques avec une profondeur plate. Le runtime n'a aucune entrée pour les normales ou les matières : il lit l'image et le
  mouvement, il **déduit** les volumes et leur donne une lumière (le **ton local** la règle).
- **Le temps sert la stabilité, pas le détail.** Une séquence fabriquée à partir d'une photo (micro-décalages, mouvement connu
  au pixel) ne rend pas plus de détail qu'une passe. Sur une vraie vidéo : aucun scintillement ajouté, luminosité gardée.
- **Il transforme plus qu'il n'améliore.** Spectaculaire sur un plan dessiné ou une image « plastique IA », plus risqué sur un
  portrait déjà photo (il devine les matières — un anneau peut cesser d'être du métal).
- **La v15 garde la luminosité.** En v9, les passes assombrissaient (peau 167 → 114 → 94 : source, 2, 4 passes) et il fallait
  compenser. Sur les mêmes sources, la v15 garde la luminosité de la source sans compensation.

## Installation

Clonez ce dépôt dans `ComfyUI/custom_nodes/`. Une installation fonctionnelle du **Visual Enhancer v15 de Merserk** est
nécessaire — voir [leur projet](https://github.com/Merserk/dlss5-visual-enhancer). Indiquez-la au pack : `config.json`
(copie de `config.example.json`, champ `merserk_dir`) ou la variable `MERSERK_DLSS5_DIR` ; un dossier qui contient
plusieurs versions côte à côte (`v9.0`, `v15.0`…) convient aussi, la plus récente est prise. Redémarrez ComfyUI : les nodes
sont dans **AXIRIS DLSS5**.

Une carte RTX récente est nécessaire. DLSS 5 Neural Rendering tourne sur `nvngx_dlssnr.dll`, un binaire propriétaire NVIDIA,
non modifié et non signé, que NVIDIA ne distribue pas hors des jeux et que la communauté réemploie. **Ce dépôt n'en contient
rien, ni aucune ligne de code NVIDIA.**

## Les réglages

**Le réglage universel n'existe pas** — ce que DLSS 5 fait dépend de ce qu'il y a dans l'image : peau, pierre, feuillage et
métal ne demandent pas le même travail, et la valeur qui sauve une image en écrase une autre. **Prévoyez de régler image par
image.** Le look livré ici est volontairement **léger** : un point de départ, pas une réponse.

Ce sont les contrôles natifs de DLSS (v15) : `style` (0, 1, 2), `intensity` (0-2), `local_tone`, `local_structure` et
`skin_structure` (0-1), le masque automatique du modèle. Pour protéger ou pousser une zone : un **masque** (blanc = plein,
noir = protégé) ou un **masque de contrôle en couleurs** — rouge = intensité, vert = ton local, bleu = structure. Pour juger un
réglage : **un seul curseur à la fois**, lu deux fois — contre le rendu précédent, et contre la source. **Pour du détail :
agrandir d'abord, DLSS 5 ensuite.**

## Crédits et licences

Ce pack : MIT. Moteur : le [Visual Enhancer de Merserk](https://github.com/Merserk/dlss5-visual-enhancer), sous sa propre
licence (Merserk Source License : usage personnel, professionnel et commercial ; pas de redistribution) — appelé tel quel,
aucune ligne de son code n'est copiée ni livrée ici. DLSS est une technologie NVIDIA ; `nvngx_dlssnr.dll` appartient à
NVIDIA. Le comparateur est écrit de zéro.
