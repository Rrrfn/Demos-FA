/* =========================================================
   پورتفولیو — اسکریپت
   سه وظیفه، بدون کتابخانه:
     ۱) منوی موبایل
     ۲) نوار پیشرفت اسکرول
     ۳) ظاهرشدن تدریجی بخش‌ها
   ========================================================= */
(function () {
  "use strict";

  var root = document.documentElement;
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  root.classList.add("js");

  /* ── ۱) منوی موبایل ── */
  var toggle = document.getElementById("navToggle");
  var nav = document.getElementById("navLinks");

  function closeNav() {
    if (!nav) return;
    nav.classList.remove("is-open");
    if (toggle) {
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "گشودن فهرست");
    }
  }

  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute(
        "aria-label",
        open ? "بستن فهرست" : "گشودن فهرست"
      );
    });

    nav.addEventListener("click", function (e) {
      if (e.target.tagName === "A") closeNav();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape" || !nav.classList.contains("is-open")) return;
      closeNav();
      toggle.focus();
    });
  }

  /* ── ۲) نوار پیشرفت و چسبیدن نوار بالا ── */
  var rail = document.getElementById("scrollRail");
  var header = document.querySelector(".nav");
  var scrollable = 1;
  var ticking = false;
  var pending = [];

  function sweep() {
    if (!pending.length) return;
    var limit = window.innerHeight * 0.92;
    pending = pending.filter(function (el) {
      var rect = el.getBoundingClientRect();
      if (el.classList.contains("in")) return false;
      if (rect.top < limit && rect.bottom > 0) {
        el.classList.add("in");
        return false;
      }
      return true;
    });
  }

  function measure() {
    scrollable = Math.max(1, root.scrollHeight - window.innerHeight);
  }

  function frame() {
    ticking = false;
    var y = window.pageYOffset || root.scrollTop;

    if (rail) {
      var ratio = Math.min(1, Math.max(0, y / scrollable));
      rail.style.transform = "scaleX(" + ratio.toFixed(4) + ")";
    }

    if (header) header.classList.toggle("is-stuck", y > 12);

    sweep();
  }

  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(frame);
  }

  measure();
  frame();
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", function () {
    measure();
    onScroll();
  });
  window.addEventListener("load", onScroll);

  /* ── ۳) ظاهرشدن تدریجی ── */
  var supported =
    "IntersectionObserver" in window && !reduced.matches;

  if (supported) {
    var targets = document.querySelectorAll(
      ".section__inner, .case, .card, .cap, .step, .trust__item, " +
      ".approach__steps li, .techstack, .about__text, .cta__inner"
    );

    var groupCount = {};
    Array.prototype.forEach.call(targets, function (el) {
      var key = (el.parentElement && el.parentElement.className) || "";
      groupCount[key] = (groupCount[key] || 0) + 1;
      el.style.setProperty("--d", ((groupCount[key] - 1) % 6) * 60 + "ms");
      el.classList.add("rv");
    });

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("in");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.06 }
    );

    Array.prototype.forEach.call(targets, function (el) {
      pending.push(el);
      observer.observe(el);
    });

    sweep();

    var sweeper = window.setInterval(function () {
      sweep();
      if (!pending.length) window.clearInterval(sweeper);
    }, 250);

    window.setTimeout(function () {
      window.clearInterval(sweeper);
      pending.forEach(function (el) { el.classList.add("in"); });
      pending = [];
    }, 15000);
  }
})();
