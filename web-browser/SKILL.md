---
name: web-browser
description: "Drive Chrome with openchrome only. Use for browser automation, authenticated sites, Proton Mail, headed or headless browsing. Invoke bundled scripts by absolute path. Do not cd into the shared skills repo."
argument-hint: Target URL, whether login is required, and Proton Mail action if any
user-invokable: true
---

# Web browser automation

There is one control plane. Invoke the bundled scripts by absolute path. Do not invent a second path.

```sh
SKILL="$HOME/.agents/skills/web-browser"
"$SKILL/scripts/openchrome-daemon.sh" start headed    # login or any site that needs cookies
"$SKILL/scripts/openchrome-daemon.sh" start headless  # public pages only
python3 "$SKILL/scripts/oc-session.py" https://example.com --mode markdown
python3 "$SKILL/scripts/proton-mail.py" inbox
"$SKILL/scripts/openchrome-daemon.sh" stop            # only when the user is done with the browser
```

## Fail-fast rules

Stop and report the exact error. Do not fall back.

- do not use VS Code browser tools (`open_browser_page`, `navigate_page`, `read_page`, `screenshot_page`, or any Playwright surface)
- do not use `fetch_webpage` as a substitute for this skill
- do not create or edit `.vscode/mcp.json`
- do not run `openchrome serve`, `openchrome run`, or `oc run` yourself
- do not `cd` into this skills repo, and do not copy these scripts into a project
- do not write project files (databases, logs, screenshots, `.openchrome/`) into this skills repo
- do not claim "cannot access" until the matching script below has been run and its stderr is quoted

## Setup (one-time per machine)

Dependencies: nvm, Node.js LTS, openchrome-mcp.

Run [./scripts/setup.sh](./scripts/setup.sh) once. It installs openchrome 1.12.9 or newer under the active nvm LTS node.

## Two modes, one daemon

The daemon is a machine-wide singleton on ports 3199 and 9222. It refuses to start if the other mode is already running.

### Headed — authenticated work

Use for Proton Mail, any login, 2FA, or a site that already has cookies in the skill profile.

```sh
"$HOME/.agents/skills/web-browser/scripts/openchrome-daemon.sh" start headed
```

This launches visible Chrome with `--user-data-dir "$HOME/.openchrome/profile"`. That directory is the only login store. It is not daily Chrome. Saved passwords may appear on the Proton sign-in page even when the Proton session cookie is gone. Leave this daemon running across chat sessions so the login survives. Do not stop it after each command.

If a login page appears: ask the user to click the sign-in button in the visible window. Do not type credentials in chat. After they confirm, run the same command again.

### Headless — public pages only

```sh
"$HOME/.agents/skills/web-browser/scripts/openchrome-daemon.sh" start headless
```

This uses `$HOME/.openchrome/web-browser-skill/headless-profile`. It has no Proton session. Never reuse a headless daemon for mail or any login.

## What to run

| Task | Command |
| --- | --- |
| Public page | `oc-session.py URL --mode markdown` |
| Authenticated page | headed daemon, then `oc-session.py URL` |
| Proton inbox / search / open / draft / send | headed daemon, then [./scripts/proton-mail.py](./scripts/proton-mail.py) |
| Click a non-mail SPA row | headed daemon, then [./scripts/oc-open.py](./scripts/oc-open.py) |

`oc-session.py` only navigates and reads. Each invocation is a new MCP session. Do not try to click in one call and read in the next.

Proton Mail steps live in [./references/webmail-and-spa.md](./references/webmail-and-spa.md). Use `proton-mail.py`. Do not re-learn Proton selectors in the target project.

## Shared-repo hygiene

This skill is a symlink target used by many projects. The target project is the only place for that project's state.

- invoke scripts by absolute path from the target project's cwd
- the daemon sets its own cwd to `$HOME/.openchrome/web-browser-skill`, so openchrome's `.openchrome/` writes stay there
- if a different skill needs a sqlite file, that skill must use an absolute path under the target project; a relative `sqlite3 foo.db` run after `cd` into this repo will create the database here. That is a bug in the other skill, not a reason to keep the file here. Delete the stray file and fix the other skill.

## Preflight

Use the mode the task needs. Do not start headless as a smoke test before mail.

Public page:

1. `"$HOME/.agents/skills/web-browser/scripts/openchrome-daemon.sh" start headless`
2. `python3 "$HOME/.agents/skills/web-browser/scripts/oc-session.py" https://example.com --mode markdown` — title must be `Example Domain`

Authenticated page or Proton Mail:

1. `"$HOME/.agents/skills/web-browser/scripts/openchrome-daemon.sh" start headed` — must print `profile: $HOME/.openchrome/profile` and `chrome.connected: true` (or use `status`)
2. `python3 "$HOME/.agents/skills/web-browser/scripts/proton-mail.py" inbox` or `oc-session.py` on the target URL
3. if a login page appears, stop and ask the user to click sign in. Run the same command again after they confirm.

The `status` command now shows readiness. The helpers reject a daemon with `chrome.connected: false` or reconnecting. Leave the headed daemon running. Stopping it drops the Proton session.

## Troubleshooting

### Login page with username and password already filled

Cause: Chrome found saved passwords in `$HOME/.openchrome/profile`, but the Proton session cookie is gone. Common reasons: the previous chat ran `stop`, started headless, or launched Chrome without `--user-data-dir "$HOME/.openchrome/profile"`.

Fix: start headed, ask the user to click sign in once, then leave the daemon running. Do not treat autofill as proof that the session is alive.

### Daemon already running in the other mode or port 3199 occupied

Cause: headless and headed cannot share the singleton. A previous daemon that crashed or was killed uncleanly can also leave port 3199 occupied while the health check fails.

Fix: `"$HOME/.agents/skills/web-browser/scripts/openchrome-daemon.sh" stop` (the stop command now aggressively kills stray Node processes on ports 3199/9222). Then start the mode you need. Stopping headed Chrome will require a fresh Proton click-through.

### Port 9222 occupied by the wrong Chrome

Cause: daily Chrome or an old openchrome is already on 9222.

Fix: the daemon refuses to attach. Stop that Chrome, then start headed again. Do not pass `--restart-chrome` and do not kill daily Chrome unless the user says so.

### Inbox loaded but the message body is empty

Cause: Proton decrypts in the browser and renders the body in a sandboxed iframe. `oc-session.py` never opens a row.

Fix: `python3 "$HOME/.agents/skills/web-browser/scripts/proton-mail.py" open --subject "exact subject"`. Increase `--wait` if decrypt is still running.

### Daemon healthy but Chrome disconnected

The `status` and helpers now detect `chrome.connected: false` or reconnecting. They print a specific recovery command instead of proceeding to a guaranteed navigation failure.

### Startup connect error in logs

```
[SelfHealing] Startup Chrome connect failed: Chrome is not running with remote debugging on port 9222
```

Expected on first tool call. Chrome launches then. Not fatal.

### "Tab X is no longer available" or "no tabId returned"

Cause: stale `tabId` from a previous script invocation or transport issue.

Fix: run the script again. Do not reuse a tabId across processes. The improved readiness check prevents most transport failures.

## Blocked criteria

A browser task is `blocked` only if:

- the user did not complete login after an explicit request, or
- a service outage prevents access after retry with evidence, or
- a policy or legal matter requires a manager decision before proceeding

Any `blocked` status must include: exact error text, each preflight step result, and what recovery was tried.
