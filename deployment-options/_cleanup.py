"""Called by 0_teardown.sh: delete the demo's model versions and its blob."""
from azure.storage.blob import BlobServiceClient
from truefoundry.ml import get_client

from _env import env

c = get_client()
for name in (env("MODEL_NAME_UPLOAD"), env("MODEL_NAME_BLOB")):
    n = 0
    for mv in c.list_model_versions(ml_repo=env("MODEL_REGISTRY"), name=name):
        mv.delete()
        n += 1
    print(f"   {name}: {n} version(s)")

cc = BlobServiceClient.from_connection_string(
    env("AZURE_STORAGE_CONNECTION_STRING")).get_container_client(env("CONTAINER"))
for b in list(cc.list_blobs(name_starts_with=env("SRC_PREFIX"))):
    cc.delete_blob(b.name)
    print(f"   blob {b.name}")
