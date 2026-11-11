// "How it thinks" page: meaning vs words, a capture followed end to end, the meaning map, model routing,
// an agent's tool trace and the MCP loop. A simulation: no dependencies, no network calls, nothing is sent.
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function norm(s) { return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, ""); }
  function rnd(i) { var x = Math.sin(i * 99.13 + 7.7) * 43758.5; return x - Math.floor(x); }
  // Colours a small text artifact: "keys": in mint, "strings" in warm, // comments faint.
  function colour(t) {
    return esc(t).replace(/(\/\/[^\n]*)/g, '<span class="c">$1</span>')
      .replace(/&quot;([^&\n]*?)&quot;(\s*:)/g, '<span class="k">"$1"</span>$2')
      .replace(/(:\s*|\[\s*|,\s*)&quot;([^&\n]*?)&quot;/g, '$1<span class="s">"$2"</span>');
  }

  // ------------------------------------------------------------------ the sample Brain
  var PLACES = [
    { name: "Inbox", c: "#b5c6da" }, { name: "Kitchen renovation", c: "#ffd2a1" }, { name: "Learn Japanese", c: "#f3a6c8" },
    { name: "Health", c: "#a9f0c7" }, { name: "Recipes", c: "#ffd27a" }, { name: "Reading", c: "#a9d4ff" }
  ];
  // [title, place, language, text, ideas] (all English on the site)
  var NOTES = [
    ["Quartz or granite?", 1, "en", "Quartz needs no sealing and resists stains; granite is cheaper per square foot but must be sealed every year. Leaning quartz for the island.", { kitchen: 1, surface: 1, decision: .8, cost: .4 }],
    ["Quartz quote", 1, "en", "White quartz, installed: $4,200, three weeks of lead time. Valid until November 30.", { kitchen: .8, surface: 1, cost: 1 }],
    ["Cabinet quotes", 1, "en", "Three quotes for the cabinets: 9,800, 11,200 and 12,500. The middle one includes soft-close drawers.", { kitchen: 1, cost: 1, decision: .3 }],
    ["Electrician visit", 1, "en", "The electrician comes on Tuesday for the island outlets and the under-cabinet lights.", { kitchen: .7, electric: 1, design: .3 }],
    ["Lighting plan", 1, "en", "Warm 2700K strips under the cabinets, three pendants over the island, a dimmer by the door.", { kitchen: .7, electric: .6, design: 1 }],
    ["Paint colours", 1, "en", "Swatches: warm white for the walls, deep green for the lower cabinets.", { kitchen: .6, design: 1 }],
    ["Renovation budget", 1, "en", "Total budget: $38,000. Stone and cabinets already take 60 % of it.", { kitchen: .8, cost: 1, decision: .4 }],
    ["Kanji: 30 a week", 2, "en", "Thirty new kanji every week, reviewed with spaced repetition.", { japanese: 1, writing: 1, learning: .8, memory: .3 }],
    ["Hiragana chart", 2, "en", "All 46 hiragana with their stroke order.", { japanese: 1, writing: 1, learning: .3 }],
    ["Anki deck", 2, "en", "Twenty new cards a day, reviews every morning before work.", { japanese: .6, learning: 1, memory: .8 }],
    ["Kyoto trip phrases", 2, "en", "Phrases for the trip: ordering food, asking for directions, train tickets.", { japanese: .9, travel: 1, food: .3 }],
    ["Particles: wa and ga", 2, "en", "Wa marks the topic, ga the subject: examples and traps.", { japanese: 1, learning: .6, writing: .2 }],
    ["Sleep log", 3, "en", "In bed by 22:30 four nights out of seven; better focus the next morning.", { sleep: 1, health: .6, method: .3 }],
    ["Morning walk", 3, "en", "Thirty minutes on foot before work, about 6,000 steps.", { exercise: 1, health: .6 }],
    ["Dentist in March", 3, "en", "Cleaning booked on March 12 at 9:00.", { medical: 1 }],
    ["Vitamin D", 3, "en", "The doctor suggests 1,000 IU a day in winter.", { medical: 1, health: .5 }],
    ["Stretching routine", 3, "en", "Ten minutes after running: hamstrings, hips, calves.", { exercise: 1, health: .5 }],
    ["Tonkotsu ramen broth", 4, "en", "Pork bones simmered for 12 hours until milky; toppings: marinated egg, nori.", { food: 1, soup: 1, japanese: .35 }],
    ["Lentil soup", 4, "en", "Red lentils, cumin and lemon. Forty minutes, and it freezes well.", { food: 1, soup: 1 }],
    ["Sourdough starter", 4, "en", "Feed it 1:1:1 every 12 hours; ready when it doubles.", { food: 1, bread: 1 }],
    ["Chicken curry", 4, "en", "A mild coconut curry, ready in 35 minutes.", { food: 1 }],
    ["Weekly groceries", 4, "en", "Lentils, coconut milk, eggs, nori, flour.", { food: .8, cost: .3 }],
    ["Building a Second Brain", 5, "en", "Capture, organize, distill, express: the CODE method.", { reading: .8, method: 1, memory: .6 }],
    ["The PARA method", 5, "en", "Projects, areas, resources, archives: file by what you will do with it, not by subject.", { reading: .6, method: 1 }],
    ["Essay on memory", 5, "en", "Why we forget: the forgetting curve, and why spaced reviews work.", { reading: .8, memory: 1, learning: .7 }],
    ["Deep Work, ch. 3", 5, "en", "Long blocks without distraction; shallow work in batches.", { reading: .8, method: 1 }],
    ["Novel to start", 5, "en", "A Japanese novel a friend suggested: Kafka on the Shore.", { reading: 1, japanese: .3 }],
    ["Voice memo from the car", 0, "en", "Ask the contractor whether the island can be 10 cm longer.", { kitchen: .8, decision: .3 }],
    ["Link from a friend", 0, "en", "An article about rest and memory.", { sleep: .6, memory: .6, reading: .4 }]
  ];
  var notes = NOTES.map(function (n, i) { return { i: i, title: n[0], place: n[1], lang: n[2], text: n[3], v: n[4] }; });

  function cos(a, b) {
    var d = 0, na = 0, nb = 0, k;
    for (k in a) { na += a[k] * a[k]; if (b[k]) d += a[k] * b[k]; }
    for (k in b) nb += b[k] * b[k];
    return na && nb ? d / Math.sqrt(na * nb) : 0;
  }
  // Toy scores on the same scale as the app's (text-embedding-3-small: unrelated notes ~0.1, same idea 0.35-0.6).
  function score(c) { return .08 + .56 * c; }
  var SIM = notes.map(function (a) {
    return notes.map(function (b) {
      if (a === b) return 1;
      var j = Math.min(a.i, b.i) * 31 + Math.max(a.i, b.i);
      return Math.max(.02, score(cos(a.v, b.v)) + (rnd(j) - .5) * .05);
    });
  });

  // Word stems (English, plus a few French ones so a French question still works) to ideas. A tiny stand-in for an embeddings model.
  var LEX = {
    kitchen: { kitchen: 1 }, cuisin: { kitchen: .8, food: .5 }, island: { kitchen: .6 }, ilot: { kitchen: .6 }, renov: { kitchen: .8 }, reno: { kitchen: .7 },
    contractor: { kitchen: .6 }, entrepreneur: { kitchen: .5 }, cabinet: { kitchen: .9, cost: .2 }, armoire: { kitchen: .9 }, sink: { kitchen: .8 }, evier: { kitchen: .8 },
    faucet: { kitchen: .6 }, robinet: { kitchen: .6 }, tile: { kitchen: .6, design: .3 }, floor: { kitchen: .5 }, plancher: { kitchen: .5 },
    countertop: { surface: 1, kitchen: .5 }, counter: { surface: .9, kitchen: .5 }, comptoir: { surface: 1, kitchen: .5 }, quartz: { surface: 1 }, granit: { surface: 1 },
    stone: { surface: .8 }, pierre: { surface: .7 }, marb: { surface: .9 },
    cost: { cost: 1 }, cout: { cost: 1 }, price: { cost: 1 }, prix: { cost: 1 }, quote: { cost: .9, decision: .2 }, devis: { cost: .9 }, budget: { cost: 1 },
    cher: { cost: .8 }, expens: { cost: .9 }, cheap: { cost: .8 }, afford: { cost: .8 }, pay: { cost: .8 }, combien: { cost: .9 }, much: { cost: .4 },
    money: { cost: .9 }, argent: { cost: .9 }, spend: { cost: .9 }, depens: { cost: .9 },
    decid: { decision: 1 }, decis: { decision: 1 }, chois: { decision: .9 }, choos: { decision: .9 }, choice: { decision: .9 }, chose: { decision: .6 },
    pick: { decision: .6 }, lean: { decision: .5 }, option: { decision: .6 }, conclu: { decision: .6 },
    electri: { electric: 1 }, outlet: { electric: .8 }, prise: { electric: .7 }, wiring: { electric: .9 }, power: { electric: .5 }, plug: { electric: .5 },
    light: { design: .8, electric: .4 }, eclair: { design: .8, electric: .4 }, lamp: { design: .7, electric: .3 }, paint: { design: .9 }, peint: { design: .9 },
    colo: { design: .8 }, couleur: { design: .8 }, pendant: { design: .6 }, style: { design: .6 },
    japan: { japanese: 1 }, japon: { japanese: 1 }, kanji: { japanese: .9, writing: 1 }, hiragana: { japanese: .9, writing: 1 }, katakana: { japanese: .9, writing: 1 },
    kana: { japanese: .9, writing: .9 }, nihongo: { japanese: 1 }, kyoto: { japanese: .8, travel: .6 }, tokyo: { japanese: .8, travel: .6 }, sushi: { japanese: .5, food: .8 },
    alphabet: { writing: 1, learning: .3 }, writ: { writing: .7 }, ecri: { writing: .7 }, stroke: { writing: .6 }, character: { writing: .6 }, caract: { writing: .6 },
    learn: { learning: 1, memory: .3 }, appren: { learning: 1, memory: .3 }, study: { learning: .9 }, studi: { learning: .9 }, etud: { learning: .9 },
    lesson: { learning: .8 }, cours: { learning: .6 }, gramm: { learning: .7, japanese: .2 }, revis: { learning: .6, memory: .6 }, review: { learning: .5, memory: .5 },
    vocab: { learning: .8 }, practi: { learning: .7 }, pratiq: { learning: .7 }, school: { learning: .6 }, ecole: { learning: .6 },
    memor: { memory: 1 }, memoi: { memory: 1 }, forget: { memory: 1, learning: .3 }, oubli: { memory: 1, learning: .3 }, rememb: { memory: 1 }, souven: { memory: .9 },
    recall: { memory: .9 }, anki: { memory: .9, learning: .8 }, flashcard: { memory: .8, learning: .8 }, spaced: { memory: .8 }, brain: { memory: .5, method: .4 },
    cerveau: { memory: .5, method: .4 },
    trip: { travel: 1 }, travel: { travel: 1 }, voyag: { travel: 1 }, vacat: { travel: .9 }, vacanc: { travel: .9 }, train: { travel: .6 }, ticket: { travel: .6 },
    billet: { travel: .6 }, direction: { travel: .5 }, hotel: { travel: .8 }, airport: { travel: .7 }, aeroport: { travel: .7 },
    sleep: { sleep: 1 }, dors: { sleep: 1 }, dorm: { sleep: 1 }, sommeil: { sleep: 1 }, bed: { sleep: .7 }, insomn: { sleep: 1 }, tired: { sleep: .7, health: .3 },
    fatigu: { sleep: .7, health: .3 }, nuit: { sleep: .6 }, night: { sleep: .6 }, rest: { sleep: .5, health: .3 }, repos: { sleep: .5, health: .3 }, nap: { sleep: .6 }, sieste: { sleep: .6 },
    walk: { exercise: 1 }, march: { exercise: .8 }, run: { exercise: 1 }, courir: { exercise: 1 }, jog: { exercise: 1 }, step: { exercise: .6 }, stretch: { exercise: .9 },
    etir: { exercise: .9 }, sport: { exercise: .9 }, exerci: { exercise: 1 }, gym: { exercise: .9 }, yoga: { exercise: .8 }, fit: { exercise: .6 }, muscle: { exercise: .7 },
    health: { health: 1 }, sante: { health: 1 }, energ: { health: .5 }, mal: { health: .4, medical: .2 }, hurt: { health: .5, medical: .4 }, sick: { medical: .7, health: .5 },
    malad: { medical: .7, health: .5 },
    doctor: { medical: 1 }, medec: { medical: 1 }, docteur: { medical: 1 }, dentist: { medical: 1 }, dent: { medical: .8 }, vitamin: { medical: .8, health: .5 },
    pill: { medical: .7 }, clinic: { medical: .9 }, appointment: { medical: .6 }, rendez: { medical: .5 },
    food: { food: 1 }, cook: { food: 1 }, recipe: { food: 1 }, recette: { food: 1 }, eat: { food: .9 }, mang: { food: .9 }, dinner: { food: .9 }, souper: { food: .9 },
    diner: { food: .8 }, lunch: { food: .9 }, meal: { food: 1 }, repas: { food: 1 }, grocer: { food: .8, cost: .2 }, epicer: { food: .8, cost: .2 },
    chicken: { food: .9 }, poulet: { food: .9 }, curry: { food: .9 }, hungry: { food: .8 }, faim: { food: .8 },
    soup: { soup: 1, food: .6 }, broth: { soup: 1, food: .5 }, bouillon: { soup: 1, food: .5 }, ramen: { soup: .9, food: .6, japanese: .3 }, potage: { soup: 1, food: .5 },
    stew: { soup: .8, food: .6 }, warm: { soup: .5 }, asleep: { sleep: 1 }, hiver: { soup: .4 }, winter: { soup: .4 }, cold: { soup: .3 }, froid: { soup: .3 },
    bread: { bread: 1, food: .5 }, pain: { bread: 1, food: .5 }, sourdough: { bread: 1, food: .5 }, levain: { bread: 1, food: .5 }, flour: { bread: .8, food: .4 },
    farine: { bread: .8, food: .4 }, bake: { bread: .9, food: .4 }, boulang: { bread: .9 },
    read: { reading: 1 }, lire: { reading: 1 }, lect: { reading: .9 }, book: { reading: 1 }, livre: { reading: 1 }, novel: { reading: 1 }, roman: { reading: 1 },
    essay: { reading: .8 }, essai: { reading: .8 }, article: { reading: .8 }, author: { reading: .7 }, auteur: { reading: .7 }, podcast: { reading: .6, learning: .3 },
    productiv: { method: 1 }, focus: { method: .9 }, concentr: { method: .9 }, method: { method: .9 }, organi: { method: .9 }, para: { method: .9 },
    workflow: { method: .8 }, distract: { method: .8 }, deep: { method: .5 }, note: { method: .4, memory: .3 }, capture: { method: .6 }, habit: { method: .6, health: .3 }
  };
  var STEMS = Object.keys(LEX).sort(function (a, b) { return b.length - a.length; });
  var STOP = ("the a an and or of to in on for with what did do does how i me my you your is are was it this that from about at by can " +
    "le la les un une des du de et ou en au aux pour avec que qui quoi quel quelle est je tu il elle mon ma mes ton ta ce cette sur dans pas ne").split(" ");

  function queryVector(q) {
    var v = {}, any = false;
    norm(q).split(/[^a-z0-9]+/).forEach(function (w) {
      if (w.length < 3 || STOP.indexOf(w) >= 0) return;
      for (var i = 0; i < STEMS.length; i++) {
        if (w.indexOf(STEMS[i]) === 0) {
          var m = LEX[STEMS[i]];
          for (var k in m) { v[k] = (v[k] || 0) + m[k]; any = true; }
          return;
        }
      }
    });
    return any ? v : null;
  }
  function byMeaning(q) {
    var v = queryVector(q);
    if (!v) return [];
    return notes.map(function (n) { return { n: n, s: score(cos(v, n.v)) }; })
      .filter(function (h) { return h.s >= .25; })
      .sort(function (a, b) { return b.s - a.s; }).slice(0, 6);
  }
  // Exact words: case-insensitive, whole words, spelled the same way (accents count), like a plain text search.
  function byWords(q) {
    var words = q.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(function (w) { return w.length > 2 && STOP.indexOf(w) < 0; });
    if (!words.length) return [];
    var out = [];
    notes.forEach(function (n) {
      var hay = " " + (n.title + " " + n.text).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ") + " ";
      var hit = words.filter(function (w) { return hay.indexOf(" " + w + " ") >= 0; });
      if (hit.length) out.push({ n: n, hit: hit });
    });
    return out.sort(function (a, b) { return b.hit.length - a.hit.length; }).slice(0, 6);
  }

  // ------------------------------------------------------------------ 1. meaning vs words
  var lastQuery = null;
  function langTag() { return ""; }
  function runQuery(q) {
    q = (q || "").trim();
    if (!q) return;
    var m = byMeaning(q), w = byWords(q);
    var mm = {}; m.forEach(function (h) { mm[h.n.i] = h.s; });
    $("#words-count").textContent = w.length;
    $("#meaning-count").textContent = m.length;
    $("#words-list").innerHTML = w.length ? w.map(function (h, k) {
      var wrong = !(h.n.i in mm) && score(cos(queryVector(q) || {}, h.n.v)) < .25;
      return '<li class="' + (wrong ? "wrong" : "") + '" style="animation-delay:' + k * 60 + 'ms"><span class="t">' + esc(h.n.title) + langTag(h.n) + "</span>" +
        '<span class="sc">“' + esc(h.hit.join("”, “")) + '”</span><span class="p">' + esc(PLACES[h.n.place].name) + "</span>" +
        (wrong ? '<span class="why">It holds the word, not the idea.</span>' : "") + "</li>";
    }).join("") : '<li class="empty">No note contains these exact words.</li>';
    $("#meaning-list").innerHTML = m.length ? m.map(function (h, k) {
      return '<li style="animation-delay:' + k * 70 + 'ms"><span class="t">' + esc(h.n.title) + langTag(h.n) + "</span>" +
        '<span class="sc">' + h.s.toFixed(2) + '</span><span class="p">' + esc(PLACES[h.n.place].name) + " · " + esc(h.n.text.slice(0, 64)) + "…</span>" +
        '<span class="bar"><i style="width:' + Math.round(Math.min(1, h.s / .65) * 100) + '%"></i></span></li>';
    }).join("") : '<li class="empty">Nothing in this small sample Brain is about that. In the app, any text has a meaning.</li>';
    $$(".ask-chips button").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-q") === q); });
    lastQuery = m.length ? { q: q, hits: m.slice(0, 3) } : null;
    if (map) map.draw();
  }
  var ask = $("#ask"), askQ = $("#ask-q");
  if (ask) {
    ask.addEventListener("submit", function (e) { e.preventDefault(); runQuery(askQ.value); });
    $$(".ask-chips button").forEach(function (b) {
      b.addEventListener("click", function () { askQ.value = b.getAttribute("data-q"); runQuery(askQ.value); });
    });
  }

  // ------------------------------------------------------------------ 2. one capture, end to end
  var SCEN = {
    voice: [
      ["you", "You speak", "Hold F8, say it, let go. Nothing to choose, no folder to open.", '// spoken, in English\n"Remind me to call the electrician on Tuesday about the island outlets."'],
      ["gpt-realtime-whisper", "Read: your voice becomes text", "On release, the recording is transcribed. Speak naturally; it writes down what you said.", '{\n  "text": "Remind me to call the electrician on Tuesday about the island outlets.",\n  "language": "en",\n  "seconds": 3.4\n}'],
      ["gpt-6-sol", "Understand", "The Archivist reads it with the places, themes and nearby notes it already knows, and answers in strict JSON.", '{\n  "title": "Call the electrician",\n  "item_type": "task",\n  "due": "Tuesday",\n  "entities": { "people": ["electrician"], "dates": ["Tuesday"] },\n  "themes": ["electrical", "island"]\n}'],
      ["gpt-6-sol", "File in PARA", "It picks the place that fits. Sure enough (0.91 is above the 0.6 bar), so it files without asking.", '"place": { "space_id": "Kitchen renovation" }   // a project\n"confidence": 0.91                           // ≥ 0.6: filed'],
      ["text-embedding-3-small", "Index twice", "Words go to the full-text index on your computer; the meaning becomes a vector of 1,536 numbers.", '// words (this computer)\nnotes_fts       "call electrician tuesday island outlets"\n\n// meaning\nnote_embeddings [0.021, -0.113, 0.067, 0.004, … 1,536 numbers]'],
      ["this computer", "Link by meaning", "Its vector is compared with every note. The closest one never says “call”: same idea, other words.", '"Electrician visit"   0.58   same idea  // linked\n"Lighting plan"       0.41               // suggested\n"Renovation budget"   0.19               // too far'],
      ["receipt", "Receipt", "A factual receipt, with Undo. The timeline keeps the change.", 'Task · filed in Kitchen renovation · due Tuesday\nLinked: Electrician visit          [Undo]']
    ],
    pdf: [
      ["you", "You drop a PDF", "Drag countertop-quote.pdf onto the window. The original is kept, untouched.", '// countertop-quote.pdf · 3 pages · 186 KB\n// sha256 kept with the original'],
      ["this computer", "Read: page by page", "The text is extracted on your computer. A scanned page would be read by local OCR (Windows OCR or Tesseract).", '"pages": 3\n"chunks": 6        // ~1,200 characters each, 150 overlap\n"p.2": "Quartz, white, 3 cm, installed: $4,200 …"'],
      ["gpt-6-sol", "Understand", "A summary, key points and entities, in the document's language.", '{\n  "title": "Quartz countertop quote",\n  "item_type": "document",\n  "summary": "Quote for a white quartz countertop, installed, $4,200, valid until Nov 30.",\n  "key_points": ["$4,200 installed", "3 weeks", "valid until Nov 30"],\n  "entities": { "dates": ["Nov 30"] }\n}'],
      ["gpt-6-sol", "File in PARA", "The Archivist recognises the project.", '"place": { "space_id": "Kitchen renovation" }\n"confidence": 0.88'],
      ["text-embedding-3-small", "Index twice, page by page", "Each of the 6 pieces gets its own words and its own vector, so an answer can cite page 2.", 'chunks_fts      6 pieces   // words\nsource_chunks   6 vectors  // meaning, one per piece\nnote_embeddings 1 vector   // the summary'],
      ["this computer", "Link by meaning", "The quote lands next to the decision it feeds.", '"Quartz or granite?"   0.55   same idea  // linked\n"Renovation budget"    0.47   same idea\n"Cabinet quotes"       0.38'],
      ["receipt", "Receipt", "Open it page by page in the document viewer, or ask about it.", 'Document · Kitchen renovation · 3 pages · $4,200\nLinked: Quartz or granite?, Renovation budget   [Undo]']
    ],
    web: [
      ["you", "You send a web page", "One click in Edge or Chrome sends the page you are reading (the browser extension).", '// https://example.com/tonkotsu-at-home\n// sent by the extension, paired once with your Brain'],
      ["this computer", "Read: the page itself", "The page is downloaded by your computer, cleaned of menus and ads, and kept as an original.", '"title": "Tonkotsu at home"\n"words": 1,840\n"chunks": 2'],
      ["gpt-6-sol", "Understand", "It recognises a recipe, so it saves it as one, with fields.", '{\n  "title": "Tonkotsu ramen at home",\n  "item_type": "recipe",\n  "fields": { "servings": 4, "time": "12 h", "ingredients": ["pork bones", "nori", "eggs"] }\n}'],
      ["gpt-6-sol", "File in PARA", "Recipes is a resource: a subject you keep for reference.", '"place": { "space_id": "Recipes" }   // a resource\n"confidence": 0.93'],
      ["text-embedding-3-small", "Index twice", "Words and meaning, for the page and its two pieces.", 'notes_fts · chunks_fts      // words\nnote_embeddings · source_chunks   // meaning'],
      ["this computer", "Link by meaning", "Your broth note is the closest. And it leans a little toward the Kyoto trip.", '"Tonkotsu ramen broth"   0.61   same idea  // linked\n"Kyoto trip phrases"        0.36\n"Lentil soup"               0.34'],
      ["receipt", "Receipt", "The original page is one click away, even offline.", 'Recipe · Recipes · 4 servings\nLinked: Tonkotsu ramen broth   [Undo]']
    ],
    photo: [
      ["you", "You add a photo", "A picture of a whiteboard after a lesson.", "// IMG_2041.jpg · 2.3 MB"],
      ["gpt-4o-mini", "Read: the vision model describes it", "An image becomes text you can search: what it shows, and the words written in it.", '"description": "A whiteboard with the hiragana rows あ to そ, stroke order arrows, and the note: review Friday."'],
      ["gpt-6-sol", "Understand", "Now it is text, the Archivist reads it like anything else.", '{\n  "title": "Hiragana practice: あ to そ",\n  "item_type": "note",\n  "themes": ["hiragana", "lessons"]\n}'],
      ["gpt-6-sol", "File in PARA", "", '"place": { "space_id": "Learn Japanese" }\n"confidence": 0.86'],
      ["text-embedding-3-small", "Index twice", "The description is indexed; the picture stays as the original.", 'notes_fts · note_embeddings · source_images'],
      ["this computer", "Link by meaning", "", '"Hiragana chart"      0.60   same idea  // linked\n"Kanji: 30 a week"    0.44   same idea\n"Anki deck"         0.37'],
      ["receipt", "Receipt", "", 'Note · Learn Japanese · from a photo\nLinked: Hiragana chart, Kanji: 30 a week   [Undo]']
    ],
    unsure: [
      ["you", "You say something short", "Not every capture is clear.", '"Gift idea for Mom: a ceramics class."'],
      ["gpt-realtime-whisper", "Read", "", '{ "text": "Gift idea for Mom: a ceramics class." }'],
      ["gpt-6-sol", "Understand", "An idea, a person, no place that fits yet.", '{\n  "title": "Gift idea: ceramics class",\n  "item_type": "idea",\n  "entities": { "people": ["Mom"] }\n}'],
      ["gpt-6-sol", "Not sure? It asks", "No place fits well (0.41, under the 0.6 bar). It waits in the Inbox, and the Archivist asks you.", '"place": { "new_space": { "name": "Gifts", "kind": "area" } }\n"confidence": 0.41      // < 0.6: ask first\n\n→ “New place: Gifts”   or   “Keep it in the Inbox”'],
      ["text-embedding-3-small", "Index twice", "Indexed right away, so you can find it even before it is filed.", "notes_fts · note_embeddings"],
      ["this computer", "Link by meaning", "Nothing close enough in this Brain. No link is better than a wrong one.", '// closest: "Weekly groceries" 0.14 · below 0.33: no link'],
      ["receipt", "Receipt, after your answer", "You said “New place: Gifts”. A brand-new Brain builds its own structure this way.", 'Idea · filed in Gifts (new area)   [Undo]']
    ]
  };
  var pipe = { scen: "voice", step: 0, playing: !reduce, timer: 0 };
  function chipClass(m) { return m === "this computer" ? "model-chip local" : (m === "you" || m === "receipt") ? "model-chip none" : "model-chip"; }
  function showStep() {
    var s = SCEN[pipe.scen][pipe.step];
    var chip = $("#pipe-model");
    chip.className = chipClass(s[0]);
    chip.textContent = s[0] === "you" ? "you" : s[0] === "receipt" ? "the Archivist" : s[0];
    $("#pipe-title").textContent = s[1];
    $("#pipe-text").textContent = s[2] || " ";
    $("#pipe-art").innerHTML = colour(s[3]);
    var track = $("#pipe-track");
    track.style.setProperty("--p", pipe.step / 6);
    $$("li", track).forEach(function (li, k) {
      li.classList.toggle("on", k === pipe.step);
      li.classList.toggle("done", k < pipe.step);
      li.classList.toggle("ask", pipe.scen === "unsure" && k === 3 && pipe.step >= 3);
    });
  }
  function pipeTick() {
    clearTimeout(pipe.timer);
    if (!pipe.playing || !pipe.visible) return;
    pipe.timer = setTimeout(function () {
      pipe.step = (pipe.step + 1) % 7;
      if (pipe.step === 0) {
        var keys = Object.keys(SCEN);
        pipe.scen = keys[(keys.indexOf(pipe.scen) + 1) % keys.length];
        syncInputs();
      }
      showStep(); pipeTick();
    }, pipe.step === 6 ? 4200 : 3000);
  }
  function syncInputs() { $$(".pipe-inputs button").forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-in") === pipe.scen ? "true" : "false"); }); }
  function setPlaying(p) {
    pipe.playing = p;
    var b = $("#pipe-play");
    b.textContent = p ? "❚❚ Pause" : "▶ Play";
    b.setAttribute("aria-pressed", p ? "true" : "false");
    pipeTick();
  }
  if ($("#pipe")) {
    $$(".pipe-inputs button").forEach(function (b) {
      b.addEventListener("click", function () { pipe.scen = b.getAttribute("data-in"); pipe.step = 0; syncInputs(); showStep(); pipeTick(); });
    });
    $$("#pipe-track li").forEach(function (li) {
      li.addEventListener("click", function () { pipe.step = +li.getAttribute("data-step"); showStep(); setPlaying(false); });
    });
    $("#pipe-prev").addEventListener("click", function () { pipe.step = (pipe.step + 6) % 7; showStep(); setPlaying(false); });
    $("#pipe-next").addEventListener("click", function () { pipe.step = (pipe.step + 1) % 7; showStep(); setPlaying(false); });
    $("#pipe-play").addEventListener("click", function () { setPlaying(!pipe.playing); });
    showStep(); setPlaying(pipe.playing);
  }

  // ------------------------------------------------------------------ 3. the meaning map
  var map = null;
  (function () {
    var cv = $("#mmap");
    if (!cv) return;
    var ctx = cv.getContext("2d"), W = 0, H = 0, dpr = 1, thr = .33, byPlace = true, sel = -1, hov = -1, P = [];
    // Positions from meaning only: classical MDS on the distance 1 - similarity (no place is used), then a
    // light push so dots do not overlap.
    (function layout() {
      var n = notes.length, i, j, it;
      var D2 = SIM.map(function (row) { return row.map(function (s) { var d = Math.pow(1 - Math.min(s, .66) / .66, .6); return d * d; }); });
      var rm = D2.map(function (r) { return r.reduce(function (a, b) { return a + b; }, 0) / n; });
      var all = rm.reduce(function (a, b) { return a + b; }, 0) / n;
      var B = D2.map(function (r, a) { return r.map(function (v, b) { return -.5 * (v - rm[a] - rm[b] + all); }); });
      function eig(M) {
        var v = M.map(function (_, k) { return rnd(k + 5) - .5; }), lam = 0;
        for (var t = 0; t < 300; t++) {
          var w = M.map(function (r) { return r.reduce(function (s, x, k) { return s + x * v[k]; }, 0); });
          lam = Math.sqrt(w.reduce(function (s, x) { return s + x * x; }, 0)) || 1;
          v = w.map(function (x) { return x / lam; });
        }
        return { v: v, l: lam };
      }
      var e1 = eig(B);
      var B2 = B.map(function (r, a) { return r.map(function (x, b) { return x - e1.l * e1.v[a] * e1.v[b]; }); });
      var e2 = eig(B2);
      for (i = 0; i < n; i++) P.push({ x: e1.v[i] * Math.sqrt(e1.l), y: e2.v[i] * Math.sqrt(e2.l) });
      for (it = 0; it < 120; it++) {
        for (i = 0; i < n; i++) for (j = i + 1; j < n; j++) {
          var dx = P[j].x - P[i].x, dy = P[j].y - P[i].y, d = Math.sqrt(dx * dx + dy * dy) || 1e-4, min = .09;
          if (d < min) { var f = (min - d) / d * .5; P[i].x -= dx * f; P[i].y -= dy * f; P[j].x += dx * f; P[j].y += dy * f; }
        }
      }
      function fit() {
        var x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
        P.forEach(function (p) { x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y); });
        P.forEach(function (p) { p.x = (p.x - x0) / (x1 - x0 || 1); p.y = (p.y - y0) / (y1 - y0 || 1); });
      }
      fit();
      for (it = 0; it < 200; it++) {   // room for every dot, in screen proportions
        for (i = 0; i < n; i++) for (j = i + 1; j < n; j++) {
          var ex = (P[j].x - P[i].x) * 1.6, ey = P[j].y - P[i].y, e = Math.sqrt(ex * ex + ey * ey) || 1e-4;
          if (e < .13) { var g = (.13 - e) / e * .25; P[i].x -= ex * g / 1.6; P[i].y -= ey * g; P[j].x += ex * g / 1.6; P[j].y += ey * g; }
        }
      }
      fit();
    })();
    function px(i) { return 40 + P[i].x * (W - 80); }
    function py(i) { return 34 + P[i].y * (H - 68); }
    function resize() {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      W = cv.clientWidth; H = cv.clientHeight;
      cv.width = W * dpr; cv.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
    }
    function pairs() {
      var out = [];
      for (var i = 0; i < notes.length; i++) for (var j = i + 1; j < notes.length; j++) if (SIM[i][j] >= thr) out.push([i, j, SIM[i][j]]);
      return out;
    }
    function colourOf(i) { return byPlace ? PLACES[notes[i].place].c : "#a9d4ff"; }
    function label(i, strong) {
      var t = notes[i].title, x = px(i), y = py(i);
      ctx.font = (strong ? "600 " : "500 ") + "12px Segoe UI, Inter, sans-serif";
      var w = ctx.measureText(t).width;
      var lx = Math.min(W - w - 8, Math.max(8, x - w / 2)), ly = y - 14;
      if (ly < 14) ly = y + 22;
      ctx.fillStyle = "rgba(34,50,74,.85)"; ctx.fillRect(lx - 4, ly - 11, w + 8, 16);
      ctx.fillStyle = strong ? "#f1f6fc" : "#b5c6da"; ctx.fillText(t, lx, ly + 1);
    }
    function draw() {
      if (!W) return;
      ctx.clearRect(0, 0, W, H);
      var pr = pairs(), focus = sel >= 0 ? sel : hov;
      ctx.setLineDash([4, 5]);
      pr.forEach(function (p) {
        var on = focus >= 0 && (p[0] === focus || p[1] === focus);
        ctx.strokeStyle = on ? "rgba(169,212,255,.95)" : "rgba(169,212,255," + (.12 + (p[2] - thr) * 1.6).toFixed(2) + ")";
        ctx.lineWidth = on ? 1.8 : 1;
        ctx.beginPath(); ctx.moveTo(px(p[0]), py(p[0])); ctx.lineTo(px(p[1]), py(p[1])); ctx.stroke();
      });
      ctx.setLineDash([]);
      if (lastQuery) {   // your question, dropped among the notes it means
        var qx = 0, qy = 0, ws = 0;
        lastQuery.hits.forEach(function (h) { var w = h.s * h.s; qx += px(h.n.i) * w; qy += py(h.n.i) * w; ws += w; });
        qx /= ws; qy /= ws; qy -= 6;
        lastQuery.hits.forEach(function (h) {
          ctx.strokeStyle = "rgba(255,210,161,.8)"; ctx.lineWidth = 1.4;
          ctx.beginPath(); ctx.moveTo(qx, qy); ctx.lineTo(px(h.n.i), py(h.n.i)); ctx.stroke();
        });
        ctx.fillStyle = "#ffd2a1"; ctx.beginPath();
        for (var k = 0; k < 10; k++) { var r = k % 2 ? 4 : 9, a = -Math.PI / 2 + k * Math.PI / 5; ctx[k ? "lineTo" : "moveTo"](qx + Math.cos(a) * r, qy + Math.sin(a) * r); }
        ctx.closePath(); ctx.fill();
        ctx.font = "600 12px Segoe UI, Inter, sans-serif"; ctx.fillStyle = "#ffd2a1";
        var qt = "“" + (lastQuery.q.length > 34 ? lastQuery.q.slice(0, 33) + "…" : lastQuery.q) + "”";
        ctx.fillText(qt, Math.min(W - ctx.measureText(qt).width - 8, Math.max(8, qx + 12)), qy - 10);
      }
      notes.forEach(function (n, i) {
        var near = focus >= 0 && (i === focus || SIM[focus][i] >= thr);
        var r = i === focus ? 9 : 6.5;
        ctx.globalAlpha = focus >= 0 && !near ? .35 : 1;
        ctx.fillStyle = colourOf(i);
        ctx.beginPath(); ctx.arc(px(i), py(i), r, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
      });
      if (focus >= 0) {
        notes.forEach(function (n, i) { if (i !== focus && SIM[focus][i] >= thr) label(i, false); });
        label(focus, true);
      } else if (W > 700) {
        [0, 9, 12, 17, 24, 22].forEach(function (i) { label(i, false); });
      }
      $("#thr-n").textContent = pr.length;
    }
    function pick(i) {
      sel = i;
      var box = $("#map-pick");
      if (i < 0) { box.innerHTML = '<p class="muted small">Click a dot to see its closest notes.</p>'; draw(); return; }
      var n = notes[i];
      var near = notes.map(function (o, j) { return { j: j, s: SIM[i][j] }; }).filter(function (o) { return o.j !== i; })
        .sort(function (a, b) { return b.s - a.s; }).slice(0, 5);
      box.innerHTML = "<h4>" + esc(n.title) + ' <span class="small muted">' + esc(PLACES[n.place].name) + "</span></h4>" +
        '<p class="small muted">' + esc(n.text) + "</p><ul>" + near.map(function (o) {
          return '<li class="' + (o.s < thr ? "weak" : "") + '"><span>' + esc(notes[o.j].title) + "</span><span>" + o.s.toFixed(2) + "</span></li>";
        }).join("") + "</ul>";
      draw();
    }
    function hit(e) {
      var r = cv.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top, best = -1, bd = 18 * 18;
      notes.forEach(function (n, i) { var dx = px(i) - x, dy = py(i) - y, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = i; } });
      return best;
    }
    cv.addEventListener("mousemove", function (e) { var h = hit(e); if (h !== hov) { hov = h; cv.style.cursor = h >= 0 ? "pointer" : "crosshair"; draw(); } });
    cv.addEventListener("mouseleave", function () { hov = -1; draw(); });
    cv.addEventListener("click", function (e) { var h = hit(e); pick(h === sel ? -1 : h); });
    $("#thr").addEventListener("input", function (e) { thr = +e.target.value; $("#thr-v").textContent = thr.toFixed(2); if (sel >= 0) pick(sel); else draw(); });
    $("#by-place").addEventListener("change", function (e) { byPlace = e.target.checked; $("#map-legend").style.opacity = byPlace ? 1 : .3; draw(); });
    $("#map-legend").innerHTML = PLACES.map(function (p) { return '<li><i style="background:' + p.c + '"></i>' + esc(p.name) + "</li>"; }).join("") +
      '';
    window.addEventListener("resize", resize);
    resize();
    map = { draw: draw };
  })();

  // ------------------------------------------------------------------ 4. models and routing
  var ROUTES = {
    type: { n: ["arch", "memory"], m: ["sol", "embed", "ocr"], t: "You type a message",
      s: ["<b>gpt-6-sol</b> reads it with about sixty tools it may use: search, file, link, open, undo.",
        "To search, your words become a vector (<b>text-embedding-3-small</b>) and the keyword index runs <b>on this computer</b>.",
        "It answers citing the items it used, or acts through a tool you can undo. At most 8 tool rounds."] },
    f8: { n: ["ear", "arch", "memory"], m: ["whisper", "sol", "embed"], t: "Hold F8, speak, let go",
      s: ["<b>gpt-realtime-whisper</b> writes down what you said, in your own language.",
        "Then the same road as typing: <b>gpt-6-sol</b> with its tools, the memory by meaning and by words."] },
    f9: { n: ["ear", "arch", "voice"], m: ["live", "whisper", "embed"], t: "F9: a live conversation",
      s: ["<b>gpt-realtime-2.1-mini</b> talks with you in real time, speech to speech; you can cut it off.",
        "It has the Archivist's persona and the same tools, so what it does is the same, visible and undoable.",
        "Your words are transcribed by <b>gpt-realtime-whisper</b> and saved with today's conversation."] },
    file: { n: ["reader", "arch", "memory"], m: ["ocr", "sol", "embed"], t: "You drop a document",
      s: ["<b>This computer</b> extracts the text page by page and keeps the original.",
        "<b>gpt-6-sol</b> summarises, files and links it.",
        "Every piece of about 1,200 characters gets its own vector (<b>text-embedding-3-small</b>), so answers cite the page."] },
    scan: { n: ["reader", "arch", "memory"], m: ["ocr", "sol", "embed"], t: "A scanned letter",
      s: ["Scanned pages are read <b>on this computer</b> by default (Windows OCR or Tesseract). A setting sends them to the vision model instead.",
        "Then the Archivist files it like any document."] },
    photo: { n: ["reader", "arch", "memory"], m: ["mini", "sol", "embed"], t: "A picture",
      s: ["<b>gpt-4o-mini</b> (vision) describes it and transcribes the text in it, so a picture becomes searchable.",
        "The Archivist files the description; the picture stays as the original."] },
    web: { n: ["arch", "reader", "memory"], m: ["sol", "mini", "ocr", "embed"], t: "Search the web",
      s: ["<b>gpt-6-sol</b> decides to search; <b>gpt-4o-mini</b> runs OpenAI's hosted web search and brings sources.",
        "Keep a page: <b>this computer</b> downloads it, keeps the original, and it is indexed like the rest."] },
    review: { n: ["memory", "arch", "voice"], m: ["astra", "embed", "tts"], t: "The weekly review",
      s: ["A reasoning model, <b>gpt-6-astra</b> (low effort), reads your week: it cites notes and connects facts.",
        "Measured: about 10 s, and deeper than a fast chat model. Ask “read it to me” and <b>gpt-4o-mini-tts</b> speaks it."] },
    mission: { n: ["arch", "reader", "memory"], m: ["sol", "mini", "ocr"], t: "A mission",
      s: ["A long job (many searches, many pages) runs in the background on <b>gpt-6-sol</b>, within a cost and time limit you set.",
        "When a choice is yours, it asks; nothing enters your Brain before you approve."] }
  };
  (function () {
    var root = $("#route");
    if (!root) return;
    var svg = $("#route-wires"), cur = null;
    function centre(el, side) {
      var r = el.getBoundingClientRect(), o = root.getBoundingClientRect();
      return { x: (side === "r" ? r.right : side === "l" ? r.left : r.left + r.width / 2) - o.left, y: r.top + r.height / 2 - o.top };
    }
    function wire(a, b, cls) {
      var dx = (b.x - a.x) * .5;
      return '<path class="' + (cls || "") + '" d="M' + a.x + "," + a.y + " C" + (a.x + dx) + "," + a.y + " " + (b.x - dx) + "," + b.y + " " + b.x + "," + b.y + '"/>';
    }
    function show(key) {
      cur = key;
      var R = ROUTES[key];
      $$(".route-in button", root).forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-r") === key ? "true" : "false"); });
      $$(".route-node", root).forEach(function (n) { var on = R.n.indexOf(n.getAttribute("data-n")) >= 0; n.classList.toggle("lit", on); n.classList.toggle("dim", !on); });
      $$(".route-model", root).forEach(function (n) { var on = R.m.indexOf(n.getAttribute("data-m")) >= 0; n.classList.toggle("lit", on); n.classList.toggle("dim", !on); });
      $("#route-why").innerHTML = "<h3>" + esc(R.t) + "</h3><ol>" + R.s.map(function (s) { return "<li>" + s + "</li>"; }).join("") + "</ol>";
      wires();
    }
    function wires() {
      if (!cur || getComputedStyle(svg).display === "none") { svg.innerHTML = ""; return; }
      var R = ROUTES[cur], btn = $('.route-in button[data-r="' + cur + '"]', root), out = "";
      var mids = R.n.map(function (k) { return $('.route-node[data-n="' + k + '"]', root); });
      var midVisible = mids[0] && mids[0].offsetParent !== null;
      var a = centre(btn, "r");
      if (midVisible) {
        mids.forEach(function (m) { out += wire(a, centre(m, "l")); });
        R.m.forEach(function (k, i) {
          var mEl = $('.route-model[data-m="' + k + '"]', root), from = mids[Math.min(i, mids.length - 1)];
          out += wire(centre(from, "r"), centre(mEl, "l"), k === "ocr" ? "local" : "");
        });
      } else {
        R.m.forEach(function (k) { out += wire(a, centre($('.route-model[data-m="' + k + '"]', root), "l"), k === "ocr" ? "local" : ""); });
      }
      svg.innerHTML = out;
    }
    $$(".route-in button", root).forEach(function (b) { b.addEventListener("click", function () { show(b.getAttribute("data-r")); }); });
    window.addEventListener("resize", wires);
    show("type");
  })();

  // ------------------------------------------------------------------ 5. an agent's tool trace
  var TRACE = [
    ["you", "What did I decide about the countertop, and what will it cost?"],
    ["state", "searching"],
    ["call", 'search_notes(<span class="fn">"countertop decision"</span>)'],
    ["res", '<span class="m">meaning</span> Quartz or granite? · 0.61 · Kitchen renovation<br><span class="m">meaning</span> Quartz quote · 0.52<br><span class="m">meaning</span> Renovation budget · 0.38', 3, 600],
    ["call", 'get_note(<span class="fn">"Quartz or granite?"</span>)'],
    ["res", '"Quartz needs no sealing… Leaning quartz for the island."', 4, 900],
    ["call", 'search_sources(<span class="fn">"quartz price installed"</span>)'],
    ["res", '<span class="m">meaning</span> countertop-quote.pdf · p.2 · 0.57<br>"Quartz, white, 3 cm, installed: $4,200 …"', 5, 1400],
    ["state", "answering"],
    ["say", 'You were leaning toward <b>quartz</b>: no sealing, and it resists stains <span class="cite">1</span>. The quote is <b>$4,200 installed</b>, valid until Nov 30 <span class="cite">2</span>, about 11 % of your $38,000 budget <span class="cite">3</span>.'],
    ["you", "Add a task to sign the quote before the 30th."],
    ["call", 'add_task(<span class="fn">"Sign the countertop quote"</span>, due=<span class="fn">"Nov 28"</span>, place=<span class="fn">"Kitchen renovation"</span>)'],
    ["receipt", "Task · Kitchen renovation · due Nov 28 · linked to the quote<u>Undo</u>"],
    ["state", "ready"]
  ];
  (function () {
    var log = $("#trace-log");
    if (!log) return;
    var playing = false, timers = [];
    function reset() { timers.forEach(clearTimeout); timers = []; log.innerHTML = ""; setCtx(0, 0); state("ready"); }
    function state(s) { var el = $("#trace-state"); el.textContent = s; el.classList.toggle("busy", s !== "ready"); }
    function setCtx(items, tok) {
      $("#ctx-items").textContent = items + (items === 1 ? " item" : " items");
      $("#ctx-tok").textContent = tok.toLocaleString("en-US") + " tokens";
      $("#ctx-fill").style.width = Math.max(items ? 1.2 : 0, tok / 3000000 * 100 * 40) + "%";
    }
    function line(t) {
      if (t[0] === "state") { state(t[1]); return; }
      var el = document.createElement("div");
      el.className = "tl " + t[0];
      el.innerHTML = t[0] === "you" ? esc(t[1]) : t[1];
      log.appendChild(el);
      log.scrollTop = log.scrollHeight;
      if (t[2]) setCtx(t[2], t[3] * (t[2] > 3 ? 2.1 : 1));
    }
    function play() {
      reset(); playing = true;
      $("#trace-play").textContent = "↺ Replay";
      var at = 200;
      TRACE.forEach(function (t) {
        timers.push(setTimeout(function () { line(t); }, reduce ? 0 : at));
        at += t[0] === "you" ? 1100 : t[0] === "say" ? 1800 : t[0] === "state" ? 300 : 800;
      });
      timers.push(setTimeout(function () { playing = false; }, at));
    }
    $("#trace-play").addEventListener("click", play);
    if ("IntersectionObserver" in window) {
      var seen = false;
      new IntersectionObserver(function (en) { if (en[0].isIntersecting && !seen) { seen = true; play(); } }, { threshold: .35 }).observe(log);
    } else play();
  })();

  // ------------------------------------------------------------------ 6. the MCP loop
  var MSGS = [
    '// Claude Code → Brain\n{ "method": "tools/call",\n  "params": { "name": "search",\n    "arguments": { "query": "what do we know about the countertop quote?" } } }',
    '// Brain → Claude Code (short and paged: an agent\'s context is precious)\n{ "items": [\n  { "id": "d1f0…", "title": "Quartz quote", "match": "meaning" },\n  { "id": "a9c2…", "title": "Quartz or granite?", "match": "meaning" },\n  { "id": "77e1…", "title": "Renovation budget", "match": "words" } ] }',
    '// Claude Code → Brain   (level: propose items)\n{ "method": "tools/call",\n  "params": { "name": "propose_item",\n    "arguments": { "title": "Quartz vs granite: cost over 10 years",\n      "content": "…", "reason": "compared for the owner today" } } }',
    '// The Archivist files it with your rules\n{ "proposal": "p7c…", "status": "applied",\n  "receipt": "Filed in Kitchen renovation, linked to 2 items." }\n// or "waiting": your rules ask for your OK first',
    '// Tomorrow, another session (Codex)\n{ "name": "search", "arguments": { "query": "granite long-term cost" } }\n→ "Quartz vs granite: cost over 10 years" · meaning · proposed by Claude Code'
  ];
  (function () {
    var svg = $("#loop-svg");
    if (!svg) return;
    var NS = "http://www.w3.org/2000/svg", cx = 210, cy = 210, R = 150, k = 0, timer = 0, visible = false;
    var LBL = ["Ask", "Answer", "Propose", "File", "Remember"];
    function el(tag, at, parent) { var e = document.createElementNS(NS, tag); for (var a in at) e.setAttribute(a, at[a]); (parent || svg).appendChild(e); return e; }
    el("circle", { cx: cx, cy: cy, r: R, "class": "ring" });
    var circ = 2 * Math.PI * R;
    var on = el("circle", { cx: cx, cy: cy, r: R, "class": "ring-on", "stroke-dasharray": circ, "stroke-dashoffset": circ, transform: "rotate(-90 " + cx + " " + cy + ")" });
    el("circle", { cx: cx, cy: cy, r: 62, "class": "hub" });
    var t1 = el("text", { x: cx, y: cy - 4, "class": "hub-t" }); t1.textContent = "Second Brain";
    var t2 = el("text", { x: cx, y: cy + 16, "class": "hub-s" }); t2.textContent = "the Archivist decides";
    var sts = LBL.map(function (l, i) {
      var a = -Math.PI / 2 + i / 5 * Math.PI * 2, x = cx + Math.cos(a) * R, y = cy + Math.sin(a) * R;
      var g = el("g", { "class": "st" });
      el("circle", { cx: x, cy: y, r: 20 }, g);
      var n = el("text", { x: x, y: y + 1 }, g); n.textContent = i + 1;
      var lx = cx + Math.cos(a) * (R + 40), ly = cy + Math.sin(a) * (R + 40) + 4;
      var t = el("text", { x: lx, y: ly, "class": "lbl" }); t.textContent = l;
      g.style.cursor = "pointer";
      g.addEventListener("click", function () { go(i, true); });
      return g;
    });
    var pk = el("circle", { r: 6, "class": "pk", cx: cx, cy: cy - R });
    function go(i, user) {
      k = i;
      sts.forEach(function (g, j) { g.classList.toggle("on", j === i); });
      on.setAttribute("stroke-dashoffset", circ * (1 - (i + 1) / 5));
      var a = -Math.PI / 2 + i / 5 * Math.PI * 2;
      pk.setAttribute("cx", cx + Math.cos(a) * R); pk.setAttribute("cy", cy + Math.sin(a) * R);
      $$("#loop-steps li").forEach(function (li, j) { li.classList.toggle("on", j === i); });
      $("#loop-msg").innerHTML = colour(MSGS[i]);
      clearTimeout(timer);
      if (!reduce && visible) timer = setTimeout(function () { go((k + 1) % 5); }, user ? 9000 : 4200);
    }
    $$("#loop-steps li").forEach(function (li, j) { li.addEventListener("click", function () { go(j, true); }); });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (en) { visible = en[0].isIntersecting; if (visible) go(k); else clearTimeout(timer); }, { threshold: .3 }).observe(svg);
    }
    go(0);
  })();

  // Pause the capture walkthrough when it is off screen.
  if ("IntersectionObserver" in window && $("#pipe")) {
    new IntersectionObserver(function (en) { pipe.visible = en[0].isIntersecting; pipeTick(); }, { threshold: .25 }).observe($("#pipe"));
  } else pipe.visible = true;

  runQuery("what did I decide for the countertop?");
  if (askQ) askQ.value = "";
  // The demos change the page's height while it loads: land on the section a link points to.
  if (location.hash.length > 1) {
    var target = document.getElementById(location.hash.slice(1));
    if (target) window.addEventListener("load", function () { target.scrollIntoView(); });
  }
})();
