# Project MCP config is not part of this skill

Do not create or edit `.vscode/mcp.json` for browser work.

The only control plane is:

```sh
"$HOME/.agents/skills/web-browser/scripts/openchrome-daemon.sh" start headed
python3 "$HOME/.agents/skills/web-browser/scripts/oc-session.py" https://example.com
```

A project MCP file is a second path. It uses stdio, couples the project to nvm absolute paths, and fights the HTTP daemon for port 9222. That is how logins get dropped.

If a project already has an openchrome MCP server, ignore it and use the scripts above.
