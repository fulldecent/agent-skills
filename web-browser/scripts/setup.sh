#!/bin/sh
# Install openchrome-mcp globally using the active nvm lts node.
# Run this once per machine before using the web-browser skill.
#
# Prerequisites: nvm installed at ~/.nvm
# See: https://github.com/nvm-sh/nvm#installing-and-updating

set -e

export NVM_DIR="$HOME/.nvm"
if [ ! -s "$NVM_DIR/nvm.sh" ]; then
  echo "ERROR: nvm not found at $NVM_DIR"
  echo "Install nvm first: https://github.com/nvm-sh/nvm#installing-and-updating"
  exit 1
fi
. "$NVM_DIR/nvm.sh"

nvm install --lts
echo "node: $(node --version) at $(which node)"

npm install -g openchrome-mcp@latest

OC_BIN="$(which openchrome)"
NODE_BIN="$(which node)"
OC_VERSION="$(openchrome --version)"

node -e '
const [major, minor, patch] = process.argv[1].split(".").map(Number);
if (major < 1 || (major === 1 && (minor < 12 || (minor === 12 && patch < 9)))) {
  console.error(`ERROR: openchrome ${process.argv[1]} has an invalid extract_data schema.`);
  console.error("Install openchrome-mcp 1.12.9 or newer.");
  process.exit(1);
}
' "$OC_VERSION"

echo ""
echo "openchrome: $OC_VERSION at $OC_BIN"
echo ""
echo "--- resolved runtime paths ---"
echo "command: $NODE_BIN"
echo "args[0]: $OC_BIN"
echo ""
echo "Installation verified. Use scripts/openchrome-daemon.sh; no project MCP file is needed."
echo "Use these paths only if the user explicitly requests optional project MCP integration."
