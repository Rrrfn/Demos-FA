/* =========================================================
   گردش‌کار زندهٔ هر پروژه
   =========================================================
   هر کارت یک تصویر ثابت دارد و یک WebP متحرک. حالت عادی همیشه همان
   تصویر ثابت است — یعنی نخستین تصویر از خود برنامه. انیمیشن فقط وقتی
   بار می‌شود که نشانگر روی کارت برود و به‌محض بیرون‌رفتن، کارت به تصویر
   ثابت برمی‌گردد.

   چرا پخش روی هاور و نه با اسکرول؟ چون بازدیدکننده باید بتواند خودش
   انتخاب کند چه چیزی را ببیند. پخش خودکار با اسکرول، ده انیمیشن را
   هم‌زمان راه می‌اندازد و کنترل را از دست کاربر می‌گیرد؛ پخش روی هاور
   هم حجم شبکه را فقط برای همان کارتی خرج می‌کند که کاربر به آن علاقه
   نشان داده، هم شروع دوباره از فریم اول را تضمین می‌کند.

   چرا جابه‌جایی «src» و نه دو لایه روی هم؟ با دو لایه، انیمیشن همهٔ
   کارت‌ها همیشه در حال پخش می‌ماند — حتی وقتی هیچ‌کدام دیده نمی‌شوند.
   جابه‌جایی منبع، انیمیشن را واقعاً متوقف می‌کند.

   روی صفحهٔ لمسی هاوری وجود ندارد؛ آنجا با یک ضربه روشن و با ضربهٔ
   بعدی خاموش می‌شود.

   چهار حالت که هیچ کاری نمی‌کنیم و پوستر می‌ماند:
     • مرورگر WebP را نمی‌فهمد
     • کاربر «کاهش حرکت» را خواسته است
     • کاربر صرفه‌جویی در داده را روشن کرده یا اتصالش 2G است
     • مرورگر PointerEvent ندارد
   ========================================================= */
(function () {
  "use strict";

  var media = document.querySelectorAll("img[data-walk]");
  if (!media.length) return;

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (reduced.matches) return;
  if (!("PointerEvent" in window)) return;

  /* روی اتصال کم‌مصرف یا کند هم انیمیشن بار نمی‌شود. هر گردش‌کار حدود نیم
     مگابایت است و کسی که «صرفه‌جویی در داده» را روشن کرده، انتظار ندارد
     یک صفحهٔ معرفی این حجم را برای انیمیشن خرج کند. */
  var conn = navigator.connection || navigator.mozConnection ||
             navigator.webkitConnection;
  if (conn && (conn.saveData || /(^|-)2g$/.test(conn.effectiveType || ""))) return;

  /* تشخیص پشتیبانی WebP با یک تصویر یک‌پیکسلی درون‌خطی. */
  var probe = new Image();
  probe.onload = probe.onerror = function () {
    if (probe.width === 1 && probe.height === 1) arm();
  };
  probe.src =
    "data:image/webp;base64,UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAwA0" +
    "JaQAA3AA/vuUAAA=";

  function arm() {
    Array.prototype.forEach.call(media, function (img) {
      var stage = img.closest(".case__media, .card__shot") || img;
      var poster = img.getAttribute("data-poster");
      var walk = img.getAttribute("data-walk");
      var failed = false;

      img.addEventListener("error", function () {
        /* اگر فایل متحرک نیامد، بی‌صدا به تصویر ثابت برگرد تا کارت هیچ‌وقت
           خالی نماند و دفعهٔ بعد هم دوباره تلاش نشود. */
        failed = true;
        stop();
      });

      function play() {
        if (failed || img.getAttribute("src") === walk) return;
        img.setAttribute("src", walk);
        stage.classList.add("is-live");
      }

      function stop() {
        if (img.getAttribute("src") !== poster) img.setAttribute("src", poster);
        stage.classList.remove("is-live");
      }

      /* ماوس و قلم: ورود و خروج نشانگر. */
      stage.addEventListener("pointerenter", function (event) {
        if (event.pointerType === "mouse") play();
      });
      stage.addEventListener("pointerleave", function (event) {
        if (event.pointerType === "mouse") stop();
      });

      /* لمس: ضربه روشن می‌کند، ضربهٔ بعدی خاموش. مرورگر روی حرکت اسکرول
         رویداد click نمی‌فرستد، پس کشیدن صفحه انیمیشن را روشن نمی‌کند. */
      stage.addEventListener("click", function (event) {
        if (event.pointerType === "mouse") return;
        if (img.getAttribute("src") === walk) stop();
        else play();
      });

      stage.classList.add("has-walk");
    });
  }
})();
