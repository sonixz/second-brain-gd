// The live graph in the hero: a tiny Second Brain that runs in this page.
// Places are rings, notes are dots. Type a thought: it blooms by the capture
// bar, a toy archivist files it in the place it shares the most words with,
// links it to its neighbours and shows a receipt with Undo. Nothing is sent:
// in the app the Archivist files by meaning with AI.
// Adapted from the PYF Studio landing (studio-site/assets/brain.js), same author.
(function () {
  "use strict";
  var canvas = document.getElementById("brain-demo");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var frame = canvas.parentNode;
  var receipt = document.getElementById("live-receipt");
  var form = document.getElementById("live-capture");
  var input = document.getElementById("live-in");
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Places as in the showcase Brain; keywords stand in for the Archivist's understanding.
  var PLACES = [
    { name: "Inbox", kw: [] },
    { name: "Kitchen renovation", kw: ["kitchen", "countertop", "counter", "quartz", "granite", "cabinet", "cabinets", "sink", "tiles", "tile", "paint", "renovation", "reno", "contractor", "oven", "fridge", "floor"] },
    { name: "Learn Japanese", kw: ["japanese", "japan", "kanji", "hiragana", "katakana", "tokyo", "kyoto", "anki", "flashcards", "vocabulary", "grammar", "lesson", "sensei", "nihongo"] },
    { name: "Health", kw: ["sleep", "run", "running", "doctor", "dentist", "workout", "health", "walk", "yoga", "gym", "steps", "water", "stretch", "meditation", "vitamin"] },
    { name: "Recipes", kw: ["recipe", "recipes", "soup", "chicken", "bread", "dinner", "lunch", "cook", "cooking", "pasta", "sauce", "grocery", "groceries", "curry", "salad", "ramen", "sourdough"] },
    { name: "Reading", kw: ["book", "books", "article", "read", "reading", "podcast", "paper", "novel", "author", "chapter", "essay", "blog"] }
  ];
  var NOTES = [
    ["Quartz or granite?", 1], ["Cabinet quotes", 1], ["Sink and faucet", 1], ["Floor tiles samples", 1],
    ["Kanji: 30 a week", 2], ["Hiragana chart", 2], ["Anki deck", 2], ["Kyoto trip phrases", 2],
    ["Sleep log", 3], ["Morning walk", 3], ["Dentist in March", 3],
    ["Chicken curry", 4], ["Sourdough starter", 4], ["Weekly groceries", 4],
    ["Building a Second Brain", 5], ["Article: PARA method", 5],
    ["Voice memo from the car", 0], ["Screenshot to sort", 0]
  ];

  var W = 0, H = 0, dpr = 1, nodes = [], edges = [], pal = {}, hover = null, drag = null, raf = 0, visible = true, last = 0;
  var hideTimer = 0, lastCapture = null;

  function rnd(i) { var x = Math.sin(i * 99.13 + 7.7) * 43758.5; return x - Math.floor(x); }
  function words(s) {
    return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").split(/[^a-z0-9]+/)
      .filter(function (w) { return w.length > 2 && STOP.indexOf(w) < 0; });
  }
  var STOP = ["the", "and", "for", "with", "this", "that", "from", "into", "about", "what", "our", "your", "you", "are", "was", "but", "not", "all", "get", "one", "two"];

  function readPalette() {
    var cs = getComputedStyle(document.documentElement);
    pal = { ink: cs.getPropertyValue("--text").trim() || "#f1f6fc", mint: cs.getPropertyValue("--mint").trim() || "#a9d4ff",
      warm: cs.getPropertyValue("--warm").trim() || "#ffd2a1", node: cs.getPropertyValue("--forest-light").trim() || "#79a5d3",
      bg: cs.getPropertyValue("--bg").trim() || "#2b3c54" };
  }
  function rgba(hex, a) { var n = parseInt(hex.replace("#", ""), 16); return "rgba(" + (n >> 16 & 255) + "," + (n >> 8 & 255) + "," + (n & 255) + "," + a + ")"; }

  // ---------- graph ----------
  var CX = .5, CY = .38;
  function build() {
    nodes = []; edges = [];
    PLACES.forEach(function (p, i) {
      var a = i === 0 ? 0 : (i - 1) / (PLACES.length - 1) * Math.PI * 2 - Math.PI / 2;
      var d = i === 0 ? 0 : 1;
      nodes.push({ name: p.name, hub: true, place: i, x: CX + Math.cos(a) * .28 * d, y: CY + Math.sin(a) * .26 * d, vx: 0, vy: 0, r: i === 0 ? 13 : 11, born: -1e9 });
    });
    NOTES.forEach(function (n, i) {
      var h = nodes[n[1]], a = rnd(i) * 6.28;
      nodes.push({ name: n[0], hub: false, place: n[1], x: h.x + Math.cos(a) * .07, y: h.y + Math.sin(a) * .08, vx: 0, vy: 0, r: 4.5, warm: rnd(i + 50) < .3, born: -1e9 });
      edges.push([nodes[nodes.length - 1], h]);
    });
    // a few links across places, as the Archivist finds them by meaning
    [[4, 13], [14, 15], [10, 11], [0, 3]].forEach(function (l) { edges.push([nodes[PLACES.length + l[0]], nodes[PLACES.length + l[1]]]); });
  }

  // The toy archivist: the place whose keywords and notes share the most words wins.
  function file(text) {
    var w = words(text), best = 0, score = 0, tag = "";
    PLACES.forEach(function (p, i) {
      if (!i) return;
      var s = 0, t = "";
      w.forEach(function (x) {
        var hit = p.kw.indexOf(x) >= 0 || p.kw.some(function (k) { return k.length > 4 && x.indexOf(k) === 0; });
        if (hit) { s += 2; if (!t) t = x; }
      });
      nodes.forEach(function (n) { if (!n.hub && n.place === i && words(n.name).some(function (x) { return w.indexOf(x) >= 0; })) s += 1; });
      if (s > score) { score = s; best = i; tag = t; }
    });
    return { place: best, tag: tag || (w[0] || "") };
  }

  function capture(text) {
    text = text.trim(); if (!text) return;
    var f = file(text), hub = nodes[f.place], w = words(text);
    var n = { name: text.length > 28 ? text.slice(0, 27) + "…" : text, hub: false, place: f.place, mine: true, warm: true, r: 5.5,
      x: .5 + (Math.random() - .5) * .04, y: .68, vx: 0, vy: 0, born: performance.now() };
    nodes.push(n);
    var made = [[n, hub]], links = 0;
    nodes.forEach(function (o) {
      if (o === n || o.hub || links >= 2) return;
      if (words(o.name).some(function (x) { return w.indexOf(x) >= 0; })) { made.push([n, o]); links++; }
    });
    made.forEach(function (e) { edges.push(e); });
    lastCapture = { node: n, edges: made };
    hover = n;
    showReceipt(f, links, text);
    kick();
  }

  function undo() {
    if (!lastCapture) return;
    var c = lastCapture; lastCapture = null;
    nodes.splice(nodes.indexOf(c.node), 1);
    edges = edges.filter(function (e) { return c.edges.indexOf(e) < 0; });
    if (hover === c.node) hover = null;
    receipt.innerHTML = '<span class="r-kind">Undone</span><span class="r-main">Nothing kept.</span>';
    clearTimeout(hideTimer); hideTimer = setTimeout(function () { receipt.hidden = true; }, 2000);
    kick();
  }

  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function showReceipt(f, links, text) {
    var inbox = f.place === 0;
    receipt.innerHTML = (inbox
      ? '<span class="r-kind wait">In the Inbox · waiting</span><span class="r-main">Not sure where this goes. The Archivist would ask you.</span>'
      : '<span class="r-kind">Filed</span><span class="r-main">' + esc(PLACES[f.place].name) + '</span>') +
      '<span class="r-meta">' + (f.tag ? "#" + esc(f.tag) + " · " : "") + (links + 1) + (links ? " links" : " link") + "</span>" +
      '<button type="button" class="r-undo">Undo</button>';
    receipt.hidden = false;
    receipt.querySelector(".r-undo").addEventListener("click", undo);
    clearTimeout(hideTimer); hideTimer = setTimeout(function () { receipt.hidden = true; }, 7000);
  }

  // ---------- physics ----------
  function step(dt) {
    var k = Math.min(dt, .05) * 60, i, j;
    for (i = 0; i < nodes.length; i++) {
      var A = nodes[i];
      for (j = i + 1; j < nodes.length; j++) {
        var B = nodes[j], dx = A.x - B.x, dy = (A.y - B.y) * 1.4, d2 = dx * dx + dy * dy + .0005, f = .000035 / d2;
        if (A.hub && B.hub) f *= 5;
        A.vx += dx * f; A.vy += dy * f; B.vx -= dx * f; B.vy -= dy * f;
      }
    }
    edges.forEach(function (e) {
      var A = e[0], B = e[1], dx = B.x - A.x, dy = B.y - A.y, d = Math.sqrt(dx * dx + dy * dy) + 1e-6,
        rest = A.hub || B.hub ? .085 : .12, f = (d - rest) * .09;
      A.vx += dx / d * f; A.vy += dy / d * f; B.vx -= dx / d * f; B.vy -= dy / d * f;
    });
    var t = performance.now() / 3000;
    nodes.forEach(function (n, idx) {
      if (n === drag) { n.vx = n.vy = 0; return; }
      n.vx += (CX - n.x) * .003 + (still ? 0 : Math.sin(t + idx) * .00003);
      n.vy += (CY - n.y) * .004;
      n.vx *= .86; n.vy *= .86; n.x += n.vx * k; n.y += n.vy * k;
      n.x = Math.max(.06, Math.min(.94, n.x)); n.y = Math.max(.07, Math.min(.68, n.y));
    });
  }

  // ---------- drawing ----------
  function neighbour(n) { return hover && edges.some(function (e) { return (e[0] === hover && e[1] === n) || (e[1] === hover && e[0] === n); }); }
  function draw(now) {
    ctx.clearRect(0, 0, W, H);
    edges.forEach(function (e) {
      var A = e[0], B = e[1], lit = hover && (A === hover || B === hover);
      ctx.strokeStyle = rgba(lit ? pal.mint : pal.node, lit ? .9 : .4); ctx.lineWidth = lit ? 1.8 : 1;
      ctx.beginPath(); ctx.moveTo(A.x * W, A.y * H); ctx.lineTo(B.x * W, B.y * H); ctx.stroke();
    });
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    nodes.forEach(function (n) {
      // rAF's timestamp can be a little older than performance.now() at capture: never a negative age
      var x = n.x * W, y = n.y * H, r = n.r, age = Math.max(0, (now - n.born) / 1000);
      if (age < 2.2) {   // the bloom
        var q = age / 2.2;
        ctx.strokeStyle = rgba(pal.warm, (1 - q) * .8); ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(x, y, r + q * 46, 0, 7); ctx.stroke();
        r *= .4 + .6 * Math.min(1, q * 3);
      }
      if (n.hub) {
        var g = ctx.createRadialGradient(x, y, r * .6, x, y, r * 2.8); g.addColorStop(0, rgba(pal.node, .3)); g.addColorStop(1, rgba(pal.node, 0));
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r * 2.8, 0, 7); ctx.fill();
        ctx.strokeStyle = rgba(n.place === 0 ? pal.warm : pal.mint, .95); ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fillStyle = rgba(pal.bg, .7); ctx.fill(); ctx.stroke();
      } else {
        var c = n.warm ? pal.warm : pal.mint;
        var gl = ctx.createRadialGradient(x, y, 0, x, y, r * 3); gl.addColorStop(0, rgba(c, .35)); gl.addColorStop(1, rgba(c, 0));
        ctx.fillStyle = gl; ctx.beginPath(); ctx.arc(x, y, r * 3, 0, 7); ctx.fill();
        ctx.fillStyle = c; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
      }
    });
    // Labels last, with a halo, so dots never cover them. Places always; a note when
    // it is hovered, just captured, or next to the hovered one.
    ctx.lineJoin = "round"; ctx.lineWidth = 3.5; ctx.strokeStyle = rgba(pal.bg, .85);
    var fresh = lastCapture && lastCapture.node;
    nodes.forEach(function (n) {
      var strong = n.hub || n === hover || n === fresh;
      if (!strong && !neighbour(n)) return;
      ctx.font = (n.hub ? "600 12.5px " : "400 11.5px ") + "'Segoe UI Variable Text', 'Segoe UI', Ubuntu, sans-serif";
      var x = n.x * W, y = n.y * H + n.r + 4;
      ctx.strokeText(n.name, x, y);
      ctx.fillStyle = rgba(pal.ink, strong ? .95 : .7);
      ctx.fillText(n.name, x, y);
    });
  }

  // ---------- size, input, loop ----------
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw(performance.now());
  }
  function at(e) { var r = canvas.getBoundingClientRect(); return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]; }
  function pick(p) {
    var best = null, bd = 1e9;
    nodes.forEach(function (n) { var d = Math.hypot((n.x - p[0]) * W, (n.y - p[1]) * H); if (d < n.r + 10 && d < bd) { bd = d; best = n; } });
    return best;
  }
  canvas.addEventListener("pointermove", function (e) {
    var p = at(e);
    if (drag) { drag.x = p[0]; drag.y = p[1]; kick(); return; }
    var n = pick(p); canvas.style.cursor = n ? "grab" : "default";
    if (n !== hover) { hover = n; kick(); }
  });
  canvas.addEventListener("pointerleave", function () { if (!drag && hover) { hover = null; kick(); } });
  canvas.addEventListener("pointerdown", function (e) { var n = pick(at(e)); if (n) { drag = n; hover = n; canvas.setPointerCapture(e.pointerId); canvas.style.cursor = "grabbing"; } });
  canvas.addEventListener("pointerup", function () { drag = null; kick(); });
  form.addEventListener("submit", function (e) { e.preventDefault(); capture(input.value); input.value = ""; });
  Array.prototype.forEach.call(frame.parentNode.querySelectorAll("[data-try]"), function (b) {
    b.addEventListener("click", function () { capture(b.getAttribute("data-try")); });
  });

  function loop(now) {
    raf = 0; step((now - last) / 1000); last = now; draw(now);
    if (visible && !document.hidden) raf = requestAnimationFrame(loop);
  }
  function start() { if (!raf && visible && !document.hidden) { last = performance.now(); raf = requestAnimationFrame(loop); } }
  // With reduced motion, settle at once and redraw only on interaction.
  function kick() {
    if (!still) { start(); return; }
    for (var s = 0; s < 240; s++) step(.016);
    draw(performance.now() + 1e6);
  }
  if ("IntersectionObserver" in window) new IntersectionObserver(function (es) { visible = es[0].isIntersecting; if (!still) start(); }).observe(canvas);
  document.addEventListener("visibilitychange", function () { if (!still) start(); });
  window.addEventListener("resize", resize);

  readPalette(); build();
  for (var s = 0; s < 300; s++) step(.016);
  resize();
  frame.classList.add("is-live");
  if (!still) start();
})();
