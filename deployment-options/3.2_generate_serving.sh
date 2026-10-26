#!/usr/bin/env bash
# Optional shortcut: the platform writes serving/server.py from the registered model's
# schema. Needs a schema, so 2a1 only. It writes files, nothing else - deploy with
# 5_deploy.py as usual.
set -euo pipefail
set -a; . ./.env; set +a
: "${MODEL_FQN:?run 2a1_register_upload.py first}"

rm -rf "$MODEL_NAME"
tfy deploy-init model --name "$MODEL_NAME" --model-version-fqn "$MODEL_FQN" \
    --workspace-fqn "$WS" --model-server fastapi      # triton is the other option
cp "$MODEL_NAME"/{server.py,requirements.txt} serving/
rm -rf "$MODEL_NAME"                                  # the rest is 5_deploy.py's job

python3 - <<'PY'
import pathlib                                        # 2B sets no MODEL_PATH
p = pathlib.Path("serving/server.py"); t = p.read_text()
p.write_text(t.replace('os.environ["MODEL_PATH"]', 'os.getenv("MODEL_PATH", "model")'))
PY
echo "serving/server.py serving/requirements.txt"
