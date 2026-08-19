# Optional project MCP config for openchrome

This reference is not part of the normal browser workflow. The canonical workflow uses `scripts/openchrome-daemon.sh` and `scripts/oc-session.py` without changing the target project.

Create `.vscode/mcp.json` only when the user explicitly asks for persistent openchrome tools in that project. Otherwise stop and return to the canonical workflow in `SKILL.md`.

## Why absolute paths are required

VS Code's MCP host launches the server process with a minimal PATH that does not include nvm-managed node. If you use `openchrome` or `node` without an absolute path, the MCP server will fail with `env: node: No such file or directory`.

When project MCP integration was explicitly requested, resolve the absolute paths after running setup and bake them into `.vscode/mcp.json`.

## Resolve the correct paths

After running `./scripts/setup.sh`, or after any nvm version change:

```sh
# load nvm
export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh"
nvm install --lts

# print the two paths you need
which node
which openchrome
```

`nvm install --lts` is intentional: `nvm use --lts` exits with status 3 when the current LTS alias names a version that is not installed. Installation is idempotent and activates the current LTS.

These values change whenever you switch nvm node versions. Update `.vscode/mcp.json` whenever you change the active LTS version.

Also confirm the selected installation is openchrome 1.12.9 or newer:

```sh
openchrome --version
```

Versions through 1.12.7 publish an invalid `extract_data` array schema that VS Code rejects. Run `./scripts/setup.sh` to install the current compatible release before creating the config.

## .vscode/mcp.json templates

### Headed mode — real profile, auto-launch (default for authenticated sites)

```json
{
  "servers": {
    "openchrome": {
      "type": "stdio",
      "command": "<output of: which node>",
      "args": [
        "<output of: which openchrome>",
        "serve",
        "--auto-launch"
      ]
    }
  }
}
```

### Headed mode — real profile, restart Chrome if already running

Add `"--restart-chrome"` to args. Quits all Chrome windows first — confirm with the user before deploying this config.

### Headless mode — isolated temp profile, non-interactive

```json
{
  "servers": {
    "openchrome": {
      "type": "stdio",
      "command": "<output of: which node>",
      "args": [
        "<output of: which openchrome>",
        "serve",
        "--auto-launch",
        "--server-mode",
        "--user-data-dir",
        "/tmp/chrome-isolated-XXXXXX"
      ]
    }
  }
}
```

Replace `/tmp/chrome-isolated-XXXXXX` with the actual temp dir created by `mktemp -d /tmp/chrome-XXXXXX`. Delete this dir after the session ends.

## After editing mcp.json

Restart the chat session. The openchrome tools will appear in the tool list once the MCP server starts.

## Verifying the config works

In a new chat with openchrome tools available, run the preflight smoke test from the skill:

```text
navigate to https://example.com and confirm the title is "Example Domain"
```

If it returns a tabId and the correct title, the config is working.

## Error: tool parameters array type must have items

Example:

```text
Failed to validate tool mcp_openchrome_extract_data: Error: tool parameters array type must have items
```

Cause: openchrome 1.12.7 and earlier declare the `extract_data.alreadyCollected` parameter as an array without an `items` schema. VS Code correctly rejects that MCP tool definition. This is an openchrome package-version problem, not an MCP config syntax problem.

Fix:

1. From the skill directory, run `./scripts/setup.sh`. It installs `openchrome-mcp@latest` under the active nvm LTS node and rejects versions older than 1.12.9.
2. Copy the newly printed `node` and `openchrome` absolute paths into `.vscode/mcp.json`. Do not retain paths from a different nvm node installation.
3. Restart the MCP server or reload the VS Code window so the old tool list is discarded.
4. Run the smoke test above.

Do not work around this by disabling `extract_data`, switching browser tools, or editing files inside the global npm package. Upgrade the package that the MCP config actually invokes.
