"""3.2. Serving package, TrueFoundry-generated. Surface: SDK.

Same codegen as 3.2_generate_serving.sh, one layer down: `tfy deploy-init model` is a
thin wrapper over this call, which POSTs to
/api/2.0/mlflow/mlfoundry-artifacts/model-versions/export-deployment-files-by-fqn
and unzips the reply. The method is private, so it can break on an SDK upgrade.
"""
import pathlib, shutil, tempfile

from truefoundry.ml import get_client
from truefoundry.ml._autogen.client import ModelServer

from _env import env

with tempfile.TemporaryDirectory() as tmp:
    out = get_client()._initialize_model_server(
        name=env("MODEL_NAME"),
        model_version_fqn=env("MODEL_FQN"),
        workspace_fqn=env("WS"),
        model_server=ModelServer.FASTAPI,      # or ModelServer.TRITON
        output_dir=tmp,
    )
    print("1. generated:")
    for f in sorted(pathlib.Path(out).iterdir()):
        print(f"   {f.name}")
    for f in ("server.py", "requirements.txt"):  # the rest is steps 4 and 5
        shutil.copy(pathlib.Path(out) / f, f"serving/{f}")

p = pathlib.Path("serving/server.py")           # 2.1 (baked) sets no MODEL_PATH
p.write_text(p.read_text().replace('os.environ["MODEL_PATH"]',
                                   'os.getenv("MODEL_PATH", "model")'))
print("2. copied into serving/:")
print("   serving/server.py")
print("   serving/requirements.txt")
