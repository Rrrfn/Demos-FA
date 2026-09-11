/* ==========================================================================
   همیار — embeddable chat widget
   One script tag adds a support assistant to any site:

     <script src="https://<hamyar-host>/widget.js" defer></script>

   The script derives its API host from its own URL, keeps the conversation
   session in the visitor's browser and needs no dependencies.
   ========================================================================== */
(function () {
  "use strict";

  var script = document.currentScript;
  var BASE = script ? new URL(script.src, location.href).origin : "";
  var SESSION_KEY = "hamyar.widget.session";
  var OPEN_KEY = "hamyar.widget.open";
  var busy = false;

  var CSS = [
    ".hm-launcher{position:fixed;inset-block-end:22px;inset-inline-start:22px;z-index:2147483000;",
    "display:flex;align-items:center;gap:.5rem;padding:.75rem 1.1rem;border-radius:999px;border:0;",
    "background:linear-gradient(140deg,#5b53e0,#3730a3);color:#fff;font:600 14px/1 'Vazirmatn',system-ui,sans-serif;",
    "box-shadow:0 12px 34px rgba(31,27,77,.34);cursor:pointer}",
    ".hm-launcher svg{width:18px;height:18px}",
    ".hm-panel{position:fixed;inset-block-end:22px;inset-inline-start:22px;z-index:2147483000;",
    "width:min(380px,calc(100vw - 32px));height:min(620px,calc(100vh - 44px));display:flex;flex-direction:column;",
    "background:#fff;border:1px solid #e3e6ef;border-radius:20px;overflow:hidden;direction:rtl;",
    "font:14px/1.8 'Vazirmatn',system-ui,sans-serif;color:#12141a;",
    "box-shadow:0 28px 70px rgba(18,20,26,.24)}",
    ".hm-head{display:flex;align-items:center;gap:.6rem;padding:.85rem 1rem;border-bottom:1px solid #e3e6ef;",
    "background:linear-gradient(180deg,#fff,#f7f8fb)}",
    ".hm-head b{font-size:14.5px}.hm-head small{display:block;font-size:11.5px;color:#5c6474}",
    ".hm-close{margin-inline-start:auto;border:0;background:none;font-size:20px;line-height:1;color:#7b8494;cursor:pointer}",
    ".hm-thread{flex:1;overflow-y:auto;padding:1rem;display:flex;flex-direction:column;gap:.7rem;background:#fbfbfe}",
    ".hm-msg{max-width:88%;padding:.6rem .85rem;border-radius:14px;font-size:13.5px;white-space:pre-wrap}",
    ".hm-msg.user{align-self:flex-start;background:#4338ca;color:#fff;border-end-start-radius:5px}",
    ".hm-msg.bot{align-self:flex-end;background:#fff;border:1px solid #e3e6ef;border-end-end-radius:5px}",
    ".hm-meta{font-size:10.5px;color:#7b8494;align-self:flex-end}",
    ".hm-sug{display:flex;flex-wrap:wrap;gap:6px;margin-top:.4rem}",
    ".hm-sug button{border:1px solid #d3d8e5;background:#fff;border-radius:999px;padding:4px 10px;",
    "font:12px 'Vazirmatn',system-ui,sans-serif;color:#333947;cursor:pointer}",
    ".hm-sug button:hover{border-color:#5b53e0;color:#4338ca}",
    ".hm-composer{display:flex;gap:.5rem;align-items:flex-end;padding:.7rem .8rem;border-top:1px solid #e3e6ef}",
    ".hm-composer textarea{flex:1;border:1px solid #d3d8e5;border-radius:12px;padding:.55rem .7rem;resize:none;",
    "font:13.5px/1.7 'Vazirmatn',system-ui,sans-serif;outline:none;max-height:110px}",
    ".hm-composer button{width:38px;height:38px;border-radius:12px;border:0;background:#4338ca;color:#fff;cursor:pointer}",
    ".hm-composer button[disabled]{background:#9aa2b1}",
    ".hm-foot{padding:0 .8rem .6rem;font-size:10.5px;color:#7b8494;text-align:center}"
  ].join("");

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function sessionId() {
    var id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = "widget-" + Math.random().toString(36).slice(2, 11);
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  function post(path, body) {
    return fetch(BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) throw new Error((data.error && data.error.message) || "خطا");
        return data;
      });
    });
  }

  var thread, panel, launcher;

  function bubble(kind, text) {
    var node = el("div", "hm-msg " + kind, text);
    thread.appendChild(node);
    thread.scrollTop = thread.scrollHeight;
    return node;
  }

  function botReply(reply) {
    bubble("bot", reply.answer);
    var meta = el("div", "hm-meta", reply.confidence_label + (reply.matched ? " · تطبیق " + reply.relevance + "٪" : ""));
    thread.appendChild(meta);
    if (reply.suggestions && reply.suggestions.length) {
      var box = el("div", "hm-sug");
      reply.suggestions.forEach(function (item) {
        var button = el("button", null, item.question);
        button.type = "button";
        button.addEventListener("click", function () { send(item.question); });
        box.appendChild(button);
      });
      thread.appendChild(box);
    }
    if (!reply.matched) {
      var handoff = el("button", null, "اتصال به کارشناس");
      handoff.type = "button";
      handoff.addEventListener("click", function () {
        post("/api/handoff", { session_id: sessionId(), reason: "ویجت", last_query: "" })
          .then(function (data) { bubble("bot", data.message); })
          .catch(function (error) { bubble("bot", error.message); });
      });
      var wrap = el("div", "hm-sug");
      wrap.appendChild(handoff);
      thread.appendChild(wrap);
    }
    thread.scrollTop = thread.scrollHeight;
  }

  function send(text) {
    var input = panel.querySelector("textarea");
    var message = (text || input.value || "").trim();
    if (!message || busy) return;
    busy = true;
    input.value = "";
    bubble("user", message);
    var thinking = bubble("bot", "…");

    post("/api/chat", { message: message, session_id: sessionId() })
      .then(function (reply) {
        thinking.remove();
        botReply(reply);
      })
      .catch(function (error) {
        thinking.remove();
        bubble("bot", "ارتباط با سرور برقرار نشد: " + error.message);
      })
      .then(function () { busy = false; });
  }

  function build() {
    var style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);

    launcher = el("button", "hm-launcher");
    launcher.type = "button";
    launcher.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.4 8.9 8.9 0 0 1-3.2-.6L4 21l1.4-4.3A8.2 8.2 0 0 1 4 11.5 8.4 8.4 0 0 1 12.5 3 8.4 8.4 0 0 1 21 11.5z"/></svg>' +
      "<span>پشتیبانی آنلاین</span>";
    launcher.addEventListener("click", toggle);

    panel = el("div", "hm-panel");
    panel.hidden = true;

    var head = el("div", "hm-head");
    head.innerHTML = "<b>همیار</b><small>دستیار هوشمند پشتیبانی · آنلاین</small>";
    var close = el("button", "hm-close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "بستن");
    close.addEventListener("click", toggle);
    head.appendChild(close);
    panel.appendChild(head);

    thread = el("div", "hm-thread");
    bubble("bot", "سلام 👋 چطور می‌توانم کمکتان کنم؟ سؤال‌تان را بنویسید؛ اگر مطمئن نباشم، پاسخ حدسی نمی‌دهم.");
    panel.appendChild(thread);

    var composer = el("div", "hm-composer");
    var input = document.createElement("textarea");
    input.rows = 1;
    input.placeholder = "پرسش خود را بنویسید…";
    var submit = el("button", null, "›");
    submit.type = "button";
    submit.addEventListener("click", function () { send(); });
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        send();
      }
    });
    composer.appendChild(input);
    composer.appendChild(submit);
    panel.appendChild(composer);

    panel.appendChild(el("div", "hm-foot", "پاسخ‌ها بر پایهٔ دانشنامهٔ رسمی — همیار"));

    document.body.appendChild(launcher);
    document.body.appendChild(panel);
  }

  function toggle() {
    var open = panel.hidden;
    panel.hidden = !open;
    launcher.hidden = open;
    localStorage.setItem(OPEN_KEY, open ? "1" : "0");
    if (open) panel.querySelector("textarea").focus();
  }

  function init() {
    build();
    if (localStorage.getItem(OPEN_KEY) === "1") toggle();
  }

  window.Hamyar = {
    open: function () { if (panel && panel.hidden) toggle(); },
    close: function () { if (panel && !panel.hidden) toggle(); },
    ask: function (text) { if (panel && panel.hidden) toggle(); send(text); }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
