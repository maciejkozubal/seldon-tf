#!/usr/bin/env bash
# 4.2. Git repo -> push serving/ to the repo; step 5 points at the commit.
# The folder says which model option it carries, so both can coexist in the repo:
#   serving-without-model/   model mounted at runtime from MODEL_FQN
#   serving-with-model/      model baked into the build context
# Usage: ./4.2_git.sh [bake]
set -euo pipefail
set -a; . ./.env; set +a
: "${GIT_CONTEXT_BASE:?set GIT_CONTEXT_BASE in .env}"
. ./_bake.sh "${1:-}"

[ "${1:-}" = bake ] && CONTEXT="$GIT_CONTEXT_BASE-with-model" || CONTEXT="$GIT_CONTEXT_BASE-without-model"
DOCKERFILE="$CONTEXT/Dockerfile"

echo "2. pushing serving/ to $GIT_REPO_URL ($GIT_BRANCH) as $CONTEXT:"
rsync -a --delete serving/ "$GIT_LOCAL/$CONTEXT/"   # a copy, never the source folder
git -C "$GIT_LOCAL" add "$CONTEXT" 2>&1 | sed 's/^/   /'
git -C "$GIT_LOCAL" commit -m "$MODEL_NAME: $(basename "$CONTEXT")" 2>&1 | sed 's/^/   /' || true
git -C "$GIT_LOCAL" -c credential.helper='!gh auth git-credential' \
    push "$GIT_REPO_URL" "HEAD:$GIT_BRANCH" 2>&1 | sed 's/^/   /'
REF=$(git -C "$GIT_LOCAL" rev-parse HEAD)

echo
echo "output: the two fields the UI build form needs"
echo "   repo url:      $GIT_REPO_URL"
echo "   build context: ./$CONTEXT"
python3 -c "from _env import set_env; set_env('GIT_BUILD_CONTEXT', '$CONTEXT', quiet=True)"
python3 -c "from _env import set_env; set_env('GIT_DOCKERFILE_PATH', '$DOCKERFILE', quiet=True)"
python3 -c "from _env import set_env; set_env('GIT_REF', '$REF')"
