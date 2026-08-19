#!/usr/bin/env python3
"""
Generic multi-step openchrome session over MCP HTTP.

Usage:
  python3 oc-session.py <url> [--mode markdown|dom|ax|semantic] [--wait <seconds>]

The openchrome HTTP daemon must already be running before calling this script.
Invoke the helper by absolute path. Do not cd into the skills repo:

    ~/.agents/skills/web-browser/scripts/openchrome-daemon.sh start headless
    ~/.agents/skills/web-browser/scripts/openchrome-daemon.sh start headed

The daemon health endpoint (port 9090) confirms readiness:
  curl http://localhost:9090/health

Exit codes:
  0  success, page content written to stdout
  1  no tabId returned (navigation failed or redirect loop)
  2  daemon not reachable
"""

import json
import sys
import time
import urllib.request
import urllib.error
import argparse

DAEMON_MCP  = "http://127.0.0.1:3199/mcp"
DAEMON_HEALTH = "http://127.0.0.1:9090/health"
DEFAULT_WAIT = 4  # seconds for JS to render after navigate


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
        data = json.dumps(body).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        req = urllib.request.Request(DAEMON_MCP, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=35) as resp:
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
                "clientInfo": {"name": "oc-session", "version": "1.0"},
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
    def extract_texts(resp):
        if not resp or "result" not in resp:
            return ""
        return "\n".join(
            c["text"] for c in resp["result"].get("content", []) if c.get("type") == "text"
        )

    @staticmethod
    def extract_nav(resp_text):
        """return (tab_id, url, title) from navigate response text"""
        for line in resp_text.split("\n"):
            try:
                d = json.loads(line)
                if "tabId" in d:
                    return d["tabId"], d.get("url"), d.get("title")
            except Exception:
                pass
        return None, None, None


def main():
    parser = argparse.ArgumentParser(description="Navigate and read a page via openchrome MCP HTTP")
    parser.add_argument("url", help="URL to navigate to")
    parser.add_argument("--mode", default="markdown", choices=["markdown", "dom", "ax", "semantic"],
                        help="read_page mode (default: markdown)")
    parser.add_argument("--wait", type=float, default=DEFAULT_WAIT,
                        help=f"seconds to wait after navigate for JS rendering (default: {DEFAULT_WAIT})")
    parser.add_argument("--max-chars", type=int, default=8000,
                        help="max chars of page content to output (default: 8000)")
    args = parser.parse_args()

    if not check_daemon():
        sys.stderr.write(
            "start the daemon first:\n"
            "  ~/.agents/skills/web-browser/scripts/openchrome-daemon.sh start headless\n"
            "or:\n"
            "  ~/.agents/skills/web-browser/scripts/openchrome-daemon.sh start headed\n"
        )
        sys.exit(2)

    s = Session()
    s.initialize()

    sys.stderr.write(f"navigating to {args.url} ...\n")
    nav = s.tool("navigate", {"url": args.url})
    nav_text = s.extract_texts(nav)
    tab_id, url, title = s.extract_nav(nav_text)

    if not tab_id:
        sys.stderr.write(f"no tabId returned\nraw response:\n{nav_text[:400]}\n")
        sys.exit(1)

    sys.stderr.write(f"landed:  {url}\ntitle:   {title}\n")

    if args.wait > 0:
        sys.stderr.write(f"waiting {args.wait}s for JS render...\n")
        time.sleep(args.wait)

    sys.stderr.write(f"reading page (mode={args.mode})...\n")
    read = s.tool("read_page", {"tabId": tab_id, "mode": args.mode})
    content = s.extract_texts(read)
    print(content[: args.max_chars])


if __name__ == "__main__":
    main()
