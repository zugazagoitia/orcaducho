#!/bin/sh
# One-line setup for orcaducho (macOS and Linux; works from sh, bash, zsh and fish):
#   curl -fsSL https://raw.githubusercontent.com/zugazagoitia/orcaducho/main/install.sh | sh
# Safe to re-run: every step is idempotent. Append `-s -- --update` after `sh` to pull the latest version.
# Strictly POSIX sh: no bashisms, so it runs under dash on Debian/Ubuntu too.
set -eu

BIN_DIR="${ORCADUCHO_BIN_DIR:-$HOME/.local/bin}"
MARKET_DIR="$HOME/.claude/plugins/marketplaces/orcaducho"

need() { command -v "$1" >/dev/null 2>&1 || { echo "orcaducho: '$1' is required ($2)" >&2; exit 1; }; }
need claude "https://claude.com/claude-code"
need python3 "Python 3.9+"
need git "git"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { echo "orcaducho: Python 3.9+ is required" >&2; exit 1; }
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
  *)
    echo "orcaducho: $BIN_DIR is not on your PATH. Add it for your shell:" >&2
    case "$(basename "${SHELL:-sh}")" in
      fish) echo "  fish_add_path $BIN_DIR" >&2 ;;
      zsh) echo "  echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc" >&2 ;;
      bash)
        if [ "$(uname -s)" = "Darwin" ]; then rc="~/.bash_profile"; else rc="~/.bashrc"; fi
        echo "  echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> $rc" >&2 ;;
      *) echo "  export PATH=\"$BIN_DIR:\$PATH\"   (in your shell's startup file)" >&2 ;;
    esac
    ;;
esac

echo "orcaducho installed. Restart Claude Code, then run 'orcaducho init' in each repo."
