#!/usr/bin/env bash
# Downloads the pinned Tailwind CSS standalone CLI binary (4.3.3, per
# references/compatibility-matrix.md's "Frontend — server-rendered (Django
# + HTMX)" section) for the host platform, into ./bin/tailwindcss (this
# script's own directory). Local/CI dev-machine use ONLY -- this block's
# `tests/` suite is fully hermetic and never invokes this script or
# touches the network; see the block README's "Tailwind (standalone CLI)"
# section for the full build command this binary is used with.
#
# Usage (from this block's materialized location, apps/api/):
#   ./bin/download-tailwind.sh
#   ./bin/tailwindcss -i static_src/input.css -o webapp/static/css/output.css --minify
set -euo pipefail

VERSION="v4.3.3"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${SCRIPT_DIR}/tailwindcss"

os="$(uname -s)"
arch="$(uname -m)"

case "${os}" in
  Linux)
    case "${arch}" in
      x86_64) asset="tailwindcss-linux-x64" ;;
      aarch64|arm64) asset="tailwindcss-linux-arm64" ;;
      *) echo "Unsupported Linux architecture: ${arch}" >&2; exit 1 ;;
    esac
    ;;
  Darwin)
    case "${arch}" in
      x86_64) asset="tailwindcss-macos-x64" ;;
      arm64) asset="tailwindcss-macos-arm64" ;;
      *) echo "Unsupported macOS architecture: ${arch}" >&2; exit 1 ;;
    esac
    ;;
  MINGW*|MSYS*|CYGWIN*)
    asset="tailwindcss-windows-x64.exe"
    ;;
  *)
    echo "Unsupported OS: ${os}" >&2
    exit 1
    ;;
esac

url="https://github.com/tailwindlabs/tailwindcss/releases/download/${VERSION}/${asset}"

echo "Downloading Tailwind CSS standalone CLI ${VERSION} (${asset})..." >&2
curl -fsSL "${url}" -o "${DEST}"
chmod +x "${DEST}"
echo "Installed: ${DEST}" >&2
"${DEST}" --help >/dev/null
echo "OK." >&2
