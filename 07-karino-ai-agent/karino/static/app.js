/* کارینو — بهبود تدریجی.
   همهٔ مسیرها بدون جاوااسکریپت هم کار می‌کنند (فرم‌ها معمولی‌اند)؛ این
   اسکریپت فقط تجربه را بهتر می‌کند: بارگذاری بدون بارگذاری صفحه، کپی متن و
   بازخورد وضعیت روی دکمه‌ها. هیچ خطایی به کاربر «بی‌صدا» نشان داده نمی‌شود. */
(function () {
  "use strict";

  var API = "/api/v1";

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* ---------------------------------------------------------- کپی متن */

  function wireCopy(button, getText) {
    if (!button) { return; }
    button.addEventListener("click", function () {
      var text = getText();
      if (!text) { return; }
      var original = button.textContent;
      var done = function (ok) {
        button.textContent = ok ? "✓ کپی شد" : "کپی نشد";
        window.setTimeout(function () { button.textContent = original; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { done(true); },
                                                 function () { done(fallbackCopy(text)); });
      } else {
        done(fallbackCopy(text));
      }
    });
  }

  function fallbackCopy(text) {
    // مرورگرهای قدیمی یا بافت ناامن: textarea موقت
    try {
      var area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      var ok = document.execCommand("copy");
      document.body.removeChild(area);
      return ok;
    } catch (error) {
      return false;
    }
  }

  /* ---------------------------------------------------------- نمایش پیشنهاد */

  var output = $("#proposal-output");
  var outputBody = $("#proposal-body");
  var outputMeta = $("#proposal-meta");
  var copyBtn = $("#proposal-copy");

  var toneLabels = { formal: "رسمی", concise: "کوتاه", consultative: "مشورتی" };
  var variantLabels = { standard: "استاندارد", short: "کوتاه" };
  var writerLabels = { llm: "مدل زبانی", rule_based: "قاعده‌محور" };

  function showProposal(payload) {
    if (!output || !outputBody) { return; }
    outputBody.textContent = payload.body || "";
    if (outputMeta) {
      outputMeta.textContent =
        (toneLabels[payload.tone] || payload.tone) + " · " +
        (variantLabels[payload.variant] || payload.variant) + " · " +
        "نویسنده: " + (writerLabels[payload.writer] || payload.writer) +
        (payload.cached ? " · از حافظه" : "");
    }
    output.hidden = false;
    output.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function showError(message) {
    if (!output || !outputBody) { return; }
    outputBody.textContent = message;
    if (outputMeta) { outputMeta.textContent = "خطا"; }
    output.hidden = false;
  }

  if (copyBtn) {
    wireCopy(copyBtn, function () { return outputBody ? outputBody.textContent : ""; });
  }

  /* دکمهٔ «نمایش متن» در فهرست پیشنهادهای صفحهٔ آگهی */
  $$("[data-load-proposal]").forEach(function (button) {
    button.addEventListener("click", function () {
      var jobId = button.getAttribute("data-load-proposal");
      var tone = button.getAttribute("data-tone") || "formal";
      var variant = button.getAttribute("data-variant") || "standard";
      button.disabled = true;
      var original = button.textContent;

      fetch(API + "/jobs/" + jobId + "/proposal?tone=" + encodeURIComponent(tone) +
            "&variant=" + encodeURIComponent(variant), { headers: { Accept: "application/json" } })
        .then(function (response) { return response.json().then(function (body) {
          return { status: response.status, body: body };
        }); })
        .then(function (result) {
          if (result.body && result.body.ok && result.body.data && result.body.data.body) {
            showProposal({
              body: result.body.data.body,
              tone: tone,
              variant: variant,
              writer: result.body.data.writer || "rule_based",
              cached: true
            });
          } else {
            var message = (result.body && result.body.error && result.body.error.message) ||
                          "متن پیشنهاد در دسترس نیست.";
            showError(message);
          }
        })
        .catch(function () { showError("ارتباط با سرور برقرار نشد."); })
        .then(function () { button.disabled = false; button.textContent = original; });
    });
  });

  /* پس از ساخت پیشنهاد با فرم، به صفحه بازمی‌گردیم؛ هش در نشانی می‌گوید
     کدام نسخه ساخته شده. همان را بی‌درنگ نمایش می‌دهیم تا کاربر لازم نباشد
     دوباره دکمه را بزند. */
  if (window.location.hash.indexOf("#proposal-") === 0) {
    var parts = window.location.hash.replace("#proposal-", "").split("-");
    var hashTone = parts[0] || "formal";
    var hashVariant = parts[1] || "standard";
    var jobIdFromPath = (window.location.pathname.match(/\/jobs\/(\d+)/) || [])[1];

    if (jobIdFromPath && output) {
      fetch(API + "/jobs/" + jobIdFromPath + "/proposal?tone=" + encodeURIComponent(hashTone) +
            "&variant=" + encodeURIComponent(hashVariant), { headers: { Accept: "application/json" } })
        .then(function (response) { return response.json(); })
        .then(function (body) {
          if (body && body.ok && body.data && body.data.body) {
            showProposal({
              body: body.data.body, tone: hashTone, variant: hashVariant,
              writer: body.data.writer || "rule_based", cached: true
            });
          }
        })
        .catch(function () { /* بدون نمایش خطا؛ فرم دستی همچنان کار می‌کند */ });
    }
  }

  /* ---------------------------------------------------------- بازخورد فرم‌ها */

  $$("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector('button[type="submit"]');
      if (!button || button.disabled) { return; }
      var label = button.textContent;
      // غیرفعال‌سازی در تیک بعدی انجام می‌شود تا ارسال جاری مختل نشود؛
      // این کار جلوی ارسال دوباره (مثلاً دو بار اجرای جمع‌آوری) را می‌گیرد.
      window.setTimeout(function () {
        button.disabled = true;
        button.textContent = "در حال انجام…";
        window.setTimeout(function () {
          button.disabled = false;
          button.textContent = label;
        }, 20000);
      }, 0);
    });
  });

  /* ---------------------------------------------------------- به‌روزرسانی خودکار */

  /* صفحهٔ نمای کلی هر ۵ دقیقه وضعیت منابع را تازه می‌کند تا اگر جمع‌آوری
     پس‌زمینه دور تازه‌ای زد، بدون بازخوانی دستی دیده شود. اعداد کلیدی هم
     به‌روز می‌شوند. خطا بی‌صدا نادیده گرفته می‌شود — این یک بهبود اختیاری است. */
  var liveIndicator = $("[data-live-status]");
  if (liveIndicator) {
    window.setInterval(function () {
      fetch(API + "/overview", { headers: { Accept: "application/json" } })
        .then(function (response) { return response.ok ? response.json() : null; })
        .then(function (body) {
          if (!body || !body.ok) { return; }
          var stamp = new Date().toLocaleTimeString("fa-IR");
          liveIndicator.textContent = "آخرین به‌روزرسانی: " + stamp;
        })
        .catch(function () { liveIndicator.textContent = "به‌روزرسانی خودکار در دسترس نیست"; });
    }, 300000);
  }
})();
