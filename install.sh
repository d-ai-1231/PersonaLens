#!/bin/bash
# Quality Review Agent — Installer
# Installs the Claude Code skill and sets up the .env file.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$PROJECT_DIR/skill-template/SKILL.md"
SKILL_DEST_DIR="$HOME/.claude/skills/review-service"
SKILL_DEST="$SKILL_DEST_DIR/SKILL.md"
ENV_FILE="$PROJECT_DIR/.env"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { printf "${BLUE}ℹ${NC}  %s\n" "$1"; }
success() { printf "${GREEN}✓${NC}  %s\n" "$1"; }
warn() { printf "${YELLOW}⚠${NC}  %s\n" "$1"; }
error() { printf "${RED}✗${NC}  %s\n" "$1" >&2; }

printf "\n"
printf "╔══════════════════════════════════════════════════════════╗\n"
printf "║  🔍 Quality Review Agent — Installer                     ║\n"
printf "╚══════════════════════════════════════════════════════════╝\n\n"

info "Project directory: $PROJECT_DIR"

# Step 1: Check Python 3.11+
print_python_install_help() {
  printf "\n"
  printf "   ${BLUE}How to install Python 3.11+:${NC}\n"
  case "$(uname -s)" in
    Darwin)
      printf "     • Homebrew:  ${GREEN}brew install python@3.11${NC}\n"
      printf "     • Installer: https://www.python.org/downloads/macos/\n"
      ;;
    Linux)
      printf "     • Debian/Ubuntu: ${GREEN}sudo apt update && sudo apt install python3.11${NC}\n"
      printf "     • Fedora:        ${GREEN}sudo dnf install python3.11${NC}\n"
      printf "     • Arch:          ${GREEN}sudo pacman -S python${NC}\n"
      printf "     • Other:         https://www.python.org/downloads/source/\n"
      ;;
    *)
      printf "     • Download: https://www.python.org/downloads/\n"
      ;;
  esac
  printf "\n"
}

if ! command -v python3 >/dev/null 2>&1; then
  error "Python 3 not found."
  print_python_install_help
  exit 1
fi
PY_VERSION=$(python3 --version 2>&1)
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  error "$PY_VERSION detected, but Python 3.11+ is required."
  print_python_install_help
  exit 1
fi
success "Found $PY_VERSION"

# Step 2: Check/create .env with GEMINI_API_KEY
if [[ -f "$ENV_FILE" ]] && grep -q "^GEMINI_API_KEY=" "$ENV_FILE"; then
  success ".env already contains GEMINI_API_KEY"
else
  warn "GEMINI_API_KEY not set."
  printf "\n"
  printf "   Get your free API key at: ${BLUE}https://aistudio.google.com/apikey${NC}\n\n"
  read -rp "   Paste your GEMINI_API_KEY: " API_KEY
  if [[ -z "${API_KEY// }" ]]; then
    error "No API key provided. Aborting."
    exit 1
  fi
  # Strip quotes and whitespace
  API_KEY=$(printf '%s' "$API_KEY" | tr -d '"' | tr -d "'" | tr -d ' \n\r\t')
  printf "GEMINI_API_KEY='%s'\n" "$API_KEY" > "$ENV_FILE"
  success "Saved API key to .env"
fi

# Step 3: Validate Python modules can be imported
info "Checking Python modules..."
if ! (cd "$PROJECT_DIR" && PYTHONPATH=src python3 -c "from quality_review_agent.skill_helper import main" 2>/dev/null); then
  error "Failed to import quality_review_agent module. Check the project structure."
  exit 1
fi
success "Python modules OK"

# Step 4: Install the Claude Code skill
if [[ ! -f "$SKILL_SRC" ]]; then
  error "Skill template not found at: $SKILL_SRC"
  exit 1
fi

mkdir -p "$SKILL_DEST_DIR"

# Replace {{PROJECT_DIR}} placeholder with the actual absolute path
# Use a delimiter other than / to avoid escaping issues
sed "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" "$SKILL_SRC" > "$SKILL_DEST"

success "Installed skill at: $SKILL_DEST"

# Step 5: Done
printf "\n"
printf "╔══════════════════════════════════════════════════════════╗\n"
printf "║  ✅ Installation Complete!                               ║\n"
printf "╚══════════════════════════════════════════════════════════╝\n\n"

printf "Next steps:\n\n"
printf "  ${BLUE}1.${NC} Restart Claude Code (if it's already running)\n"
printf "  ${BLUE}2.${NC} Try the skill by asking:\n\n"
printf "       ${GREEN}Review this site: https://example.com${NC}\n\n"
printf "  ${BLUE}3.${NC} Or use the CLI directly:\n\n"
printf "       ${GREEN}cd \"$PROJECT_DIR\"${NC}\n"
printf "       ${GREEN}PYTHONPATH=src python3 -m quality_review_agent interactive https://example.com${NC}\n\n"
printf "  ${BLUE}4.${NC} Or use the web UI:\n\n"
printf "       ${GREEN}cd \"$PROJECT_DIR\" && ./start-web.sh${NC}\n"
printf "       then open ${BLUE}http://127.0.0.1:8080${NC}\n\n"
