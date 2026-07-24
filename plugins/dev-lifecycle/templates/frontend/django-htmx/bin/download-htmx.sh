#!/usr/bin/env bash
# Downloads the pinned htmx.org 2.0.10 static build (references/
# compatibility-matrix.md's "Frontend — server-rendered (Django + HTMX)"
# section) into webapp/static/htmx/htmx.min.js -- the exact static path
# templates/webapp/base.html's <script src="{% static 'htmx/htmx.min.js' %}">
# expects Django's staticfiles to serve. A single static file, not an npm
# package -- this block has no Node toolchain/package.json at all (see the
# block README's "Tailwind (standalone CLI)" section for the parallel
# no-Node posture on the CSS side). Local/CI dev-machine use ONLY -- this
# block's `tests/` suite is fully hermetic and never invokes this script
# or touches the network.
#
# Usage (from this block's materialized location, apps/api/):
#   ./bin/download-htmx.sh
set -euo pipefail

VERSION="2.0.10"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="${SCRIPT_DIR}/../webapp/static/htmx"
DEST="${DEST_DIR}/htmx.min.js"

url="https://unpkg.com/htmx.org@${VERSION}/dist/htmx.min.js"

mkdir -p "${DEST_DIR}"
echo "Downloading htmx.org ${VERSION} (${url})..." >&2
curl -fsSL "${url}" -o "${DEST}"
echo "Installed: ${DEST}" >&2
