#!/usr/bin/env bash
# 4.3. Laptop -> nothing to build. Step 4 uploads serving/ and the platform builds it.
# Usage: ./4.3_local.sh [bake]
set -euo pipefail
set -a; . ./.env; set +a
. ./_bake.sh "${1:-}"

echo "2. nothing to build; these files get uploaded:"
find serving -type f | sed 's/^/   /'

echo
echo "output: folder to upload, or ./5_deploy.py local"
echo "   $(cd serving && pwd -P)"
