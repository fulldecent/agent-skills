#!/usr/bin/env python3
"""
Single-session navigate -> click -> wait -> read for authenticated SPAs (webmail, portals).

The bundled oc-session.py only navigates and reads. It cannot open an item that
requires a click, because each invocation of oc-session.py starts a fresh MCP
session with a new tabId. Opening a message therefore has to happen inside ONE
MCP session: navigate, click the row, wait for the SPA route to change, then read.

This helper does exactly that against the already-running openchrome HTTP daemon.
Start the daemon first (headed for authenticated sites):

    ./scripts/openchrome-daemon.sh start headed

Usage:
    python3 oc-open.py <url> --click "<visible text>" [options]

Options:
    --click TEXT        Case-insensitive visible text of the row/link to open.
    --scope CSS         Restrict the search to this container (default: whole page).
    --expect-url SUBSTR Confirm the URL contains this substring after the click.
                        If it does not appear, the click is reported as failed.
    --iframe            Also extract text from same-origin iframes. Webmail bodies
                        (Proton, Gmail, etc.) render inside a sandboxed iframe, so
                        read_page of the parent document never contains the body.
                        With --iframe the output is the message header plus iframe
                        body; the parent read_page (--mode) is skipped.
    --mode MODE         read_page mode for the parent document (default: markdown).
                        Ignored when --iframe is set.
    --wait N            Seconds to wait after navigate and after click (default: 7).
    --max-chars N       Max characters of combined output (default: 8000).

Exit codes:
    0  success
    1  navigation failed (no tabId)
    2  daemon not reachable
    3  click target not found, or --expect-url not satisfied
"""

import argparse
import json
import sys
import time
import urllib.request

DAEMON_MCP = "http://127.0.0.1:3199/mcp"
DAEMON_HEALTH = "http://127.0.0.1:9090/health"
DEFAULT_WAIT = 7


def check_daemon():
    try:
        with urllib.request.urlopen(DAEMON_HEALTH, timeout=3) as r:
            return json.loads(r.read()).get("status") == "ok"
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
        with urllib.request.urlopen(req, timeout=45) as resp:
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
            "jsonrpc": "2.0", "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "oc-open", "version": "1.0"},
            },
            "id": self._next_id(),
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def tool(self, name, args):
        return self._post({
            "jsonrpc": "2.0", "method": "tools/call",
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


def _first_json_object(text):
    """Decode the first JSON object in text, ignoring any trailing hint lines."""
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj
    except Exception:
        return None


# Finds the most specific element whose text contains the needle, climbs to the
# nearest clickable ancestor, and dispatches real mouse events. SPAs like Proton
# often bind to mousedown, so a bare .click() is not enough.
CLICK_JS = r"""
(() => {
  const needle = %s.toLowerCase();
  const scopeSel = %s;
  const scope = scopeSel ? document.querySelector(scopeSel) : document.body;
  if (!scope) return 'SCOPE NOT FOUND';
  const matches = Array.from(scope.querySelectorAll('*'))
    .filter(e => e.offsetParent && (e.innerText || '').toLowerCase().includes(needle));
  if (!matches.length) return 'NOT FOUND';
  matches.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
  const el = matches[0];
  const clickable = el.closest('[data-element-id],[role="button"],[role="link"],a,li,button,.item-container') || el;
  const r = clickable.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  for (const type of ['mousedown', 'mouseup', 'click']) {
    clickable.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy}));
  }
  return 'CLICKED ' + clickable.tagName + ': ' + (el.innerText || '').replace(/\s+/g, ' ').slice(0, 80);
})()
"""

# Returns the post-click URL, the reading-pane header, and any same-origin iframe
# bodies (the message body itself).
READ_JS = r"""
(() => {
  const out = {href: location.href, header: '', iframes: []};
  const h = document.querySelector('.message-header, [data-testid="message-header"]');
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--click", help="visible text of the element to open")
    ap.add_argument("--scope", default=None, help="CSS selector to restrict the search")
    ap.add_argument("--expect-url", default=None, help="substring the URL must contain after the click")
    ap.add_argument("--iframe", action="store_true", help="also extract same-origin iframe text")
    ap.add_argument("--mode", default="markdown", choices=["markdown", "dom", "ax", "semantic"])
    ap.add_argument("--wait", type=float, default=DEFAULT_WAIT)
    ap.add_argument("--max-chars", type=int, default=8000)
    a = ap.parse_args()

    if not check_daemon():
        sys.stderr.write(
            "start the daemon first:\n"
            "  ./scripts/openchrome-daemon.sh start headed\n"
        )
        sys.exit(2)

    s = Session()
    s.initialize()

    sys.stderr.write(f"navigating to {a.url} ...\n")
    tab = extract_tab_id(s.texts(s.tool("navigate", {"url": a.url})))
    if not tab:
        sys.stderr.write("no tabId returned (navigation failed)\n")
        sys.exit(1)
    time.sleep(a.wait)

    if a.click:
        scope_arg = json.dumps(a.scope) if a.scope else "null"
        click_code = CLICK_JS % (json.dumps(a.click), scope_arg)
        result = s.texts(s.tool("javascript_tool", {"tabId": tab, "code": click_code}))
        sys.stderr.write(f"click: {result[:160]}\n")
        if "CLICKED" not in result:
            sys.stderr.write("click target not found; nothing opened\n")
            sys.exit(3)
        time.sleep(a.wait)

    href = None
    header = ""
    iframe_texts = []
    if a.iframe or a.expect_url:
        raw = s.texts(s.tool("javascript_tool", {"tabId": tab, "code": READ_JS}))
        # openchrome may append a "Hint:" line after the JS return value, so decode
        # only the leading JSON object rather than the whole text blob.
        data = _first_json_object(raw)
        if data is not None:
            href = data.get("href")
            header = data.get("header", "")
            iframe_texts = data.get("iframes", [])
        else:
            sys.stderr.write(f"could not parse read JS result: {raw[:200]}\n")

    if a.expect_url:
        if not href or a.expect_url not in href:
            sys.stderr.write(
                f"URL check failed: expected '{a.expect_url}' in '{href}'. "
                "The click likely hit the wrong element.\n"
            )
            sys.exit(3)
        sys.stderr.write(f"url confirmed: {href}\n")
    elif href:
        sys.stderr.write(f"url now: {href}\n")

    parts = []
    # For webmail/SPAs the iframe body is the payload, so surface it first; the
    # parent read_page (often a huge list view) would otherwise eat the char budget.
    if a.iframe:
        if header:
            parts.append("===== MESSAGE HEADER =====\n" + header)
        if iframe_texts:
            parts.append("===== MESSAGE BODY (iframe) =====\n" + "\n\n".join(iframe_texts))
        else:
            parts.append("===== MESSAGE BODY (iframe) =====\n(no same-origin iframe text found; "
                         "the message may still be loading, or is cross-origin)")
    else:
        page = s.texts(s.tool("read_page", {"tabId": tab, "mode": a.mode}))
        if page:
            parts.append(page)
    print("\n\n".join(parts)[: a.max_chars])


if __name__ == "__main__":
    main()
