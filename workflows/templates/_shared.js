/* Shared browser helpers for the code-graph report templates.
 * Injected by codegraph_core.render() into the `HELPERS` token, after
 * `const DATA = ...`, so everything here must be a pure function or a
 * constant — nothing may read DATA at load time.
 *
 * Provides: DOM/format helpers, a tooltip, canvas fitting, a sortable table,
 * and the two canvas renderers both reports share (force graph + dependency
 * matrix), parameterised by colour/tooltip callbacks so each report can encode
 * its own meaning on the same geometry. */

const $ = (id) => document.getElementById(id);
const tip = $("tip");
const PALETTE = ["#32FE6B","#C8FF6A","#00C800","#006A26","#8FD6FF","#FFD966",
                 "#FF8A6A","#C79BFF","#6AFFD6","#FF6AC1","#B0B0B0","#5B8DEF"];

/* Layers keep a stable colour across both reports: index into PALETTE. */
function buildLayerColors(layers) {
  const map = {};
  (layers || []).forEach((l, i) => { map[l] = PALETTE[i % PALETTE.length]; });
  return map;
}

const fmt = (n) => n >= 10000 ? (n / 1000).toFixed(1) + "k" : String(n);
const signed = (n) => (n > 0 ? "+" : "") + n;
const median = (xs) => {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b), m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

function showTip(html, ev) {
  tip.innerHTML = html;
  tip.style.display = "block";
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.min(ev.clientX + pad, innerWidth - w - pad) + "px";
  tip.style.top = Math.min(ev.clientY + pad, innerHeight - h - pad) + "px";
}
const hideTip = () => { tip.style.display = "none"; };

/* Size a canvas to its box at device resolution. Returns null while the
   element still has no layout (e.g. called before first paint), so callers
   can skip drawing rather than render into a zero-width bitmap. */
function fitCanvas(canvas) {
  const w = canvas.clientWidth;
  if (!w) return null;
  const dpr = window.devicePixelRatio || 1;
  const h = canvas.getAttribute("height") | 0;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}
function noData(ctx, text) {
  ctx.fillStyle = "#9E9E9E";
  ctx.font = "12px system-ui, sans-serif";
  ctx.fillText(text, 12, 22);
}

/* ------------------------------------------------------------- force graph */
/* opts: { canvas, nodes, edges, colorFor(node), tooltipFor(node),
           emphasise(node)  -> true to always label and ring the node,
           edgeIsNew(edge)  -> true to draw the edge as an addition }
   Returns { render, focusOn(predicate) }. Positions are simulated once and
   rescaled on resize, so render() is cheap to call again. */
function createForceGraph(opts) {
  const { canvas, nodes, edges } = opts;
  const n = nodes.length;
  const colorFor = opts.colorFor || (() => "#32FE6B");
  const emphasise = opts.emphasise || (() => false);
  const edgeIsNew = opts.edgeIsNew || (() => false);
  const maxLoc = Math.max(...nodes.map((x) => x.loc || 0), 1);
  const radius = (x) => 3 + 13 * Math.sqrt((x.loc || 0) / maxLoc);

  const neighbours = nodes.map(() => new Set());
  edges.forEach((e) => { neighbours[e.s].add(e.t); neighbours[e.t].add(e.s); });

  let ctx = null, w = 0, h = 0, pos = null, focus = null, only = null;

  /* Grid-bucketed repulsion + spring attraction; linear enough for ~1000 nodes. */
  function layout() {
    pos = nodes.map((_, i) => {
      const a = (i / n) * Math.PI * 2, r = Math.min(w, h) * 0.38;
      return { x: w / 2 + Math.cos(a) * r, y: h / 2 + Math.sin(a) * r, vx: 0, vy: 0 };
    });
    const ticks = Math.max(60, Math.min(320, Math.round(26000 / n)));
    const cell = Math.max(24, Math.sqrt((w * h) / n));
    for (let t = 0; t < ticks; t++) {
      const buckets = new Map();
      pos.forEach((p, i) => {
        const key = ((p.x / cell) | 0) + ":" + ((p.y / cell) | 0);
        if (!buckets.has(key)) buckets.set(key, []);
        buckets.get(key).push(i);
      });
      pos.forEach((p, i) => {
        const cx = (p.x / cell) | 0, cy = (p.y / cell) | 0;
        for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
          for (const j of buckets.get((cx + dx) + ":" + (cy + dy)) || []) {
            if (j === i) continue;
            const ax = p.x - pos[j].x, ay = p.y - pos[j].y;
            const d2 = ax * ax + ay * ay || 0.01;
            if (d2 > cell * cell * 4) continue;
            const f = 420 / d2;
            p.vx += ax * f; p.vy += ay * f;
          }
        }
        p.vx += (w / 2 - p.x) * 0.006;
        p.vy += (h / 2 - p.y) * 0.006;
      });
      edges.forEach((e) => {
        const a = pos[e.s], b = pos[e.t];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.hypot(dx, dy) || 0.01;
        const f = (d - 90) * 0.012 * Math.min(1, (e.w || 1) / 3 + 0.4);
        a.vx += (dx / d) * f; a.vy += (dy / d) * f;
        b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
      });
      pos.forEach((p) => {
        p.vx *= 0.82; p.vy *= 0.82;
        p.x = Math.max(14, Math.min(w - 14, p.x + p.vx));
        p.y = Math.max(14, Math.min(h - 14, p.y + p.vy));
      });
    }
  }

  function arrow(a, b, target) {
    const d = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const ux = (b.x - a.x) / d, uy = (b.y - a.y) / d, back = radius(target) + 7;
    const hx = b.x - ux * back, hy = b.y - uy * back;
    ctx.beginPath();
    ctx.moveTo(hx, hy);
    ctx.lineTo(hx - ux * 7 - uy * 3.2, hy - uy * 7 + ux * 3.2);
    ctx.lineTo(hx - ux * 7 + uy * 3.2, hy - uy * 7 - ux * 3.2);
    ctx.fill();
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);
    const inScope = (i) => !only || only(nodes[i], i);
    const lit = (i) => (focus === null || i === focus || neighbours[focus].has(i)) && inScope(i);

    edges.forEach((e) => {
      const on = (focus === null || e.s === focus || e.t === focus) && (inScope(e.s) || inScope(e.t));
      const fresh = edgeIsNew(e);
      if (!on) {
        ctx.strokeStyle = "rgba(255,255,255,.04)";
        ctx.lineWidth = 0.5;
      } else if (fresh) {
        ctx.strokeStyle = "rgba(200,255,106,.85)";
        ctx.lineWidth = Math.min(3, 1.2 + (e.w || 1) * 0.2);
      } else {
        ctx.strokeStyle = "rgba(50,254,107,.34)";
        ctx.lineWidth = Math.min(2.4, 0.6 + (e.w || 1) * 0.18);
      }
      const a = pos[e.s], b = pos[e.t];
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      if (!on) return;
      ctx.fillStyle = fresh ? "rgba(200,255,106,.9)" : "rgba(50,254,107,.55)";
      arrow(a, b, nodes[e.t]);
    });

    nodes.forEach((node, i) => {
      ctx.globalAlpha = lit(i) ? 1 : 0.14;
      ctx.beginPath();
      ctx.arc(pos[i].x, pos[i].y, radius(node), 0, Math.PI * 2);
      ctx.fillStyle = colorFor(node);
      ctx.fill();
      if (emphasise(node)) {
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = 1.6;
        ctx.stroke();
      } else if ((node.ca || 0) + (node.ce || 0) === 0) {
        ctx.strokeStyle = "#FFD966";
        ctx.lineWidth = 1.4;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    });

    ctx.font = "11px system-ui, sans-serif";
    nodes.forEach((node, i) => {
      if (!lit(i)) return;
      if (radius(node) < 8 && focus === null && !emphasise(node)) return;
      ctx.fillStyle = emphasise(node) ? "#FFFFFF" : "rgba(255,255,255,.82)";
      ctx.fillText(node.id.split(".").slice(-2).join("."), pos[i].x + radius(node) + 4, pos[i].y + 3.5);
    });
  }

  function hit(ev) {
    if (!pos) return null;
    const box = canvas.getBoundingClientRect();
    const mx = ev.clientX - box.left, my = ev.clientY - box.top;
    let best = null, bestD = 1e9;
    pos.forEach((p, i) => {
      const d = Math.hypot(p.x - mx, p.y - my);
      if (d < radius(nodes[i]) + 5 && d < bestD) { best = i; bestD = d; }
    });
    return best;
  }

  canvas.addEventListener("mousemove", (ev) => {
    const i = hit(ev);
    if (i === null) return hideTip();
    showTip(opts.tooltipFor(nodes[i]), ev);
  });
  canvas.addEventListener("mouseleave", hideTip);
  canvas.addEventListener("click", (ev) => {
    if (!pos) return;
    focus = hit(ev);
    draw();
  });

  function render() {
    const fit = fitCanvas(canvas);
    if (!fit) return;
    ctx = fit.ctx;
    if (!n) return noData(ctx, "no modules found");
    if (!pos) {
      w = fit.w; h = fit.h;
      layout();
    } else if (fit.w !== w || fit.h !== h) {
      const rx = fit.w / w, ry = fit.h / h;
      pos.forEach((p) => { p.x *= rx; p.y *= ry; });
      w = fit.w; h = fit.h;
    }
    draw();
  }
  /* Restrict the lit set to nodes matching a predicate (null = all). */
  function focusOn(predicate) {
    only = predicate;
    focus = null;
    if (pos) draw();
  }
  return { render, focusOn };
}

/* -------------------------------------------------------- dependency matrix */
/* opts: { canvas, nodes, edges, order, cellColor(edge, row, col), tooltipFor(from, into, row, col) }
   `order` is the topological node order from the payload: with it, every
   ordinary import lands above the diagonal and anything below is a back-edge. */
function createMatrix(opts) {
  const { canvas, nodes, edges } = opts;
  const n = nodes.length;
  const order = opts.order && opts.order.length === n ? opts.order : nodes.map((_, i) => i);
  const rank = new Map(order.map((idx, i) => [idx, i]));
  let cs = 0, ox = 0;

  canvas.addEventListener("mousemove", (ev) => {
    if (!cs) return;
    const box = canvas.getBoundingClientRect();
    const c = Math.floor((ev.clientX - box.left - ox) / cs);
    const r = Math.floor((ev.clientY - box.top) / cs);
    if (r < 0 || c < 0 || r >= n || c >= n) return hideTip();
    showTip(opts.tooltipFor(nodes[order[r]], nodes[order[c]], r, c), ev);
  });
  canvas.addEventListener("mouseleave", hideTip);

  function render() {
    const fit = fitCanvas(canvas);
    if (!fit) return;
    const { ctx, w, h } = fit;
    if (!n) return noData(ctx, "no modules found");
    const side = Math.min(w, h) - 2;
    cs = side / n;
    ox = (w - side) / 2;

    ctx.fillStyle = "rgba(255,255,255,.035)";
    ctx.fillRect(ox, 0, side, side);
    ctx.fillStyle = "rgba(255,255,255,.07)";        // every 10th row/column
    for (let i = 10; i < n; i += 10) {
      ctx.fillRect(ox, i * cs, side, 0.6);
      ctx.fillRect(ox + i * cs, 0, 0.6, side);
    }
    ctx.strokeStyle = "rgba(255,255,255,.18)";
    ctx.beginPath(); ctx.moveTo(ox, 0); ctx.lineTo(ox + side, side); ctx.stroke();

    edges.forEach((e) => {
      const r = rank.get(e.s), c = rank.get(e.t);
      if (r === undefined || c === undefined) return;
      ctx.fillStyle = opts.cellColor(e, r, c);
      ctx.fillRect(ox + c * cs, r * cs, Math.max(1.2, cs - 0.4), Math.max(1.2, cs - 0.4));
    });
  }
  return { render };
}

/* ------------------------------------------------------------ sorted table */
function sortableTable(tableId, columns, rows, initial) {
  const table = $(tableId);
  let key = initial, desc = true, visible = rows;
  table.querySelector("thead").innerHTML = "<tr>" +
    columns.map((c) => `<th data-k="${c.k}" title="${c.t || c.h}">${c.h}</th>`).join("") + "</tr>";
  function paint() {
    const sorted = [...visible].sort((a, b) => {
      const x = a[key], y = b[key];
      const cmp = typeof x === "string" ? x.localeCompare(y) : x - y;
      return desc ? -cmp : cmp;
    });
    table.querySelector("tbody").innerHTML = sorted.map((row) => "<tr>" +
      columns.map((c) => `<td class="${c.flag ? c.flag(row) : ""}">${c.f ? c.f(row) : row[c.k]}</td>`).join("") +
      "</tr>").join("");
    table.querySelectorAll("thead th").forEach((th) => th.classList.toggle("on", th.dataset.k === key));
  }
  table.querySelector("thead").addEventListener("click", (ev) => {
    const th = ev.target.closest("th");
    if (!th) return;
    if (th.dataset.k === key) desc = !desc; else { key = th.dataset.k; desc = true; }
    paint();
  });
  paint();
  return { filter: (pred) => { visible = rows.filter(pred); paint(); return visible.length; } };
}

/* Canvases need layout, so draw after first paint and on (debounced) resize.
   Kicked off from DOMContentLoaded rather than load: `load` waits on every
   subresource, including the brand font, which may never arrive offline.
   render() is idempotent, so the extra pass on `load` just re-fits. */
function scheduleRenders(renderers) {
  const renderAll = () => renderers.forEach((r) => r && r.render());
  const kick = () => requestAnimationFrame(renderAll);
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", kick);
  else kick();
  addEventListener("load", renderAll);
  let timer = null;
  addEventListener("resize", () => {
    clearTimeout(timer);
    timer = setTimeout(renderAll, 250);
  });
}
