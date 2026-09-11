/* ==========================================================================
   چشم‌باز — کلاینت داشبورد
   قاعده: هیچ داده‌ای در سمت کلاینت ساخته نمی‌شود. هر عددی که نمایش داده
   می‌شود یا از API آمده یا مستقیماً از آن محاسبه شده. نبود داده یعنی پیام
   صریح، نه عدد جایگزین.
   ========================================================================== */
(function () {
  "use strict";

  var BOOT = window.__CBZ__ || { config: {}, registry: { assets: [], kinds: [] } };
  var OWNER_HEADER = "X-Owner";

  var state = {
    selected: null,
    range: "7D",
    kind: "all",
    query: "",
    moversWindow: "1D",
    autoRefresh: true,
    series: null,
    overview: null,
    watchlist: {},
    inFlight: {},
    showSuppressed: true
  };

  /* ------------------------------------------------------------------ utils */
  var FA = "۰۱۲۳۴۵۶۷۸۹";
  function fa(value) {
    return String(value).replace(/[0-9]/g, function (d) { return FA[+d]; });
  }

  function faGroup(value, decimals) {
    if (value === null || value === undefined || isNaN(value)) { return "—"; }
    var d = decimals || 0;
    var text = Number(value).toFixed(d);
    var parts = text.split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, "٬");
    return fa(parts.join("٫"));
  }

  function el(id) { return document.getElementById(id); }

  function esc(text) {
    return String(text === null || text === undefined ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function clockText(ts) {
    if (!ts) { return "—"; }
    var d = new Date(ts * 1000);
    return fa(("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2) + ":" + ("0" + d.getSeconds()).slice(-2));
  }

  function dateText(ts, withDate) {
    if (!ts) { return "—"; }
    var d = new Date(ts * 1000);
    var t = ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
    if (!withDate) { return fa(t); }
    var j = d.toLocaleDateString("fa-IR", { month: "2-digit", day: "2-digit" });
    return j + " " + fa(t);
  }

  function dirClass(direction) {
    if (direction > 0) { return "up"; }
    if (direction < 0) { return "down"; }
    return "flat";
  }

  var toastTimer = null;
  function toast(message, isError) {
    var node = el("toast");
    if (!node) { return; }
    node.textContent = message;
    node.className = "toast on" + (isError ? " err" : "");
    if (toastTimer) { clearTimeout(toastTimer); }
    toastTimer = setTimeout(function () { node.className = "toast"; }, 3600);
  }

  /* -------------------------------------------------------------------- API */
  function api(path, options) {
    var opts = options || {};
    opts.headers = opts.headers || {};
    opts.headers["Accept"] = "application/json";
    if (opts.body && !opts.headers["Content-Type"]) {
      opts.headers["Content-Type"] = "application/json";
    }
    return fetch(path, opts).then(function (response) {
      return response.json().catch(function () { return null; }).then(function (payload) {
        if (!payload || payload.ok !== true) {
          var err = (payload && payload.error) || {};
          var message = err.message || ("خطای ارتباط با سرور (کد " + fa(response.status) + ")");
          var error = new Error(message);
          error.code = err.code || "http_" + response.status;
          error.field = err.field;
          error.status = response.status;
          throw error;
        }
        return payload.data;
      });
    });
  }

  function guard(key, promise) {
    if (state.inFlight[key]) { return Promise.resolve(null); }
    state.inFlight[key] = true;
    return promise.finally(function () { state.inFlight[key] = false; });
  }

  /* ----------------------------------------------------------------- ticker */
  function renderTicker(items) {
    var host = el("ticker");
    if (!host) { return; }
    if (!items || !items.length) {
      host.innerHTML = '<div class="skeleton">قیمت شاخصی در دسترس نیست</div>';
      return;
    }
    host.innerHTML = items.map(function (card) {
      var cls = dirClass(card.direction);
      var change = card.change_pct === null ? "—" : (card.direction >= 0 ? "+" : "−") + card.change_pct_text;
      return (
        '<div class="tick' + (card.slug === state.selected ? " selected" : "") + '" data-slug="' + esc(card.slug) + '">' +
          '<div class="t"><span>' + esc(card.title) + '</span><span class="badge ' + esc(card.freshness) + '">' + esc(card.freshness_label) + '</span></div>' +
          '<div class="p">' + esc(card.price_text) + '</div>' +
          '<div class="c ' + cls + '">' + esc(change) + '</div>' +
        '</div>'
      );
    }).join("");
  }

  /* ------------------------------------------------------------------- stats */
  function renderStats(data) {
    var host = el("market-stats");
    if (!host) { return; }
    var totals = data.totals || {};
    var history = data.history || {};
    var stats = [
      { k: "دارایی‌ها", v: faGroup(totals.assets), cls: "" },
      { k: "قیمت‌های موجود", v: faGroup(totals.with_data), cls: "" },
      { k: "داده تازه", v: faGroup(totals.usable), cls: "" },
      { k: "صعودی", v: faGroup(totals.gainers), cls: "up" },
      { k: "نزولی", v: faGroup(totals.losers), cls: "down" },
      { k: "نمونه‌های تاریخچه", v: faGroup(history.points), cls: "gold" }
    ];
    host.innerHTML = stats.map(function (item) {
      return '<div class="stat"><div class="k">' + item.k + '</div><div class="v ' + item.cls + '">' + item.v + "</div></div>";
    }).join("");
  }

  /* ------------------------------------------------------------------ assets */
  function renderKindChips(data) {
    var host = el("kind-chips");
    if (!host) { return; }
    var kinds = [{ value: "all", label: "همه", count: data.totals ? data.totals.assets : 0 }];
    (data.groups || []).forEach(function (group) {
      kinds.push({ value: group.kind, label: group.label, count: group.count });
    });
    host.innerHTML = kinds.map(function (kind) {
      return '<button type="button" class="chip' + (state.kind === kind.value ? " on" : "") +
        '" data-kind="' + esc(kind.value) + '">' + esc(kind.label) + " (" + faGroup(kind.count) + ")</button>";
    }).join("");
  }

  function assetRow(card) {
    var cls = dirClass(card.direction);
    var change = card.change_pct === null ? "—" : (card.direction > 0 ? "+" : card.direction < 0 ? "−" : "") + card.change_pct_text;
    var starred = state.watchlist[card.slug] ? "★" : "☆";
    return (
      '<tr data-slug="' + esc(card.slug) + '"' + (card.slug === state.selected ? ' class="selected"' : "") + ">" +
        '<td class="name">' + esc(card.title) +
          (card.symbol ? '<span class="sym">' + esc(card.symbol) + "</span>" : "") + "</td>" +
        '<td class="price num">' + esc(card.price_text) + "</td>" +
        '<td class="pct num ' + cls + '">' + esc(change) + "</td>" +
        '<td class="num hide-sm">' + esc(card.day_low_text) + " – " + esc(card.day_high_text) + "</td>" +
        '<td class="hide-sm">' + esc(card.source || "—") + "</td>" +
        '<td><span class="badge ' + esc(card.freshness) + '">' + esc(card.freshness_label) + "</span></td>" +
        '<td class="hide-sm num">' + esc(card.age_text) + "</td>" +
        '<td><button type="button" class="btn tiny" data-star="' + esc(card.slug) + '" title="افزودن به دیده‌بان">' + starred + "</button></td>" +
      "</tr>"
    );
  }

  function renderAssets(data, options) {
    var host = el("assets-body");
    var hint = el("assets-hint");
    if (!host) { return; }
    var opts = options || {};
    var cards = opts.cards || [];
    if (!opts.cards) {
      (data.groups || []).forEach(function (group) {
        if (state.kind === "all" || state.kind === group.kind) {
          cards = cards.concat(group.assets);
        }
      });
    }
    if (!cards.length) {
      host.innerHTML = '<tr><td colspan="8" class="skeleton">' + esc(opts.empty || "قلمی با این فیلتر نیست") + "</td></tr>";
    } else {
      host.innerHTML = cards.map(assetRow).join("");
    }
    if (hint) {
      hint.textContent = opts.hint || (faGroup(cards.length) + " قلم");
    }
  }

  /* ------------------------------------------------------------------ movers */
  function moverRow(item) {
    var cls = dirClass(item.direction);
    return (
      '<div class="row" data-slug="' + esc(item.slug) + '">' +
        '<div class="grow"><div class="title">' + esc(item.title) + "</div>" +
        '<div class="sub">' + esc(item.price_text) + "</div></div>" +
        '<div class="val ' + cls + '">' + esc(item.arrow) + " " + esc(item.change_pct_text) + "</div>" +
      "</div>"
    );
  }

  function renderMovers(data) {
    ["movers-up", "movers-down"].forEach(function (id) {});
    var up = el("movers-up");
    var down = el("movers-down");
    if (up) {
      up.innerHTML = (data.gainers || []).length
        ? data.gainers.map(moverRow).join("")
        : '<div class="empty">در این بازه صعودی ثبت نشده است.</div>';
    }
    if (down) {
      down.innerHTML = (data.losers || []).length
        ? data.losers.map(moverRow).join("")
        : '<div class="empty">در این بازه نزولی ثبت نشده است.</div>';
    }
    var host = el("mover-windows");
    if (host) {
      var windows = [{ key: "1D", label: "۲۴ ساعت" }, { key: "7D", label: "۷ روز" }, { key: "30D", label: "۳۰ روز" }];
      host.innerHTML = windows.map(function (item) {
        return '<button type="button" class="chip' + (state.moversWindow === item.key ? " on" : "") +
          '" data-mover-window="' + item.key + '">' + item.label + "</button>";
      }).join("");
    }
  }

  /* ----------------------------------------------------------------- sources */
  function renderSources(data) {
    var host = el("sources-list");
    var hint = el("sources-hint");
    if (!host) { return; }
    var items = data.items || [];
    if (!items.length) {
      host.innerHTML = '<div class="empty">هنوز واکشی‌ای ثبت نشده است. دکمهٔ «واکشی تازه» را بزنید.</div>';
      return;
    }
    host.innerHTML = items.map(function (item) {
      var ok = item.last_ok;
      var dot = ok === true ? "ok" : ok === false ? "bad" : "warn";
      var state1 = ok === true ? "سالم" : ok === false ? "خطا" : "نامعلوم";
      var reliability = item.reliability || {};
      var rate = reliability.success_rate === null || reliability.success_rate === undefined
        ? "—" : faGroup(reliability.success_rate * 100, 0) + "٪";
      var breaker = item.breaker && item.breaker.open
        ? '<span class="badge expired">مدارشکن باز</span>' : "";
      return (
        '<div class="src">' +
          '<span class="dot ' + dot + '"></span>' +
          '<div class="grow"><div class="nm">' + esc(item.name) + " " + breaker + "</div>" +
          '<div class="meta">آخرین بررسی: ' + esc(dateText(item.last_checked_at, true)) +
          " · موفقیت: " + rate +
          (item.last_latency_ms ? " · تأخیر: " + faGroup(item.last_latency_ms) + " م‌ث" : "") + "</div>" +
          (item.last_error ? '<div class="err">' + esc(item.last_error) + "</div>" : "") +
          "</div>" +
          '<span class="badge ' + (ok === true ? "live" : ok === false ? "expired" : "unknown") + '">' + state1 + "</span>" +
        "</div>"
      );
    }).join("");
    if (hint) { hint.textContent = faGroup(items.length) + " منبع"; }
  }

  /* --------------------------------------------------------------- watchlist */
  function renderWatchlist(data) {
    var host = el("watchlist-body");
    var count = el("watchlist-count");
    if (count) { count.textContent = faGroup(data.count) + " قلم"; }
    if (!host) { return; }
    if (!data.items || !data.items.length) {
      host.innerHTML = '<div class="empty">هنوز قلمی نشان نکرده‌اید. ستارهٔ کنار هر دارایی را بزنید.</div>';
      return;
    }
    host.innerHTML = data.items.map(function (card) {
      var cls = dirClass(card.direction);
      return (
        '<div class="row" data-slug="' + esc(card.slug) + '">' +
          '<div class="grow"><div class="title">' + esc(card.title) + "</div>" +
          '<div class="sub">' + esc(card.price_text) + " · " + esc(card.freshness_label) + "</div></div>" +
          '<div class="val ' + cls + '">' + esc(card.change_pct_text) + "</div>" +
          '<button type="button" class="btn tiny" data-star="' + esc(card.slug) + '">★</button>' +
        "</div>"
      );
    }).join("");
  }

  /* ------------------------------------------------------------------ alerts */
  function renderAlertKinds() {
    var host = el("alert-kind");
    if (!host) { return; }
    var kinds = [
      { value: "above", label: "بالاتر از (قیمت)" },
      { value: "below", label: "پایین‌تر از (قیمت)" },
      { value: "pct_move", label: "نوسان بیش از (٪)" }
    ];
    host.innerHTML = kinds.map(function (kind) {
      return '<option value="' + kind.value + '">' + esc(kind.label) + "</option>";
    }).join("");
  }

  function alertRow(rule) {
    var cls = rule.direction ? dirClass(rule.direction) : "flat";
    var status = rule.status === "active"
      ? '<span class="badge live">فعال</span>' : '<span class="badge unknown">متوقف</span>';
    var gate = rule.is_usable ? "" : '<span class="badge stale">دادهٔ غیرقابل‌اتکا</span>';
    return (
      '<div class="row" data-rule="' + esc(rule.id) + '">' +
        '<div class="grow">' +
          '<div class="title">' + esc(rule.title) + " · " + esc(rule.kind_label) + " " + esc(rule.threshold_text) + "</div>" +
          '<div class="sub">قیمت فعلی: ' + esc(rule.current_price_text) + " · تغییر: " + esc(rule.current_pct_text) +
            " · فاصله: " + esc(rule.distance_text) + (rule.fired_count ? " · وقوع: " + faGroup(rule.fired_count) : "") +
          "</div>" +
          '<div class="sub">' + status + " " + gate + "</div>" +
        "</div>" +
        '<button type="button" class="btn tiny" data-toggle-rule="' + esc(rule.id) + '">' +
          (rule.status === "active" ? "توقف" : "فعال‌سازی") + "</button>" +
        '<button type="button" class="btn tiny" data-delete-rule="' + esc(rule.id) + '">حذف</button>' +
      "</div>"
    );
  }

  function renderAlerts(data) {
    var host = el("alerts-body");
    var stats = el("alerts-stats");
    if (stats) {
      var s = data.stats || {};
      stats.textContent = "فعال: " + faGroup(s.active_rules) + " از " + faGroup(s.rules) +
        " · رخداد ۲۴س: " + faGroup(s.events_24h);
    }
    if (!host) { return; }
    if (!data.items || !data.items.length) {
      host.innerHTML = '<div class="empty">هیچ هشداری ساخته نشده است.</div>';
      return;
    }
    host.innerHTML = data.items.map(alertRow).join("");
  }

  function renderEvents(data) {
    var host = el("events-body");
    if (!host) { return; }
    if (!data.items || !data.items.length) {
      host.innerHTML = '<div class="empty">رخدادی ثبت نشده است.</div>';
      return;
    }
    host.innerHTML = data.items.map(function (event) {
      var when = dateText(event.created_at, true);
      var tag = event.suppressed
        ? '<span class="badge stale">مهارشده</span>'
        : '<span class="badge live">آگاه‌سازی</span>';
      // متن رخداد قیمت را در خود دارد؛ فقط اگر نداشت جدا نشان می‌دهیم
      // تا همان عدد دو بار پشت سر هم تکرار نشود.
      var price = event.price_text && event.message.indexOf(event.price_text) === -1
        ? esc(event.price_text) + " · "
        : "";
      return (
        '<div class="row">' +
          '<div class="grow"><div class="title">' + esc(event.message) + "</div>" +
          '<div class="sub">' + price + esc(when) +
          (event.reason ? " · " + esc(event.reason) : "") + "</div></div>" +
          tag +
        "</div>"
      );
    }).join("");
  }

  /* ------------------------------------------------------------------ status */
  function renderStatus(data) {
    var host = el("status-body");
    if (!host) { return; }
    var scheduler = data.scheduler || {};
    var database = data.database || {};
    var history = data.history || {};
    var rows = [
      ["زمان‌بند", scheduler.running ? "در حال اجرا" : "متوقف"],
      ["دورهای اجراشده", faGroup(scheduler.cycles)],
      ["بازهٔ جمع‌آوری", faGroup(scheduler.collect_interval_seconds) + " ثانیه"],
      ["بازهٔ ارزیابی هشدار", faGroup(scheduler.alert_interval_seconds) + " ثانیه"],
      ["حجم پایگاه داده", faGroup(database.size_bytes / 1024, 0) + " کیلوبایت"],
      ["نمونه‌های تاریخچه", faGroup(history.points) + " برای " + faGroup(history.assets) + " دارایی"],
      ["نسخهٔ اسکیما", faGroup(database.schema_version)],
      ["مدارشکن", scheduler.lease ? esc(scheduler.lease.split("|")[0]) : "آزاد"]
    ];
    host.innerHTML = rows.map(function (row) {
      return '<div class="row"><div class="grow"><div class="title">' + row[0] + '</div></div><div class="val">' + row[1] + "</div></div>";
    }).join("");
  }

  /* ------------------------------------------------------------------- chart */
  function svgNode(name, attrs) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    return node;
  }

  function renderChart(series, card) {
    var wrap = el("chart-wrap");
    var title = el("chart-title");
    var priceNode = el("chart-price");
    var meta = el("chart-meta");
    var source = el("chart-source");
    if (!wrap) { return; }

    if (title && card) { title.textContent = card.title + (card.symbol ? " · " + card.symbol : ""); }
    if (priceNode && card) { priceNode.textContent = card.price_text; }
    if (meta && card) {
      var cls = dirClass(card.direction);
      var change = card.change_pct === null ? "—" : (card.direction > 0 ? "+" : card.direction < 0 ? "−" : "") + card.change_pct_text;
      meta.innerHTML =
        '<span class="' + cls + '">' + esc(change) + " / " + esc(card.change_abs_text) + "</span>" +
        "<span>منبع: " + esc(card.source || "—") + "</span>" +
        "<span>مشاهده: " + esc(card.age_text) + "</span>" +
        '<span class="badge ' + esc(card.freshness) + '">' + esc(card.freshness_label) + "</span>" +
        (card.change_basis ? "<span>مبنای تغییر: " + esc(card.change_basis) + "</span>" : "");
    }
    if (source && card) { source.textContent = card.observed_at ? "زمان مشاهده: " + dateText(card.observed_at, true) : "—"; }

    var points = (series && series.points) || [];
    if (!series || !series.has_data || points.length < 2) {
      wrap.innerHTML =
        '<div class="chart-empty"><b>دادهٔ کافی برای این بازه ثبت نشده است</b>' +
        "تاریخچه از لحظهٔ شروع سرویس انباشته می‌شود، پس بازه‌های بلندتر پس از چند روز پر می‌شوند. " +
        "برای پرشدن فوری، «واکشی تازه» را بزنید." +
        (series ? '<div style="margin-top:6px">نمونه‌های ثبت‌شده: ' + faGroup(series.count) + "</div>" : "") +
        "</div>";
      return;
    }

    var W = 1000, H = 330, padT = 18, padB = 30, padX = 62;
    var prices = points.map(function (p) { return p.price; });
    var min = Math.min.apply(null, prices);
    var max = Math.max.apply(null, prices);
    if (max === min) { max = min + Math.max(1e-6, Math.abs(min) * 0.001); }
    var span = max - min;
    var top = max + span * 0.08;
    var bottom = min - span * 0.08;
    var innerH = H - padT - padB;
    var innerW = W - padX * 2;

    function xAt(index) { return padX + (index / (points.length - 1)) * innerW; }
    function yAt(price) { return padT + (1 - (price - bottom) / (top - bottom)) * innerH; }

    var svg = svgNode("svg", { viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none", role: "img" });
    var defs = svgNode("defs", {});
    var gradient = svgNode("linearGradient", { id: "cbz-fill", x1: "0", y1: "0", x2: "0", y2: "1" });
    gradient.appendChild(svgNode("stop", { offset: "0%", "stop-color": "#e3b856", "stop-opacity": "0.30" }));
    gradient.appendChild(svgNode("stop", { offset: "100%", "stop-color": "#e3b856", "stop-opacity": "0.01" }));
    defs.appendChild(gradient);
    svg.appendChild(defs);

    for (var g = 0; g <= 4; g++) {
      var y = padT + (g / 4) * innerH;
      svg.appendChild(svgNode("line", {
        x1: padX, y1: y, x2: W - padX / 2, y2: y, stroke: "#1d2431", "stroke-width": 1
      }));
      var labelPrice = top - (g / 4) * (top - bottom);
      var text = svgNode("text", {
        x: padX - 8, y: y + 4, fill: "#8794a8", "font-size": 13, "text-anchor": "end"
      });
      text.textContent = faGroup(labelPrice, labelPrice > 1000 ? 0 : 2);
      svg.appendChild(text);
    }

    var line = "";
    var area = "M " + xAt(0) + " " + (H - padB) + " ";
    points.forEach(function (point, index) {
      var px = xAt(index), py = yAt(point.price);
      line += (index === 0 ? "M " : "L ") + px + " " + py + " ";
      area += "L " + px + " " + py + " ";
    });
    area += "L " + xAt(points.length - 1) + " " + (H - padB) + " Z";

    svg.appendChild(svgNode("path", { d: area, fill: "url(#cbz-fill)", stroke: "none" }));
    svg.appendChild(svgNode("path", {
      d: line, fill: "none", stroke: "#e3b856", "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round"
    }));

    var last = points[points.length - 1];
    svg.appendChild(svgNode("circle", {
      cx: xAt(points.length - 1), cy: yAt(last.price), r: 4.5, fill: "#e3b856",
      stroke: "#07090d", "stroke-width": 2
    }));

    var withDate = series.range !== "1D";
    [0, Math.floor((points.length - 1) / 2), points.length - 1].forEach(function (index, order) {
      if (index < 0 || !points[index]) { return; }
      var anchor = order === 0 ? "end" : order === 2 ? "start" : "middle";
      var xLabel = order === 0 ? padX : order === 2 ? W - padX / 2 : xAt(index);
      var node = svgNode("text", {
        x: xLabel, y: H - 8, fill: "#8794a8", "font-size": 13, "text-anchor": anchor
      });
      node.textContent = dateText(points[index].ts, withDate);
      svg.appendChild(node);
    });

    var hoverLine = svgNode("line", {
      x1: 0, y1: padT, x2: 0, y2: H - padB, stroke: "#e3b856",
      "stroke-width": 1, "stroke-dasharray": "4 4", opacity: 0
    });
    var hoverDot = svgNode("circle", { cx: 0, cy: 0, r: 4, fill: "#e3b856", opacity: 0 });
    svg.appendChild(hoverLine);
    svg.appendChild(hoverDot);

    wrap.innerHTML = "";
    wrap.appendChild(svg);

    var tooltip = document.createElement("div");
    tooltip.className = "tooltip";
    wrap.appendChild(tooltip);

    function onMove(event) {
      var rect = svg.getBoundingClientRect();
      var relX = ((event.clientX - rect.left) / rect.width) * W;
      var ratio = (relX - padX) / innerW;
      ratio = Math.max(0, Math.min(1, ratio));
      var index = Math.round(ratio * (points.length - 1));
      var point = points[index];
      if (!point) { return; }
      var px = xAt(index), py = yAt(point.price);
      hoverLine.setAttribute("x1", px);
      hoverLine.setAttribute("x2", px);
      hoverLine.setAttribute("opacity", 0.65);
      hoverDot.setAttribute("cx", px);
      hoverDot.setAttribute("cy", py);
      hoverDot.setAttribute("opacity", 1);
      tooltip.classList.add("on");
      tooltip.innerHTML = '<span class="tv">' + esc(point.price_text) + "</span> " +
        (card && card.unit_label ? esc(card.unit_label) : "") + "<br>" +
        dateText(point.ts, true) +
        (point.samples > 1 ? " · " + faGroup(point.samples) + " نمونه" : "");
      var leftPx = (px / W) * rect.width;
      tooltip.style.left = leftPx + "px";
      tooltip.style.top = ((py / H) * rect.height) + "px";
    }

    function onLeave() {
      tooltip.classList.remove("on");
      hoverLine.setAttribute("opacity", 0);
      hoverDot.setAttribute("opacity", 0);
    }

    svg.addEventListener("mousemove", onMove);
    svg.addEventListener("mouseleave", onLeave);
  }

  function renderRanges(series) {
    var host = el("range-row");
    if (!host || !series) { return; }
    host.innerHTML = (series.ranges || []).map(function (item) {
      var cls = "chip" + (item.key === state.range ? " on" : "");
      var disabled = item.has_data ? "" : ' title="برای این بازه هنوز دادهٔ کافی ثبت نشده"';
      return '<button type="button" class="' + cls + '"' + disabled + ' data-range="' + esc(item.key) + '">' +
        esc(item.label) + "</button>";
    }).join("");
  }

  /* ------------------------------------------------------------------ loaders */
  function loadOverview() {
    return guard("overview", api("/api/v1/overview").then(function (data) {
      state.overview = data;
      renderStats(data);
      renderKindChips(data);
      renderTicker(data.featured);
      renderMovers(data.movers || { gainers: [], losers: [] });
      renderSources({ items: data.sources, statuses: data.sources });
      setLive(true, "داده تا " + dateText(data.generated_at, false));
      if (state.query) {
        runSearch(state.query);
      } else {
        renderAssets(data);
      }
      if (!state.selected && data.featured && data.featured.length) {
        selectAsset(data.featured[0].slug, { silent: true });
      }
      return data;
    }));
  }

  function loadSourcesFull() {
    return guard("sources", api("/api/v1/sources").then(function (data) {
      renderSources(data);
      return data;
    }));
  }

  function loadWatchlist() {
    return guard("watchlist", api("/api/v1/watchlist").then(function (data) {
      state.watchlist = {};
      (data.items || []).forEach(function (item) { state.watchlist[item.slug] = true; });
      renderWatchlist(data);
      return data;
    }));
  }

  function loadAlerts() {
    return guard("alerts", api("/api/v1/alerts?page_size=50").then(function (data) {
      renderAlerts(data);
      return data;
    }));
  }

  function loadEvents() {
    var suppressed = state.showSuppressed ? "1" : "0";
    return guard("events", api("/api/v1/events?page_size=40&suppressed=" + suppressed).then(function (data) {
      renderEvents(data);
      return data;
    }));
  }

  function loadStatus() {
    return guard("status", api("/api/v1/status").then(function (data) {
      renderStatus(data);
      return data;
    }));
  }

  function selectAsset(slug, options) {
    var opts = options || {};
    state.selected = slug;
    if (state.overview) {
      var ticker = el("ticker");
      if (ticker) {
        Array.prototype.forEach.call(ticker.children, function (node) {
          if (node.dataset && node.dataset.slug) {
            node.classList.toggle("selected", node.dataset.slug === slug);
          }
        });
      }
      var body = el("assets-body");
      if (body) {
        Array.prototype.forEach.call(body.children, function (node) {
          if (node.dataset && node.dataset.slug) {
            node.classList.toggle("selected", node.dataset.slug === slug);
          }
        });
      }
    }
    if (!opts.silent) { loadSeries(); }
  }

  function loadSeries() {
    if (!state.selected) { return Promise.resolve(null); }
    var slug = state.selected;
    var range = state.range;
    return guard("series", api("/api/v1/assets/" + encodeURIComponent(slug) + "/series?range=" + encodeURIComponent(range))
      .then(function (data) {
        if (state.selected !== slug) { return null; }
        state.series = data;
        renderRanges(data);
        return api("/api/v1/assets/" + encodeURIComponent(slug)).then(function (card) {
          if (state.selected !== slug) { return null; }
          renderChart(data, card);
          return data;
        });
      }));
  }

  function runSearch(query) {
    state.query = query;
    if (!query) {
      if (state.overview) { renderAssets(state.overview); }
      return Promise.resolve(null);
    }
    return guard("search", api("/api/v1/search?q=" + encodeURIComponent(query)).then(function (data) {
      renderAssets(null, {
        cards: data.items,
        hint: data.items.length ? faGroup(data.items.length) + " نتیجه برای «" + query + "»" : "نتیجه‌ای یافت نشد",
        empty: "دارایی‌ای با عبارت «" + query + "» پیدا نشد"
      });
      return data;
    }));
  }

  function loadMovers() {
    return guard("movers", api("/api/v1/movers?window=" + encodeURIComponent(state.moversWindow) + "&limit=5")
      .then(function (data) {
        renderMovers(data);
        return data;
      }));
  }

  function setLive(ok, text) {
    var dot = el("live-dot");
    var label = el("live-text");
    if (dot) { dot.className = "dot " + (ok ? "ok" : "bad"); }
    if (label && text) { label.textContent = text; }
  }

  function loadAll() {
    return Promise.all([
      loadOverview().catch(handleError),
      loadSourcesFull().catch(handleError),
      loadWatchlist().catch(handleError),
      loadAlerts().catch(handleError),
      loadEvents().catch(handleError),
      loadStatus().catch(handleError)
    ]);
  }

  function handleError(error) {
    setLive(false, error.status === 503 ? "داده در دسترس نیست" : "خطا در دریافت داده");
    toast(error.message || "خطا در دریافت داده", true);
    return null;
  }

  /* ------------------------------------------------------------------ events */
  function onCollect() {
    var button = el("btn-collect");
    if (button) { button.disabled = true; button.textContent = "در حال واکشی…"; }
    api("/api/v1/collect", { method: "POST" }).then(function (data) {
      var saved = 0;
      (data.providers || []).forEach(function (run) { saved += run.received || 0; });
      toast("واکشی تمام شد: " + faGroup(saved) + " قیمت از منابع");
      return loadAll().then(function () { return loadSeries(); });
    }).catch(function (error) {
      toast(error.message, true);
    }).finally(function () {
      if (button) { button.disabled = false; button.textContent = "واکشی تازه"; }
    });
  }

  function toggleStar(slug) {
    return api("/api/v1/watchlist/" + encodeURIComponent(slug), { method: "POST" }).then(function (data) {
      state.watchlist[slug] = data.in_watchlist;
      toast(data.in_watchlist ? "به دیده‌بان اضافه شد" : "از دیده‌بان برداشته شد");
      return Promise.all([loadWatchlist(), state.overview ? loadOverview() : Promise.resolve(null)]);
    }).catch(function (error) { toast(error.message, true); });
  }

  function submitAlert(event) {
    event.preventDefault();
    var slug = el("alert-slug").value;
    var kind = el("alert-kind").value;
    var threshold = parseFloat(el("alert-threshold").value);
    var oneShot = el("alert-oneshot").checked;
    var message = el("alert-msg");
    if (isNaN(threshold) || threshold <= 0) {
      message.className = "form-msg err";
      message.textContent = "آستانه باید عددی بزرگ‌تر از صفر باشد.";
      return;
    }
    message.className = "form-msg";
    message.textContent = "در حال ساخت…";
    api("/api/v1/alerts", {
      method: "POST",
      body: JSON.stringify({ slug: slug, kind: kind, threshold: threshold, one_shot: oneShot })
    }).then(function () {
      message.className = "form-msg ok";
      message.textContent = "هشدار ساخته شد.";
      return Promise.all([loadAlerts(), loadEvents()]);
    }).catch(function (error) {
      message.className = "form-msg err";
      message.textContent = error.message;
    });
  }

  function previewAlert() {
    var slug = el("alert-slug").value;
    var kind = el("alert-kind").value;
    var threshold = parseFloat(el("alert-threshold").value);
    var message = el("alert-msg");
    if (isNaN(threshold) || threshold <= 0) {
      message.className = "form-msg err";
      message.textContent = "آستانه نامعتبر است.";
      return;
    }
    message.className = "form-msg";
    message.textContent = "بررسی…";
    api("/api/v1/alerts/preview", {
      method: "POST",
      body: JSON.stringify({ slug: slug, kind: kind, threshold: threshold })
    }).then(function (data) {
      message.className = "form-msg ok";
      message.textContent = (data.would_fire ? "با قیمت فعلی فعال می‌شود" : "با قیمت فعلی فعال نمی‌شود") +
        " · " + (data.current_price_text || "—") + " · تغییر " + (data.current_pct_text || "—");
    }).catch(function (error) {
      message.className = "form-msg err";
      message.textContent = error.message;
    });
  }

  function bindEvents() {
    document.addEventListener("click", function (event) {
      var target = event.target;
      if (!target || !target.closest) { return; }

      var star = target.closest("[data-star]");
      if (star) {
        event.stopPropagation();
        toggleStar(star.getAttribute("data-star"));
        return;
      }

      var range = target.closest("[data-range]");
      if (range) {
        state.range = range.getAttribute("data-range");
        loadSeries();
        return;
      }

      var kindChip = target.closest("[data-kind]");
      if (kindChip) {
        state.kind = kindChip.getAttribute("data-kind");
        if (state.overview) {
          renderKindChips(state.overview);
          renderAssets(state.overview);
        }
        return;
      }

      var moverWindow = target.closest("[data-mover-window]");
      if (moverWindow) {
        state.moversWindow = moverWindow.getAttribute("data-mover-window");
        loadMovers();
        return;
      }

      var toggleRule = target.closest("[data-toggle-rule]");
      if (toggleRule) {
        var ruleId = toggleRule.getAttribute("data-toggle-rule");
        var row = toggleRule.closest("[data-rule]");
        var active = row && row.querySelector(".badge.live");
        api("/api/v1/alerts/" + ruleId, {
          method: "PATCH",
          body: JSON.stringify({ status: active ? "paused" : "active" })
        }).then(function () { return loadAlerts(); }).catch(function (error) { toast(error.message, true); });
        return;
      }

      var deleteRule = target.closest("[data-delete-rule]");
      if (deleteRule) {
        api("/api/v1/alerts/" + deleteRule.getAttribute("data-delete-rule"), { method: "DELETE" })
          .then(function () { toast("هشدار حذف شد"); return Promise.all([loadAlerts(), loadEvents()]); })
          .catch(function (error) { toast(error.message, true); });
        return;
      }

      var asset = target.closest("[data-slug]");
      if (asset) {
        selectAsset(asset.getAttribute("data-slug"));
      }
    });

    var collect = el("btn-collect");
    if (collect) { collect.addEventListener("click", onCollect); }

    var form = el("alert-form");
    if (form) { form.addEventListener("submit", submitAlert); }
    var preview = el("btn-preview");
    if (preview) { preview.addEventListener("click", previewAlert); }

    var suppressed = el("events-suppressed");
    if (suppressed) {
      state.showSuppressed = suppressed.checked;
      suppressed.addEventListener("change", function () {
        state.showSuppressed = suppressed.checked;
        loadEvents();
      });
    }

    var search = el("search-input");
    if (search) {
      var timer = null;
      search.addEventListener("input", function () {
        var value = search.value.trim();
        if (timer) { clearTimeout(timer); }
        timer = setTimeout(function () { runSearch(value); }, 260);
      });
      search.addEventListener("keydown", function (event) {
        if (event.key === "Escape") { search.value = ""; runSearch(""); }
      });
    }

    var auto = el("btn-autorefresh");
    if (auto) {
      auto.addEventListener("click", function () {
        state.autoRefresh = !state.autoRefresh;
        auto.textContent = "به‌روزرسانی خودکار: " + (state.autoRefresh ? "روشن" : "خاموش");
        auto.setAttribute("aria-pressed", state.autoRefresh ? "true" : "false");
      });
    }

    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible" && state.autoRefresh) {
        loadOverview().catch(handleError);
      }
    });
  }

  /* -------------------------------------------------------------------- boot */
  function tickClock() {
    var node = el("server-clock");
    if (node) { node.textContent = clockText(Date.now() / 1000); }
    var update = el("last-update");
    if (update && state.overview && state.overview.database && state.overview.database.newest_reading) {
      update.textContent = dateText(state.overview.database.newest_reading, true);
    }
  }

  function boot() {
    renderAlertKinds();
    bindEvents();
    tickClock();
    setInterval(tickClock, 1000);
    loadAll().then(function () { return loadSeries(); });

    setInterval(function () {
      if (!state.autoRefresh || document.visibilityState !== "visible") { return; }
      loadOverview().catch(handleError);
      loadAlerts().catch(handleError);
      loadEvents().catch(handleError);
      loadSeries();
      loadStatus().catch(handleError);
    }, 30000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
