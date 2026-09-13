/* ==========================================================================
   گزارش‌ساز — بهبود تدریجی
   --------------------------------------------------------------------------
   قاعدهٔ این فایل: **بدون جاوااسکریپت هم باید کار کند.** فرم بارگذاری یک فرم
   معمولی است؛ این کد فقط تجربه را بهتر می‌کند (رها کردن فایل، نمایش نام،
   بازخورد انتظار). اگر مرورگر اسکریپت را اجرا نکند، همهٔ صفحه‌ها کار می‌کنند.

   هیچ کتابخانهٔ بیرونی بار نمی‌شود و هیچ چیزی از کاربر پنهان نمی‌ماند.
   ========================================================================== */
(function () {
  "use strict";

  var MESSAGES = {
    ext: "فقط فایل XLSX یا CSV پذیرفته می‌شود. قالب‌های قدیمی مثل xls را در " +
         "اکسل با فرمت xlsx ذخیره کنید.",
    size: "حجم فایل از سقف مجاز بیشتر است.",
    empty: "فایل انتخاب‌شده خالی است."
  };

  function formatSize(bytes) {
    if (!bytes) return "";
    var units = ["بایت", "کیلوبایت", "مگابایت", "گیگابایت"];
    var index = 0;
    var value = bytes;
    while (value >= 1024 && index < units.length - 1) {
      value = value / 1024;
      index += 1;
    }
    return (index === 0 ? value : value.toFixed(1)) + " " + units[index];
  }

  function extensionOf(name) {
    var parts = String(name || "").toLowerCase().split(".");
    return parts.length > 1 ? parts.pop() : "";
  }

  function setupUploader(form) {
    var dropzone = form.querySelector("[data-dropzone]");
    var input = form.querySelector("[data-file-input]");
    var picked = form.querySelector("[data-file-name]");
    var error = form.querySelector("[data-file-error]");
    var submit = form.querySelector("[data-submit]");
    if (!input) return;

    var maxBytes = parseInt(form.getAttribute("data-max-bytes") || "0", 10);

    function clearError() {
      if (error) { error.hidden = true; error.textContent = ""; }
    }

    function showError(text) {
      if (error) { error.hidden = false; error.textContent = text; }
    }

    function describe(file) {
      if (!file) return;
      if (picked) {
        picked.hidden = false;
        picked.textContent = file.name + " — " + formatSize(file.size);
      }
    }

    function validate(file) {
      if (!file) { showError(MESSAGES.empty); return false; }
      var ext = extensionOf(file.name);
      if (ext !== "xlsx" && ext !== "csv") {
        showError(MESSAGES.ext);
        return false;
      }
      if (!file.size) { showError(MESSAGES.empty); return false; }
      if (maxBytes && file.size > maxBytes) {
        showError(MESSAGES.size + " سقف مجاز " + formatSize(maxBytes) + " است.");
        return false;
      }
      clearError();
      return true;
    }

    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      if (file && validate(file)) { describe(file); }
    });

    if (dropzone) {
      ["dragenter", "dragover"].forEach(function (event) {
        dropzone.addEventListener(event, function (e) {
          e.preventDefault();
          form.classList.add("is-dragging");
        });
      });
      ["dragleave", "drop"].forEach(function (event) {
        dropzone.addEventListener(event, function () {
          form.classList.remove("is-dragging");
        });
      });
      dropzone.addEventListener("drop", function (e) {
        e.preventDefault();
        var files = e.dataTransfer && e.dataTransfer.files;
        if (!files || !files.length) return;
        var file = files[0];
        if (!validate(file)) return;
        /* انتقال فایل انتخاب‌شده به input واقعی — با DataTransfer که در
           مرورگرهای امروزی پشتیبانی می‌شود. اگر پشتیبانی نشود، کاربر همان
           فایل را دستی انتخاب می‌کند و چیزی نمی‌شکند. */
        try {
          var transfer = new DataTransfer();
          transfer.items.add(file);
          input.files = transfer.files;
          describe(file);
        } catch (err) {
          input.click();
        }
      });
      dropzone.addEventListener("click", function (e) {
        if (e.target === input) return;
        e.preventDefault();
        input.click();
      });
    }

    form.addEventListener("submit", function (e) {
      var file = input.files && input.files[0];
      if (!file) {
        e.preventDefault();
        showError(MESSAGES.empty);
        return;
      }
      if (!validate(file)) { e.preventDefault(); return; }
      form.classList.add("is-busy");
      if (submit) {
        submit.textContent = "در حال پردازش…";
        submit.disabled = true;
      }
    });
  }

  /* فهرست: باز کردن خودکار بخش‌ها وقتی صفحه با لنگر باز شده است. */
  function openAnchors() {
    if (!location.hash) return;
    var target = document.querySelector(location.hash);
    if (target && target.tagName === "DETAILS") { target.open = true; }
  }

  function setupTables() {
    /* جدول‌های خیلی پهن روی موبایل: با کلید صفحه‌کلید هم قابل اسکرول شوند. */
    var scrolls = document.querySelectorAll(".table-scroll");
    Array.prototype.forEach.call(scrolls, function (node) {
      if (node.scrollWidth <= node.clientWidth) return;
      node.setAttribute("tabindex", "0");
      node.setAttribute("role", "region");
      node.setAttribute("aria-label", "جدول قابل اسکرول افقی");
    });
  }

  function init() {
    var forms = document.querySelectorAll("[data-uploader]");
    Array.prototype.forEach.call(forms, setupUploader);
    openAnchors();
    setupTables();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
