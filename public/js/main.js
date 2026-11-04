// Second Brain GD landing page. No dependencies, no network calls.
(function () {
  "use strict";
  document.documentElement.classList.add("js");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Mobile navigation
  var toggle = document.querySelector(".nav-toggle");
  var links = document.getElementById("nav-links");
  if (toggle && links) {
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    links.addEventListener("click", function (e) {
      if (e.target.tagName === "A") { links.classList.remove("open"); toggle.setAttribute("aria-expanded", "false"); }
    });
  }

  // Reveal sections on scroll
  var targets = document.querySelectorAll(".card, .code-flow li, .feature, .gallery figure, .arch-node, .road-col, .doc-cards a");
  if ("IntersectionObserver" in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("visible"); io.unobserve(en.target); } });
    }, { threshold: 0.12 });
    targets.forEach(function (t) { t.classList.add("reveal"); io.observe(t); });
  }


  // Journal: phase filters, rail, reader dialog
  var reader = document.getElementById("reader");
  function openLoop(card) {
    if (!reader || !card) return;
    card.hidden = false;
    var img = card.querySelector(".loop-thumb img");
    reader.querySelector(".reader-img").innerHTML = img ? '<img alt="" src="' + img.getAttribute("src") + '">' : "";
    reader.querySelector(".loop-meta").innerHTML = card.querySelector(".loop-meta").innerHTML;
    reader.querySelector("#reader-title").textContent = card.querySelector(".loop-open").textContent;
    reader.querySelector(".reader-text").innerHTML = card.querySelector(".loop-full").innerHTML;
    reader.className = "reader " + card.className.replace("loop-card", "").trim();
    if (reader.showModal) reader.showModal(); else reader.setAttribute("open", "");
    if (history.replaceState) history.replaceState(null, "", "#" + card.id);
  }
  if (reader) {
    reader.querySelector(".reader-close").addEventListener("click", function () { reader.close(); });
    reader.addEventListener("click", function (e) { if (e.target === reader) reader.close(); });
    document.querySelectorAll(".loop-open").forEach(function (b) {
      b.addEventListener("click", function () { openLoop(b.closest(".loop-card")); });
    });
    document.querySelectorAll(".rail button").forEach(function (b) {
      b.addEventListener("click", function () { openLoop(document.getElementById(b.getAttribute("data-target"))); });
    });
    var loopsBox = document.querySelector(".loops");
    var more = document.querySelector(".loops-more");
    if (more) more.addEventListener("click", function () { loopsBox.classList.remove("collapsed"); });
    var phaseButtons = document.querySelectorAll(".phases button");
    phaseButtons.forEach(function (b) {
      b.addEventListener("click", function () {
        var ph = b.getAttribute("data-phase");
        if (ph !== "all") loopsBox.classList.remove("collapsed");
        phaseButtons.forEach(function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
        document.querySelectorAll(".loop-card").forEach(function (c) {
          c.hidden = ph !== "all" && c.getAttribute("data-phase") !== ph;
        });
        document.querySelectorAll(".rail button").forEach(function (r) {
          var c = document.getElementById(r.getAttribute("data-target"));
          r.classList.toggle("dim", !!(c && c.hidden));
        });
      });
    });
    var m = location.hash.match(/^#(loop-[\w-]+)$/);
    if (m && document.getElementById(m[1])) openLoop(document.getElementById(m[1]));
  }

  // Screenshots open full size
  var lb = document.getElementById("lightbox");
  if (lb) {
    document.querySelectorAll(".shot img").forEach(function (im) {
      im.parentNode.setAttribute("tabindex", "0");
      im.parentNode.setAttribute("role", "button");
      var open = function () {
        lb.querySelector("img").src = im.currentSrc || im.src;
        lb.querySelector("img").alt = im.alt;
        var cap = im.parentNode.querySelector("figcaption");
        lb.querySelector("p").textContent = cap ? cap.textContent : "";
        if (lb.showModal) lb.showModal();
      };
      im.parentNode.addEventListener("click", open);
      im.parentNode.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
    });
    lb.addEventListener("click", function () { lb.close(); });
  }

  // Docs: copy buttons, scroll-spy, filter, mobile table of contents
  document.querySelectorAll(".doc pre").forEach(function (pre) {
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "copy"; btn.textContent = "Copy";
    btn.addEventListener("click", function () {
      var text = pre.querySelector("code") ? pre.querySelector("code").innerText : pre.innerText;
      var done = function () { btn.textContent = "Copied"; setTimeout(function () { btn.textContent = "Copy"; }, 1400); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () {}); 
    });
    pre.appendChild(btn);
  });
  var byId = null;
  var navLinks = document.querySelectorAll(".docs-nav a[href^='#']");
  if (navLinks.length && "IntersectionObserver" in window) {
    byId = {};
    navLinks.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting && byId[en.target.id]) {
          navLinks.forEach(function (a) { a.classList.remove("active"); });
          byId[en.target.id].classList.add("active");
        }
      });
    }, { rootMargin: "-80px 0px -70% 0px" });
    document.querySelectorAll(".doc[id]").forEach(function (d) { spy.observe(d); });
  }
  var filter = document.querySelector(".docs-search");
  if (filter) {
    filter.addEventListener("input", function () {
      var q = filter.value.trim().toLowerCase();
      document.querySelectorAll(".doc[id]").forEach(function (d) {
        var hit = !q || d.textContent.toLowerCase().indexOf(q) !== -1;
        d.hidden = !hit;
        if (byId && byId[d.id]) byId[d.id].parentNode.hidden = !hit;
      });
    });
  }
  var toc = document.querySelector(".docs-toc-toggle");
  if (toc) toc.addEventListener("click", function () {
    var nav = document.querySelector(".docs-nav");
    var open = nav.classList.toggle("open");
    toc.setAttribute("aria-expanded", open ? "true" : "false");
  });

  // Knowledge-graph background in the hero
  var canvas = document.getElementById("graph");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var nodes = [], w = 0, h = 0, dpr = 1, raf = 0;

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var count = Math.round(Math.min(70, Math.max(22, (w * h) / 22000)));
    nodes = [];
    for (var i = 0; i < count; i++) {
      nodes.push({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - .5) * .25, vy: (Math.random() - .5) * .25,
        r: 1.5 + Math.random() * 2.5, p: Math.random() * Math.PI * 2 });
    }
  }

  function frame(t) {
    ctx.clearRect(0, 0, w, h);
    var maxD = Math.min(170, w / 5);
    for (var i = 0; i < nodes.length; i++) {
      var a = nodes[i];
      if (!reduce) {
        a.x += a.vx; a.y += a.vy;
        if (a.x < 0 || a.x > w) a.vx *= -1;
        if (a.y < 0 || a.y > h) a.vy *= -1;
      }
      for (var j = i + 1; j < nodes.length; j++) {
        var b = nodes[j], dx = a.x - b.x, dy = a.y - b.y, d = Math.sqrt(dx * dx + dy * dy);
        if (d < maxD) {
          ctx.strokeStyle = "rgba(121,165,211," + (0.35 * (1 - d / maxD)).toFixed(3) + ")";
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
    }
    for (var k = 0; k < nodes.length; k++) {
      var n = nodes[k], glow = reduce ? .6 : .5 + .5 * Math.sin(t / 900 + n.p);
      ctx.fillStyle = "rgba(169,212,255," + (0.08 + 0.10 * glow).toFixed(3) + ")";
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r * 3.2, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "rgba(169,212,255," + (0.55 + 0.4 * glow).toFixed(3) + ")";
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill();
    }
    if (!reduce) raf = requestAnimationFrame(frame);
  }

  resize();
  window.addEventListener("resize", function () { cancelAnimationFrame(raf); resize(); frame(performance.now()); });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) cancelAnimationFrame(raf); else if (!reduce) raf = requestAnimationFrame(frame);
  });
  frame(performance.now());
})();
