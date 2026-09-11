/* ==========================================================================
   همیار — support console client
   Tabs, dashboard chart, knowledge-base CRUD, log filters. No dependencies.
   ========================================================================== */
(function () {
  "use strict";

  var root = document.getElementById("consoleRoot");
  if (!root) return;

  var TOKEN_KEY = "hamyar.adminToken";
  var els = {
    toasts: document.getElementById("toasts"),
    rows: document.getElementById("kbRows"),
    search: document.getElementById("kbSearch"),
    category: document.getElementById("kbCategory"),
    meta: document.getElementById("kbMeta"),
    navKbCount: document.getElementById("navKbCount"),
    modal: document.getElementById("faqModal"),
    form: document.getElementById("faqForm"),
    faqId: document.getElementById("faqId"),
    question: document.getElementById("faqQuestion"),
    answer: document.getElementById("faqAnswer"),
    categoryInput: document.getElementById("faqCategoryInput"),
    variants: document.getElementById("faqVariants"),
    modalTitle: document.getElementById("faqModalTitle"),
    logRows: document.getElementById("logRows"),
    logSearch: document.getElementById("logSearch"),
    logMeta: document.getElementById("logMeta"),
    dailyChart: document.getElementById("dailyChart")
  };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function faDigits(value) {
    return String(value).replace(/[0-9]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹".charAt(Number(d)); });
  }

  function toast(message, kind) {
    var node = el("div", "toast" + (kind ? " toast--" + kind : ""), message);
    els.toasts.appendChild(node);
    setTimeout(function () { node.remove(); }, 4200);
  }

  function headers(json) {
    var head = {};
    if (json) head["Content-Type"] = "application/json";
    var token = localStorage.getItem(TOKEN_KEY);
    if (token) head["X-Admin-Token"] = token;
    return head;
  }

  function request(path, options) {
    options = options || {};
    return fetch(path, {
      method: options.method || "GET",
      headers: headers(options.body !== undefined),
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) {
          var error = new Error((body.error && body.error.message) || "خطا در ارتباط با سرور");
          error.details = (body.error && body.error.details) || {};
          throw error;
        }
        return body;
      });
    });
  }

  /* ------------------------------------------------------------- tabs */
  function selectTab(name) {
    root.querySelectorAll("[role=tab]").forEach(function (tab) {
      tab.setAttribute("aria-selected", tab.dataset.tab === name ? "true" : "false");
    });
    root.querySelectorAll("[data-panel]").forEach(function (panel) {
      panel.hidden = panel.dataset.panel !== name;
    });
    if (location.hash.slice(1) !== name) history.replaceState(null, "", "#" + name);
  }

  root.querySelectorAll("[role=tab]").forEach(function (tab) {
    tab.addEventListener("click", function () { selectTab(tab.dataset.tab); });
  });
  selectTab((location.hash || "#dashboard").slice(1));

  /* ------------------------------------------------------------ chart */
  (function renderDaily() {
    if (!els.dailyChart) return;
    var series = JSON.parse(els.dailyChart.dataset.series || "[]");
    if (!series.length) return;
    var max = Math.max.apply(null, series.map(function (d) { return d.total; })) || 1;

    var bars = el("div", "chart__bars");
    var axis = el("div", "chart__axis");
    series.forEach(function (day) {
      var col = el("div", "chart__col");
      col.title = day.day + " — " + faDigits(day.total) + " گفت‌وگو";
      var answered = el("span");
      answered.style.height = Math.max(3, (day.answered / max) * 100) + "%";
      var unanswered = el("span", "is-unanswered");
      unanswered.style.height = Math.max(0, ((day.total - day.answered) / max) * 100) + "%";
      col.appendChild(unanswered);
      col.appendChild(answered);
      bars.appendChild(col);
      axis.appendChild(el("span", null, day.day.slice(5)));
    });
    els.dailyChart.appendChild(bars);
    els.dailyChart.appendChild(axis);
  })();

  /* ------------------------------------------------------- knowledge base */
  function badge(text) { return el("span", "badge", text); }

  function renderRows(faqs) {
    els.rows.innerHTML = "";
    if (!faqs.length) {
      var empty = el("tr");
      var cell = el("td", "empty-row", "پرسشی با این فیلترها پیدا نشد.");
      cell.colSpan = 5;
      empty.appendChild(cell);
      els.rows.appendChild(empty);
      return;
    }
    faqs.forEach(function (faq) {
      var tr = el("tr");
      tr.dataset.id = faq.id;
      tr.dataset.question = faq.question;
      tr.dataset.answer = faq.answer;
      tr.dataset.category = faq.category;
      tr.dataset.variants = (faq.variants || []).join("\n");

      tr.appendChild(el("td", "num", faDigits(faq.id)));
      var questionCell = el("td", "clip");
      questionCell.appendChild(el("span", null, faq.question));
      tr.appendChild(questionCell);
      var categoryCell = el("td");
      categoryCell.appendChild(badge(faq.category));
      tr.appendChild(categoryCell);
      tr.appendChild(el("td", "num", faDigits((faq.variants || []).length)));

      var actions = el("td", "actions");
      var edit = el("button", "btn btn--ghost btn--sm", "ویرایش");
      edit.type = "button"; edit.dataset.edit = "";
      var remove = el("button", "btn btn--danger btn--sm", "حذف");
      remove.type = "button"; remove.dataset.delete = "";
      actions.appendChild(edit);
      actions.appendChild(remove);
      tr.appendChild(actions);
      els.rows.appendChild(tr);
    });
  }

  function loadFaqs() {
    var params = new URLSearchParams();
    if (els.search.value.trim()) params.set("search", els.search.value.trim());
    if (els.category.value) params.set("category", els.category.value);
    params.set("limit", "200");
    request("/api/faqs?" + params.toString()).then(function (data) {
      renderRows(data.faqs || []);
      els.meta.textContent = faDigits(data.total || 0) + " پرسش";
      els.navKbCount.textContent = faDigits(data.total || 0);
    }).catch(function (error) { toast(error.message, "error"); });
  }

  var searchTimer;
  els.search.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadFaqs, 280);
  });
  els.category.addEventListener("change", loadFaqs);

  /* ------------------------------------------------------------- modal */
  function clearErrors() {
    els.form.querySelectorAll(".field__error").forEach(function (node) { node.textContent = ""; });
    els.form.querySelectorAll(".field--error").forEach(function (node) { node.classList.remove("field--error"); });
  }

  function openModal(row) {
    clearErrors();
    var editing = Boolean(row);
    els.modalTitle.textContent = editing ? "ویرایش پرسش" : "پرسش جدید";
    els.faqId.value = editing ? row.dataset.id : "";
    els.question.value = editing ? row.dataset.question : "";
    els.answer.value = editing ? row.dataset.answer : "";
    els.categoryInput.value = editing ? row.dataset.category : "";
    els.variants.value = editing ? row.dataset.variants : "";
    els.modal.hidden = false;
    els.question.focus();
  }

  function closeModal() { els.modal.hidden = true; }

  document.getElementById("addFaq").addEventListener("click", function () { openModal(null); });
  document.getElementById("closeModal").addEventListener("click", closeModal);
  document.getElementById("cancelModal").addEventListener("click", closeModal);
  els.modal.addEventListener("click", function (event) {
    if (event.target === els.modal) closeModal();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !els.modal.hidden) closeModal();
  });

  els.rows.addEventListener("click", function (event) {
    var row = event.target.closest("tr");
    if (!row) return;
    if (event.target.closest("[data-edit]")) { openModal(row); return; }
    if (event.target.closest("[data-delete]")) {
      var id = row.dataset.id;
      if (!window.confirm("این پرسش از دانشنامه حذف شود؟")) return;
      request("/api/faqs/" + id, { method: "DELETE" })
        .then(function () {
          toast("پرسش حذف شد.", "ok");
          loadFaqs();
          row.remove();
        })
        .catch(function (error) { toast(error.message, "error"); });
    }
  });

  document.getElementById("saveFaq").addEventListener("click", function () {
    clearErrors();
    var payload = {
      question: els.question.value.trim(),
      answer: els.answer.value.trim(),
      category: els.categoryInput.value.trim() || "عمومی",
      variants: els.variants.value.split("\n").map(function (line) { return line.trim(); }).filter(Boolean)
    };
    var id = els.faqId.value;
    var path = id ? "/api/faqs/" + id : "/api/faqs";
    var method = id ? "PUT" : "POST";

    request(path, { method: method, body: payload })
      .then(function () {
        toast(id ? "پرسش به‌روزرسانی شد." : "پرسش افزوده شد.", "ok");
        closeModal();
        loadFaqs();
      })
      .catch(function (error) {
        var details = error.details || {};
        Object.keys(details).forEach(function (field) {
          var holder = els.form.querySelector('[data-error="' + field + '"]');
          if (holder) {
            holder.textContent = details[field];
            var wrapper = holder.closest(".field");
            if (wrapper) wrapper.classList.add("field--error");
          }
        });
        var general = els.form.querySelector('[data-error="general"]');
        if (general) general.textContent = error.message;
        toast(error.message, "error");
      });
  });

  /* --------------------------------------------------------------- logs */
  var logStatus = "";
  function renderLogs(turns) {
    els.logRows.innerHTML = "";
    if (!turns.length) {
      var empty = el("tr");
      var cell = el("td", "empty-row", "پیامی با این فیلترها پیدا نشد.");
      cell.colSpan = 6;
      empty.appendChild(cell);
      els.logRows.appendChild(empty);
      return;
    }
    turns.forEach(function (turn) {
      var tr = el("tr");
      tr.appendChild(el("td", "num muted", turn.created_at));
      var messageCell = el("td", "clip");
      messageCell.appendChild(el("span", null, turn.message));
      tr.appendChild(messageCell);
      var matchedCell = el("td", "clip small muted");
      matchedCell.appendChild(el("span", null, turn.matched_question || "—"));
      tr.appendChild(matchedCell);
      tr.appendChild(el("td", "num", faDigits(Math.round((turn.score || 0) * 100)) + "٪"));

      var confidenceCell = el("td");
      var cls = turn.confidence === "high" ? "badge--ok"
        : turn.confidence === "medium" ? "badge--warn" : "badge--danger";
      var label = turn.confidence === "high" ? "بالا" : turn.confidence === "medium" ? "متوسط" : "پایین";
      confidenceCell.appendChild(el("span", "badge " + cls, label));
      tr.appendChild(confidenceCell);

      var feedbackCell = el("td");
      if (turn.feedback === "up") feedbackCell.appendChild(el("span", "badge badge--ok", "مفید"));
      else if (turn.feedback === "down") feedbackCell.appendChild(el("span", "badge badge--danger", "مفید نبود"));
      else feedbackCell.appendChild(el("span", "muted tiny", "—"));
      tr.appendChild(feedbackCell);

      els.logRows.appendChild(tr);
    });
  }

  function loadLogs() {
    var params = new URLSearchParams();
    if (els.logSearch.value.trim()) params.set("search", els.logSearch.value.trim());
    if (logStatus) params.set("status", logStatus);
    params.set("limit", "50");
    request("/api/conversations?" + params.toString()).then(function (data) {
      renderLogs(data.items || []);
      els.logMeta.textContent = faDigits(data.total || 0) + " پیام";
    }).catch(function (error) { toast(error.message, "error"); });
  }

  var logTimer;
  els.logSearch.addEventListener("input", function () {
    clearTimeout(logTimer);
    logTimer = setTimeout(loadLogs, 280);
  });

  document.querySelectorAll("#logFilter [data-status]").forEach(function (button) {
    button.addEventListener("click", function () {
      logStatus = button.dataset.status;
      document.querySelectorAll("#logFilter [data-status]").forEach(function (other) {
        other.setAttribute("aria-pressed", other === button ? "true" : "false");
      });
      loadLogs();
    });
  });

  /* -------------------------------------------------------------- token */
  var tokenInput = document.getElementById("tokenInput");
  var saveToken = document.getElementById("saveToken");
  if (saveToken) {
    if (tokenInput && localStorage.getItem(TOKEN_KEY)) {
      tokenInput.value = localStorage.getItem(TOKEN_KEY);
    }
    saveToken.addEventListener("click", function () {
      localStorage.setItem(TOKEN_KEY, tokenInput.value.trim());
      toast("توکن ذخیره شد.", "ok");
    });
  }
})();
