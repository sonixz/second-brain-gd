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
    { name: "Inbox", kw: [] },
    { name: "Kitchen renovation", kw: ["kitchen", "countertop", "counter", "quartz", "granite", "cabinet", "cabinets", "sink", "tiles", "tile", "paint", "renovation", "reno", "contractor", "oven", "fridge", "floor", "electrician"] },
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
    ["Voice memo from the car", 0], ["Screenshot to sort", 0],
    ["Paint colours", 1], ["Electrician visit", 1], ["Lighting plan", 1],
    ["Particles: wa, ga", 2], ["Podcast for learners", 2],
    ["10k steps", 3], ["Stretching routine", 3], ["Vitamin D", 3],
    ["Ramen broth", 4], ["Lentil soup", 4], ["Tomato sauce", 4],
    ["Deep Work, ch. 3", 5], ["Novel to start", 5], ["Essay on memory", 5],
    ["Link from a friend", 0]
  ];

  var W = 0, H = 0, dpr = 1, nodes = [], edges = [], pal = {}, hover = null, drag = null, raf = 0, visible = true, last = 0;
  var lastCapture = null, flyers = [], glow = null;

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
    L = wide ? { wide: true, cx: .5, cy: .5, x0: .02, x1: .97, y0: .05, y1: .95, rx: .1, ry: .1, k: .000014, hub: .07, note: .09,
                 // Inbox, Kitchen renovation, Learn Japanese, Health, Recipes, Reading
                 anchors: [[.6, .56], [.6, .2], [.84, .2], [.89, .6], [.74, .42], [.15, .86]] }
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
      nodes.push({ name: n[0], hub: false, place: n[1], x: h.x + Math.cos(a) * L.rx * .4, y: h.y + Math.sin(a) * L.ry * .4, vx: 0, vy: 0, r: 4.5, warm: rnd(i + 50) < .3, born: -1e9 });
      edges.push([nodes[nodes.length - 1], h]);
    });
    // a few links across places, as the Archivist finds them by meaning
    [[4, 13], [14, 15], [10, 11], [0, 3]].forEach(function (l) { edges.push([nodes[PLACES.length + l[0]], nodes[PLACES.length + l[1]]]); });
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
      .then(function () { s = feed("a-say", "", true); return typeInto(function (t) { s.textContent = t; }, "Hello. 33 notes in 6 places. Speak, drop a file, send a page or ask me anything.", 18, w); })
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
        return w(700);
      })
      .then(function () {
        var to = nearHub(1);
        return fly("note", "Call the electrician · Tue", barPoint(), to, 800, w).then(function () { return to; });
      })
      .then(function (to) {
        addNode("Call the electrician · Tue", 1, to, { scripted: true, links: ["Electrician visit"] });
        feed("a-receipt", receiptHTML("Task · filed", "Kitchen renovation", "due Tuesday · #electrician", ["Electrician visit"]), true);
        setState("ready");
        return w(2200);
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
      .then(function () { setState("ready"); return w(1900); })
      // 3. you paste a web page
      .then(function () { return typeInto(function (t) { input.value = t; }, "https://example.com/tonkotsu-ramen", 28, w); })
      .then(function () { return w(350); })
      .then(function () {
        input.value = "";
        feed("a-you", '<span class="k">LINK</span>example.com/tonkotsu-ramen', true);
        setState("reading");
        return w(900);
      })
      .then(function () {
        var to = nearHub(4);
        return fly("web", "example.com/tonkotsu-ramen", barPoint(), to, 900, w).then(function () { return to; });
      })
      .then(function (to) {
        addNode("Tonkotsu ramen (web)", 4, to, { scripted: true, kind: "web", links: ["Ramen broth"] });
        feed("a-receipt", receiptHTML("Web page · filed", "Recipes", "Tonkotsu ramen · 12 min read", ["Ramen broth"]), true);
        setState("ready");
        return w(2200);
      })
      // 4. you ask: the answer follows the links, and cites its notes
      .then(function () { return typeInto(function (t) { input.value = t; }, "What did I decide about the countertop?", 32, w); })
      .then(function () { return w(350); })
      .then(function () {
        input.value = "";
        feed("a-you", '<span class="k">ASK</span>What did I decide about the countertop?', true);
        setState("thinking");
        return w(800);
      })
      .then(function () {
        lightPath([hub(1), byName("Quartz or granite?"), byName("Quartz countertop quote")]);
        s = feed("a-say", "", true);
        return typeInto(function (t) { s.textContent = t; }, "Quartz. You chose it in « Quartz or granite? », and the new quote fits the budget: $4,200.", 16, w);
      })
      .then(function () {
        s.insertAdjacentHTML("beforeend", '<span class="r-links"><span>Quartz or granite?</span><span>Quartz countertop quote</span></span>');
        setState("ready");
        return w(2600);
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
        return w(2400);
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
        A.vx += dx * f; A.vy += dy * f; B.vx -= dx * f; B.vy -= dy * f;
      }
    }
    edges.forEach(function (e) {
      var A = e[0], B = e[1], dx = B.x - A.x, dy = B.y - A.y, d = Math.sqrt(dx * dx + dy * dy) + 1e-6,
        rest = A.hub || B.hub ? L.hub : L.note, f = (d - rest) * .09;
      A.vx += dx / d * f; A.vy += dy / d * f; B.vx -= dx / d * f; B.vy -= dy / d * f;
    });
    var t = performance.now() / 3000;
    if (!L.wide !== !((canvas.clientWidth || 0) > 960)) layout();
    nodes.forEach(function (n, idx) {
      if (n === drag) { n.vx = n.vy = 0; return; }
      // Pulled to the centre, or on wide screens to its place's anchor (a hub firmly, a note gently).
      var an = L.anchors && L.anchors[n.place], g = an ? (n.hub ? .03 : .0006) : 0;
      n.vx += (an ? (an[0] - n.x) * g : (L.cx - n.x) * .003) + (still ? 0 : Math.sin(t + idx) * .00003);
      n.vy += an ? (an[1] - n.y) * g : (L.cy - n.y) * .004;
      n.vx *= .86; n.vy *= .86; n.x += n.vx * k; n.y += n.vy * k;
      n.x = Math.max(L.x0, Math.min(L.x1, n.x)); n.y = Math.max(L.y0, Math.min(L.y1, n.y));
    });
  }

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
  function draw(now) {
    ctx.clearRect(0, 0, W, H);
    var lit = glow ? glow.edges : [];
    edges.forEach(function (e) {
      var A = e[0], B = e[1], on = hover && (A === hover || B === hover), path = lit.indexOf(e) >= 0;
      ctx.strokeStyle = path ? rgba(pal.warm, .95) : rgba(on ? pal.mint : pal.node, on ? .9 : .4); ctx.lineWidth = path ? 2.4 : on ? 1.8 : 1;
      ctx.beginPath(); ctx.moveTo(A.x * W, A.y * H); ctx.lineTo(B.x * W, B.y * H); ctx.stroke();
    });
    if (glow && glow.nodes.length > 1 && !still) {   // a spark travelling the answer's path
      var segs = glow.nodes.length - 1, u = ((now - glow.t0) / 650) % (segs + .6);
      if (u < segs) {
        var i0 = Math.floor(u), fr = u - i0, P = glow.nodes[i0], Q = glow.nodes[i0 + 1];
        if (P && Q) { ctx.fillStyle = pal.warm; ctx.beginPath(); ctx.arc((P.x + (Q.x - P.x) * fr) * W, (P.y + (Q.y - P.y) * fr) * H, 3.6, 0, 7); ctx.fill(); }
      }
    }
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    nodes.forEach(function (n) {
      if (now < n.born) return;   // still flying there
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
        ctx.fillStyle = c;
        if (n.kind === "doc") { roundRect(x - r * .8, y - r, r * 1.6, r * 2, 2); ctx.fill(); }          // a document: a page
        else if (n.kind === "agent") { ctx.beginPath(); ctx.moveTo(x, y - r * 1.2); ctx.lineTo(x + r * 1.2, y); ctx.lineTo(x, y + r * 1.2); ctx.lineTo(x - r * 1.2, y); ctx.closePath(); ctx.fill(); }  // from an agent: a diamond
        else { ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill(); }
        if (n.kind === "web") { ctx.strokeStyle = rgba(c, .8); ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(x, y, r + 3, 0, 7); ctx.stroke(); }  // a web page: a ring
      }
    });
    flyers = flyers.filter(function (f) { return now - f.t0 < f.dur; });
    flyers.forEach(function (f) { drawFlyer(f, now); });
    // Labels last, with a halo, so dots never cover them. Places always; a note when it is
    // hovered, new (the last 7 s), on the answer's path, or next to the hovered one.
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    ctx.lineJoin = "round"; ctx.lineWidth = 3.5; ctx.strokeStyle = rgba(pal.bg, .85);
    nodes.forEach(function (n) {
      if (now < n.born) return;
      var strong = n.hub || n === hover || (now - n.born < 7000) || (glow && glow.nodes.indexOf(n) >= 0);
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
  for (var s = 0; s < 300; s++) step(.016);
  resize();
  start();
  startScene();
})();
