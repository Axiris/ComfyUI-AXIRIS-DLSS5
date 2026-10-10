// The BEFORE / AFTER slider — written from scratch for this pack (same approach as the comparator of axiris.ai).
//
// Two images in the SAME box (object-fit: contain), the AFTER underneath, the BEFORE on top, clipped at the slider
// (never distorted, only hidden). Drag with mouse, finger or pen (Pointer Events + capture), click anywhere to send
// the slider there (animated), keyboard ← → (2 %, Shift = 10 %), Home / End. Vertical or horizontal.

export const SLIDER_CSS = `
.axs-scene { position: relative; width: 100%; height: 100%; min-height: 80px; overflow: hidden; background: #000;
  cursor: col-resize; touch-action: none; user-select: none; -webkit-user-select: none; outline: none; --axs-x: 50%; }
.axs-scene.axs-h { cursor: row-resize; }
.axs-scene:focus-visible { box-shadow: inset 0 0 0 2px #76b900; }
.axs-scene img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; display: block;
  pointer-events: none; -webkit-user-drag: none; }
.axs-before { position: absolute; inset: 0; clip-path: inset(0 calc(100% - var(--axs-x)) 0 0); }
.axs-h .axs-before { clip-path: inset(0 0 calc(100% - var(--axs-x)) 0); }
.axs-line { position: absolute; top: 0; bottom: 0; left: var(--axs-x); width: 2px; margin-left: -1px; background: #f2f2f2;
  box-shadow: 0 0 6px rgba(0,0,0,.7); pointer-events: none; }
.axs-h .axs-line { top: var(--axs-x); bottom: auto; left: 0; right: 0; width: auto; height: 2px; margin: -1px 0 0 0; }
/* the grip: thin, in proportion to the picture (16 % of its height, 28-56 px), see-through in its middle */
.axs-grip { position: absolute; top: 50%; left: 50%; width: 6px; height: clamp(28px, 16%, 56px); transform: translate(-50%, -50%);
  border-radius: 3px; background: linear-gradient(#76b900 40%, transparent 40% 60%, #76b900 60%); filter: drop-shadow(0 0 2px rgba(0,0,0,.8)); }
.axs-h .axs-grip { width: clamp(28px, 16%, 56px); height: 6px; background: linear-gradient(90deg, #76b900 40%, transparent 40% 60%, #76b900 60%); }
.axs-scene:not(.axs-dragging) .axs-before { transition: clip-path .3s ease; }
.axs-scene:not(.axs-dragging) .axs-line { transition: left .3s ease, top .3s ease; }
@media (prefers-reduced-motion: reduce) { .axs-scene .axs-before, .axs-scene .axs-line { transition: none; } }
.axs-label { position: absolute; bottom: 8px; padding: 4px 10px; font: 600 11px/1.3 system-ui, sans-serif; letter-spacing: .08em;
  text-transform: uppercase; color: #fff; background: rgba(0,0,0,.62); pointer-events: none; white-space: nowrap; }
.axs-label-before { left: 0; border-right: 3px solid rgba(255,255,255,.55); }
.axs-label-after { right: 0; border-bottom: 3px solid #76b900; }
.axs-h .axs-label-before { top: 8px; bottom: auto; }
`;

const clamp = (v) => Math.min(100, Math.max(0, v));

export function createSlider(root, { direction = "vertical", labelBefore = "BEFORE", labelAfter = "AFTER" } = {}) {
  const horizontal = direction === "horizontal";
  const scene = document.createElement("div");
  scene.className = "axs-scene" + (horizontal ? " axs-h" : "");
  scene.tabIndex = 0;
  scene.setAttribute("role", "slider");
  scene.setAttribute("aria-valuemin", "0");
  scene.setAttribute("aria-valuemax", "100");
  scene.innerHTML =
    '<img class="axs-after" alt="" draggable="false">' +
    '<div class="axs-before"><img alt="" draggable="false"></div>' +
    '<div class="axs-line"><span class="axs-grip"></span></div>' +
    '<span class="axs-label axs-label-before"></span><span class="axs-label axs-label-after"></span>';
  root.appendChild(scene);
  const imgAfter = scene.querySelector(".axs-after");
  const imgBefore = scene.querySelector(".axs-before img");
  const lBefore = scene.querySelector(".axs-label-before");
  const lAfter = scene.querySelector(".axs-label-after");

  let x = 50, pid = null;
  const set = (v) => {
    x = clamp(v);
    scene.style.setProperty("--axs-x", x + "%");
    scene.setAttribute("aria-valuenow", String(Math.round(x)));
  };
  const at = (e) => {
    const r = scene.getBoundingClientRect();
    return horizontal ? (r.height > 0 ? ((e.clientY - r.top) / r.height) * 100 : 50)
                      : (r.width > 0 ? ((e.clientX - r.left) / r.width) * 100 : 50);
  };
  const down = (e) => {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    pid = e.pointerId;
    try { scene.setPointerCapture(pid); } catch (_) { /* no capture: dragging still works inside the scene */ }
    set(at(e));                     // first contact = a click: the slider GLIDES there (CSS transition)
    scene.focus({ preventScroll: true });
    e.preventDefault(); e.stopPropagation();
  };
  const move = (e) => {
    if (e.pointerId !== pid) return;
    scene.classList.add("axs-dragging");
    set(at(e));
    e.stopPropagation();
  };
  const up = (e) => {
    if (e.pointerId !== pid) return;
    pid = null;
    scene.classList.remove("axs-dragging");
    try { scene.releasePointerCapture(e.pointerId); } catch (_) { /* already released */ }
  };
  const key = (e) => {
    const step = e.shiftKey ? 10 : 2;
    let v = null;
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") v = x - step;
    else if (e.key === "ArrowRight" || e.key === "ArrowDown") v = x + step;
    else if (e.key === "Home") v = 0;
    else if (e.key === "End") v = 100;
    if (v === null) return;
    e.preventDefault(); e.stopPropagation();
    set(v);
  };
  scene.addEventListener("pointerdown", down);
  scene.addEventListener("pointermove", move);
  scene.addEventListener("pointerup", up);
  scene.addEventListener("pointercancel", up);
  scene.addEventListener("keydown", key);
  // inside a LiteGraph node: the canvas must not take the mouse or the wheel
  for (const ev of ["mousedown", "touchstart", "wheel"]) scene.addEventListener(ev, (e) => e.stopPropagation());

  const labels = (a, b) => {
    lBefore.textContent = a; lAfter.textContent = b;
    scene.setAttribute("aria-label", "Before / after slider: " + a + " / " + b);
  };
  labels(labelBefore, labelAfter);
  set(50);

  return {
    container: scene, imgBefore, imgAfter,
    set(urlBefore, urlAfter) { imgBefore.src = urlBefore; imgAfter.src = urlAfter; },
    labels,
    position: set,
    destroy() {
      scene.removeEventListener("pointerdown", down);
      scene.removeEventListener("pointermove", move);
      scene.removeEventListener("pointerup", up);
      scene.removeEventListener("pointercancel", up);
      scene.removeEventListener("keydown", key);
    },
  };
}
