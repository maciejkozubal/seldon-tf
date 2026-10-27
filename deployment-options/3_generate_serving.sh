#!/usr/bin/env bash
# 3. Serving package. Surface: CLI.
# tfy deploy-init writes server.py + requirements.txt from the registered model's schema,
# so no inference code is hand-written. It does NOT write a Dockerfile, so we add a
# generic one: the customer can edit it or drop in their own.
# Needs a model version with a schema (2.2.x). Files only; image is 4, deploy is 5.
set -euo pipefail
set -a; . ./.env; set +a
: "${MODEL_FQN:?run 2.2.1_register_upload.py first}"

rm -rf "$MODEL_NAME" serving
tfy deploy-init model --name "$MODEL_NAME" --model-version-fqn "$MODEL_FQN" \
    --workspace-fqn "$WS" --model-server fastapi      # triton is the other option
mkdir -p serving
cp "$MODEL_NAME"/{server.py,requirements.txt} serving/
rm -rf "$MODEL_NAME"                                  # deploy.py / infer.py: step 5's job

cat > serving/Dockerfile <<DOCKER
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "$PORT"]
DOCKER

# serving/ is inside a git repo, so the packager would honour .gitignore and drop
# serving/model/. A .tfyignore takes precedence and keeps the baked model in the tarball.
printf '__pycache__/\n' > serving/.tfyignore

python3 - <<'PY'
import pathlib                                      # 2.1 (baked) sets no MODEL_PATH
p = pathlib.Path("serving/server.py"); t = p.read_text()
p.write_text(t.replace('os.environ["MODEL_PATH"]', 'os.getenv("MODEL_PATH", "model")'))
PY

echo "1. generated into serving/:"
find serving -type f | sed 's/^/   /'
