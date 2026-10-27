#!/usr/bin/env bash
# 0. Teardown: ./0_teardown.sh [--yes]
# Removes everything the demo creates, so every later script really does something:
#   services, local folders (1_train/, serving/), local docker images, repo folders.
# Not removed: model versions in the registry, blobs, and Docker Hub tags (see below).
set -euo pipefail
set -a; . ./.env; set +a

NAMES=()
for m in tfy baked; do for i in own tfy-git tfy-local; do
    NAMES+=("$SERVICE_BASE-$m-image-$i")
done; done

if [ "${1:-}" != "--yes" ]; then
    echo "would delete:"
    printf '   service   %s\n' "${NAMES[@]}"
    printf '   local     %s\n' 1_train/ serving/
    printf '   image     %s\n' "$IMAGE_BASE-without-model:1" "$IMAGE_BASE-with-model:1"
    printf '   repo      %s\n' "$GIT_CONTEXT_BASE-without-model/" "$GIT_CONTEXT_BASE-with-model/"
    exit 1
fi

echo "1. services:"
for n in "${NAMES[@]}"; do
    python3 -c "
from truefoundry.deploy import delete_application
try:
    delete_application('$WS:$n'); print('   deleted  $n')
except Exception as e: print(f'   skipped  $n  ({type(e).__name__})')"
done

echo "2. local folders:"
rm -rf 1_train serving && echo "   1_train/ serving/"

echo "3. local docker images:"
for t in "$IMAGE_BASE-without-model:1" "$IMAGE_BASE-with-model:1"; do
    docker rmi -f "$t" >/dev/null 2>&1 && echo "   $t" || echo "   skipped  $t"
done

echo "4. repo folders:"
for d in "$GIT_CONTEXT_BASE-without-model" "$GIT_CONTEXT_BASE-with-model"; do
    git -C "$GIT_LOCAL" rm -rq --ignore-unmatch "$d" && echo "   $d"
done
git -C "$GIT_LOCAL" commit -qm "teardown: drop generated serving folders" 2>/dev/null || true
git -C "$GIT_LOCAL" -c credential.helper='!gh auth git-credential' \
    push -q "$GIT_REPO_URL" "HEAD:$GIT_BRANCH" && echo "   pushed"

echo "5. model versions + blob:"
python3 _cleanup.py

echo "6. Docker Hub:"
if [ -n "${DOCKERHUB_USER:-}" ] && [ -n "${DOCKERHUB_TOKEN:-}" ]; then
    JWT=$(curl -sf -X POST https://hub.docker.com/v2/users/login \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$DOCKERHUB_USER\",\"password\":\"$DOCKERHUB_TOKEN\"}" \
        | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
    for r in "${IMAGE_BASE#*/}-without-model" "${IMAGE_BASE#*/}-with-model"; do
        if curl -sf -X DELETE -H "Authorization: JWT $JWT" \
                "https://hub.docker.com/v2/repositories/$DOCKERHUB_USER/$r/" >/dev/null; then
            echo "   deleted  $DOCKERHUB_USER/$r"
        else
            echo "   skipped  $DOCKERHUB_USER/$r"
        fi
    done
else
    echo "   skipped: set DOCKERHUB_USER and DOCKERHUB_TOKEN in .env"
fi

echo
echo "left behind, not deletable from here:"
echo "   ECR repos in TrueFoundry's AWS account, which is why a rebuild of a"
echo "   previously-used service name hits the immutable-tag error."
