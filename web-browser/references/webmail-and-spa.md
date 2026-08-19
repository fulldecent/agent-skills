# Proton Mail and other authenticated SPAs

Proton Mail has no SMTP or IMAP for this workflow. Use the website through the headed daemon and [../scripts/proton-mail.py](../scripts/proton-mail.py). Do not copy these steps into a project skill.

Read `SKILL.md` first. Mail is headed-only. The login lives in `$HOME/.openchrome/profile`. Leave that daemon running.

## Why this is a separate helper

`oc-session.py` navigates and reads one page. That is not enough for Proton:

1. Each script invocation is a new MCP session. A click in one process is gone in the next.
2. The inbox list is not the message. The body is decrypted in the browser and rendered in a sandboxed iframe.
3. Decrypt is asynchronous. Reading too early looks like an empty inbox.

`proton-mail.py` keeps navigate, wait-for-decrypt, click, and iframe read in one process.

## Canonical Proton commands

```sh
SKILL="$HOME/.agents/skills/web-browser"
"$SKILL/scripts/openchrome-daemon.sh" start headed
"$SKILL/scripts/openchrome-daemon.sh" status   # confirms chrome.connected: true

python3 "$SKILL/scripts/proton-mail.py" inbox
python3 "$SKILL/scripts/proton-mail.py" search "invoice"
python3 "$SKILL/scripts/proton-mail.py" open --subject "exact subject from the list"
python3 "$SKILL/scripts/proton-mail.py" compose \
    --to someone@example.com --subject "Subject" --body "Body"
python3 "$SKILL/scripts/proton-mail.py" compose \
    --to someone@example.com --subject "Subject" --body "Body" --send
```

Do not stop the daemon between these commands. Stopping headed Chrome drops the Proton session. The next chat will show the sign-in page with the password already filled. That is autofill, not a live session. Ask the user to click sign in once, then leave the daemon up.

The `stop` command is now more robust and will clean up stray processes that previously caused "port 3199 is occupied but the openchrome health check failed".

## Login and decrypt

1. Start headed. Confirm `status` shows `chrome.connected: true` (or `ready: true`).
2. Run `proton-mail.py inbox`.
3. If stderr says the login page is showing, stop. Ask the user to click sign in in the visible window. Do not type the password in chat.
4. Run `inbox` again. The helper waits until rows appear and the decrypt banner is gone.
5. If rows are still missing, raise `--wait`. Twelve seconds is the default because Proton decrypts locally.

The helpers now reject a daemon whose Chrome connection is dead. The `status` command shows both health and readiness.

The account path is `/u/<n>/`. It is not always `0`. After a successful inbox load, reuse the printed URL.

## Opening a message

`open` clicks the shortest visible row that contains the subject, then waits for `/inbox/<id>` or `/all-mail/<id>`, then reads the iframe.

If the body is empty, decrypt is still running or the click missed. Quote the stderr and retry with a longer `--wait` or a more specific `--subject`. Do not fall back to `read_page` on the parent document. That page is the app shell.

## Search, draft, send

- `search` opens all-mail with `#keyword=`. It lists matching rows. It does not open a message.
- `compose` without `--send` fills to, subject, and body and leaves the draft open.
- `compose --send` clicks send after the fields are filled. Confirm the recipient with the user before `--send`.

## Non-mail SPAs

For a member portal or other click-to-open page that is not Proton, use [../scripts/oc-open.py](../scripts/oc-open.py) the same way: one process, `--expect-url`, and `--iframe` when the payload is inside a frame.

## What not to do

- do not drive Proton with `oc-session.py` plus ad-hoc `javascript_tool` calls
- do not write a project-local Proton script
- do not start headless, then hope cookies appear
- do not treat a filled password field as logged in
