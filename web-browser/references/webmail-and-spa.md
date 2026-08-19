# Authenticated webmail and single-page apps

This reference covers opening and reading content that only appears after a click
inside a single-page app (SPA) — webmail such as Proton Mail or Gmail, member
portals, dashboards. The canonical `scripts/oc-session.py` cannot do this on its
own. Use `scripts/oc-open.py` for these cases.

Read `SKILL.md` first. This document is Mode B territory: the site is behind a
login and you are already running the headed daemon.

## Why oc-session.py is not enough

`oc-session.py` does exactly two things: navigate, then read. It cannot open an
item that requires a click. Two facts make this a hard limit:

1. Each invocation of `oc-session.py` starts a **fresh MCP session with a new
   tabId**. A click performed in one invocation is gone by the next. Navigate,
   click, wait, and read must all happen inside a single MCP session.
2. In an SPA the message body is not in the inbox document. Reading the inbox
   again after a click returns the same list, which looks like "the click did
   nothing."

If you only ever navigated and read, you never actually opened anything. Say
"the inbox loaded, but I did not open a message" rather than concluding the
browser cannot expose the body.

## The three gotchas

### 1. Same-session navigate → click → wait → read

Opening a message is one session: navigate to the inbox, click the exact row,
wait for the SPA route to change, then read. `oc-open.py` does this in one
process. Do not split these steps across separate `oc-session.py` or `oc run`
calls.

### 2. Confirm the click by the URL, not by confidence

Natural-language clicking (`interact`) can silently hit the wrong element — for
example the "New message" button instead of a conversation row. Opening a Proton
message changes the URL to `/u/<n>/inbox/<conversation-id>`. Verify that the URL
changed before trusting anything you read. `oc-open.py --expect-url "/inbox/"`
fails loudly when the click missed.

### 3. The message body is inside a sandboxed iframe

Proton (and Gmail) render the sanitized message HTML inside an `<iframe>`.
`read_page --mode markdown` of the parent document returns the app shell and the
conversation list, never the body. Read the iframe explicitly:

```js
Array.from(document.querySelectorAll('iframe'))
  .map(f => { try { return f.contentDocument?.body?.innerText || ''; } catch (e) { return ''; } })
  .filter(t => t.trim())
  .join('\n')
```

`oc-open.py --iframe` extracts the header and this iframe body for you and puts
them first, so the large list view does not consume the character budget.

## Canonical webmail workflow

```sh
# 1. Start headed (the openchrome profile is its own profile; expect a fresh login)
./scripts/openchrome-daemon.sh start headed

# 2. Confirm auth; if this redirects to the sign-in page, ask the user to log in
#    in the visible Chrome window, then continue
python3 ./scripts/oc-session.py https://mail.proton.me/u/0/inbox --mode markdown

# 3. Open a specific message and read its body, all in one session
python3 ./scripts/oc-open.py https://mail.proton.me/u/1/inbox \
    --click "exact subject text from the list" \
    --expect-url "/inbox/" \
    --iframe --wait 10

# 4. Stop when done
./scripts/openchrome-daemon.sh stop
```

Notes:

- the account path segment is `/u/<n>/`; the number is not always `0`. Read the
  inbox first to learn which one is active (the page title shows the address).
- SPAs render asynchronously. If a click reports `NOT FOUND`, the list had not
  finished rendering — increase `--wait`.
- the headed daemon uses openchrome's own profile at `~/.openchrome/profile`,
  which is separate from your day-to-day Chrome profile. Being logged into Chrome
  normally does not carry over; a fresh login in the openchrome window is
  expected. Cookies in that profile may persist between daemon runs.

## When to fall back to the raw MCP tools

`oc-open.py` matches a row by visible text. If a subject is ambiguous or the
element is not text-addressable, drive the daemon directly: use `find` to get a
stable ref, then `interact`/`computer` with that ref, then the iframe read above.
Keep it all in one MCP session.
