// The hero's background: a tiny Second Brain that runs in this page.
// Places are rings, notes are dots. On its own, it plays a scripted scene of the app at
// work (about 45 s, in a loop): you speak a note, drop a PDF, send a web page, ask the
// Archivist a question, an AI agent proposes a note over MCP, and one capture is too
// vague, so the Archivist asks. The Archivist's panel is its "terminal".
// Type, click « Try it » or drag a dot and it's your turn: the toy archivist files what
// you type in the place it shares the most words with, with a receipt and Undo. The
// scene comes back after a while without you. Nothing is sent: in the app the Archivist
// files by meaning with AI. Same pattern as the Agent Manager GD landing (js/live.js).
// The graph was adapted from the PYF Studio landing (studio-site/assets/brain.js), same author.
(function () {
  "use strict";
  var canvas = document.getElementById("brain-demo");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var log = document.getElementById("a-log");
  var state = document.querySelector(".a-state");
  var pauseBtn = document.querySelector(".a-pause");
  var form = document.getElementById("live-capture");
  var input = document.getElementById("live-in");
  var voice = document.querySelector(".live-voice");
  var said = voice && voice.querySelector(".lv-said");
  var bars = voice ? Array.prototype.slice.call(voice.querySelectorAll(".lv-meter i")) : [];
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Places as in the showcase Brain; keywords stand in for the Archivist's understanding.
  var PLACES = [
    { name: "Inbox", c: "#ffd2a1", kw: [] },
    { name: "Kitchen renovation", c: "#ffc48a", kw: ["kitchen", "countertop", "counter", "quartz", "granite", "cabinet", "cabinets", "sink", "tiles", "tile", "paint", "renovation", "reno", "contractor", "oven", "fridge", "floor", "electrician"] },
    { name: "Learn Japanese", c: "#f3a6c8", kw: ["japanese", "japan", "kanji", "hiragana", "katakana", "tokyo", "kyoto", "anki", "flashcards", "vocabulary", "grammar", "lesson", "sensei", "nihongo"] },
    { name: "Health", c: "#a9f0c7", kw: ["sleep", "run", "running", "doctor", "dentist", "workout", "health", "walk", "yoga", "gym", "steps", "water", "stretch", "meditation", "vitamin"] },
    { name: "Recipes", c: "#ffe08a", kw: ["recipe", "recipes", "soup", "chicken", "bread", "dinner", "lunch", "cook", "cooking", "pasta", "sauce", "grocery", "groceries", "curry", "salad", "ramen", "sourdough"] },
    { name: "Reading", c: "#a9d4ff", kw: ["book", "books", "article", "read", "reading", "podcast", "paper", "novel", "author", "chapter", "essay", "blog"] }
  ];
  // Places of different sizes, as in a real Brain: a big project, a big resource, small corners.
  // Kinds: d = document, w = web page, a = from an agent.
  var NOTES = [
    // Kitchen renovation: the big project
    ["Quartz or granite?", 1], ["Cabinet quotes", 1], ["Sink and faucet", 1], ["Floor tiles samples", 1], ["Paint colours", 1],
    ["Electrician visit", 1], ["Lighting plan", 1], ["Countertop samples", 1], ["Plumber quote", 1, "d"], ["Backsplash ideas", 1, "w"],
    ["Island dimensions", 1], ["Appliance list", 1], ["Range hood", 1, "w"], ["Permit checklist", 1, "d"], ["Contractor schedule", 1],
    ["Budget tracker", 1, "a"],
    // Reading: a big resource
    ["Building a Second Brain", 5], ["Article: PARA method", 5], ["Deep Work, ch. 3", 5], ["Novel to start", 5], ["Essay on memory", 5],
    ["Zettelkasten notes", 5, "w"], ["Paper: spaced repetition", 5, "d"], ["Thinking, Fast and Slow", 5], ["Atomic Habits, ch. 2", 5],
    ["How to Take Smart Notes", 5, "d"], ["Quotes to keep", 5], ["Article: local-first software", 5, "w"],
    // Learn Japanese: a medium project
    ["Kanji: 30 a week", 2], ["Hiragana chart", 2], ["Anki deck", 2], ["Kyoto trip phrases", 2], ["Particles: wa, ga", 2],
    ["Podcast for learners", 2], ["Genki, lesson 7", 2, "d"], ["NHK Easy News", 2, "w"],
    // Recipes, Health, the Inbox: small
    ["Ramen broth", 4], ["Lentil soup", 4], ["Sourdough starter", 4], ["Weekly groceries", 4], ["Dashi stock", 4, "w"],
    ["Sleep log", 3], ["Dentist in March", 3], ["Vitamin D", 3], ["Sleep and memory", 3, "w"],
    ["Voice memo from the car", 0], ["Photo of a whiteboard", 0]
  ];

  var W = 0, H = 0, dpr = 1, nodes = [], edges = [], pal = {}, hover = null, drag = null, raf = 0, visible = true, last = 0;
  var lastCapture = null, flyers = [], glow = null, stars = [], pulses = [], lastPulse = 0, mouse = [.5, .5];

  function rnd(i) { var x = Math.sin(i * 99.13 + 7.7) * 43758.5; return x - Math.floor(x); }
  function words(s) {
    return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").split(/[^a-z0-9]+/)
      .filter(function (w) { return w.length > 2 && STOP.indexOf(w) < 0; });
  }
  var STOP = ["the", "and", "for", "with", "this", "that", "from", "into", "about", "what", "our", "your", "you", "are", "was", "but", "not", "all", "get", "one", "two"];
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function readPalette() {
    var cs = getComputedStyle(document.documentElement);
    pal = { ink: cs.getPropertyValue("--text").trim() || "#f1f6fc", mint: cs.getPropertyValue("--mint").trim() || "#a9d4ff",
      warm: cs.getPropertyValue("--warm").trim() || "#ffd2a1", node: cs.getPropertyValue("--forest-light").trim() || "#79a5d3",
      bg: cs.getPropertyValue("--bg").trim() || "#2b3c54", panel: cs.getPropertyValue("--panel").trim() || "#33475f" };
  }
  function rgba(hex, a) { var n = parseInt(hex.replace("#", ""), 16); return "rgba(" + (n >> 16 & 255) + "," + (n >> 8 & 255) + "," + (n & 255) + "," + a + ")"; }

  // ---------- graph ----------
  // Wide screens: the graph fills the whole hero, a sky behind the content. Each place
  // has its own anchor, spread so rings stay clear of the text, the panel and the bar.
  // Narrow screens: it spreads behind everything, dimmed by CSS.
  var L = {};
  function layout() {
    var wide = (canvas.clientWidth || 0) > 960;
    // k: repulsion, hub / note: spring lengths (in canvas fractions, so the wide hero needs smaller ones)
    L = wide ? { wide: true, cx: .5, cy: .5, x0: .02, x1: .97, y0: .05, y1: .95, rx: .1, ry: .1, k: .000006, hub: .06, note: .06,
                 // Inbox, Kitchen renovation, Learn Japanese, Health, Recipes, Reading
                 anchors: [[.505, .5], [.92, .2], [.06, .52], [.35, .9], [.93, .68], [.085, .18]] }
             : { wide: false, cx: .5, cy: .45, x0: .06, x1: .94, y0: .04, y1: .92, rx: .3, ry: .3, k: .000035, hub: .085, note: .12 };
  }
  function build() {
    layout();
    nodes = []; edges = [];
    PLACES.forEach(function (p, i) {
      var a = i === 0 ? 0 : (i - 1) / (PLACES.length - 1) * Math.PI * 2 - Math.PI / 2;
      var d = i === 0 ? 0 : 1;
      var an = L.anchors && L.anchors[i];
      nodes.push({ name: p.name, hub: true, place: i, x: an ? an[0] : L.cx + Math.cos(a) * L.rx * d, y: an ? an[1] : L.cy + Math.sin(a) * L.ry * d, vx: 0, vy: 0, r: i === 0 ? 13 : 11, born: -1e9 });
    });
    NOTES.forEach(function (n, i) {
      var h = nodes[n[1]], a = rnd(i) * 6.28;
      nodes.push({ name: n[0], hub: false, place: n[1], x: h.x + Math.cos(a) * L.rx * .4, y: h.y + Math.sin(a) * L.ry * .4, vx: 0, vy: 0,
        r: 3.4 + rnd(i + 9) * 2.2, rest: .3 + rnd(i + 21) * .8, warm: rnd(i + 50) < .3, kind: { d: "doc", w: "web", a: "agent" }[n[2]] || "", born: -1e9 });
      edges.push([nodes[nodes.length - 1], h]);
    });
    // a few links across places, as the Archivist finds them by meaning
    [["Kanji: 30 a week", "Anki deck"], ["Building a Second Brain", "Article: PARA method"], ["Sink and faucet", "Plumber quote"],
     ["Quartz or granite?", "Floor tiles samples"]].forEach(function (l) { var a = byName(l[0]), b = byName(l[1]); if (a && b) edges.push([a, b]); });
    // "same idea" pairs across places, drawn dashed: the meaning layer
    [["Sleep and memory", "Paper: spaced repetition"], ["Anki deck", "Paper: spaced repetition"], ["Ramen broth", "Dashi stock"],
     ["Kyoto trip phrases", "NHK Easy News"], ["Building a Second Brain", "Zettelkasten notes"], ["Countertop samples", "Quartz or granite?"]
    ].forEach(function (l) { var a = byName(l[0]), b = byName(l[1]); if (a && b) { var e = [a, b]; e.same = true; edges.push(e); } });
    // and inside each place, its notes linked in a loose chain
    PLACES.forEach(function (p, i) {
      var mine = nodes.filter(function (n) { return !n.hub && n.place === i; });
      for (var k = 1; k < mine.length; k++) if (rnd(k * 7 + i) < .7) { var e = [mine[k - 1], mine[k]]; e.intra = true; edges.push(e); }
    });
    // the sky behind: dust at three depths, drifting slowly
    stars = [];
    for (var k = 0; k < 110; k++) stars.push({ x: rnd(k + 300), y: rnd(k + 700), z: .25 + rnd(k + 900) * .75, tw: rnd(k + 1100) * 6.28 });
    pulses = [];
  }
  function byName(name) { for (var i = 0; i < nodes.length; i++) if (nodes[i].name === name) return nodes[i]; return null; }
  function edgeOf(a, b) { for (var i = 0; i < edges.length; i++) { var e = edges[i]; if ((e[0] === a && e[1] === b) || (e[0] === b && e[1] === a)) return e; } return null; }

  // Where the capture bar sits, in canvas fractions (new captures bloom there).
  function barPoint() {
    var c = canvas.getBoundingClientRect(), f = form.getBoundingClientRect();
    if (!c.width || !c.height) return [L.cx, L.y1];
    return [Math.max(L.x0, Math.min(L.x1, (f.left + f.width * .45 - c.left) / c.width)), Math.max(L.y0, Math.min(L.y1, (f.top - c.top) / c.height))];
  }

  // A new item in the graph: it blooms next to its place (or at « at »), linked to its place and to
  // the named notes. Born beside its hub, it never drags the others across the hero.
  function nearHub(place) { var h = nodes[place], a = Math.random() * 6.28; return [h.x + Math.cos(a) * L.note * .6, h.y + Math.sin(a) * L.note * .6]; }
  function addNode(name, place, at, opt) {
    opt = opt || {};
    at = at || nearHub(place);
    var n = { name: name.length > 30 ? name.slice(0, 29) + "…" : name, hub: false, place: place, warm: true, r: opt.kind ? 6.5 : 5.5,
      kind: opt.kind || "", x: at[0], y: at[1], vx: 0, vy: 0, born: performance.now() + (opt.delay || 0) };
    n[opt.scripted ? "scripted" : "mine"] = true;
    nodes.push(n);
    var made = [[n, nodes[place]]];
    (opt.links || []).forEach(function (o) { if (typeof o === "string") o = byName(o); if (o && o !== n) made.push([n, o]); });
    made.forEach(function (e) { edges.push(e); });
    kick();
    return { node: n, edges: made };
  }
  function removeWhere(test) {
    nodes = nodes.filter(function (n) { return !test(n); });
    edges = edges.filter(function (e) { return !test(e[0]) && !test(e[1]); });
    if (hover && test(hover)) hover = null;
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

  // ---------- the Archivist's panel ----------
  function setState(s) { if (!state) return; state.textContent = "● " + s; state.setAttribute("data-s", s.replace(/[^a-z]/g, "")); }
  // One line in the feed. The scripted scene's lines are hidden from screen readers (they would loop for ever).
  function feed(cls, html, scripted) {
    var el = document.createElement("div");
    el.className = cls + (scripted ? " scripted" : "");
    if (scripted) el.setAttribute("aria-hidden", "true");
    el.innerHTML = html;
    var hello = log.querySelector(".a-say.hello"); if (hello && cls !== "a-say hello") hello.remove();
    log.appendChild(el);
    while (log.children.length > 6) log.removeChild(log.firstElementChild);
    return el;
  }
  function receiptHTML(kind, main, meta, links, wait) {
    return '<span class="r-kind' + (wait ? " wait" : "") + '">' + esc(kind) + '</span><span class="r-main">' + esc(main) + "</span>" +
      (meta ? '<span class="r-meta">' + esc(meta) + "</span>" : "") +
      (links && links.length ? '<span class="r-links">' + links.map(function (l) { return "<span>" + esc(l) + "</span>"; }).join("") + "</span>" : "");
  }

  // Your own capture (it's your turn).
  function capture(text) {
    text = text.trim(); if (!text) return;
    var f = file(text), w = words(text), links = [];
    nodes.forEach(function (o) {
      if (o.hub || links.length >= 2) return;
      if (words(o.name).some(function (x) { return w.indexOf(x) >= 0; })) links.push(o);
    });
    var to = nearHub(f.place);
    fly("note", text, barPoint(), to, 750);
    var c = addNode(text, f.place, to, { links: links, delay: still ? 0 : 750 });
    lastCapture = c;
    hover = c.node;
    showReceipt(f, links.length);
    setState("filing…");
    setTimeout(function () { if (!running) setState("ready"); }, 900);
  }
  function undo(btn) {
    if (!lastCapture) return;
    var c = lastCapture; lastCapture = null;
    removeWhere(function (n) { return n === c.node; });
    var card = btn.parentNode;
    card.innerHTML = '<span class="r-kind">Undone</span><span class="r-main">Nothing kept.</span>';
    card.classList.add("old");
    kick();
  }
  function showReceipt(f, links) {
    Array.prototype.forEach.call(log.querySelectorAll(".a-receipt"), function (o) {
      o.classList.add("old"); var u = o.querySelector(".r-undo"); if (u) u.remove();
    });
    var inbox = f.place === 0;
    var card = feed("a-receipt", (inbox
      ? '<span class="r-kind wait">In the Inbox · waiting</span><span class="r-main">Not sure where this goes. I would ask you.</span>'
      : '<span class="r-kind">Filed</span><span class="r-main">' + esc(PLACES[f.place].name) + '</span>') +
      '<span class="r-meta">' + (f.tag ? "#" + esc(f.tag) + " · " : "") + (links + 1) + (links ? " links" : " link") + "</span>" +
      '<button type="button" class="r-undo">Undo</button>');
    card.querySelector(".r-undo").addEventListener("click", function () { undo(this); });
  }

  // ---------- the scripted scene ----------
  var running = false, cycle = 0, timers = [], userPaused = false, yourTurn = false, idleTimer = 0, inView = true, meterTimer = 0;
  var STOPPED = {};
  function wait(ms) { return new Promise(function (r) { timers.push(setTimeout(r, ms)); }); }
  function stepper(my) {   // each await checks the scene is still the one playing
    return function (ms) { return wait(ms).then(function () { if (!running || my !== cycle) throw STOPPED; }); };
  }
  function typeInto(set, text, ms, w) {
    var i = 0;
    function next() { if (i >= text.length) return Promise.resolve(); i++; set(text.slice(0, i)); return w(ms).then(next); }
    return next();
  }
  // Something arriving from outside: a file dropped, an agent's proposal. Drawn on the canvas.
  function fly(kind, label, a, b, ms, w) {
    if (!still) { flyers.push({ kind: kind, label: label.length > 30 ? label.slice(0, 29) + "…" : label, a: a, b: b, t0: performance.now(), dur: ms }); start(); }
    return w ? w(still ? 0 : ms) : null;
  }
  function lightPath(list) {
    var es = [];
    for (var i = 0; i + 1 < list.length; i++) { var e = edgeOf(list[i], list[i + 1]); if (e) es.push(e); }
    glow = { nodes: list, edges: es, t0: performance.now() };
    kick();
  }
  function meter(on, warm) {
    clearInterval(meterTimer);
    if (!voice) return;
    voice.classList.toggle("on", on);
    if (on && !still) meterTimer = setInterval(function () { bars.forEach(function (b) { b.style.height = (18 + Math.random() * 82) + "%"; }); }, 120);
  }
  function resetScene() {
    removeWhere(function (n) { return n.scripted || n.mine; });
    flyers = []; glow = null; lastCapture = null; hover = null;
    meter(false); if (said) said.textContent = "";
    input.value = "";
    log.innerHTML = "";
    kick();
  }

  function play(my) {
    var w = stepper(my);
    resetScene();
    log.setAttribute("aria-live", "off");
    setState("ready");
    var hub = function (i) { return nodes[i]; };
    var at = function (n) { return [n.x, n.y]; };
    var s;
    return Promise.resolve()
      // 0. hello
      .then(function () { s = feed("a-say", "", true); return typeInto(function (t) { s.textContent = t; }, "Hello. " + (NOTES.length) + " notes in " + PLACES.length + " places. Speak, drop a file, send a page or ask me anything.", 18, w); })
      .then(function () { return w(900); })
      // 1. you speak (F8): the words come as you say them, then a task is filed
      .then(function () {
        setState("listening"); meter(true); said.textContent = "";
        var ws = "Remind me to call the electrician on Tuesday".split(" "), k = 0;
        function next() { if (k >= ws.length) return Promise.resolve(); said.textContent += (k ? " " : "") + ws[k++]; return w(230).then(next); }
        return next();
      })
      .then(function () { return w(500); })
      .then(function () {
        meter(false);
        feed("a-you", '<span class="k warm">VOICE</span>Remind me to call the electrician on Tuesday', true);
        setState("filing…");
        return w(840);
      })
      .then(function () {
        var to = nearHub(1);
        return fly("note", "Call the electrician · Tue", barPoint(), to, 800, w).then(function () { return to; });
      })
      .then(function (to) {
        addNode("Call the electrician · Tue", 1, to, { scripted: true, links: ["Electrician visit"] });
        feed("a-receipt", receiptHTML("Task · filed", "Kitchen renovation", "due Tuesday · #electrician", ["Electrician visit"]), true);
        setState("ready");
        return w(450).then(function () { return w(450); }).then(function () { return w(1300); });
      })
      // 2. you drop a PDF: it is read, summarised, filed and linked
      .then(function () {
        var to = [hub(1).x - .03, hub(1).y + .12];
        feed("a-you", '<span class="k">FILE</span>countertop-quote.pdf', true);
        return fly("pdf", "countertop-quote.pdf", [1.04, .08], to, 1300, w).then(function () { return to; });
      })
      .then(function (to) {
        setState("reading");
        s = feed("a-progress", '<span><span class="k">PDF</span>Reading 3 pages…</span><span class="bar"><i></i></span>', true);
        var bar = s.querySelector("i"), p = 0;
        function next() { if (p >= 100) return Promise.resolve(to); p += 20; bar.style.width = p + "%"; return w(260).then(next); }
        return next();
      })
      .then(function (to) {
        setState("linking");
        addNode("Quartz countertop quote", 1, to, { scripted: true, kind: "doc", links: ["Quartz or granite?", "Cabinet quotes"] });
        s.remove();
        feed("a-receipt", receiptHTML("Document · filed", "Kitchen renovation", "Quartz countertop quote · $4,200", ["Quartz or granite?", "Cabinet quotes"]), true);
        return w(700);
      })
      .then(function () { return w(840); })
      .then(function () { setState("ready"); return w(450); })
      .then(function () { return w(1200); })
      // 3. you paste a web page
      .then(function () { return typeInto(function (t) { input.value = t; }, "https://example.com/tonkotsu-ramen", 28, w); })
      .then(function () { return w(350); })
      .then(function () {
        input.value = "";
        feed("a-you", '<span class="k">LINK</span>example.com/tonkotsu-ramen', true);
        setState("reading");
        return w(600);
      })
      .then(function () {
        var to = nearHub(4);
        return fly("web", "example.com/tonkotsu-ramen", barPoint(), to, 900, w).then(function () { return to; });
      })
      .then(function (to) {
        addNode("Tonkotsu ramen (web)", 4, to, { scripted: true, kind: "web", links: ["Ramen broth"] });
        feed("a-receipt", receiptHTML("Web page · filed", "Recipes", "Tonkotsu ramen · 12 min read", ["Ramen broth"]), true);
        setState("ready");
        return w(450).then(function () { return w(450); }).then(function () { return w(1300); });
      })
      // 4. you ask: the answer follows the links, and cites its notes
      .then(function () { return typeInto(function (t) { input.value = t; }, "What did I decide about the countertop?", 32, w); })
      .then(function () { return w(350); })
      .then(function () {
        input.value = "";
        feed("a-you", '<span class="k">ASK</span>What did I decide about the countertop?', true);
        setState("thinking");
        return w(400);
      })
      .then(function () {
        lightPath([hub(1), byName("Quartz or granite?"), byName("Quartz countertop quote")]);
        s = feed("a-say", "", true);
        return typeInto(function (t) { s.textContent = t; }, "Quartz. You chose it in « Quartz or granite? », and the new quote fits the budget: $4,200.", 16, w);
      })
      .then(function () {
        s.insertAdjacentHTML("beforeend", '<span class="r-links"><span>Quartz or granite?</span><span>Quartz countertop quote</span></span>');
        setState("ready");
        return w(760).then(function () { return w(1800); });
      })
      // 5. an AI agent proposes a note over MCP: the Archivist checks it with your rules and files it
      .then(function () {
        glow = null; kick();
        var to = [hub(1).x + .07, hub(1).y + .1];
        feed("a-you", '<span class="k">MCP</span>Claude Desktop proposes « Quartz vs granite: a comparison »', true);
        setState("checking");
        return fly("mcp", "✦ Claude Desktop · MCP", [.5, -.06], to, 1500, w).then(function () { return to; });
      })
      .then(function (to) {
        addNode("Quartz vs granite (table)", 1, to, { scripted: true, kind: "agent", links: ["Quartz or granite?", "Quartz countertop quote"] });
        feed("a-receipt", receiptHTML("Proposal · approved by your rules", "Kitchen renovation", "from Claude Desktop · a table", ["Quartz or granite?", "Quartz countertop quote"]), true);
        setState("ready");
        return w(800).then(function () { return w(1600); });
      })
      // 6. too vague to file: it waits in the Inbox, and the Archivist asks you
      .then(function () { return typeInto(function (t) { input.value = t; }, "Gift idea for Mom", 40, w); })
      .then(function () { return w(350); })
      .then(function () {
        input.value = "";
       
        var to = nearHub(0);
        return fly("note", "Gift idea for Mom", barPoint(), to, 800, w).then(function () { return to; });
      })
      .then(function (to) {
        addNode("Gift idea for Mom", 0, to, { scripted: true });
        s = feed("a-receipt", receiptHTML("In the Inbox · asking you", "Gift idea for Mom: where should it go?", "", null, true) +
          '<span class="a-choices"><button type="button" tabindex="-1">New place: Gifts</button><button type="button" tabindex="-1">Keep in the Inbox</button></span>', true);
        setState("waiting for you");
        return w(1800);
      })
      .then(function () { s.querySelector(".a-choices button").classList.add("on"); return w(900); })
      .then(function () { feed("a-say", "Done: a new place, Gifts. I'll file the next ones there.", true); setState("ready"); return w(3400); })
      .then(function () { if (running && my === cycle) return play(my); })
      .catch(function (e) { if (e !== STOPPED) throw e; });
  }

  function startScene() {
    if (running || userPaused || yourTurn || !inView || document.hidden) return;
    running = true; cycle++; updateBtn(); play(cycle);
  }
  function stopScene() {
    running = false; cycle++; timers.forEach(clearTimeout); timers = []; meter(false); flyers = []; updateBtn();
  }
  function updateBtn() {
    if (!pauseBtn) return;
    pauseBtn.hidden = false;
    var playing = running && !yourTurn;
    pauseBtn.textContent = playing ? "❚❚" : "▶";
    pauseBtn.setAttribute("aria-pressed", String(!playing));
    pauseBtn.setAttribute("aria-label", playing ? "Pause the scene" : "Play the scene");
    pauseBtn.title = playing ? "Pause the scene" : (yourTurn ? "Replay the scene" : "Play the scene");
  }
  // The visitor takes over: the scene stops and the toy archivist is theirs.
  function yourTurnNow() {
    if (!yourTurn) {
      yourTurn = true; stopScene(); resetScene(); setState("ready");
      log.setAttribute("aria-live", "polite");
      feed("a-say hello", "Your turn. Tell me anything: I'll file it and link it.");
      updateBtn();
    }
    clearTimeout(idleTimer);
    idleTimer = setTimeout(function back() {   // the scene comes back after a quiet minute
      if (document.activeElement === input || input.value) { idleTimer = setTimeout(back, 20000); return; }
      yourTurn = false; startScene(); updateBtn();
    }, 60000);
  }
  if (pauseBtn) pauseBtn.addEventListener("click", function () {
    if (yourTurn) { clearTimeout(idleTimer); yourTurn = false; userPaused = false; startScene(); }
    else if (running) { userPaused = true; stopScene(); setState("paused"); }
    else { userPaused = false; startScene(); }
    updateBtn();
  });
  input.addEventListener("focus", yourTurnNow);
  input.addEventListener("input", yourTurnNow);

  // ---------- physics ----------
  function step(dt) {
    var k = Math.min(dt, .05) * 60, i, j;
    for (i = 0; i < nodes.length; i++) {
      var A = nodes[i];
      for (j = i + 1; j < nodes.length; j++) {
        var B = nodes[j], dx = A.x - B.x, dy = (A.y - B.y) * 1.4, d2 = dx * dx + dy * dy + .0005, f = L.k / d2;
        if (A.hub && B.hub) f *= 5;
        else if (d2 > .03) continue;            // notes only feel their neighbours: other clusters don't blow them into fans
        else if (A.place !== B.place) f *= .4;
        if (!A.hub && !B.hub) f *= .35;   // notes only nudge each other apart
        A.vx += dx * f; A.vy += dy * f; B.vx -= dx * f; B.vy -= dy * f;
      }
    }
    // Links between notes pull nothing: each note keeps its home inside its place's circle (below).
    var t = performance.now() / 1000;
    if (!L.wide !== !((canvas.clientWidth || 0) > 960)) layout();
    nodes.forEach(function (n, idx) {
      if (n === drag) { n.vx = n.vy = 0; return; }
      var an = L.anchors && L.anchors[n.place];
      if (n.hub) {   // a place floats very gently around its anchor
        var ax = an ? an[0] : L.cx, ay = an ? an[1] : L.cy;
        if (!still) { ax += Math.sin(t * .13 + n.place * 1.7) * .01; ay += Math.cos(t * .11 + n.place * 2.3) * .014; }
        n.vx += (ax - n.x) * .05; n.vy += (ay - n.y) * .05;
      } else {        // a note has a home inside its place's circle, and drifts slowly around it
        if (n.oa === undefined) { n.oa = Math.random() * 6.28; n.or = .22 + Math.sqrt(Math.random()) * .55; }
        if (!still) n.oa += (n.place % 2 ? 1 : -1) * .0009 * (.5 + (idx % 4) * .2);
        var h = nodes[n.place], R = zoneR[n.place] || 70;
        var rr = Math.max(15, n.or * R), gx = W ? h.x + Math.cos(n.oa) * rr / W : h.x, gy = H ? h.y + Math.sin(n.oa) * rr / H : h.y;
        n.vx += (gx - n.x) * .02; n.vy += (gy - n.y) * .02;
      }
      n.vx *= .82; n.vy *= .82; n.x += n.vx * k; n.y += n.vy * k;
      n.x = Math.max(L.x0, Math.min(L.x1, n.x)); n.y = Math.max(L.y0, Math.min(L.y1, n.y));
    });
  }
  var zoneR = [];

  // ---------- drawing ----------
  function neighbour(n) { return hover && edges.some(function (e) { return (e[0] === hover && e[1] === n) || (e[1] === hover && e[0] === n); }); }
  function roundRect(x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function drawFlyer(f, now) {
    var q = Math.min(1, (now - f.t0) / f.dur), e = 1 - Math.pow(1 - q, 3);
    var x = (f.a[0] + (f.b[0] - f.a[0]) * e) * W, y = (f.a[1] + (f.b[1] - f.a[1]) * e - Math.sin(e * Math.PI) * .05) * H;
    ctx.save();
    ctx.globalAlpha = q > .85 ? (1 - q) / .15 : 1;
    ctx.font = "600 12px 'Segoe UI Variable Text', 'Segoe UI', Ubuntu, sans-serif";
    var small = f.kind === "note" || f.kind === "web";
    if (small) ctx.font = "500 11.5px 'Segoe UI Variable Text', 'Segoe UI', Ubuntu, sans-serif";
    var tw = ctx.measureText(f.label).width, pdf = f.kind === "pdf", w = tw + (pdf ? 50 : 26), h = pdf ? 38 : small ? 24 : 28;
    ctx.translate(x - w / 2, y - h / 2);
    ctx.shadowColor = "rgba(5,12,24,.55)"; ctx.shadowBlur = 18; ctx.shadowOffsetY = 6;
    roundRect(0, 0, w, h, pdf ? 9 : h / 2); ctx.fillStyle = rgba(pal.panel, .96); ctx.fill();
    ctx.shadowColor = "transparent";
    ctx.strokeStyle = rgba(f.kind === "mcp" ? pal.mint : pal.warm, .9); ctx.lineWidth = 1.3; ctx.stroke();
    ctx.textBaseline = "middle"; ctx.textAlign = "left";
    if (pdf) {   // a little page with a folded corner
      ctx.fillStyle = rgba(pal.warm, .95);
      ctx.beginPath(); ctx.moveTo(10, 8); ctx.lineTo(22, 8); ctx.lineTo(28, 14); ctx.lineTo(28, 30); ctx.lineTo(10, 30); ctx.closePath(); ctx.fill();
      ctx.fillStyle = rgba(pal.panel, 1); ctx.font = "700 6.5px sans-serif"; ctx.fillText("PDF", 11.5, 23);
      ctx.font = "600 12px 'Segoe UI Variable Text', 'Segoe UI', Ubuntu, sans-serif";
      ctx.fillStyle = pal.ink; ctx.fillText(f.label, 38, h / 2);
    } else { ctx.fillStyle = pal.ink; ctx.fillText(f.label, 13, h / 2 + .5); }
    ctx.restore();
  }
  function placeColour(n) { return PLACES[n.place] ? PLACES[n.place].c : pal.mint; }
  // As in the app: each place is a clear circle with its ring in the middle and its name and count above;
  // notes are small squares inside; links run between notes only. Behind: a few stars and a pale planet.
  function counts(now) {
    var c = PLACES.map(function () { return 0; });
    nodes.forEach(function (n) { if (!n.hub && now >= n.born && c[n.place] !== undefined) c[n.place]++; });
    return c;
  }
  // ---------- the constellation behind everything ----------
  // A web of stars, each linked to its nearest neighbours, drifting slowly: a picture of a meaning
  // database. Signals hop from star to star along the links, a star lights up when one arrives, and
  // now and then a signal splits in two, like one idea waking up the next ones.
  var sky = { stars: [], links: [], adj: [], signals: [], last: 0, w: 0, h: 0 };
  function buildSky() {
    if (!W || !H || (sky.stars.length && Math.abs(sky.w - W) < 60 && Math.abs(sky.h - H) < 60)) return;
    sky.w = W; sky.h = H;
    var n = Math.max(28, Math.min(120, Math.round(W * H / 12500))), cols = Math.max(4, Math.round(Math.sqrt(n * W / H))), rows = Math.ceil(n / cols);
    var st = [], k = 0, i, j;
    for (j = 0; j < rows; j++) for (i = 0; i < cols; i++) {
      k++;
      st.push({ bx: (i + .12 + rnd(k * 3.1) * .76) / cols, by: (j + .12 + rnd(k * 5.7) * .76) / rows, ph: rnd(k * 9.3) * 6.28,
        sp: .5 + rnd(k * 2.2), big: rnd(k * 4.4) < .16, flash: -1e9 });
    }
    var links = [], seen = {}, adj = st.map(function () { return []; }), reach = Math.max(140, Math.min(260, Math.sqrt(W * H / n) * 1.9));
    st.forEach(function (a, ia) {
      var near = st.map(function (b, ib) { return { ib: ib, d: Math.hypot((a.bx - b.bx) * W, (a.by - b.by) * H) }; })
        .filter(function (o) { return o.ib !== ia; }).sort(function (p, q) { return p.d - q.d; });
      var want = a.big ? 4 : 2 + (ia % 2);
      for (var m = 0; m < want && m < near.length && near[m].d < reach; m++) {
        var ib = near[m].ib, key = Math.min(ia, ib) + "-" + Math.max(ia, ib);
        if (seen[key]) continue;
        seen[key] = 1; links.push({ a: ia, b: ib, d: near[m].d, hot: -1e9 });
        adj[ia].push(links.length - 1); adj[ib].push(links.length - 1);
      }
    });
    sky.stars = st; sky.links = links; sky.adj = adj; sky.signals = []; sky.reach = reach;
  }
  function starAt(s0, t) {
    return [(s0.bx + Math.sin(t * .07 * s0.sp + s0.ph) * .007) * W, (s0.by + Math.cos(t * .06 * s0.sp + s0.ph * 1.3) * .01) * H];
  }
  function sendSignal(from, now, hops, col, prevLink) {
    var opts = sky.adj[from].filter(function (li) { return li !== prevLink; });
    if (!opts.length) return;
    var li = opts[Math.floor(Math.random() * opts.length)], L0 = sky.links[li];
    sky.signals.push({ li: li, from: from, to: L0.a === from ? L0.b : L0.a, t0: now, dur: 650 + L0.d * 3.2, hops: hops, col: col });
  }
  function drawSky(now) {
    buildSky();
    ctx.fillStyle = "rgba(255,255,255,.028)"; ctx.beginPath(); ctx.arc(W * .8, H * 1.38, H * 1.02, 0, 7); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,.018)"; ctx.beginPath(); ctx.arc(W * .04, -H * .25, H * .55, 0, 7); ctx.fill();
    var tt = still ? 0 : now / 1000, i;
    for (i = 0; i < stars.length; i++) {   // fine dust
      var du = stars[i], tw = .7 + .3 * Math.sin(tt * (.6 + du.z) + du.tw);
      ctx.fillStyle = rgba(pal.ink, (.06 + .18 * du.z) * tw);
      ctx.beginPath(); ctx.arc(du.x * W, du.y * H, .4 + du.z * .8, 0, 7); ctx.fill();
    }
    var P = sky.stars.map(function (s0) { return starAt(s0, tt); });
    // signals: start a few, move them, hand them on
    if (!still) {
      if (now - sky.last > 520 && sky.signals.length < 10 && sky.stars.length) {
        sky.last = now;
        var from = Math.floor(Math.random() * sky.stars.length);
        sendSignal(from, now, 3 + Math.floor(Math.random() * 4), Math.random() < .22 ? pal.warm : pal.mint, -1);
      }
      sky.signals = sky.signals.filter(function (g) {
        if (now - g.t0 < g.dur) return true;
        sky.stars[g.to].flash = now;
        if (g.hops > 1) {
          sendSignal(g.to, now, g.hops - 1, g.col, g.li);
          if (Math.random() < .22 && sky.signals.length < 14) sendSignal(g.to, now, g.hops - 1, g.col, g.li);   // an idea wakes up two
        }
        return false;
      });
    }
    // links: faint threads, brighter where a signal just passed
    ctx.lineWidth = .8;
    sky.links.forEach(function (l) {
      var a = P[l.a], b = P[l.b], base = .05 + .1 * (1 - l.d / sky.reach), heat = Math.max(0, 1 - (now - l.hot) / 1400);
      ctx.strokeStyle = rgba(pal.mint, base + .28 * heat);
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    });
    // the signals themselves: a light with a short tail
    sky.signals.forEach(function (g) {
      var q = Math.min(1, (now - g.t0) / g.dur), e = q * q * (3 - 2 * q), a = P[g.from], b = P[g.to];
      sky.links[g.li].hot = now;
      for (var k = 4; k >= 0; k--) {
        var qq = Math.max(0, e - k * .035), x = a[0] + (b[0] - a[0]) * qq, y = a[1] + (b[1] - a[1]) * qq;
        if (k) { ctx.fillStyle = rgba(g.col, .28 * (1 - k / 5)); ctx.beginPath(); ctx.arc(x, y, 1.4, 0, 7); ctx.fill(); continue; }
        var gl = ctx.createRadialGradient(x, y, 0, x, y, 9); gl.addColorStop(0, rgba(g.col, .7)); gl.addColorStop(1, rgba(g.col, 0));
        ctx.fillStyle = gl; ctx.beginPath(); ctx.arc(x, y, 9, 0, 7); ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,.95)"; ctx.beginPath(); ctx.arc(x, y, 1.4, 0, 7); ctx.fill();
      }
    });
    // the stars: small points, a few brighter ones, and a flash when a signal lands
    sky.stars.forEach(function (s0, k) {
      var x = P[k][0], y = P[k][1], f = Math.max(0, 1 - (now - s0.flash) / 1100), r = s0.big ? 1.9 : 1.15;
      if (s0.big || f > 0) {
        var R = (s0.big ? 7 : 0) + f * 14, gl = ctx.createRadialGradient(x, y, 0, x, y, R || 1);
        gl.addColorStop(0, rgba(pal.mint, (s0.big ? .22 : 0) + f * .5)); gl.addColorStop(1, rgba(pal.mint, 0));
        ctx.fillStyle = gl; ctx.beginPath(); ctx.arc(x, y, R || 1, 0, 7); ctx.fill();
      }
      ctx.fillStyle = rgba(f > .2 ? "#ffffff" : pal.ink, .45 + .25 * (s0.big ? 1 : 0) + .3 * f);
      ctx.beginPath(); ctx.arc(x, y, r + f * 1.2, 0, 7); ctx.fill();
    });
  }
  function drawZones(now) {
    var c = counts(now), m = Math.min(W, H);
    PLACES.forEach(function (p, i) {
      var h = nodes[i]; if (!h) return;
      var R = Math.max(28, Math.min(10 + 4.4 * c[i], m * .15)), X = h.x * W, Y = h.y * H;   // more notes, a bigger circle
      zoneR[i] = zoneR[i] ? zoneR[i] + (R - zoneR[i]) * .08 : R;
      R = zoneR[i];
      ctx.fillStyle = rgba(pal.mint, .07); ctx.beginPath(); ctx.arc(X, Y, R, 0, 7); ctx.fill();
      ctx.strokeStyle = rgba(p.c, .42); ctx.lineWidth = 1.2; ctx.stroke();
    });
  }
  // Lights: small sparks running along the links, between places and between notes, the Brain at work.
  function drawLights(now) {
    if (still) return;
    if (now - lastPulse > 420 && pulses.length < 6 && edges.length) {
      lastPulse = now;
      var pool = edges.filter(function (e) { return (e.intra || e.same) && now >= e[0].born && now >= e[1].born; });
      var e = pool[Math.floor(Math.random() * pool.length)];
      if (e) pulses.push({ e: e, t0: now, dur: 1500 + Math.random() * 1400, back: Math.random() < .5 });
    }
    pulses = pulses.filter(function (p) { return now - p.t0 < p.dur && nodes.indexOf(p.e[0]) >= 0 && nodes.indexOf(p.e[1]) >= 0; });
    pulses.forEach(function (p) {
      var q = (now - p.t0) / p.dur, e = p.e, x1, y1, x2, y2;
      x1 = e[0].x * W; y1 = e[0].y * H; x2 = e[1].x * W; y2 = e[1].y * H;
      if (p.back) { var tx = x1, ty = y1; x1 = x2; y1 = y2; x2 = tx; y2 = ty; }
      var c = e.same ? pal.mint : placeColour(e[0]);
      var fade = Math.sin(q * Math.PI);
      for (var k = 3; k >= 0; k--) {   // a short tail
        var qq = Math.max(0, q - k * .025), x = x1 + (x2 - x1) * qq, y = y1 + (y2 - y1) * qq;
        if (k === 0) {
          var g = ctx.createRadialGradient(x, y, 0, x, y, 8); g.addColorStop(0, rgba(c, .75 * fade)); g.addColorStop(1, rgba(c, 0));
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 8, 0, 7); ctx.fill();
          ctx.fillStyle = rgba("#ffffff", .9 * fade); ctx.beginPath(); ctx.arc(x, y, 1.5, 0, 7); ctx.fill();
        } else { ctx.fillStyle = rgba(c, .35 * fade * (1 - k / 4)); ctx.beginPath(); ctx.arc(x, y, 1.6, 0, 7); ctx.fill(); }
      }
    });
  }
  function draw(now) {
    ctx.clearRect(0, 0, W, H);
    drawSky(now);
    drawZones(now);
    var lit = glow ? glow.edges : [];
    edges.forEach(function (e) {
      var A = e[0], B = e[1], on = hover && (A === hover || B === hover), path = lit.indexOf(e) >= 0;
      if ((A.hub || B.hub) && !path && !on) return;   // no spokes: the circle says where a note belongs
      if (now < A.born || now < B.born) return;
      var len = Math.hypot((B.x - A.x) * W, (B.y - A.y) * H), fade = Math.max(.25, Math.min(1, 1.15 - len / (W * .55)));   // long links stay discreet
      ctx.strokeStyle = path ? rgba(pal.warm, .95) : on ? rgba(pal.mint, .9) : rgba(pal.mint, (e.same ? .24 : e.intra ? .34 : .3) * fade);
      ctx.lineWidth = path ? 2.2 : on ? 1.6 : 1;
      ctx.beginPath(); ctx.moveTo(A.x * W, A.y * H); ctx.lineTo(B.x * W, B.y * H); ctx.stroke();
    });
    drawLights(now);
    if (glow && glow.nodes.length > 1 && !still) {   // a spark travelling the answer's path
      var segs = glow.nodes.length - 1, u = ((now - glow.t0) / 650) % (segs + .6);
      if (u < segs) {
        var i0 = Math.floor(u), fr = u - i0, P = glow.nodes[i0], Q = glow.nodes[i0 + 1];
        if (P && Q) { ctx.fillStyle = pal.warm; ctx.beginPath(); ctx.arc((P.x + (Q.x - P.x) * fr) * W, (P.y + (Q.y - P.y) * fr) * H, 3.6, 0, 7); ctx.fill(); }
      }
    }
    nodes.forEach(function (n, idx) {
      if (now < n.born) return;   // still flying there
      var x = n.x * W, y = n.y * H, age = Math.max(0, (now - n.born) / 1000), grow = 1;
      if (age < 2.2) {   // the bloom
        var q = age / 2.2;
        ctx.strokeStyle = rgba(pal.warm, (1 - q) * .8); ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(x, y, 6 + q * 40, 0, 7); ctx.stroke();
        grow = .4 + .6 * Math.min(1, q * 3);
      }
      if (n.hub) {   // the place's ring on a soft disc, with a glow
        var hg = ctx.createRadialGradient(x, y, 6, x, y, 34); hg.addColorStop(0, rgba(placeColour(n), .22)); hg.addColorStop(1, rgba(placeColour(n), 0));
        ctx.fillStyle = hg; ctx.beginPath(); ctx.arc(x, y, 34, 0, 7); ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,.07)"; ctx.beginPath(); ctx.arc(x, y, 19, 0, 7); ctx.fill();
        ctx.strokeStyle = rgba(placeColour(n), .95); ctx.lineWidth = 2.2;
        ctx.beginPath(); ctx.arc(x, y, 10, 0, 7); ctx.stroke();
        return;
      }
      var warm = n.mine || n.scripted || rnd(idx + 77) < .08, c = warm ? pal.warm : "#a8c8ec", s2 = (n.mine || n.scripted ? 4.2 : 3.3) * grow;
      ctx.fillStyle = rgba(c, .92);
      if (n.kind === "agent") { ctx.beginPath(); ctx.moveTo(x, y - s2 * 1.3); ctx.lineTo(x + s2 * 1.3, y); ctx.lineTo(x, y + s2 * 1.3); ctx.lineTo(x - s2 * 1.3, y); ctx.closePath(); ctx.fill(); }
      else if (n.kind === "doc") ctx.fillRect(x - s2 * .85, y - s2 * 1.15, s2 * 1.7, s2 * 2.3);
      else ctx.fillRect(x - s2, y - s2, s2 * 2, s2 * 2);
      if (n.kind === "web") { ctx.strokeStyle = rgba(c, .7); ctx.lineWidth = 1; ctx.strokeRect(x - s2 - 2.5, y - s2 - 2.5, s2 * 2 + 5, s2 * 2 + 5); }
    });
    flyers = flyers.filter(function (f) { return now - f.t0 < f.dur; });
    flyers.forEach(function (f) { drawFlyer(f, now); });
    // Labels last, with a halo. Places: name and count above their circle, always. A note when it is
    // hovered, new (the last 7 s), on the answer's path, or next to the hovered one.
    var c = counts(now);
    ctx.textAlign = "center"; ctx.lineJoin = "round"; ctx.lineWidth = 3.5; ctx.strokeStyle = rgba(pal.bg, .85);
    nodes.forEach(function (n) {
      if (now < n.born) return;
      if (n.hub) {
        if (!L.wide) return;   // on a phone the places stay a quiet background, unnamed
        var R = zoneR[n.place] || 60, ly = n.y * H - R - 7, below = ly < 16;
        ctx.textBaseline = below ? "top" : "bottom";
        ctx.font = "500 14px 'Segoe UI Variable Text', 'Segoe UI', Ubuntu, sans-serif";
        var label = n.name + "  ·  " + c[n.place];
        ctx.strokeText(label, n.x * W, below ? n.y * H + R + 7 : ly);
        ctx.fillStyle = rgba(pal.ink, .92); ctx.fillText(label, n.x * W, below ? n.y * H + R + 7 : ly);
        return;
      }
      var strong = n === hover || (now - n.born < 7000) || (glow && glow.nodes.indexOf(n) >= 0);
      if (!strong && !neighbour(n)) return;
      ctx.textBaseline = "top";
      ctx.font = "400 11.5px 'Segoe UI Variable Text', 'Segoe UI', Ubuntu, sans-serif";
      var tw = ctx.measureText(n.name).width, x = Math.max(tw / 2 + 6, Math.min(W - tw / 2 - 6, n.x * W)), y = n.y * H + 8;   // kept inside the frame
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
    mouse = p;
    if (drag) { drag.x = p[0]; drag.y = p[1]; kick(); return; }
    var n = pick(p); canvas.style.cursor = n ? "grab" : "default";
    if (n !== hover) { hover = n; kick(); }
  });
  canvas.addEventListener("pointerleave", function () { if (!drag && hover) { hover = null; kick(); } });
  canvas.addEventListener("pointerdown", function (e) { var n = pick(at(e)); if (n) { drag = n; hover = n; canvas.setPointerCapture(e.pointerId); canvas.style.cursor = "grabbing"; } });
  canvas.addEventListener("pointerup", function () { drag = null; kick(); });
  form.addEventListener("submit", function (e) { e.preventDefault(); yourTurnNow(); capture(input.value); input.value = ""; });
  Array.prototype.forEach.call(document.querySelectorAll("[data-try]"), function (b) {
    b.addEventListener("click", function () { yourTurnNow(); capture(b.getAttribute("data-try")); });
  });

  function loop() {
    // One clock for everything: rAF's own timestamp can lag performance.now(), which births and flights are set with.
    var now = performance.now();
    raf = 0; step((now - last) / 1000); last = now; draw(now);
    if (visible && !document.hidden) raf = requestAnimationFrame(loop);
  }
  function start() { if (!still && !raf && visible && !document.hidden) { last = performance.now(); raf = requestAnimationFrame(loop); } }
  // With reduced motion, settle at once and redraw only on change; the scene still plays, without anything flying.
  function kick() {
    if (!still) { start(); return; }
    for (var s = 0; s < 240; s++) step(.016);
    draw(performance.now() + 1e6);
  }
  if ("IntersectionObserver" in window) new IntersectionObserver(function (es) {
    visible = inView = es[0].isIntersecting;
    if (inView) { start(); startScene(); } else if (running) stopScene();
  }, { threshold: .15 }).observe(canvas);
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { if (running) stopScene(); } else { start(); startScene(); }
  });
  window.addEventListener("resize", resize);

  readPalette(); build();
  resize();   // the canvas size first: notes find their home inside circles measured in pixels
  for (var s = 0; s < 300; s++) step(.016);
  draw(performance.now());
  start();
  startScene();
})();
