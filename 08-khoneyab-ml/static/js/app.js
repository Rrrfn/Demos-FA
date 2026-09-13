/* ============================================================================
   خانه‌یاب — بهبود تدریجی
   ----------------------------------------------------------------------------
   صفحه‌ها بدون این فایل هم کامل کار می‌کنند: هر فرم یک ارسال معمولی دارد و
   هر لینک یک نشانی واقعی است. کاری که اینجا انجام می‌شود حذف رفت‌وبرگشت‌های
   غیرضروری است — نه ساختن قابلیتی که بدون JavaScript وجود ندارد.

   سه چیز: ناوبری موبایل، دکمه‌های مقایسه/نشان، و به‌روزرسانی زندهٔ برآورد.
   ========================================================================= */
(function () {
  'use strict';

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* ------------------------------------------------------------------ توست */
  var toastEl = $('[data-toast]');
  var toastTimer = null;
  function toast(message) {
    if (!toastEl || !message) return;
    toastEl.textContent = message;
    toastEl.hidden = false;
    toastEl.classList.add('is-on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastEl.classList.remove('is-on');
      setTimeout(function () { toastEl.hidden = true; }, 220);
    }, 2400);
  }

  /* -------------------------------------------------------------- ناوبری موبایل */
  var navToggle = $('[data-nav-toggle]');
  var nav = $('#mainnav');
  if (navToggle && nav) {
    navToggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function (event) {
      if (!nav.classList.contains('is-open')) return;
      if (nav.contains(event.target) || navToggle.contains(event.target)) return;
      nav.classList.remove('is-open');
      navToggle.setAttribute('aria-expanded', 'false');
    });
  }

  /* ------------------------------------------------------------- شمارنده‌های سرصفحه */
  function setCounter(name, value) {
    var el = $('[data-count="' + name + '"]');
    if (!el) return;
    el.textContent = value;
    el.classList.toggle('is-empty', !value);
    el.classList.remove('is-pulse');
    void el.offsetWidth;               /* بازنشانی انیمیشن */
    el.classList.add('is-pulse');
  }

  function post(url, body) {
    var init = {
      method: 'POST',
      headers: { 'X-Requested-With': 'fetch', 'Accept': 'application/json' },
      credentials: 'same-origin'
    };
    if (body) {
      init.headers['Content-Type'] = 'application/x-www-form-urlencoded';
      init.body = body;
    }
    return fetch(url, init).then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    });
  }

  /* -------------------------------------------------- مقایسه و نشان‌کردن (AJAX) */
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form.matches || !form.matches('form[data-toggle]')) return;
    event.preventDefault();

    var kind = form.dataset.toggle;             /* compare | saved */
    var button = form.querySelector('button');
    if (button.disabled) return;
    button.disabled = true;

    post(form.action, new URLSearchParams(new FormData(form)).toString())
      .then(function (payload) {
        if (payload.reason === 'full') {
          toast('فهرست مقایسه پر است — حداکثر چهار ملک.');
          return;
        }
        if (kind === 'compare') {
          var inList = payload.in_compare;
          button.classList.toggle('is-on', inList);
          button.textContent = inList ? 'در مقایسه' : 'مقایسه';
          button.setAttribute('aria-pressed', inList ? 'true' : 'false');
          setCounter('compare', payload.count);
          toast(inList ? 'به فهرست مقایسه افزوده شد.' : 'از فهرست مقایسه برداشته شد.');
        } else {
          var saved = payload.saved;
          button.classList.toggle('is-on', saved);
          button.textContent = saved ? 'نشان‌شده' : 'نشان‌کردن';
          button.setAttribute('aria-pressed', saved ? 'true' : 'false');
          setCounter('saved', payload.count);
          toast(saved ? 'نشان شد.' : 'نشان برداشته شد.');
        }
      })
      .catch(function () {
        form.submit();                          /* عقب‌نشینی به ارسال معمولی فرم */
      })
      .finally(function () { button.disabled = false; });
  });

  /* ------------------------------------------------------ برآورد زندهٔ قیمت */
  var estimateForm = $('form[data-estimate]');
  var estimateOut = $('[data-estimate-result]');

  function renderEstimate(data) {
    var box = estimateOut;
    if (!box) return;
    $('[data-est-price]', box).textContent = data.price_text;
    $('[data-est-m2]', box).textContent = data.price_per_m2;
    $('[data-est-low]', box).textContent = data.low_short;
    $('[data-est-high]', box).textContent = data.high_short;
    $('[data-est-half]', box).textContent = data.half_width_pct;
    $('[data-est-base]', box).textContent = data.base_short;
    $('[data-est-delta]', box).textContent = data.delta_short;
    $('[data-est-summary]', box).textContent = data.summary;

    var list = $('[data-est-factors]', box);
    if (list) {
      list.innerHTML = data.factors.map(function (factor) {
        return '<li class="factor factor-' + factor.direction + '">' +
          '<div class="factor-head">' +
            '<span class="factor-name">' + factor.label + '<i>' + factor.value + '</i></span>' +
            '<span class="factor-amount">' + factor.signed + factor.amount + '</span>' +
          '</div>' +
          '<div class="track"><span style="width:' + factor.width + '%"></span></div>' +
        '</li>';
      }).join('');
    }

    var comparableCount = $('[data-est-cmp-count]', box);
    if (comparableCount) comparableCount.textContent = data.comparable_count;
    var comparableMedian = $('[data-est-cmp-median]', box);
    if (comparableMedian) comparableMedian.textContent = data.comparable_median_short;
    var comparableM2 = $('[data-est-cmp-m2]', box);
    if (comparableM2) comparableM2.textContent = data.comparable_median_m2;
    var standing = $('[data-est-standing]', box);
    if (standing) standing.textContent = data.standing;
  }

  if (estimateForm && estimateOut) {
    var timer = null;
    var endpoint = estimateForm.dataset.endpoint || '/api/estimate';

    function refresh() {
      var query = new URLSearchParams(new FormData(estimateForm)).toString();
      var url = endpoint + '?' + query;
      estimateOut.classList.add('is-busy');
      fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
        .then(function (response) {
          if (!response.ok) throw new Error('HTTP ' + response.status);
          return response.json();
        })
        .then(function (payload) { renderEstimate(payload.data.explanation); })
        .catch(function () { /* فرم همچنان با ارسال معمولی کار می‌کند */ })
        .finally(function () {
          estimateOut.classList.remove('is-busy');
          history.replaceState(null, '', '/estimate?' + query);
        });
    }

    estimateForm.addEventListener('input', function (event) {
      if (event.target.type === 'checkbox') return;
      clearTimeout(timer);
      timer = setTimeout(refresh, 260);
    });
    estimateForm.addEventListener('change', function (event) {
      clearTimeout(timer);
      timer = setTimeout(refresh, 60);
    });
    estimateForm.addEventListener('submit', function (event) {
      event.preventDefault();
      clearTimeout(timer);
      refresh();
    });
  }

  /* --------------------------------------------- اعمال خودکار فیلترهای جست‌وجو */
  var filterForm = $('form[data-autofilter]');
  if (filterForm) {
    var filterTimer = null;
    filterForm.addEventListener('change', function (event) {
      if (event.target.type === 'number') return;
      clearTimeout(filterTimer);
      filterTimer = setTimeout(function () {
        filterForm.requestSubmit ? filterForm.requestSubmit() : filterForm.submit();
      }, 120);
    });
  }

  /* -------------------------------------------------------- رونوشت نشانی اشتراکی */
  $$('[data-copy]').forEach(function (button) {
    button.addEventListener('click', function () {
      var target = document.querySelector(button.dataset.copy);
      if (!target) return;
      var text = target.textContent.trim();
      var done = function () { toast('نشانی رونوشت شد.'); };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(done, function () {});
      } else {
        var area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.style.position = 'absolute';
        area.style.insetInlineStart = '-9999px';
        document.body.appendChild(area);
        area.select();
        try { document.execCommand('copy'); done(); } catch (error) { /* بی‌صدا */ }
        document.body.removeChild(area);
      }
    });
  });

  /* ------------------------------------------- تنطیم مقادیر آمادهٔ فرم برآورد */
  $$('[data-preset]').forEach(function (button) {
    button.addEventListener('click', function () {
      if (!estimateForm) return;
      var preset = JSON.parse(button.dataset.preset);
      Object.keys(preset).forEach(function (key) {
        var field = estimateForm.elements[key];
        if (!field) return;
        if (field.type === 'checkbox') {
          field.checked = Boolean(Number(preset[key]));
        } else {
          field.value = preset[key];
        }
      });
      estimateForm.dispatchEvent(new Event('change', { bubbles: true }));
    });
  });
})();
