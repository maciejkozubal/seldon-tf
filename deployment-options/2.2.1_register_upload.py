"""2.2.1. Register, uploaded -> MODEL_FQN. The platform stores the file."""
import joblib, numpy as np
from truefoundry.ml import SklearnFramework, get_client, sklearn_infer_schema

from _env import env, set_env

FILE = env("MODEL_FILE")
model, sample = joblib.load(f"1_train/{FILE}"), np.load("1_train/sample.npy")

mv = get_client().log_model(
    ml_repo=env("MODEL_REGISTRY"),
    name=env("MODEL_NAME_UPLOAD"),
    model_file_or_folder=f"1_train/{FILE}",
    framework=SklearnFramework(
        model_filepath=FILE,
        serialization_format="joblib",
        # the schema is what lets the platform generate a server with no inference code
        model_schema=sklearn_infer_schema(sample, model, "predict"),
    ),
)

print("1. uploaded to TrueFoundry-managed storage:")
print(f"   {mv._model_version.artifact_storage_root}")
print("2. registered in TrueFoundry:")
set_env("MODEL_FQN", mv.fqn)
