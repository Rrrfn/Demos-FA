/* ==========================================================================
   NAFEH — لایهٔ وضعیت: سبد خرید، علاقه‌مندی‌ها، کد تخفیف
   بدون وابستگی بیرونی · ذخیره‌سازی در localStorage
   ========================================================================== */
(function () {
  "use strict";

  var DATA = window.NAFEH || { fragrances: [], freeShipFrom: 5000000 };
  var KEY = { cart: "nafeh.cart.v1", wish: "nafeh.wish.v1", coupon: "nafeh.coupon.v1" };

  var bySlug = {};
  DATA.fragrances.forEach(function (f) { bySlug[f.slug] = f; });

  var FREE_SHIP = DATA.freeShipFrom || 5000000;
  var SHIPPING = { pickup: 350000, post: 180000, free: 0 };
  var COUPONS = { NAFEH10: 10, ATELIER: 15 };

  function read(key, fallback) {
    try {
      var raw = window.localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }
  }
  function write(key, value) {
    try { window.localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* ignore */ }
  }

  var state = {
    cart: read(KEY.cart, []),
    wish: read(KEY.wish, []),
    coupon: read(KEY.coupon, null)
  };

  /* ---------------------------------------------------------- formatting */
  var FA = "۰۱۲۳۴۵۶۷۸۹";
  function digits(v) {
    return String(v).replace(/[0-9]/g, function (d) { return FA[+d]; });
  }
  function toman(n) {
    return digits(Number(n).toLocaleString("en-US").replace(/,/g, "٬")) + " تومان";
  }
  function num(n) { return digits(n); }

  /* ---------------------------------------------------------- helpers */
  function find(slug) { return bySlug[slug] || null; }
  function optionOf(slug, ml) {
    var f = find(slug);
    if (!f) return null;
    for (var i = 0; i < f.opts.length; i++) {
      if (Number(f.opts[i].ml) === Number(ml)) return f.opts[i];
    }
    return null;
  }
  function defaultMl(slug) {
    var f = find(slug);
    if (!f) return 50;
    var mid = f.opts.filter(function (o) { return o.ml === 50; })[0];
    return mid ? mid.ml : f.opts[f.opts.length - 1].ml;
  }
  function lines() {
    return state.cart.map(function (l) {
      var f = find(l.slug), o = optionOf(l.slug, l.ml);
      if (!f || !o) return null;
      return { slug: l.slug, ml: Number(l.ml), qty: l.qty, frag: f, opt: o, total: o.price * l.qty };
    }).filter(Boolean);
  }
  function count() {
    return state.cart.reduce(function (s, l) { return s + l.qty; }, 0);
  }
  function subtotal() {
    return lines().reduce(function (s, l) { return s + l.total; }, 0);
  }
  function discount() {
    if (!state.coupon) return 0;
    var pct = COUPONS[state.coupon];
    return pct ? Math.round(subtotal() * pct / 100) : 0;
  }
  function couponInfo() {
    if (!state.coupon) return null;
    var pct = COUPONS[state.coupon];
    return pct ? { code: state.coupon, pct: pct } : null;
  }
  function shipCost(method) {
    if (method === "free") return 0;
    if (method && SHIPPING[method] !== undefined) return SHIPPING[method];
    return subtotal() >= FREE_SHIP ? 0 : SHIPPING.post;
  }
  function total(method) {
    var t = subtotal() - discount();
    if (count() > 0) t += shipCost(method);
    return Math.max(0, t);
  }

  /* ---------------------------------------------------------- mutations */
  function emit() {
    document.dispatchEvent(new CustomEvent("nafeh:change", { detail: { count: count() } }));
  }
  function save() {
    write(KEY.cart, state.cart);
    write(KEY.wish, state.wish);
    write(KEY.coupon, state.coupon);
    emit();
  }
  function add(slug, ml, qty) {
    if (!find(slug)) return false;
    ml = Number(ml) || defaultMl(slug);
    qty = Number(qty) || 1;
    var line = state.cart.filter(function (l) { return l.slug === slug && Number(l.ml) === ml; })[0];
    if (line) line.qty += qty;
    else state.cart.push({ slug: slug, ml: ml, qty: qty });
    save();
    return true;
  }
  function setQty(slug, ml, qty) {
    qty = Number(qty);
    if (qty <= 0) return remove(slug, ml);
    state.cart.forEach(function (l) {
      if (l.slug === slug && Number(l.ml) === Number(ml)) l.qty = qty;
    });
    save();
  }
  function step(slug, ml, delta) {
    var line = state.cart.filter(function (l) { return l.slug === slug && Number(l.ml) === Number(ml); })[0];
    if (line) setQty(slug, ml, line.qty + delta);
  }
  function remove(slug, ml) {
    state.cart = state.cart.filter(function (l) {
      return !(l.slug === slug && Number(l.ml) === Number(ml));
    });
    save();
  }
  function clear() { state.cart = []; state.coupon = null; save(); }
  function toggleWish(slug) {
    var i = state.wish.indexOf(slug);
    if (i === -1) state.wish.push(slug); else state.wish.splice(i, 1);
    save();
    return i === -1;
  }
  function isWished(slug) { return state.wish.indexOf(slug) !== -1; }
  function applyCoupon(code) {
    code = String(code || "").trim().toUpperCase();
    if (!COUPONS[code]) { state.coupon = null; save(); return false; }
    state.coupon = code;
    save();
    return true;
  }

  window.Store = {
    data: DATA,
    find: find,
    optionOf: optionOf,
    defaultMl: defaultMl,
    lines: lines,
    count: count,
    subtotal: subtotal,
    discount: discount,
    couponInfo: couponInfo,
    shipCost: shipCost,
    total: total,
    freeShipFrom: FREE_SHIP,
    add: add,
    setQty: setQty,
    step: step,
    remove: remove,
    clear: clear,
    toggleWish: toggleWish,
    isWished: isWished,
    wish: function () { return state.wish.slice(); },
    applyCoupon: applyCoupon,
    digits: digits,
    num: num,
    money: toman
  };
})();
