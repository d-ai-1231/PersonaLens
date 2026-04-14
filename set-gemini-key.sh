#!/bin/zsh
set -euo pipefail

cd "/Users/dave/Documents/Coding/Quality Review Agent"

printf "Enter GEMINI_API_KEY: "
stty -echo
read -r GEMINI_API_KEY_INPUT
stty echo
printf "\n"

if [[ -z "${GEMINI_API_KEY_INPUT}" ]]; then
  echo "No key entered."
  exit 1
fi

GEMINI_API_KEY_INPUT="${GEMINI_API_KEY_INPUT//‘/}"
GEMINI_API_KEY_INPUT="${GEMINI_API_KEY_INPUT//’/}"
GEMINI_API_KEY_INPUT="${GEMINI_API_KEY_INPUT//“/}"
GEMINI_API_KEY_INPUT="${GEMINI_API_KEY_INPUT//”/}"
GEMINI_API_KEY_INPUT="${GEMINI_API_KEY_INPUT%\"}"
GEMINI_API_KEY_INPUT="${GEMINI_API_KEY_INPUT#\"}"
GEMINI_API_KEY_INPUT="${GEMINI_API_KEY_INPUT%\'}"
GEMINI_API_KEY_INPUT="${GEMINI_API_KEY_INPUT#\'}"
GEMINI_API_KEY_INPUT="$(printf '%s' "$GEMINI_API_KEY_INPUT" | tr -cd '[:print:]')"

cat > .env <<EOF
GEMINI_API_KEY='${GEMINI_API_KEY_INPUT}'
EOF

chmod 600 .env
echo "Saved GEMINI_API_KEY to .env"
