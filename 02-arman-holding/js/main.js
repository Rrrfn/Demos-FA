/* =========================================================
   هلدینگ آرمان — تعاملات سایت (ظریف و سازمانی)
   ========================================================= */
(function () {
  "use strict";

  /* ---------- ۱) هدر چسبان: سایه هنگام اسکرول ---------- */
  const header = document.getElementById("header");
  if (header) {
    const onScroll = () => header.classList.toggle("scrolled", window.scrollY > 10);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ---------- ۲) مگامنو «حوزه‌های فعالیت» ---------- */
  const megaTrigger = document.querySelector('[data-mega]');
  const mega = document.getElementById("mega");
  if (megaTrigger && mega) {
    const open = (openFlag) => {
      mega.classList.toggle("open", openFlag);
      megaTrigger.setAttribute("aria-expanded", String(openFlag));
      megaTrigger.parentElement.classList.toggle("open", openFlag);
    };
    megaTrigger.addEventListener("click", (e) => {
      e.preventDefault();
      open(!mega.classList.contains("open"));
    });
    // بستن با کلیک بیرون یا Esc
    document.addEventListener("click", (e) => {
      if (!megaTrigger.contains(e.target) && !mega.contains(e.target)) open(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") open(false);
    });
    // بستن با کلیک روی هر گزینه
    mega.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => open(false)));
  }

  /* ---------- ۳) منوی موبایل ---------- */
  const navToggle = document.getElementById("navToggle");
  const nav = document.getElementById("nav");
  if (navToggle && nav) {
    navToggle.addEventListener("click", () => {
      const isOpen = nav.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", String(isOpen));
      navToggle.textContent = isOpen ? "✕" : "☰";
    });
    nav.querySelectorAll("a").forEach((a) =>
      a.addEventListener("click", () => {
        nav.classList.remove("open");
        navToggle.setAttribute("aria-expanded", "false");
        navToggle.textContent = "☰";
      })
    );
  }

  /* ---------- ۴) نمایش تدریجی هنگام اسکرول ---------- */
  const revealEls = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && revealEls.length) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    revealEls.forEach((el) => io.observe(el));
  } else {
    revealEls.forEach((el) => el.classList.add("visible"));
  }

  /* ---------- ۵) شمارنده اعداد (ارقام فارسی) ---------- */
  const FA = "۰۱۲۳۴۵۶۷۸۹";
  const toFa = (s) => String(s).replace(/\d/g, (d) => FA[+d]);
  const counters = document.querySelectorAll("[data-count]");
  if (counters.length) {
    const animate = (el) => {
      const raw = el.getAttribute("data-count");
      const hasComma = raw.includes("٬");
      const faDigits = { "۰": 0, "۱": 1, "۲": 2, "۳": 3, "۴": 4, "۵": 5, "۶": 6, "۷": 7, "۸": 8, "۹": 9 };
      const latin = String(raw).replace(/[۰-۹]/g, (d) => faDigits[d]);
      const target = parseFloat(latin.replace(/[^\d.]/g, "")) || 0;
      const start = performance.now();
      const dur = 1500;
      const frame = (now) => {
        const p = Math.min((now - start) / dur, 1);
        const eased = 1 - Math.pow(1 - p, 3);
        const v = Math.round(target * eased);
        const grouped = hasComma ? v.toLocaleString("en-US").replace(/,/g, "٬") : String(v);
        el.textContent = (raw.startsWith("+") ? "+" : "") + toFa(grouped);
        if (p < 1) requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
    };
    const cio = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            animate(entry.target);
            cio.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.5 }
    );
    counters.forEach((c) => cio.observe(c));
  }

  /* ---------- ۶) فرم تماس: اعتبارسنجی + نمایش پیام موفق ---------- */
  const form = document.getElementById("contactForm");
  const success = document.getElementById("formSuccess");
  if (form && success) {
    const markInvalid = (row) => row.classList.add("invalid");
    const markValid = (row) => row.classList.remove("invalid");
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const name = document.getElementById("cf-name");
      const email = document.getElementById("cf-email");
      const msg = document.getElementById("cf-msg");
      let ok = true;
      if (!name.value.trim()) { markInvalid(name.closest(".form-row")); ok = false; }
      else markValid(name.closest(".form-row"));
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value.trim())) { markInvalid(email.closest(".form-row")); ok = false; }
      else markValid(email.closest(".form-row"));
      if (!msg.value.trim()) { markInvalid(msg.closest(".form-row")); ok = false; }
      else markValid(msg.closest(".form-row"));
      if (ok) {
        form.style.display = "none";
        success.classList.add("show");
      }
    });
    // پاک‌سازی خطا هنگام تایپ
    form.querySelectorAll("input, textarea").forEach((input) =>
      input.addEventListener("input", () => markValid(input.closest(".form-row")))
    );
    document.getElementById("successClose").addEventListener("click", () => {
      form.reset();
      success.classList.remove("show");
      form.style.display = "block";
    });
  }
})();