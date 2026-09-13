/* حس‌سنج — بهبود تدریجی.
   این فایل اختیاری است: با غیرفعال بودن JavaScript، فرم تحلیل متن و فرم
   بارگذاری فایل هر دو با ارسال معمولی کار می‌کنند. کاری که اینجا اضافه می‌شود
   فقط سرعت است — نتیجه بدون بارگذاری کامل صفحه به‌روز می‌شود و متن در نشانی
   صفحه می‌ماند تا قابل اشتراک باشد. */
(function () {
  'use strict';

  /* ------------------------------------------------ تحلیل متن بدون رفرش */
  var form = document.querySelector('.analyze-form');
  var region = document.getElementById('result-region');

  if (form && region) {
    var field = form.querySelector('textarea');
    var submit = form.querySelector('button[type="submit"]');
    var pending = null;

    var setBusy = function (busy) {
      form.classList.toggle('is-busy', busy);
      if (submit) submit.textContent = busy ? 'در حال تحلیل…' : 'تحلیل کن';
    };

    var swap = function (url, push) {
      if (pending) pending.abort();
      pending = new AbortController();
      setBusy(true);

      fetch(url, { signal: pending.signal, headers: { 'X-Requested-With': 'fetch' } })
        .then(function (response) { return response.text(); })
        .then(function (html) {
          var parsed = new DOMParser().parseFromString(html, 'text/html');
          var next = parsed.getElementById('result-region');
          if (!next) return;
          region.replaceWith(next);
          region = next;
          if (push !== false) history.replaceState(null, '', url);
        })
        .catch(function (error) {
          if (error && error.name === 'AbortError') return;
          // اگر شبکه لنگید، همان مسیر معمولی مرورگر را رها می‌کنیم.
          window.location.href = url;
        })
        .then(function () { setBusy(false); });
    };

    var urlFor = function (value) {
      var url = new URL(form.action, window.location.origin);
      url.search = '';
      url.searchParams.set('q', value);
      return url.toString();
    };

    //: وقتی متن از جای دیگری (نمونهٔ آماده یا نشانی) نوشته می‌شود، شمارندهٔ
    //: نویسه باید همان لحظه به‌روز شود؛ رویداد ``input`` واقعی مرورگر فقط با
    //: تایپ دستی می‌آید، پس خودمان خبر می‌دهیم.
    var announce = function () {
      if (field) field.dispatchEvent(new Event('input', { bubbles: true }));
    };

    var analyse = function (push) {
      var value = (field && field.value || '').trim();
      if (!value) {
        // متن خالی: منطقهٔ نتیجه پاک می‌شود بدون درخواست به سرور.
        var emptied = region.cloneNode(false);
        region.replaceWith(emptied);
        region = emptied;
        history.replaceState(null, '', form.action);
        return;
      }
      swap(urlFor(value), push);
    };

    form.addEventListener('submit', function (event) {
      if (!window.fetch || !window.URL) return;   // مسیر معمولی
      event.preventDefault();
      analyse(true);
    });

    // متن تایپ‌شده با تأخیر کوتاه تحلیل می‌شود؛ درخواست‌ها روی هم نمی‌افتند
    // چون هر درخواست تازه، درخواست قبلی را لغو می‌کند.
    if (field && window.fetch) {
      var timer = null;
      field.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(function () { analyse(true); }, 550);
      });
      field.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
          event.preventDefault();
          clearTimeout(timer);
          analyse(true);
        }
      });
    }

    // نمونه‌های آماده هم بدون بارگذاری صفحه می‌آیند.
    document.querySelectorAll('.examples .chip').forEach(function (chip) {
      chip.addEventListener('click', function (event) {
        if (!window.fetch) return;
        var url = new URL(chip.href);
        var value = url.searchParams.get('q') || '';
        if (field) field.value = value;
        announce();
        event.preventDefault();
        analyse(true);
      });
    });

    window.addEventListener('popstate', function () {
      if (field) field.value = new URL(window.location.href).searchParams.get('q') || '';
      announce();
      analyse(false);
    });
  }

  /* ------------------------------------------------ فرم بارگذاری فایل */
  var drop = document.querySelector('.drop');
  if (drop) {
    var input = drop.querySelector('input[type="file"]');
    var title = drop.querySelector('.drop-title');
    var form2 = drop.closest('form');

    if (input && title) {
      input.addEventListener('change', function () {
        var file = input.files && input.files[0];
        if (!file) return;
        var kb = Math.max(1, Math.round(file.size / 1024));
        title.textContent = file.name + ' — ' + kb.toLocaleString('fa-IR') + ' کیلوبایت';
      });
    }

    if (form2) {
      form2.addEventListener('submit', function () {
        form2.classList.add('is-busy');
        form2.querySelectorAll('button[type="submit"]').forEach(function (button) {
          button.disabled = true;
          if (button.value === 'download') {
            button.textContent = 'در حال ساخت فایل…';
          } else {
            button.textContent = 'در حال تحلیل…';
          }
        });
      });
    }
  }

  /* ------------------------------------------------ شمارندهٔ نویسه */
  var textarea = document.querySelector('.analyze-form textarea');
  var counter = document.getElementById('char-counter');
  if (textarea && counter) {
    var max = parseInt(counter.dataset.max || '0', 10);
    var digits = function (value) {
      return String(value).replace(/\d/g, function (digit) {
        return '۰۱۲۳۴۵۶۷۸۹'[Number(digit)];
      });
    };
    var paint = function () {
      var used = textarea.value.length;
      counter.textContent = digits(used) + ' از ' + digits(max) + ' نویسه';
      counter.classList.toggle('is-full', max > 0 && used >= max);
    };
    textarea.addEventListener('input', paint);
    paint();
  }
})();
