// BEFORE / AFTER inside the node — the ComfyUI extension of AXBeforeAfter.
//
// The Python node writes both batches as JPEG in temp/ and returns a `ui`; this file shows them INSIDE the node,
// image or video: two batches read under ONE index (play / pause / loop, position bar, fps) — the sync is structural.
// It also follows the image selected in Save Image / Preview Image when `after` is a batch of variants, and turns a
// click on the Explorer's board into that variant. The slider itself is ours: ./axiris-slider.js.
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { SLIDER_CSS, createSlider } from "./axiris-slider.js";

(function () {
  "use strict";
  const CLASS = "AXBeforeAfter";
  const STYLE_ID = "axba-style";
  const CSS = SLIDER_CSS + `
.axba-root { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 120px; box-sizing: border-box;
  background: #1a1a1a; color: #ddd; font: 12px system-ui, sans-serif; }
.axba-root .axs-scene { flex: 1 1 auto; }
.axba-bar { flex: 0 0 auto; display: flex; align-items: center; gap: 6px; padding: 4px 6px; background: #222; border-top: 1px solid #333; }
.axba-bar[hidden] { display: none; }
.axba-bar button { background: #333; color: #eee; border: 1px solid #555; border-radius: 3px; padding: 2px 8px; cursor: pointer; font-size: 12px; }
.axba-bar button.on { background: #76b900; color: #000; border-color: #76b900; }
.axba-bar input[type=range] { flex: 1 1 auto; min-width: 60px; }
.axba-bar .axba-count { min-width: 76px; text-align: right; font-variant-numeric: tabular-nums; color: #bbb; }
.axba-empty { flex: 1 1 auto; display: flex; align-items: center; justify-content: center; color: #777; text-align: center; padding: 12px; }
`;

  function addStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement("style"); s.id = STYLE_ID; s.textContent = CSS;
    document.head.appendChild(s);
  }
  const viewUrl = (f) => api.apiURL("/view?filename=" + encodeURIComponent(f.filename) + "&type=" + encodeURIComponent(f.type || "temp") +
    "&subfolder=" + encodeURIComponent(f.subfolder || "") + "&rand=" + Math.random());
  const widget = (node, name, def) => { const w = (node.widgets || []).find((x) => x.name === name); return w ? w.value : def; };

  app.registerExtension({
    name: "axiris.dlss5.beforeAfter",
    async beforeRegisterNodeDef(nodeType, nodeData) {
      if (nodeData.name !== CLASS) return;
      addStyle();

      const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
        const node = this;
        const root = document.createElement("div");
        root.className = "axba-root";
        const empty = document.createElement("div");
        empty.className = "axba-empty";
        empty.textContent = "Connect `before` and `after`, then run: the slider shows up here.";
        root.appendChild(empty);

        const cmp = createSlider(root, {
          direction: widget(node, "direction", "vertical"),
          labelBefore: widget(node, "label_before", "BEFORE"),
          labelAfter: widget(node, "label_after", "AFTER"),
        });
        cmp.container.style.display = "none";

        const bar = document.createElement("div");
        bar.className = "axba-bar";
        bar.hidden = true;
        bar.innerHTML = '<button class="axba-play" title="play / pause (both sides move together)">▶</button>' +
          '<button class="axba-loop on" title="loop">⟳</button>' +
          '<input type="range" class="axba-pos" min="0" max="0" value="0" step="1" title="frame">' +
          '<span class="axba-count">0 / 0</span><span class="axba-fps"></span>';
        root.appendChild(bar);
        const bPlay = bar.querySelector(".axba-play"), bLoop = bar.querySelector(".axba-loop");
        const iPos = bar.querySelector(".axba-pos"), sCount = bar.querySelector(".axba-count"), sFps = bar.querySelector(".axba-fps");
        for (const ev of ["mousedown", "pointerdown", "touchstart", "wheel"]) bar.addEventListener(ev, (e) => e.stopPropagation());

        // two batches, ONE index
        const st = { before: [], after: [], n: 0, i: 0, fps: 24, timer: null, loop: true, follow: false };
        function show(i) {
          if (!st.n) return;
          st.i = ((i % st.n) + st.n) % st.n;
          cmp.set(st.before[st.i].src, st.after[st.i].src);
          iPos.value = String(st.i);
          sCount.textContent = (st.i + 1) + " / " + st.n;
        }
        function pause() {
          if (st.timer) { clearInterval(st.timer); st.timer = null; }
          bPlay.textContent = "▶"; bPlay.classList.remove("on");
        }
        function play() {
          if (st.n < 2) return;
          pause();
          bPlay.textContent = "⏸"; bPlay.classList.add("on");
          st.timer = setInterval(() => {
            if (st.i + 1 >= st.n && !st.loop) { pause(); return; }
            show(st.i + 1);
          }, 1000 / Math.max(1, st.fps));
        }
        bPlay.addEventListener("click", () => (st.timer ? pause() : play()));
        bLoop.addEventListener("click", () => { st.loop = !st.loop; bLoop.classList.toggle("on", st.loop); });
        iPos.addEventListener("input", () => { pause(); show(parseInt(iPos.value, 10) || 0); });

        // labels follow their widgets live (no rerun)
        for (const name of ["label_before", "label_after"]) {
          const w = (node.widgets || []).find((x) => x.name === name);
          if (!w) continue;
          const cb = w.callback;
          w.callback = function () {
            const rr = cb ? cb.apply(this, arguments) : undefined;
            cmp.labels(widget(node, "label_before", "BEFORE"), widget(node, "label_after", "AFTER"));
            return rr;
          };
        }

        const dom = node.addDOMWidget("axba_view", "div", root, { serialize: false, getMinHeight: () => 200 });
        dom.axba = { cmp, st, show, play, pause, bar, empty, sFps };
        node.axba = dom.axba;

        // FOLLOW THE SELECTION: when `after` is a batch (the Explorer's variants) and a Save Image / Preview Image receives
        // THE SAME batch, the image selected there (click, arrows) becomes the one in the slider. Graph read only.
        function neighbours() {
          const g = node.graph; if (!g) return [];
          const input = (node.inputs || []).find((x) => x.name === "after");
          const link = input && input.link != null ? g.links[input.link] : null;
          if (!link) return [];
          const origin = g.getNodeById(link.origin_id);
          const out = origin && origin.outputs && origin.outputs[link.origin_slot];
          return ((out && out.links) || []).map((id) => g.links[id]).filter(Boolean).map((l) => g.getNodeById(l.target_id))
            .filter((v) => v && v !== node && /^(SaveImage|PreviewImage)$/.test(v.type));
        }
        // THE CLICKABLE BOARD: the Preview Image connected to the Explorer's « board » output — a click on a tile = that
        // variant. The grid is the one nodes_dlss5._board() draws: `columns` of the Explorer, 8 px gaps, a title band of
        // max(40, side/10) above each tile, tile 0 = the source.
        function boardPreviews() {
          const g = node.graph; if (!g) return [];
          const input = (node.inputs || []).find((x) => x.name === "after");
          const link = input && input.link != null ? g.links[input.link] : null;
          const origin = link ? g.getNodeById(link.origin_id) : null;
          const iBoard = origin && (origin.outputs || []).findIndex((o) => o.name === "board");
          if (!origin || iBoard == null || iBoard < 0) return [];
          const cols = Number(((origin.widgets || []).find((w) => w.name === "columns") || {}).value) || 4;
          return ((origin.outputs[iBoard].links) || []).map((id) => g.links[id]).filter(Boolean)
            .map((l) => g.getNodeById(l.target_id)).filter((v) => v && v.type === "PreviewImage").map((v) => ({ v, cols }));
        }
        function wireBoard() {
          for (const { v, cols } of boardPreviews()) {
            const el = document.querySelector('[data-node-id="' + v.id + '"]');
            if (!el || el.__axbaBoard === node.id) continue;
            el.__axbaBoard = node.id;
            el.addEventListener("click", (ev) => {
              // ComfyUI lays a DIV over the image: take the preview's image, the click counts if it lands in its frame
              const img = el.querySelector("img");
              if (!img || !img.naturalWidth || !st.n) return;
              const rc = img.getBoundingClientRect();
              const W = img.naturalWidth, H = img.naturalHeight;
              const s = Math.min(rc.width / W, rc.height / H);                  // object-fit: contain
              const px = (ev.clientX - rc.left - (rc.width - W * s) / 2) / s;
              const py = (ev.clientY - rc.top - (rc.height - H * s) / 2) / s;
              if (px < 0 || py < 0 || px > W || py > H) return;
              const c = (W - (cols - 1) * 8) / cols;
              const band = Math.max(40, Math.floor(c / 10));
              const k = Math.floor(py / (c + band + 8)) * cols + Math.floor(px / (c + 8));
              if (k >= 1 && k - 1 < st.n) {
                pause(); show(k - 1); node.setDirtyCanvas(true, true);
                ev.stopPropagation(); ev.preventDefault();
              }
            }, true);
          }
        }
        let lastSeen = null;
        dom.axba.follower = setInterval(() => {
          if (!st.follow || st.n < 2) return;
          wireBoard();
          for (const v of neighbours()) {
            const i = v.imageIndex;
            if (typeof i === "number" && i !== lastSeen && i >= 0 && i < st.n) {
              lastSeen = i; pause(); show(i); node.setDirtyCanvas(true, true);
              return;
            }
          }
        }, 250);

        node.size = [Math.max(node.size[0], 560), Math.max(node.size[1], 470)];
        node.setDirtyCanvas(true, true);
        return r;
      };

      // AFTER A RUN: the Python node wrote both batches in temp/
      const onExecuted = nodeType.prototype.onExecuted;
      nodeType.prototype.onExecuted = function (message) {
        onExecuted && onExecuted.apply(this, arguments);
        const a = this.axba; if (!a) return;
        const d = (message && message.axba && message.axba[0]) || null;
        if (!d) return;
        a.pause();
        const load = (list) => list.map((f) => { const im = new Image(); im.src = viewUrl(f); return im; });   // preload, one index
        a.st.before = load(d.before || []);
        a.st.after = load(d.after || []);
        a.st.n = Math.min(a.st.before.length, a.st.after.length);
        a.st.fps = Number(d.fps) || 24;
        a.st.i = 0;
        a.st.follow = !!d.choice;          // one image against N variants: no playback, follow the selection
        a.cmp.labels(widget(this, "label_before", d.label_before || "BEFORE"), widget(this, "label_after", d.label_after || "AFTER"));
        const iPos = a.bar.querySelector(".axba-pos");
        iPos.max = String(Math.max(0, a.st.n - 1));
        a.sFps.textContent = a.st.n > 1 && !a.st.follow ? (a.st.fps + " fps") : "";
        a.bar.hidden = a.st.n < 2;
        a.empty.style.display = a.st.n ? "none" : "";
        a.cmp.container.style.display = a.st.n ? "" : "none";
        if (a.st.n) { a.cmp.position(50); a.show(0); }
        if (a.st.n > 1 && !a.st.follow) a.play();
        this.setDirtyCanvas(true, true);
      };

      const onRemoved = nodeType.prototype.onRemoved;
      nodeType.prototype.onRemoved = function () {
        if (this.axba) { this.axba.pause(); clearInterval(this.axba.follower); this.axba.cmp.destroy(); }
        onRemoved && onRemoved.apply(this, arguments);
      };
    },
  });
})();
