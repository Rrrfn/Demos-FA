/* ==========================================================================
   NAFEH — لایهٔ تعامل: ناوبری، جست‌وجو، سبد، فیلترها، فرم‌ها
   ========================================================================== */
(function () {
  "use strict";

  var S = window.Store;
  var D = S.data;
  var FR = D.fragrances || [];
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var SVG = {
    heart: '<path d="M12 20s-7-4.4-7-9.4A4.1 4.1 0 0 1 12 7.6a4.1 4.1 0 0 1 7 3c0 5-7 9.4-7 9.4z"/>',
    bag: '<path d="M6 8h12l-1 12H7L6 8z"/><path d="M9.2 8V6.6a2.8 2.8 0 0 1 5.6 0V8"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    minus: '<path d="M5 12h14"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    check: '<path d="M4 12.5l5 5L20 6.5"/>'
  };
  function ico(name, cls) {
    return '<svg class="' + (cls || "ico") + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + SVG[name] + "</svg>";
  }

  /* ------------------------------------------------------------ toast */
  var toastEl = $("#toast"), toastTimer;
  function toast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.classList.add("is-on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove("is-on"); }, 2600);
  }

  /* ------------------------------------------------------------ card */
  function starsHTML(rating) {
    var pct = Math.round(rating / 5 * 100);
    return '<span class="stars" style="--pct:' + pct + '%" role="img" aria-label="' +
      S.num(rating) + ' از ۵"><span class="stars__bg" aria-hidden="true">★★★★★</span>' +
      '<span class="stars__fg" aria-hidden="true">★★★★★</span></span>';
  }
  function cardHTML(f, revealOnly) {
    var prices = f.opts.map(function (o) { return o.price; });
    var lo = Math.min.apply(null, prices);
    var hi = Math.max.apply(null, prices);
    var price = lo !== hi
      ? '<span class="pc__from">از</span> <b>' + S.money(lo) + "</b>"
      : "<b>" + S.money(lo) + "</b>";
    var badge = f.badge
      ? '<span class="tag tag--' + (f.badge === "جدید" ? "new" : f.badge === "پرفروش" ? "best" : "limited") + '">' + f.badge + "</span>"
      : "";
    return '<article class="pc" data-slug="' + f.slug + '">' +
      '<div class="pc__media">' +
      '<a href="product-' + f.slug + '.html" aria-label="' + f.fa + '">' +
      '<img src="assets/img/' + f.img + '" alt="شیشهٔ عطر ' + f.fa + ' — ' + f.latin + '" loading="lazy"></a>' +
      badge +
      '<button class="pc__wish" data-wish="' + f.slug + '" aria-label="افزودن ' + f.fa + ' به علاقه‌مندی‌ها">' + ico("heart") + "</button>" +
      '<div class="pc__quick"><button class="btn btn--ghost btn--sm" data-quick-add="' + f.slug + '">افزودن سریع</button></div>' +
      "</div>" +
      '<div class="pc__body">' +
      '<p class="pc__latin">' + f.latin + "</p>" +
      '<h3 class="pc__name"><a href="product-' + f.slug + '.html">' + f.fa + "</a></h3>" +
      '<p class="pc__fam">' + f.families.join(" · ") + " · " + f.conc + "</p>" +
      '<div class="pc__meta">' + starsHTML(f.rating) + '<span class="pc__rev">' + S.num(f.reviews) + " نظر</span></div>" +
      '<p class="pc__price">' + price + "</p>" +
      "</div></article>";
  }

  /* ------------------------------------------------------------ header */
  var hdr = $("#hdr");
  function onScroll() {
    if (hdr) hdr.classList.toggle("is-stuck", window.scrollY > 12);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  function syncCounts() {
    $$("[data-cart-count]").forEach(function (el) { el.textContent = S.num(S.count()); });
    $$("[data-wish-count]").forEach(function (el) { el.textContent = S.num(S.wish().length); });
    $$("[data-wish]").forEach(function (el) {
      var on = S.isWished(el.getAttribute("data-wish"));
      el.classList.toggle("is-on", on);
      el.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  /* ------------------------------------------------------------ mobile nav */
  var nav = $("#nav"), burger = $("#burger"), navX = $("#navClose");
  function setNav(open) {
    if (!nav) return;
    if (open) closeFilters();
    nav.classList.toggle("is-open", open);
    if (burger) burger.setAttribute("aria-expanded", open ? "true" : "false");
    syncOverlay();
  }
  if (burger) {
    burger.addEventListener("click", function () { setNav(!nav.classList.contains("is-open")); });
  }
  if (navX) navX.addEventListener("click", function () { setNav(false); });

  /* ------------------------------------------------------------ search */
  var panel = $("#searchPanel"), field = $("#searchField");
  function openSearch(open) {
    if (!panel) return;
    panel.hidden = !open;
    document.body.style.overflow = open ? "hidden" : "";
    if (open && field) setTimeout(function () { field.focus(); }, 60);
  }
  var so = $("#searchOpen"), sc = $("#searchClose");
  if (so) so.addEventListener("click", function () { openSearch(true); });
  if (sc) sc.addEventListener("click", function () { openSearch(false); });
  $$("[data-quick]").forEach(function (b) {
    b.addEventListener("click", function () {
      if (field) field.value = b.getAttribute("data-quick");
      goSearch(b.getAttribute("data-quick"));
    });
  });
  function goSearch(q) {
    window.location.href = "shop.html?q=" + encodeURIComponent(q);
  }
  var sf = $("#searchForm");
  if (sf) sf.addEventListener("submit", function (e) { e.preventDefault(); goSearch(field ? field.value : ""); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { openSearch(false); setNav(false); closeDrawer(); closeFilters(); }
  });

  /* ------------------------------------------------------------ drawer */
  var drawer = $("#cartDrawer"), overlay = $("#overlay");
  /* One overlay for every off-canvas panel, so two of them can never sit on
     top of each other. */
  function syncOverlay() {
    var any = !!(drawer && drawer.classList.contains("is-open")) ||
      !!(nav && nav.classList.contains("is-open")) ||
      !!(filters && filters.classList.contains("is-open"));
    if (overlay) overlay.hidden = !any;
    document.body.style.overflow = any ? "hidden" : "";
  }
  function renderDrawer() {
    var body = $("#drawerBody"), foot = $("#drawerFoot");
    if (!body) return;
    var lines = S.lines();
    if (!lines.length) {
      body.innerHTML = '<div class="drawer__empty">' + ico("bag") +
        "<p>سبد خرید شما خالی است.</p></div>";
      if (foot) foot.innerHTML = '<a class="btn btn--line btn--block" href="shop.html">رفتن به فروشگاه</a>';
      return;
    }
    body.innerHTML = lines.map(function (l) {
      return '<div class="li" data-line="' + l.slug + "|" + l.ml + '">' +
        '<div class="li__media"><img src="assets/img/' + l.frag.img + '" alt="' + l.frag.fa + '"></div>' +
        '<div class="li__info"><h4>' + l.frag.fa + '</h4>' +
        '<span class="li__opt">' + l.opt.label + '</span><br>' +
        '<span class="li__price">' + S.money(l.total) + "</span></div>" +
        '<div class="li__tools">' +
        '<div class="qty"><button class="qty__b" data-cstep="-1" data-slug="' + l.slug + '" data-ml="' + l.ml + '" aria-label="کاهش">' + ico("minus") + "</button>" +
        '<input type="text" value="' + S.num(l.qty) + '" inputmode="numeric" data-cqty="' + l.slug + "|" + l.ml + '" aria-label="تعداد">' +
        '<button class="qty__b" data-cstep="1" data-slug="' + l.slug + '" data-ml="' + l.ml + '" aria-label="افزایش">' + ico("plus") + "</button></div>" +
        '<button class="link-x" data-cdel="' + l.slug + "|" + l.ml + '">حذف</button>' +
        "</div></div>";
    }).join("");
    if (foot) {
      var free = S.subtotal() >= S.freeShipFrom;
      foot.innerHTML =
        '<div class="sum__row"><span>جمع کل</span><b>' + S.money(S.subtotal()) + "</b></div>" +
        '<p class="sum__note">' + (free ? "ارسال رایگان فعال شد." :
          "تا " + S.money(S.freeShipFrom - S.subtotal()) + " دیگر، ارسال رایگان می‌شود.") + "</p>" +
        '<a class="btn btn--solid btn--block" href="checkout.html">ادامهٔ فرآیند خرید</a>' +
        '<a class="btn btn--line btn--block btn--sm" href="cart.html">مشاهدهٔ سبد خرید</a>';
    }
  }
  function openDrawer() {
    if (!drawer) return;
    renderDrawer();
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    syncOverlay();
  }
  function closeDrawer() {
    if (!drawer) return;
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    syncOverlay();
  }
  var co = $("#cartOpen"), cc = $("#cartClose");
  if (co) co.addEventListener("click", openDrawer);
  if (cc) cc.addEventListener("click", closeDrawer);
  if (overlay) overlay.addEventListener("click", function () { closeDrawer(); closeFilters(); setNav(false); });

  /* ------------------------------------------------------------ filters drawer (mobile) */
  var filters = $("#filters");
  function closeFilters() {
    if (!filters) return;
    filters.classList.remove("is-open");
    syncOverlay();
  }
  var ft = $("#filtersToggle");
  if (ft && filters) {
    ft.addEventListener("click", function () {
      var open = !filters.classList.contains("is-open");
      if (open) setNav(false);
      filters.classList.toggle("is-open", open);
      syncOverlay();
    });
  }

  /* ------------------------------------------------------------ delegated actions */
  document.addEventListener("click", function (e) {
    var wish = e.target.closest("[data-wish]");
    if (wish) {
      e.preventDefault();
      var slug = wish.getAttribute("data-wish");
      var added = S.toggleWish(slug);
      var f = S.find(slug);
      toast(added ? "«" + f.fa + "» به علاقه‌مندی‌ها اضافه شد" : "«" + f.fa + "» از علاقه‌مندی‌ها حذف شد");
      return;
    }
    var qa = e.target.closest("[data-quick-add]");
    if (qa) {
      e.preventDefault();
      var s2 = qa.getAttribute("data-quick-add");
      var fr = S.find(s2);
      S.add(s2, S.defaultMl(s2), 1);
      toast("«" + fr.fa + "» به سبد خرید اضافه شد");
      return;
    }
    var cs = e.target.closest("[data-cstep]");
    if (cs) {
      S.step(cs.getAttribute("data-slug"), cs.getAttribute("data-ml"), Number(cs.getAttribute("data-cstep")));
      return;
    }
    var cd = e.target.closest("[data-cdel]");
    if (cd) {
      var parts = cd.getAttribute("data-cdel").split("|");
      S.remove(parts[0], parts[1]);
      toast("از سبد خرید حذف شد");
    }
  });

  document.addEventListener("change", function (e) {
    var q = e.target.closest("[data-cqty]");
    if (q) {
      var p = q.getAttribute("data-cqty").split("|");
      var v = parseInt(String(q.value).replace(/[^\d۰-۹]/g, "")
        .replace(/[۰-۹]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹".indexOf(d); }), 10);
      S.setQty(p[0], p[1], isNaN(v) ? 1 : v);
      return;
    }
    var size = e.target.closest('input[name="size"]');
    if (size) {
      $$(".size").forEach(function (el) { el.classList.toggle("is-on", el.contains(size)); });
      var priceEl = $("#pdpPrice"), sticky = $("#stickyPrice");
      var text = S.money(Number(size.getAttribute("data-price")));
      if (priceEl) priceEl.textContent = text;
      if (sticky) sticky.textContent = text;
    }
  });

  /* ------------------------------------------------------------ reveal */
  if (!REDUCED && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("is-in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    $$(".reveal").forEach(function (el) { io.observe(el); });
  } else {
    $$(".reveal").forEach(function (el) { el.classList.add("is-in"); });
  }

  /* ------------------------------------------------------------ shop page */
  var shopGrid = $("#shopGrid");
  if (shopGrid) {
    var fstate = { q: "", families: [], collections: [], concs: [], maxPrice: Infinity, sort: "featured" };
    var range = $("#priceMax"), rangeOut = $("#priceOut");
    var price50 = function (f) {
      var o = f.opts.filter(function (x) { return x.ml === 50; })[0];
      return o ? o.price : f.from;
    };
    var top = Math.max.apply(null, FR.map(price50));
    if (range) { range.max = top; range.value = top; }
    fstate.maxPrice = top;

    var params = new URLSearchParams(window.location.search);
    if (params.get("q")) fstate.q = params.get("q");
    if (params.get("family")) fstate.families = [params.get("family")];
    if (params.get("collection")) fstate.collections = [params.get("collection")];
    var sInput = $("#shopSearch");
    if (sInput && fstate.q) sInput.value = fstate.q;
    $$('input[name="family"]').forEach(function (i) { i.checked = fstate.families.indexOf(i.value) !== -1; });
    $$('input[name="collection"]').forEach(function (i) { i.checked = fstate.collections.indexOf(i.value) !== -1; });

    function matches(f) {
      if (fstate.q) {
        var needle = fstate.q.trim().toLowerCase();
        var hay = (f.fa + " " + f.latin + " " + f.note + " " + f.noteLatin + " " +
          f.families.join(" ") + " " + f.conc).toLowerCase();
        if (hay.indexOf(needle) === -1) return false;
      }
      if (fstate.families.length && !f.familyKeys.some(function (k) { return fstate.families.indexOf(k) !== -1; })) return false;
      if (fstate.collections.length && !f.collections.some(function (k) { return fstate.collections.indexOf(k) !== -1; })) return false;
      if (fstate.concs.length && fstate.concs.indexOf(f.concKey) === -1) return false;
      if (price50(f) > fstate.maxPrice) return false;
      return true;
    }
    function sorted(list) {
      var out = list.slice();
      if (fstate.sort === "price-asc") out.sort(function (a, b) { return price50(a) - price50(b); });
      else if (fstate.sort === "price-desc") out.sort(function (a, b) { return price50(b) - price50(a); });
      else if (fstate.sort === "rating") out.sort(function (a, b) { return b.rating - a.rating; });
      else if (fstate.sort === "new") {
        out.sort(function (a, b) {
          var an = a.badge === "جدید" ? 0 : 1, bn = b.badge === "جدید" ? 0 : 1;
          return an - bn;
        });
      }
      return out;
    }
    function renderChips() {
      var box = $("#activeChips");
      if (!box) return;
      var chips = [];
      if (fstate.q) chips.push(["q", "جست‌وجو: " + fstate.q]);
      fstate.families.forEach(function (k) { chips.push(["family:" + k, D.families[k]]); });
      fstate.collections.forEach(function (k) {
        var c = (D.collections || []).filter(function (x) { return x.slug === k; })[0];
        chips.push(["collection:" + k, c ? c.fa : k]);
      });
      fstate.concs.forEach(function (k) { chips.push(["conc:" + k, D.concentrations[k]]); });
      box.innerHTML = chips.map(function (c) {
        return '<span class="chip">' + c[1] + '<button data-chip="' + c[0] + '" aria-label="حذف فیلتر">×</button></span>';
      }).join("");
    }
    function renderShop() {
      var list = sorted(FR.filter(matches));
      shopGrid.innerHTML = list.map(function (f) { return cardHTML(f); }).join("");
      var rc = $("#resultCount");
      if (rc) rc.textContent = S.num(list.length);
      var empty = $("#emptyState");
      if (empty) empty.hidden = list.length > 0;
      $$(".reveal", shopGrid).forEach(function (el) { el.classList.add("is-in"); });
      renderChips();
      syncCounts();
    }
    function syncRange() {
      if (!range || !rangeOut) return;
      rangeOut.textContent = "تا " + S.money(Number(range.value));
    }
    syncRange();
    if (range) range.addEventListener("input", function () {
      fstate.maxPrice = Number(range.value);
      syncRange();
      renderShop();
    });
    if (sInput) sInput.addEventListener("input", function () {
      fstate.q = sInput.value;
      renderShop();
    });
    $$('input[name="family"]').forEach(function (i) {
      i.addEventListener("change", function () {
        fstate.families = $$('input[name="family"]:checked').map(function (x) { return x.value; });
        renderShop();
      });
    });
    $$('input[name="collection"]').forEach(function (i) {
      i.addEventListener("change", function () {
        fstate.collections = $$('input[name="collection"]:checked').map(function (x) { return x.value; });
        renderShop();
      });
    });
    $$('input[name="conc"]').forEach(function (i) {
      i.addEventListener("change", function () {
        fstate.concs = $$('input[name="conc"]:checked').map(function (x) { return x.value; });
        renderShop();
      });
    });
    var sortSel = $("#sortSelect");
    if (sortSel) sortSel.addEventListener("change", function () { fstate.sort = sortSel.value; renderShop(); });

    function resetAll() {
      fstate = { q: "", families: [], collections: [], concs: [], maxPrice: top, sort: fstate.sort };
      if (sInput) sInput.value = "";
      if (range) range.value = top;
      $$('input[name="family"], input[name="collection"], input[name="conc"]').forEach(function (i) { i.checked = false; });
      syncRange();
      renderShop();
    }
    var cf = $("#clearFilters"), er = $("#emptyReset");
    if (cf) cf.addEventListener("click", resetAll);
    if (er) er.addEventListener("click", resetAll);
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-chip]");
      if (!b) return;
      var key = b.getAttribute("data-chip");
      if (key === "q") { fstate.q = ""; if (sInput) sInput.value = ""; }
      else if (key.indexOf("family:") === 0) {
        var fk = key.split(":")[1];
        fstate.families = fstate.families.filter(function (x) { return x !== fk; });
        $$('input[name="family"]').forEach(function (i) { if (i.value === fk) i.checked = false; });
      } else if (key.indexOf("collection:") === 0) {
        var ck = key.split(":")[1];
        fstate.collections = fstate.collections.filter(function (x) { return x !== ck; });
        $$('input[name="collection"]').forEach(function (i) { if (i.value === ck) i.checked = false; });
      } else if (key.indexOf("conc:") === 0) {
        var nk = key.split(":")[1];
        fstate.concs = fstate.concs.filter(function (x) { return x !== nk; });
        $$('input[name="conc"]').forEach(function (i) { if (i.value === nk) i.checked = false; });
      }
      renderShop();
    });
    renderShop();
  }

  /* ------------------------------------------------------------ product page */
  var pdp = $("[data-pdp]");
  if (pdp) {
    var slug = pdp.getAttribute("data-pdp");
    var main = $("#galMain");
    $$(".gal__thumb").forEach(function (t) {
      t.addEventListener("click", function () {
        var src = t.getAttribute("data-src");
        $$(".gal__thumb").forEach(function (x) { x.classList.remove("is-on"); });
        t.classList.add("is-on");
        if (main) {
          main.classList.remove("is-in");
          main.src = src;
          main.alt = t.getAttribute("data-alt") || "";
          var pack = src.indexOf("/products/") !== -1;
          main.classList.toggle("is-photo", !pack);
        }
      });
    });
    var qtyInput = $("#pdpQty");
    $$(".qty__b").forEach(function (b) {
      b.addEventListener("click", function () {
        if (!qtyInput) return;
        var cur = parseInt(qtyInput.value.replace(/[۰-۹]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹".indexOf(d); }), 10) || 1;
        cur += Number(b.getAttribute("data-step"));
        if (cur < 1) cur = 1;
        if (cur > 10) cur = 10;
        qtyInput.value = S.num(cur);
      });
    });
    function currentMl() {
      var el = $('input[name="size"]:checked');
      return el ? Number(el.value) : S.defaultMl(slug);
    }
    function currentQty() {
      if (!qtyInput) return 1;
      var v = parseInt(qtyInput.value.replace(/[۰-۹]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹".indexOf(d); }), 10);
      return isNaN(v) || v < 1 ? 1 : v;
    }
    function addCurrent() {
      var f = S.find(slug);
      S.add(slug, currentMl(), currentQty());
      toast("«" + f.fa + "» به سبد خرید اضافه شد");
      openDrawer();
    }
    var addBtn = $("#pdpAdd");
    if (addBtn) addBtn.addEventListener("click", addCurrent);
    var sb = $("[data-sticky-add]");
    if (sb) sb.addEventListener("click", addCurrent);

    var sticky = $("#stickyBuy");
    if (sticky && "IntersectionObserver" in window) {
      var anchor = $(".pdp__buy");
      var sio = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { sticky.classList.toggle("is-on", !en.isIntersecting); });
      }, { threshold: 0 });
      if (anchor) sio.observe(anchor);
    }
  }

  /* ------------------------------------------------------------ cart page */
  var cartList = $("#cartList");
  if (cartList) {
    function renderCartPage() {
      var lines = S.lines();
      $("#cartEmpty").hidden = lines.length > 0;
      $("#toCheckout").style.display = lines.length ? "" : "none";
      document.querySelector(".cart-page__side").style.display = lines.length ? "" : "none";
      cartList.innerHTML = lines.map(function (l) {
        return '<div class="cart-line">' +
          '<div class="cart-line__media"><img src="assets/img/' + l.frag.img + '" alt="' + l.frag.fa + '"></div>' +
          '<div class="cart-line__info"><h3>' + l.frag.fa + '</h3>' +
          '<p class="muted">' + l.frag.latin + " · " + l.opt.label + "</p>" +
          '<div class="cart-line__tools"><div class="qty">' +
          '<button class="qty__b" data-cstep="-1" data-slug="' + l.slug + '" data-ml="' + l.ml + '" aria-label="کاهش">' + ico("minus") + "</button>" +
          '<input type="text" value="' + S.num(l.qty) + '" inputmode="numeric" data-cqty="' + l.slug + "|" + l.ml + '" aria-label="تعداد">' +
          '<button class="qty__b" data-cstep="1" data-slug="' + l.slug + '" data-ml="' + l.ml + '" aria-label="افزایش">' + ico("plus") + "</button>" +
          "</div>" +
          '<button class="link-x" data-cdel="' + l.slug + "|" + l.ml + '">حذف از سبد</button>' +
          '<a class="link-x" href="product-' + l.slug + '.html">مشاهدهٔ محصول</a>' +
          "</div></div>" +
          '<div class="cart-line__price">' + S.money(l.total) + "</div></div>";
      }).join("");
      $("#sumSub").textContent = S.money(S.subtotal());
      var free = S.subtotal() >= S.freeShipFrom;
      $("#sumShip").textContent = free ? "رایگان" : S.money(S.shipCost("post"));
      var info = S.couponInfo();
      $("#sumTotal").textContent = S.money(S.total(free ? "free" : "post"));
      $("#couponMsg").textContent = info ? "کد «" + info.code + "» اعمال شد (" + S.num(info.pct) + "٪)" : "";
      syncCounts();
    }
    renderCartPage();
    document.addEventListener("nafeh:change", renderCartPage);
    var cb = $("#couponBtn");
    if (cb) cb.addEventListener("click", function () {
      var code = $("#coupon").value;
      if (S.applyCoupon(code)) toast("کد تخفیف اعمال شد");
      else toast("کد تخفیف معتبر نیست. کد نمایشی: NAFEH10");
    });
  }

  /* ------------------------------------------------------------ checkout */
  var form = $("#checkoutForm");
  if (form) {
    var step = 1;
    function showStep(n) {
      step = n;
      $$(".fset", form).forEach(function (fs) { fs.hidden = Number(fs.getAttribute("data-step")) !== n; });
      $$("[data-step-dot]").forEach(function (li) {
        var i = Number(li.getAttribute("data-step-dot"));
        li.classList.toggle("is-on", i === n);
        li.classList.toggle("is-done", i < n);
      });
      window.scrollTo({ top: Math.max(0, $(".steps").offsetTop - 140), behavior: REDUCED ? "auto" : "smooth" });
    }
    function setErr(id, msg) {
      var el = $('[data-err="' + id + '"]');
      if (el) el.textContent = msg || "";
      return !msg;
    }
    function digitsOf(v) {
      return String(v).replace(/[۰-۹]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹".indexOf(d); });
    }
    function validateStep1() {
      var ok = true;
      ok = setErr("co-name", $("#co-name").value.trim().length >= 3 ? "" : "نام باید حداقل ۳ حرف باشد.") && ok;
      ok = setErr("co-phone", /^09\d{9}$/.test(digitsOf($("#co-phone").value).trim()) ? "" : "شمارهٔ موبایل معتبر نیست (۰۹xxxxxxxxx).") && ok;
      var em = $("#co-email").value.trim();
      ok = setErr("co-email", !em || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em) ? "" : "ایمیل معتبر نیست.") && ok;
      ok = setErr("co-city", $("#co-city").value.trim().length >= 2 ? "" : "شهر را وارد کنید.") && ok;
      ok = setErr("co-address", $("#co-address").value.trim().length >= 10 ? "" : "نشانی باید کامل‌تر باشد.") && ok;
      ok = setErr("co-postal", /^\d{10}$/.test(digitsOf($("#co-postal").value).trim()) ? "" : "کد پستی باید ۱۰ رقم باشد.") && ok;
      return ok;
    }
    function shipMethod() {
      var el = $('input[name="ship"]:checked');
      return el ? el.value : "post";
    }
    function renderSummary() {
      var lines = S.lines();
      var box = $("#checkoutItems");
      if (box) {
        box.innerHTML = lines.map(function (l) {
          return '<div class="sum__row"><span>' + l.frag.fa + " × " + S.num(l.qty) +
            "</span><b>" + S.money(l.total) + "</b></div>";
        }).join("") || '<div class="sum__row"><span>سبد خرید خالی است</span><b>—</b></div>';
      }
      var cost = S.shipCost(shipMethod());
      if (S.count() && cost === 0 && shipMethod() !== "free") cost = 0;
      $("#coSub").textContent = S.money(S.subtotal());
      $("#coShip").textContent = cost === 0 ? "رایگان" : S.money(cost);
      $("#coDiscount").textContent = S.discount() ? "-" + S.money(S.discount()) : "—";
      $("#coTotal").textContent = S.money(S.subtotal() - S.discount() + cost);
    }
    $$("[data-next]").forEach(function (b) {
      b.addEventListener("click", function () {
        var target = Number(b.getAttribute("data-next"));
        if (step === 1 && !validateStep1()) { toast("لطفاً خطاهای فرم را برطرف کنید"); return; }
        showStep(target);
        renderSummary();
      });
    });
    $$("[data-prev]").forEach(function (b) {
      b.addEventListener("click", function () { showStep(Number(b.getAttribute("data-prev"))); });
    });
    $$(".opt input").forEach(function (i) {
      i.addEventListener("change", function () {
        i.closest(".opts, .pay").querySelectorAll(".opt").forEach(function (o) {
          o.classList.toggle("is-on", o.contains(i));
        });
        renderSummary();
      });
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!validateStep1()) { showStep(1); toast("لطفاً خطاهای فرم را برطرف کنید"); return; }
      if (S.count() === 0) { toast("سبد خرید خالی است"); return; }
      var code = "NF-" + S.num(1405) + "-" + S.num(Math.floor(1000 + Math.random() * 8999));
      $("#orderCode").textContent = code;
      form.hidden = true;
      $(".steps").hidden = true;
      $("#orderDone").hidden = false;
      S.clear();
      renderSummary();
      syncCounts();
      window.scrollTo({ top: 0, behavior: REDUCED ? "auto" : "smooth" });
    });
    renderSummary();
    document.addEventListener("nafeh:change", renderSummary);
  }

  /* ------------------------------------------------------------ wishlist */
  var wishGrid = $("#wishGrid");
  if (wishGrid) {
    function renderWish() {
      var slugs = S.wish();
      var list = slugs.map(function (s) { return S.find(s); }).filter(Boolean);
      wishGrid.innerHTML = list.map(function (f) { return cardHTML(f); }).join("");
      $("#wishEmpty").hidden = list.length > 0;
      syncCounts();
    }
    renderWish();
    document.addEventListener("nafeh:change", renderWish);
  }

  /* ------------------------------------------------------------ account */
  var tabs = $$(".tab");
  if (tabs.length) {
    tabs.forEach(function (t) {
      t.addEventListener("click", function () {
        tabs.forEach(function (x) { x.classList.toggle("is-on", x === t); });
        var isLogin = t.getAttribute("data-tab") === "login";
        $("#loginForm").hidden = !isLogin;
        $("#registerForm").hidden = isLogin;
      });
    });
    function digitsOnly(v) { return String(v).replace(/[۰-۹]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹".indexOf(d); }); }
    var lf = $("#loginForm");
    lf.addEventListener("submit", function (e) {
      e.preventDefault();
      var ok = true;
      var phone = digitsOnly($("#lg-phone").value).trim();
      ok = setFieldErr("lg-phone", /^09\d{9}$/.test(phone) ? "" : "شمارهٔ موبایل معتبر نیست.") && ok;
      ok = setFieldErr("lg-pass", $("#lg-pass").value.length >= 6 ? "" : "گذرواژه باید حداقل ۶ نویسه باشد.") && ok;
      toast(ok ? "ورود نمایشی انجام شد" : "لطفاً خطاها را برطرف کنید");
    });
    var rf = $("#registerForm");
    rf.addEventListener("submit", function (e) {
      e.preventDefault();
      var ok = true;
      ok = setFieldErr("rg-name", $("#rg-name").value.trim().length >= 3 ? "" : "نام را کامل وارد کنید.") && ok;
      ok = setFieldErr("rg-phone", /^09\d{9}$/.test(digitsOnly($("#rg-phone").value).trim()) ? "" : "شمارهٔ موبایل معتبر نیست.") && ok;
      var em = $("#rg-email").value.trim();
      ok = setFieldErr("rg-email", /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em) ? "" : "ایمیل معتبر نیست.") && ok;
      toast(ok ? "حساب نمایشی ساخته شد" : "لطفاً خطاها را برطرف کنید");
    });
  }
  function setFieldErr(id, msg) {
    var el = $('[data-err="' + id + '"]');
    if (el) el.textContent = msg || "";
    return !msg;
  }

  /* ------------------------------------------------------------ contact */
  var cf2 = $("#contactForm");
  if (cf2) {
    cf2.addEventListener("submit", function (e) {
      e.preventDefault();
      var ok = true;
      ok = setFieldErr("ct-name", $("#ct-name").value.trim().length >= 3 ? "" : "نام را کامل وارد کنید.") && ok;
      var ph = String($("#ct-phone").value).replace(/[۰-۹]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹".indexOf(d); }).trim();
      ok = setFieldErr("ct-phone", /^09\d{9}$/.test(ph) ? "" : "شمارهٔ موبایل معتبر نیست.") && ok;
      ok = setFieldErr("ct-msg", $("#ct-msg").value.trim().length >= 10 ? "" : "متن پیام کوتاه است.") && ok;
      if (ok) {
        $("#contactDone").hidden = false;
        cf2.reset();
        toast("پیام شما ثبت شد");
      } else {
        toast("لطفاً خطاها را برطرف کنید");
      }
    });
  }

  /* ------------------------------------------------------------ newsletter */
  var nf2 = $("#newsForm");
  if (nf2) {
    nf2.addEventListener("submit", function (e) {
      e.preventDefault();
      var mail = $("#newsEmail").value.trim();
      var msg = $("[data-news-msg]");
      var ok = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(mail);
      if (msg) msg.textContent = ok ? "عضویت شما ثبت شد. سپاس!" : "نشانی ایمیل معتبر نیست.";
      if (ok) nf2.reset();
    });
  }

  /* ------------------------------------------------------------ init */
  syncCounts();
  renderDrawer();
  document.addEventListener("nafeh:change", function () { syncCounts(); renderDrawer(); });
  window.addEventListener("storage", function () { window.location.reload(); });
})();
