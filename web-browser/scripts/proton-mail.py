#!/usr/bin/env python3
"""
Proton Mail actions against the already-running headed openchrome daemon.

Invoke by absolute path. Do not cd into the skills repo.

    python3 ~/.agents/skills/web-browser/scripts/proton-mail.py inbox
    python3 ~/.agents/skills/web-browser/scripts/proton-mail.py open --subject "exact subject"
    python3 ~/.agents/skills/web-browser/scripts/proton-mail.py search "invoice"
    python3 ~/.agents/skills/web-browser/scripts/proton-mail.py compose \
        --to someone@example.com --subject "Subject" --body "Body"
    python3 ~/.agents/skills/web-browser/scripts/proton-mail.py compose \
        --to someone@example.com --subject "Subject" --body "Body" --send

The headed daemon must already be running:

    ~/.agents/skills/web-browser/scripts/openchrome-daemon.sh start headed

Exit codes:
    0  success
    1  navigation failed
    2  daemon not reachable
    3  login page, decrypt wait failed, or target not found
    4  compose/send failed
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

DAEMON_MCP = "http://127.0.0.1:3199/mcp"
DAEMON_HEALTH = "http://127.0.0.1:9090/health"
DEFAULT_INBOX = "https://mail.proton.me/u/0/inbox"
DEFAULT_WAIT = 12


def check_daemon():
    try:
        with urllib.request.urlopen(DAEMON_HEALTH, timeout=5) as r:
            data = json.loads(r.read())
            if data.get("status") != "ok":
                return False
            chrome = data.get("chrome", {})
            if not chrome.get("connected", False) or chrome.get("reconnecting", False):
                sys.stderr.write(f"daemon healthy but Chrome not ready: {json.dumps(chrome)}\n")
                sys.stderr.write("restart headed daemon: openchrome-daemon.sh stop && openchrome-daemon.sh start headed\n")
                return False
            return True
    except Exception as e:
        sys.stderr.write(f"daemon not reachable at {DAEMON_HEALTH}: {e}\n")
        return False


class Session:
    def __init__(self):
        self._session_id = None
        self._msg_id = 1

    def _post(self, body):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        req = urllib.request.Request(
            DAEMON_MCP, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            sid = resp.getheader("Mcp-Session-Id")
            if sid:
                self._session_id = sid
            raw = resp.read().decode()
            for line in raw.splitlines():
                if line.startswith("data: "):
                    try:
                        return json.loads(line[6:])
                    except Exception:
                        pass
            try:
                return json.loads(raw)
            except Exception:
                return {"raw": raw[:300]}

    def _next_id(self):
        mid = self._msg_id
        self._msg_id += 1
        return mid

    def initialize(self):
        self._post({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "proton-mail", "version": "1.0"},
            },
            "id": self._next_id(),
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def tool(self, name, args):
        return self._post({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
            "id": self._next_id(),
        })

    @staticmethod
    def texts(resp):
        if not resp or "result" not in resp:
            return ""
        return "\n".join(
            c["text"] for c in resp["result"].get("content", []) if c.get("type") == "text"
        )


def extract_tab_id(nav_text):
    for line in nav_text.split("\n"):
        try:
            d = json.loads(line)
            if "tabId" in d:
                return d["tabId"]
        except Exception:
            pass
    return None


def first_json_object(text):
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj
    except Exception:
        return None


JS_STATE = r"""
(() => {
  const href = location.href;
  const text = (document.body && document.body.innerText || '').slice(0, 4000);
  const login = /account\.proton\.(me|ch)/.test(href)
    || /sign in/i.test(document.title)
    || (/email or username/i.test(text) && /password/i.test(text));
  const rows = Array.from(document.querySelectorAll(
    '[data-testid^="message-item"], [data-testid="message-item"], .item-container, [data-element-id]'
  )).filter(e => e.offsetParent);
  const subjects = rows.slice(0, 30).map(e => (e.innerText || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
  const decrypting = /decrypt/i.test(text) && subjects.length === 0;
  const inboxChrome = /new message|compose|inbox|all mail|sent/i.test(text)
    && /mail\.proton\.(me|ch)/.test(href)
    && !login;
  return JSON.stringify({
    href,
    title: document.title,
    login,
    decrypting,
    inboxChrome,
    subjectCount: subjects.length,
    subjects
  });
})()
"""

JS_CLICK_SUBJECT = r"""
(() => {
  const needle = %s.toLowerCase();
  const matches = Array.from(document.querySelectorAll(
    '[data-testid^="message-item"], .item-container, [data-element-id], [role="button"], a, li'
  )).filter(e => e.offsetParent && (e.innerText || '').toLowerCase().includes(needle));
  if (!matches.length) return 'NOT FOUND';
  matches.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
  const el = matches[0];
  const clickable = el.closest('[data-testid^="message-item"],[data-element-id],[role="button"],a,li,.item-container') || el;
  const r = clickable.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  for (const type of ['mousedown', 'mouseup', 'click']) {
    clickable.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy}));
  }
  return 'CLICKED ' + clickable.tagName + ': ' + (el.innerText || '').replace(/\s+/g, ' ').slice(0, 80);
})()
"""

JS_READ_MESSAGE = r"""
(() => {
  const out = {href: location.href, header: '', iframes: []};
  const h = document.querySelector('.message-header, [data-testid="message-header"], [data-testid="conversation-header"]');
  if (h) out.header = (h.innerText || '').replace(/\s+/g, ' ').slice(0, 400);
  for (const f of Array.from(document.querySelectorAll('iframe'))) {
    try {
      const b = f.contentDocument && f.contentDocument.body;
      const t = b ? b.innerText.trim() : '';
      if (t) out.iframes.push(t);
    } catch (e) {
      out.iframes.push('[iframe blocked: ' + e.message + ']');
    }
  }
  return JSON.stringify(out);
})()
"""

JS_OPEN_COMPOSER = r"""
(() => {
  const open = document.querySelector('[data-testid="composer:to"], .composer, [data-testid^="composer"]');
  if (open) return 'ALREADY OPEN';
  const el = Array.from(document.querySelectorAll('button, [role="button"], a'))
    .find(e => e.offsetParent && /new message|compose/i.test((e.innerText || e.getAttribute('aria-label') || '').trim()));
  if (!el) return 'NOT FOUND';
  el.click();
  return 'CLICKED';
})()
"""

JS_COMPOSE = r"""
(() => {
  const to = %s;
  const subject = %s;
  const body = %s;
  const send = %s;

  const clickText = (re) => {
    const el = Array.from(document.querySelectorAll('button, [role="button"], a'))
      .find(e => e.offsetParent && re.test((e.innerText || e.getAttribute('aria-label') || '').trim()));
    if (!el) return null;
    el.click();
    return el.innerText || el.getAttribute('aria-label') || 'clicked';
  };

  const setValue = (el, value) => {
    if (!el) return false;
    el.focus();
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value');
    if (setter && setter.set) setter.set.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    return true;
  };

  const opened = document.querySelector('[data-testid="composer:to"], .composer, [data-testid^="composer"]');
  if (!opened) return JSON.stringify({ok: false, error: 'composer not open'});

  const toEl = document.querySelector(
    'input[data-testid="composer:to"], input[id*="to"], input[placeholder*="Email" i], .composer input[type="email"], .composer input[type="text"]'
  );
  const subjectEl = document.querySelector(
    'input[data-testid="composer:subject"], input[placeholder*="Subject" i], input[id*="subject"]'
  );
  if (to && !setValue(toEl, to)) return JSON.stringify({ok: false, error: 'to field not found'});
  if (subject && !setValue(subjectEl, subject)) return JSON.stringify({ok: false, error: 'subject field not found'});

  let bodySet = false;
  const bodyEl = document.querySelector('[data-testid="composer:body"], [contenteditable="true"], textarea');
  if (bodyEl) {
    bodyEl.focus();
    if (bodyEl.getAttribute('contenteditable') === 'true') {
      bodyEl.textContent = body;
      bodyEl.dispatchEvent(new Event('input', {bubbles: true}));
      bodySet = true;
    } else {
      bodySet = setValue(bodyEl, body);
    }
  }
  if (!bodySet) {
    for (const f of Array.from(document.querySelectorAll('iframe'))) {
      try {
        const doc = f.contentDocument;
        const editable = doc && (doc.querySelector('[contenteditable="true"]') || doc.body);
        if (editable) {
          editable.textContent = body;
          bodySet = true;
          break;
        }
      } catch (e) {}
    }
  }
  if (body && !bodySet) return JSON.stringify({ok: false, error: 'body field not found'});

  if (send) {
    const sent = clickText(/^send$/i) || document.querySelector('[data-testid="composer:send-button"]');
    if (sent && sent.click) sent.click();
    if (!sent) return JSON.stringify({ok: false, error: 'send button not found'});
    return JSON.stringify({ok: true, action: 'sent', href: location.href});
  }
  return JSON.stringify({ok: true, action: 'drafted', href: location.href});
})()
"""


def js(session, tab, code):
    return session.texts(session.tool("javascript_tool", {"tabId": tab, "code": code}))


def require_daemon():
    if not check_daemon():
        sys.stderr.write(
            "start the headed daemon first:\n"
            "  ~/.agents/skills/web-browser/scripts/openchrome-daemon.sh start headed\n"
        )
        sys.exit(2)


def open_session(url):
    s = Session()
    s.initialize()
    sys.stderr.write(f"navigating to {url} ...\n")
    tab = extract_tab_id(s.texts(s.tool("navigate", {"url": url})))
    if not tab:
        sys.stderr.write("no tabId returned (navigation failed)\n")
        sys.exit(1)
    return s, tab


def wait_ready(session, tab, wait):
    deadline = time.time() + wait
    last = None
    while time.time() < deadline:
        raw = js(session, tab, JS_STATE)
        last = first_json_object(raw) or {"raw": raw[:200]}
        if last.get("login"):
            sys.stderr.write(
                "login page is showing. Ask the user to click Sign in in the "
                "Do not type the password in chat.\n"
            )
            sys.exit(3)
        if not last.get("decrypting") and (
            last.get("subjectCount", 0) > 0 or last.get("inboxChrome")
        ):
            return last
        if last.get("subjectCount", 0) > 0 and not last.get("decrypting"):
            return last
        time.sleep(1)
    sys.stderr.write(
        "inbox did not finish decrypting in time. "
        f"last state: {json.dumps(last)[:400]}\n"
    )
    sys.exit(3)


def print_inbox(state):
    print(f"url: {state.get('href')}")
    print(f"title: {state.get('title')}")
    print(f"messages: {state.get('subjectCount')}")
    for i, subject in enumerate(state.get("subjects") or [], 1):
        print(f"{i}. {subject}")


def cmd_inbox(args):
    s, tab = open_session(args.url)
    state = wait_ready(s, tab, args.wait)
    print_inbox(state)


def cmd_search(args):
    query = args.query
    base = args.url.rstrip("/")
    if "/inbox" in base:
        search_url = base.replace("/inbox", "/all-mail") + "#keyword=" + urllib.parse.quote(query)
    else:
        search_url = "https://mail.proton.me/u/0/all-mail#keyword=" + urllib.parse.quote(query)
    s, tab = open_session(search_url)
    state = wait_ready(s, tab, args.wait)
    print(f"query: {query}")
    print_inbox(state)


def cmd_open(args):
    s, tab = open_session(args.url)
    wait_ready(s, tab, args.wait)
    result = js(s, tab, JS_CLICK_SUBJECT % json.dumps(args.subject))
    sys.stderr.write(f"click: {result[:160]}\n")
    if "CLICKED" not in result:
        sys.stderr.write("message row not found\n")
        sys.exit(3)
    time.sleep(min(args.wait, 8))
    raw = js(s, tab, JS_READ_MESSAGE)
    data = first_json_object(raw) or {}
    href = data.get("href", "")
    if "/inbox/" not in href and "/all-mail/" not in href:
        sys.stderr.write(f"URL check failed after click: {href}\n")
        sys.exit(3)
    parts = [f"url: {href}"]
    if data.get("header"):
        parts.append("===== MESSAGE HEADER =====\n" + data["header"])
    opened = js(s, tab, JS_OPEN_COMPOSER)
    sys.stderr.write(f"composer: {opened[:80]}\n")
    if "CLICKED" not in opened and "ALREADY OPEN" not in opened:
        sys.stderr.write("compose button not found\n")
        sys.exit(4)
    iframes = data.get("iframes") or []
    if iframes:
        parts.append("===== MESSAGE BODY (iframe) =====\n" + "\n\n".join(iframes))
    else:
        parts.append("===== MESSAGE BODY (iframe) =====\n(no same-origin iframe text yet)")
    print("\n\n".join(parts)[: args.max_chars])


def cmd_compose(args):
    s, tab = open_session(args.url)
    wait_ready(s, tab, args.wait)
    last = None
    deadline = time.time() + args.wait
    while time.time() < deadline:
        code = JS_COMPOSE % (
            json.dumps(args.to),
            json.dumps(args.subject),
            json.dumps(args.body),
            "true" if args.send else "false",
        )
        raw = js(s, tab, code)
        last = first_json_object(raw) or {"ok": False, "error": raw[:200]}
        if last.get("ok"):
            print(json.dumps(last, indent=2))
            return
        time.sleep(1)
    sys.stderr.write(f"compose failed: {(last or {}).get('error')}\n")
    sys.exit(4)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=DEFAULT_INBOX, help="inbox URL; /u/N is discovered after login")
    parser.add_argument("--wait", type=float, default=DEFAULT_WAIT, help="seconds to wait for decrypt/render")
    parser.add_argument("--max-chars", type=int, default=8000)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("inbox", help="list visible inbox rows after decrypt")

    p_open = sub.add_parser("open", help="open one message by subject text")
    p_open.add_argument("--subject", required=True)

    p_search = sub.add_parser("search", help="search all mail")
    p_search.add_argument("query")

    p_compose = sub.add_parser("compose", help="open composer and fill a draft")
    p_compose.add_argument("--to", required=True)
    p_compose.add_argument("--subject", required=True)
    p_compose.add_argument("--body", required=True)
    p_compose.add_argument("--send", action="store_true", help="click send after filling")

    args = parser.parse_args()
    require_daemon()
    if args.cmd == "inbox":
        cmd_inbox(args)
    elif args.cmd == "open":
        cmd_open(args)
    elif args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "compose":
        cmd_compose(args)


if __name__ == "__main__":
    main()
