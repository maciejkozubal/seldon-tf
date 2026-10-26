"""2.2.2. Register a model already in blob storage -> MODEL_FQN. Nothing is re-uploaded.

Same call as 2.2.1 but with a BlobStorageDirectory source. URI must point at a folder
inside the ML repo's artifact root (REPO_ROOT in .env), or the platform answers
"Invalid source URI".
"""
import joblib, numpy as np
from azure.storage.blob import BlobServiceClient
from truefoundry.ml import (BlobStorageDirectory, SklearnFramework, get_client,
                            sklearn_infer_schema)

from _env import env, set_env

FILE = env("MODEL_FILE")
BLOB = f"{env('SRC_PREFIX')}/{FILE}"        # URI in .env must point at the folder holding it

svc = BlobServiceClient.from_connection_string(env("AZURE_STORAGE_CONNECTION_STRING"))
container = svc.get_container_client(env("CONTAINER"))
with open(f"1_train/{FILE}", "rb") as f:
    container.get_blob_client(BLOB).upload_blob(f, overwrite=True)

print("1. uploaded to blob storage:")
for b in container.list_blobs(name_starts_with=env("SRC_PREFIX")):
    print(f"   {b.name}  {b.size} B  {b.last_modified:%Y-%m-%d %H:%M}")

mv = get_client().log_model(
    ml_repo=env("MODEL_REGISTRY"),
    name=env("MODEL_NAME_BLOB"),
    model_file_or_folder=BlobStorageDirectory(uri=env("URI")),   # pointer, not an upload
    framework=SklearnFramework(
        model_filepath=FILE,
        serialization_format="joblib",
        model_schema=sklearn_infer_schema(
            np.load("1_train/sample.npy"), joblib.load(f"1_train/{FILE}"), "predict"),
    ),
)
print("2. registered in TrueFoundry:")
set_env("MODEL_FQN", mv.fqn)
