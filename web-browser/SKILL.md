---
name: web-browser
description: Drive a real Chrome browser for web access. Enforces openchrome as the only allowed automation path. Covers two modes — temporary isolated profile (headless, non-interactive) and existing real profile (headed, authenticated). Includes fail-fast rules, setup, cleanup, and documented gotchas.
argument-hint: Target URL, whether auth is required, and whether headed mode is needed
user-invokable: true
---

# Web browser automation

## Fail-fast rules — read these first

If any of the following appear, **stop immediately and report the exact error**. Do not silently fall back to any other tool.

- do not use VS Code built-in browser tools (`open_browser_page`, `navigate_page`, `read_page`, `screenshot_page`, or any tool from the VS Code playwright surface) — they have no cookies, no session, and no access to authenticated pages
- do not use `fetch_webpage` or other HTTP-only tools as a substitute for browser automation
- do not create or edit `.vscode/mcp.json` for an ordinary browser task
- do not claim "cannot access" until the preflight checklist below has been attempted and each step is documented

The VS Code browser tools are for public document fetches only, not for browser automation. Any agent that substitutes them for openchrome is non-compliant with this skill.

## Allowed tool

**openchrome** via its MCP server. No other browser automation tool is approved.

## Setup (one-time per machine)

Dependencies: nvm, Node.js LTS, openchrome-mcp.

Run [./scripts/setup.sh](./scripts/setup.sh) once. It installs the latest openchrome globally under the active nvm LTS node and verifies version 1.12.9 or newer.

The normal workflow does not need project configuration or absolute binary paths. The bundled daemon helper loads nvm and resolves openchrome itself.

## Canonical workflow — use this unless explicitly told otherwise

Run these scripts from this skill directory. Do not copy them into the target project.

1. Select a mode and start the skill-owned HTTP MCP daemon:

  ```sh
  ./scripts/openchrome-daemon.sh start headless  # public, non-interactive work
  ./scripts/openchrome-daemon.sh start headed    # authentication or human interaction
  ```

2. Navigate and read pages with the bundled client:

  ```sh
  python3 ./scripts/oc-session.py https://example.com --mode markdown
  ```

3. For authentication, leave the headed daemon running while the user logs in, then call `oc-session.py` again.

4. When the browser task is finished, stop resources started by this skill:

  ```sh
  ./scripts/openchrome-daemon.sh stop
  ```

This is the canonical control plane. It behaves the same in every target project because it neither reads nor writes that project's `.vscode/mcp.json`.

### Optional project MCP integration

Create `.vscode/mcp.json` only when the user explicitly asks to expose openchrome tools persistently in that project. Do not infer consent from a browser task. This changes project state, requires a VS Code reload, and couples the project to absolute nvm paths.

When explicitly requested, follow [./references/mcp-config.md](./references/mcp-config.md). Do not mix project stdio MCP and the canonical HTTP daemon in one browser session.

## Two modes

### Mode A — temporary isolated profile (headless, non-interactive)

Use for: public or unauthenticated tasks, one-shot research, CI-style automation.

Profile is created fresh and does not persist after the daemon is stopped.

```sh
./scripts/openchrome-daemon.sh start headless
python3 ./scripts/oc-session.py https://example.com --mode markdown
./scripts/openchrome-daemon.sh stop
```

#### One-shot CLI navigation (single read only)

```sh
"$OC_BIN" run navigate --arg url=https://example.com
```

Returns JSON with `tabId`, `title`, and `url`. **Do not reuse the tabId in a second `oc run` call** — each invocation starts a fresh session and the tabId will not be found.

`stop` removes the helper's PID, log, and ownership marker and stops the Chrome debugging process only when the helper started it.

---

### Mode B — existing real profile (headed, for authenticated sites)

Use for: any site where the user is already logged in, 2FA flows, member portals.

Start the canonical daemon in headed mode:

```sh
./scripts/openchrome-daemon.sh start headed
python3 ./scripts/oc-session.py https://example.com --mode markdown
```

Openchrome uses the available real or synchronized profile. Cookies may persist across uses. Read the navigation warning: if the real profile is locked, extensions, saved passwords, and bookmarks are unavailable even when synchronized cookies are present.

If Chrome is already running without a debug port and authentication is unavailable, stop and ask before restarting Chrome. Restarting quits all Chrome windows and momentarily loses open tabs.

#### Authentication handling

- if the target page loads as logged in: proceed
- if a login page appears: do not attempt to supply credentials in chat — ask the user to log in in the visible Chrome window, then confirm before continuing
- after login confirmation: navigate to the target URL again to verify

Do not declare "cannot access" until login has been requested and the user has confirmed the outcome.

#### Opening content behind a click (webmail, SPAs)

`oc-session.py` only navigates and reads. It cannot open an item that requires a
click, because each invocation is a fresh MCP session with a new tabId, and in a
single-page app the message body is not in the inbox document. Reaching the inbox
is not the same as opening a message.

For these sites use [./scripts/oc-open.py](./scripts/oc-open.py), which performs
navigate → click → wait → read in one MCP session and extracts the message body
from its sandboxed iframe:

```sh
python3 ./scripts/oc-open.py https://mail.proton.me/u/1/inbox \
    --click "exact subject text" --expect-url "/inbox/" --iframe --wait 10
```

See [./references/webmail-and-spa.md](./references/webmail-and-spa.md) for the
three gotchas: same-session interaction, confirming the click by URL change, and
reading the iframe body.

---

## Preflight checklist before first use in a session

Run these in order. Stop at the first failure and report.

1. `./scripts/openchrome-daemon.sh start headless` — must report ready
2. `./scripts/openchrome-daemon.sh status` — must return JSON with `"status":"ok"`
3. `python3 ./scripts/oc-session.py https://example.com --mode markdown` — must report title `Example Domain`
4. `./scripts/openchrome-daemon.sh stop` — must report cleanup

If any step fails, see troubleshooting below and stop rather than switching control planes.

---

## Troubleshooting

### "env: node: No such file or directory" from MCP server

Cause: optional project MCP integration has no absolute node path.

Fix: return to the canonical script workflow. If project MCP integration was explicitly requested, re-run `setup.sh`, copy the printed paths into the config, and see [./references/mcp-config.md](./references/mcp-config.md).

### "tool parameters array type must have items"

Cause: optional project MCP integration points to openchrome 1.12.7 or earlier. Its `extract_data.alreadyCollected` array schema omits `items`, so VS Code rejects the tool.

Fix: run [./scripts/setup.sh](./scripts/setup.sh), update `.vscode/mcp.json` with the paths it prints, then restart the MCP server or reload VS Code. See [./references/mcp-config.md](./references/mcp-config.md#error-tool-parameters-array-type-must-have-items).

Do not fall back to another browser tool or patch the global npm package.

### Startup connect error in logs

```
[SelfHealing] Startup Chrome connect failed: Chrome is not running with remote debugging on port 9222
```

Expected when `--auto-launch` is set. Chrome launches on the first tool call. This is a diagnostic probe, not a fatal error.

### "Tab X is no longer available"

Cause: stale `tabId` from a previous call, or Chrome was restarted.

Fix: call `navigate` again (no tabId needed), use the new tabId for all subsequent steps.

### `oc run` can't chain tool calls

Cause: each `oc run` starts a fresh one-shot MCP server with a new session. Tabs from one call don't exist in the next.

Fix: use [./scripts/openchrome-daemon.sh](./scripts/openchrome-daemon.sh) with [./scripts/oc-session.py](./scripts/oc-session.py).

### Clicked an item in webmail but got nothing / empty body

Cause: one of three things. The click and the read ran in separate sessions
(each `oc-session.py` invocation is a new session, so the click was lost); the
click hit the wrong element and no message opened; or the read looked at the
parent document while the body renders inside a sandboxed iframe.

Fix: use [./scripts/oc-open.py](./scripts/oc-open.py) with `--expect-url` and
`--iframe` so navigate → click → wait → read happen in one session, the click is
confirmed by the URL change, and the iframe body is extracted. See
[./references/webmail-and-spa.md](./references/webmail-and-spa.md).

### openchrome server exits immediately when run with `&` in a shell

Cause: STDIO mode reads stdin as the MCP protocol. Backgrounding it causes EOF/`read EIO` and immediate exit.

Fix: always use `--http <port>` for shell daemon use. STDIO mode is for MCP hosts (VS Code, Claude Code) only.

### PID file ENOENT warning

Benign. openchrome writes its PID to a global temp path; if a previous cleanup removed that dir, this warning appears but the server continues normally.

### Port 9222 conflict

```sh
lsof -ti tcp:9222 -sTCP:LISTEN    # find the PID
kill <pid>
```

If that Chrome was using the real profile with active tabs, warn the user before killing it.

---

## Blocked criteria

A browser task is `blocked` only if:

- the user did not provide auth access after an explicit request, or
- a service outage prevents access after retry with evidence, or
- a policy or legal matter requires a manager decision before proceeding

Any `blocked` status must include: exact error text, each preflight step result, troubleshooting steps attempted, and what recovery was tried.
