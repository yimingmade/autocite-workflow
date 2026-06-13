#!/usr/bin/env bash
#
# Install Autocite into Codex and/or Claude Code.
#
# Local usage:
#   bash scripts/install.sh --codex
#   bash scripts/install.sh --claude
#   bash scripts/install.sh --all --force
#
# Remote usage after publishing to GitHub:
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/scripts/install.sh | bash -s -- --codex
#
# Env overrides for remote usage:
#   INSTALL_REPO=<owner/repo>   default: yimingmade/autocite-workflow
#   INSTALL_REF=<branch-or-tag> default: main
#   CODEX_HOME=<path>          default: ~/.codex
#   CLAUDE_HOME=<path>         default: ~/.claude

set -euo pipefail

INSTALL_CODEX=""
INSTALL_CLAUDE=""
EXPLICIT=0
FORCE=""
VALIDATE_ONLY=""

usage() {
  cat <<'USAGE'
Install Autocite into Codex and/or Claude Code.

Default behaviour:
  bash scripts/install.sh            Auto-detect ~/.codex and ~/.claude.

Explicit selection:
  bash scripts/install.sh --codex    Install Codex skill only.
  bash scripts/install.sh --claude   Install Claude Code skill only.
  bash scripts/install.sh --all      Install both.

Options:
  --force                            Replace existing target skill.
  --validate-only                    Validate package, do not install.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --codex) INSTALL_CODEX=1; EXPLICIT=1 ;;
    --claude) INSTALL_CLAUDE=1; EXPLICIT=1 ;;
    --all) INSTALL_CODEX=1; INSTALL_CLAUDE=1; EXPLICIT=1 ;;
    --force) FORCE="--force" ;;
    --validate-only) VALIDATE_ONLY="--validate-only" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[install] Unknown arg: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "[install] python3 is required." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd || true)"
if [[ -n "${SCRIPT_DIR:-}" && -f "$SCRIPT_DIR/../SKILL.md" ]]; then
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
  CLEANUP=""
else
  REPO="${INSTALL_REPO:-yimingmade/autocite-workflow}"
  REF="${INSTALL_REF:-main}"
  TMPDIR="$(mktemp -d)"
  CLEANUP="$TMPDIR"
  trap '[[ -n "${CLEANUP:-}" ]] && rm -rf "$CLEANUP"' EXIT
  echo "[install] Fetching $REPO@$REF..."
  curl -fsSL "https://api.github.com/repos/$REPO/tarball/$REF" | tar -xz -C "$TMPDIR" --strip-components=1
  REPO_ROOT="$TMPDIR"
fi

if [[ $EXPLICIT == 0 ]]; then
  [[ -d "${CODEX_HOME:-$HOME/.codex}" ]] && INSTALL_CODEX=1
  [[ -d "${CLAUDE_HOME:-$HOME/.claude}" ]] && INSTALL_CLAUDE=1
  if [[ -z "${INSTALL_CODEX:-}" && -z "${INSTALL_CLAUDE:-}" ]]; then
    echo "[install] No Codex or Claude Code home detected. Pass --codex, --claude, or --all." >&2
    exit 1
  fi
fi

echo "[install] Validating package..."
python3 "$REPO_ROOT/scripts/validate_package.py" --root "$REPO_ROOT"

if [[ -n "$VALIDATE_ONLY" ]]; then
  exit 0
fi

if [[ "${INSTALL_CODEX:-}" == 1 ]]; then
  python3 "$REPO_ROOT/scripts/install_codex_skill.py" --source "$REPO_ROOT" $FORCE
fi

if [[ "${INSTALL_CLAUDE:-}" == 1 ]]; then
  python3 "$REPO_ROOT/scripts/install_claude_skill.py" --source "$REPO_ROOT" $FORCE
fi
