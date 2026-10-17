#!/bin/sh
# One-line setup for orcaducho:
#   curl -fsSL https://raw.githubusercontent.com/zugazagoitia/orcaducho/main/install.sh | sh
# Safe to re-run: every step is idempotent. Run with `sh -s -- --update` to pull the latest version.
set -eu

BIN_DIR="${ORCADUCHO_BIN_DIR:-$HOME/.local/bin}"
MARKET_DIR="$HOME/.claude/plugins/marketplaces/orcaducho"

need() { command -v "$1" >/dev/null 2>&1 || { echo "orcaducho: '$1' is required ($2)" >&2; exit 1; }; }
need claude "https://claude.com/claude-code"
need python3 "Python 3.9+"
need git "git"
command -v gh >/dev/null 2>&1 || echo "orcaducho: 'gh' not found; GitHub issues and the final PR will be skipped" >&2

claude plugin marketplace add zugazagoitia/orcaducho
if [ "${1:-}" = "--update" ]; then
  claude plugin marketplace update orcaducho
  claude plugin update orcaducho@orcaducho
fi
claude plugin install orcaducho@orcaducho

python3 "$MARKET_DIR/bin/orcaducho" install --dir "$BIN_DIR"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "orcaducho: add $BIN_DIR to your PATH (e.g. echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc)" >&2 ;;
esac

echo "orcaducho installed. Restart Claude Code, then run 'orcaducho init' in each repo."
