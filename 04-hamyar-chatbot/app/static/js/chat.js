/* ==========================================================================
   همیار — visitor chat client
   Session handling, streaming-style replies, confidence transparency,
   feedback and human handoff. No dependencies.
   ========================================================================== */
(function () {
  "use strict";

  var root = document.getElementById("chatRoot");
  if (!root) return;

  var API = {
    chat: "/api/chat",
    history: "/api/history",
    feedback: "/api/feedback",
    handoff: "/api/handoff",
    suggestions: "/api/suggestions",
    faqs: "/api/faqs"
  };
  var SESSION_KEY = "hamyar.session";
  var els = {
    thread: document.getElementById("thread"),
    empty: document.getElementById("emptyState"),
    form: document.getElementById("composer"),
    input: document.getElementById("message"),
    send: document.getElementById("send"),
    counter: document.getElementById("charCount"),
    newChat: document.getElementById("newChat"),
    clear: document.getElementById("clearThread"),
    toasts: document.getElementById("toasts"),
    historyList: document.getElementById("historyList"),
    historyEmpty: document.getElementById("historyEmpty"),
    catList: document.getElementById("catList"),
    metrics: {
      confidence: document.getElementById("mConfidence"),
      bar: document.getElementById("mConfBar"),
      score: document.getElementById("mScore"),
      matched: document.getElementById("mMatched"),
      latency: document.getElementById("mLatency"),
      category: document.getElementById("mCategory")
    }
  };

  var pending = false;
  var lastQuery = "";

  /* ------------------------------------------------------------- helpers */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function faDigits(value) {
    return String(value).replace(/[0-9]/g, function (d) {
      return "۰۱۲۳۴۵۶۷۸۹".charAt(Number(d));
    });
  }

  function toast(message, kind) {
    var node = el("div", "toast" + (kind ? " toast--" + kind : ""), message);
    els.toasts.appendChild(node);
    setTimeout(function () { node.remove(); }, 4200);
  }

  function sessionId() {
    var id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = "web-" + Math.random().toString(36).slice(2, 11);
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  function request(path, options) {
    return fetch(path, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) {
          var message = (body && body.error && body.error.message) || "خطا در ارتباط با سرور";
          throw new Error(message);
        }
        return body;
      });
    });
  }

  /* --------------------------------------------------------- rendering */
  function scrollDown() {
    els.thread.scrollTop = els.thread.scrollHeight;
  }

  function hideEmpty() {
    if (els.empty) els.empty.hidden = true;
  }

  function confidenceClass(value) {
    return value === "high" ? "badge--ok" : value === "medium" ? "badge--warn" : "badge--danger";
  }

  function renderUser(text) {
    var article = el("article", "msg msg--user");
    article.appendChild(el("div", "msg__bubble", text));
    var meta = el("div", "msg__meta");
    meta.appendChild(el("span", null, "شما"));
    article.appendChild(meta);
    els.thread.appendChild(article);
    hideEmpty();
    scrollDown();
  }

  function renderBot(reply) {
    var article = el("article", "msg msg--bot" + (reply.matched ? "" : " is-fallback"));
    if (reply.conversation_id) article.dataset.conversationId = reply.conversation_id;

    article.appendChild(el("div", "msg__bubble", reply.answer));

    var meta = el("div", "msg__meta");
    meta.appendChild(el("span", "badge " + confidenceClass(reply.confidence), reply.confidence_label));
    if (reply.matched) {
      meta.appendChild(el("span", null, "تطبیق " + faDigits(reply.relevance) + "٪"));
    }
    if (reply.latency_ms) {
      meta.appendChild(el("span", null, faDigits(reply.latency_ms) + " میلی‌ثانیه"));
    }
    article.appendChild(meta);

    if (reply.matched && reply.matched_question) {
      article.appendChild(el("p", "msg__source", "پرسش مرجع دانشنامه: " + reply.matched_question));
    }

    // Suggestions double as the recovery path of a controlled fallback.
    if (reply.suggestions && reply.suggestions.length) {
      var list = el("div", "suggestions");
      reply.suggestions.forEach(function (item) {
        var chip = el("button", "chip", item.question);
        chip.type = "button";
        chip.addEventListener("click", function () { send(item.question); });
        list.appendChild(chip);
      });
      article.appendChild(list);
    }

    var tools = el("div", "msg__tools");
    var copy = el("button", null, "کپی پاسخ");
    copy.type = "button";
    copy.addEventListener("click", function () {
      navigator.clipboard.writeText(reply.answer).then(function () {
        toast("پاسخ کپی شد.", "ok");
      }, function () { toast("کپی ناموفق بود."); });
    });
    tools.appendChild(copy);

    if (reply.conversation_id) {
      [["up", "مفید بود"], ["down", "مفید نبود"]].forEach(function (pair) {
        var button = el("button", null, pair[1]);
        button.type = "button";
        button.dataset.feedback = pair[0];
        button.addEventListener("click", function () {
          vote(reply.conversation_id, pair[0], button, tools);
        });
        tools.appendChild(button);
      });
    }

    if (!reply.matched) {
      var handoff = el("button", null, "اتصال به کارشناس");
      handoff.type = "button";
      handoff.addEventListener("click", requestHandoff);
      tools.appendChild(handoff);
    }

    article.appendChild(tools);
    els.thread.appendChild(article);
    hideEmpty();
    scrollDown();
    updateInsights(reply);
  }

  function typing() {
    var article = el("article", "msg msg--bot");
    article.id = "typing";
    var bubble = el("div", "msg__bubble");
    var dots = el("span", "typing");
    dots.appendChild(el("i")); dots.appendChild(el("i")); dots.appendChild(el("i"));
    bubble.appendChild(dots);
    article.appendChild(bubble);
    els.thread.appendChild(article);
    scrollDown();
    return article;
  }

  function updateInsights(reply) {
    var m = els.metrics;
    m.confidence.textContent = reply.confidence_label;
    m.score.textContent = reply.matched ? faDigits(reply.relevance) + "٪" : "زیر آستانه";
    m.matched.textContent = reply.matched_question || "—";
    m.latency.textContent = faDigits(reply.latency_ms) + " میلی‌ثانیه";
    m.category.textContent = reply.category || "—";
    m.bar.style.width = Math.max(6, Math.min(100, reply.relevance || 0)) + "%";
    m.bar.className = reply.confidence === "high" ? "is-high"
      : reply.confidence === "medium" ? "is-medium" : "is-low";
  }

  /* ---------------------------------------------------------- behaviour */
  function send(text) {
    var message = (text || els.input.value || "").trim();
    if (!message || pending) return;
    lastQuery = message;

    hideEmpty();
    renderUser(message);
    els.input.value = "";
    autoGrow();
    updateCounter();
    setPending(true);
    var placeholder = typing();

    request(API.chat, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message, session_id: sessionId() })
    }).then(function (reply) {
      placeholder.remove();
      renderBot(reply);
      if (reply.session_generated && reply.session_id) {
        localStorage.setItem(SESSION_KEY, reply.session_id);
      }
      loadHistoryList();
    }).catch(function (error) {
      placeholder.remove();
      toast(error.message || "ارسال پیام ناموفق بود.", "error");
      renderBot({
        answer: "ارتباط با سرور برقرار نشد. لطفاً یک بار دیگر تلاش کنید.",
        confidence: "low",
        confidence_label: "بدون ارتباط",
        matched: false,
        relevance: 0,
        suggestions: []
      });
    }).then(function () {
      setPending(false);
    });
  }

  function vote(conversationId, value, button, container) {
    request(API.feedback, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, feedback: value })
    }).then(function () {
      Array.prototype.forEach.call(container.querySelectorAll("[data-feedback]"), function (node) {
        node.setAttribute("aria-pressed", node === button ? "true" : "false");
      });
      toast("ممنون از بازخوردتان.", "ok");
    }).catch(function (error) { toast(error.message, "error"); });
  }

  function requestHandoff() {
    request(API.handoff, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId(),
        reason: "درخواست از چت",
        last_query: lastQuery
      })
    }).then(function (data) {
      toast(data.message || "درخواست شما ثبت شد.", "ok");
    }).catch(function (error) { toast(error.message, "error"); });
  }

  function setPending(value) {
    pending = value;
    els.send.disabled = value;
    els.input.disabled = value;
  }

  function autoGrow() {
    els.input.style.height = "auto";
    els.input.style.height = Math.min(els.input.scrollHeight, 148) + "px";
  }

  function updateCounter() {
    els.counter.textContent = faDigits(els.input.value.length) + " / " + faDigits(500);
  }

  function categoryQuestions(category, button) {
    Array.prototype.forEach.call(els.catList.querySelectorAll("button"), function (node) {
      node.setAttribute("aria-pressed", node === button ? "true" : "false");
    });
    request(API.faqs + "?category=" + encodeURIComponent(category) + "&limit=6")
      .then(function (data) {
        var questions = (data.faqs || []).map(function (faq) { return faq.question; });
        var article = el("article", "msg msg--bot");
        article.appendChild(el("div", "msg__bubble",
          "این‌ها پرتکرارترین پرسش‌های دستهٔ «" + category + "» هستند:"));
        var list = el("div", "suggestions");
        questions.forEach(function (question) {
          var chip = el("button", "chip", question);
          chip.type = "button";
          chip.addEventListener("click", function () { send(question); });
          list.appendChild(chip);
        });
        article.appendChild(list);
        els.thread.appendChild(article);
        hideEmpty();
        scrollDown();
      })
      .catch(function (error) { toast(error.message, "error"); });
  }

  function loadHistoryList() {
    request(API.history + "?session_id=" + encodeURIComponent(sessionId()) + "&limit=8")
      .then(function (data) {
        var turns = (data.turns || []).slice().reverse();
        els.historyList.innerHTML = "";
        if (!turns.length) {
          els.historyList.appendChild(el("p", "tiny muted", "هنوز گفت‌وگویی ثبت نشده است."));
          return;
        }
        turns.forEach(function (turn) {
          var item = el("div", "item", turn.message);
          item.appendChild(el("time", null, turn.created_at));
          els.historyList.appendChild(item);
        });
      })
      .catch(function () { /* history is a nice-to-have */ });
  }

  function restoreTranscript() {
    request(API.history + "?session_id=" + encodeURIComponent(sessionId()) + "&limit=40")
      .then(function (data) {
        (data.turns || []).forEach(function (turn) {
          renderUser(turn.message);
          if (turn.answered) {
            renderBot({
              answer: turn.matched_question ? "پاسخ «" + turn.matched_question + "»" : "پاسخ ثبت‌شده",
              confidence: turn.confidence,
              confidence_label: turn.confidence === "high" ? "اطمینان بالا"
                : turn.confidence === "medium" ? "اطمینان متوسط" : "اطمینان پایین",
              matched: true,
              relevance: Math.round((turn.score || 0) * 100),
              matched_question: turn.matched_question,
              latency_ms: turn.latency_ms,
              category: turn.category,
              suggestions: []
            });
          }
        });
      })
      .catch(function () { /* a fresh session simply has no transcript */ });
  }

  /* ------------------------------------------------------------- wiring */
  els.form.addEventListener("submit", function (event) {
    event.preventDefault();
    send();
  });

  els.input.addEventListener("input", function () {
    autoGrow();
    updateCounter();
  });

  els.input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  });

  els.newChat.addEventListener("click", function () {
    var id = "web-" + Math.random().toString(36).slice(2, 11);
    localStorage.setItem(SESSION_KEY, id);
    els.thread.querySelectorAll(".msg").forEach(function (node) { node.remove(); });
    if (els.empty) els.empty.hidden = false;
    loadHistoryList();
    toast("گفت‌وگوی تازه آغاز شد.", "ok");
  });

  els.clear.addEventListener("click", function () {
    localStorage.removeItem(SESSION_KEY);
    els.thread.querySelectorAll(".msg").forEach(function (node) { node.remove(); });
    if (els.empty) els.empty.hidden = false;
    loadHistoryList();
    toast("تاریخچهٔ این مرورگر پاک شد.", "ok");
  });

  document.querySelectorAll("[data-ask]").forEach(function (node) {
    node.addEventListener("click", function () { send(node.getAttribute("data-ask")); });
  });

  document.querySelectorAll("[data-category]").forEach(function (node) {
    node.addEventListener("click", function () {
      categoryQuestions(node.getAttribute("data-category"), node);
    });
  });

  var sideHandoff = document.getElementById("handoffSide");
  if (sideHandoff) sideHandoff.addEventListener("click", requestHandoff);
  var topHandoff = document.getElementById("handoffTop");
  if (topHandoff) topHandoff.addEventListener("click", requestHandoff);

  updateCounter();
  loadHistoryList();
  restoreTranscript();
})();
