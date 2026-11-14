// The home page's feature format (SITE-J): the bar that follows the reader, and the pictures with numbered points.
// No dependency, no network call.
(function () {
  "use strict";
  var header = document.querySelector(".site-header");
  var nav = document.querySelector(".featnav");
  var sections = Array.prototype.slice.call(document.querySelectorAll(".feat-sec"));

  // ---------------------------------------------------------------- the bar that follows the reader
  if (nav && sections.length) {
    var links = Array.prototype.slice.call(nav.querySelectorAll("a"));
    var progress = nav.querySelector(".featnav-progress");
    var index = document.querySelector(".features-index");
    var last = document.getElementById(links[links.length - 1].getAttribute("href").slice(1)) || sections[sections.length - 1];
    var current = "";
    var onScroll = function () {
      var h = header ? header.offsetHeight : 57;
      document.documentElement.style.setProperty("--header-h", h + "px");
      var top = index ? index.getBoundingClientRect().bottom : 0;
      var end = last.getBoundingClientRect().bottom;
      nav.classList.toggle("show", top < h && end > h + 80);
      var first = sections[0].getBoundingClientRect().top + window.scrollY;
      var total = last.getBoundingClientRect().bottom + window.scrollY - first;
      var done = Math.max(0, Math.min(1, (window.scrollY + h - first) / Math.max(1, total)));
      if (progress) progress.style.transform = "scaleX(" + done.toFixed(4) + ")";
      var now = "";
      links.forEach(function (a) {
        var t = document.getElementById(a.getAttribute("href").slice(1));
        if (t && t.getBoundingClientRect().top - h - 60 <= 0) now = a.getAttribute("href");
      });
      if (now !== current) {
        current = now;
        links.forEach(function (a) {
          var on = a.getAttribute("href") === now;
          a.classList.toggle("on", on);
          if (on && nav.classList.contains("show")) {
            var box = nav.querySelector(".featnav-in");
            box.scrollLeft = a.offsetLeft - box.clientWidth / 2 + a.clientWidth / 2;
          }
        });
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    onScroll();
  }

  // ---------------------------------------------------------------- the film in the hero
  // Muted and looping while it is in view; « Sound » plays it once from the start with its narration, then it goes
  // back to the silent loop. With reduced motion or data saving it does not start by itself: the poster, and a click.
  var film = document.querySelector("video.film");
  if (film) {
    var sound = document.querySelector(".film-sound"), pause = document.querySelector(".film-pause"), full = document.querySelector(".film-full");
    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var saveData = !!(navigator.connection && navigator.connection.saveData);
    var auto = !reduce && !saveData, held = false;
    film.muted = true;
    var show = function () {
      sound.textContent = film.muted ? "🔊 Sound" : "🔇 Mute";
      sound.setAttribute("aria-pressed", String(!film.muted));
      pause.textContent = film.paused ? "▶" : "❚❚";
      pause.setAttribute("aria-label", film.paused ? "Play the film" : "Pause the film");
    };
    var play = function () { var p = film.play(); if (p && p.catch) p.catch(function () {}); };
    // the film opens on a fade from black: the silent loop starts just after it (with the sound, from the start)
    film.addEventListener("loadedmetadata", function () { if (film.muted && film.currentTime < 1) film.currentTime = 1.0; }, { once: true });
    if (auto && "IntersectionObserver" in window) {
      new IntersectionObserver(function (es) {
        es.forEach(function (e) {
          if (e.isIntersecting) { if (!held) play(); } else if (film.muted) film.pause();
        });
      }, { threshold: 0.25 }).observe(film);
    }
    sound.addEventListener("click", function () {
      if (film.muted) { film.muted = false; film.loop = false; film.currentTime = 0; held = false; play(); }
      else { film.muted = true; film.loop = true; }
      show();
    });
    pause.addEventListener("click", function () { if (film.paused) { held = false; play(); } else { held = true; film.pause(); } });
    film.addEventListener("click", function () { if (film.paused) { held = false; play(); } else { held = true; film.pause(); } });
    if (full) full.addEventListener("click", function () { if (film.requestFullscreen) film.requestFullscreen(); else if (film.webkitEnterFullscreen) film.webkitEnterFullscreen(); });
    film.addEventListener("ended", function () { film.muted = true; film.loop = true; show(); if (auto) play(); });
    ["play", "pause", "volumechange"].forEach(function (ev) { film.addEventListener(ev, show); });
    show();
  }

  // ---------------------------------------------------------------- pictures with numbered points
  var SVG = "http://www.w3.org/2000/svg";
  document.querySelectorAll("[data-anno]").forEach(function (anno) {
    var svg = anno.querySelector(".anno-lines");
    var cards = Array.prototype.slice.call(anno.querySelectorAll(".anno-card"));
    var paths = {};
    var light = function (n, on) {
      anno.querySelectorAll('.anno-card[data-for="' + n + '"], .hot[data-n="' + n + '"]').forEach(function (el) { el.classList.toggle("on", on); });
      if (paths[n]) paths[n].classList.toggle("on", on);
    };
    var draw = function () {
      if (!svg) return;
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      paths = {};
      if (window.matchMedia("(max-width: 960px)").matches) return;
      var box = anno.getBoundingClientRect();
      cards.forEach(function (card) {
        var n = card.getAttribute("data-for");
        var hot = anno.querySelector('.hot[data-n="' + n + '"]');
        if (!hot) return;
        var c = card.getBoundingClientRect(), p = hot.getBoundingClientRect();
        var px = p.left + p.width / 2 - box.left, py = p.top + p.height / 2 - box.top;
        var leftSide = c.left + c.width / 2 < p.left;
        var cx = (leftSide ? c.right : c.left) - box.left, cy = c.top + c.height / 2 - box.top;
        var mid = (cx + px) / 2;
        var path = document.createElementNS(SVG, "path");
        path.setAttribute("d", "M" + cx + " " + cy + " C" + mid + " " + cy + " " + mid + " " + py + " " + px + " " + py);
        svg.appendChild(path);
        paths[n] = path;
      });
    };
    cards.forEach(function (card) {
      var n = card.getAttribute("data-for");
      ["mouseenter", "focus"].forEach(function (ev) { card.addEventListener(ev, function () { light(n, true); }); });
      ["mouseleave", "blur"].forEach(function (ev) { card.addEventListener(ev, function () { light(n, false); }); });
    });
    anno.querySelectorAll(".hot").forEach(function (hot) {
      var n = hot.getAttribute("data-n");
      hot.addEventListener("mouseenter", function () { light(n, true); });
      hot.addEventListener("mouseleave", function () { light(n, false); });
    });
    // the picture at full size, in the page's own lightbox: a click on it, or the « Whole picture » button
    var lb = document.getElementById("lightbox"), pic = anno.querySelector(".hot-wrap img"), fig = anno.querySelector(".anno-fig");
    if (lb && pic && fig) {
      var open = function () {
        lb.querySelector("img").src = pic.currentSrc || pic.src;
        lb.querySelector("img").alt = pic.alt;
        var cap = fig.querySelector("figcaption");
        lb.querySelector("p").textContent = cap ? cap.textContent : "";
        if (lb.showModal) lb.showModal();
      };
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "whole"; btn.textContent = "⤢ Whole picture";
      btn.addEventListener("click", open);
      pic.addEventListener("click", open);
      fig.appendChild(btn);
    }
    window.addEventListener("resize", draw);
    window.addEventListener("load", draw);
    var img = anno.querySelector("img");
    if (img && !img.complete) img.addEventListener("load", draw);
    draw();
  });
})();
