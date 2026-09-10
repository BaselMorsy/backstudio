#!/usr/bin/env bash
# Installs the `backstudio` CLI globally on PATH (macOS/Linux).
#
# Uses `uv tool install`, which puts backstudio in its own isolated
# environment (separate from `uv sync`'s project-local .venv, which is for
# BackStudio's own contributors/developers) and links its console script
# onto a directory uv keeps on PATH.
set -euo pipefail

echo "Installing BackStudio (backstudio CLI)..."

if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found - installing it first (https://docs.astral.sh/uv/)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # uv's own installer updates PATH via a shell profile, which only takes
    # effect in a NEW shell - export it here too so this script can use uv
    # immediately without asking the user to restart first.
    export PATH="$HOME/.local/bin:$PATH"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Pinned to 3.11 to match .python-version (the primary/tested interpreter) -
# Python 3.12 is also supported (see docs-site/getting-started/installation.md)
# if you'd rather use `uv tool install --editable . --python 3.12` yourself.
uv tool install --editable . --python 3.11

echo ""
echo "Done. The 'backstudio' command should now be on your PATH."
echo "Try: backstudio --help"
echo "If that doesn't work yet, restart your shell (or run: source ~/.bashrc / ~/.zshrc) and try again."
