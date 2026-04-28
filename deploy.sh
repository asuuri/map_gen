#!/usr/bin/env bash
# Deploy dist/ to a web server via rsync.
# Configure DEST before running.
set -euo pipefail

DEST="user@example.com:/var/www/maps/"   # ← edit this

python generate_index.py "$@"

rsync -avz --delete dist/ "$DEST"
