#!/usr/bin/env bash
# 4.2. Git repo -> push serving/ to the repo; step 4 points at the commit.
# Usage: ./4.2_git.sh [bake]
set -euo pipefail
set -a; . ./.env; set +a
. ./_bake.sh "${1:-}"

echo "2. pushing serving/ to $GIT_REPO_URL ($GIT_BRANCH):"
DST="$GIT_LOCAL/$GIT_BUILD_CONTEXT"
[ "$(cd serving && pwd -P)" = "$(cd "$DST" 2>/dev/null && pwd -P || echo -)" ] \
    || rsync -a serving/ "$DST/"   # serving/ may already be the repo folder; no --delete
git -C "$GIT_LOCAL" add "$GIT_BUILD_CONTEXT" 2>&1 | sed 's/^/   /'
git -C "$GIT_LOCAL" commit -m "$MODEL_NAME: serving package" 2>&1 | sed 's/^/   /' || true
git -C "$GIT_LOCAL" -c credential.helper='!gh auth git-credential' \
    push "$GIT_REPO_URL" "HEAD:$GIT_BRANCH" 2>&1 | sed 's/^/   /'
REF=$(git -C "$GIT_LOCAL" rev-parse HEAD)

echo
echo "output: the two fields the UI build form needs"
echo "   repo url:      $GIT_REPO_URL"
echo "   build context: ./$GIT_BUILD_CONTEXT"
python3 -c "from _env import set_env; set_env('GIT_REF', '$REF')"   # so GIT_REF never goes stale
