#!/usr/bin/env bash
# 4.1. Docker image -> you build and push; step 5 only references the digest.
# The tag says which model option it carries, so both can coexist in the registry.
# Usage: ./4.1_docker.sh [bake]
set -euo pipefail
set -a; . ./.env; set +a
: "${IMAGE_BASE:?set IMAGE_BASE in .env}"
. ./_bake.sh "${1:-}"

[ "${1:-}" = bake ] && IMAGE="$IMAGE_BASE-with-model:1" || IMAGE="$IMAGE_BASE-without-model:1"

echo "2. building and pushing $IMAGE:"
docker build --platform linux/amd64 -t "$IMAGE" serving 2>&1 | sed 's/^/   /'   # cluster is x86
docker push "$IMAGE" 2>&1 | sed 's/^/   /'
DIGEST=$(docker image inspect --format '{{index .RepoDigests 0}}' "$IMAGE")

echo
echo "output: image URI for the UI, or ./5_deploy.py docker"
echo "   $IMAGE"
# the digest is pinned in .env for step 5, but the UI wants the tag above
python3 -c "from _env import set_env; set_env('IMAGE', '$IMAGE', quiet=True)"
python3 -c "from _env import set_env; set_env('IMAGE_DIGEST', '$DIGEST', quiet=True)"
