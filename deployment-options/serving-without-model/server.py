from contextlib import asynccontextmanager
from typing import List
from fastapi import FastAPI
import numpy as np
from pydantic import BaseModel, Field
import logging
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s: %(message)s"
)
logger = logging.getLogger("server")


# Define model input schema
class ModelInput(BaseModel):
    input_0: List[List[float]]


def load_model():
    import joblib

    # MODEL_PATH: 2.2 sets it at runtime, 2.1 falls back to the baked-in folder
    # MODEL_FILE: passed in by step 5, so this file works for any joblib sklearn model
    return joblib.load(os.path.join(os.getenv("MODEL_PATH", "model"),
                                    os.getenv("MODEL_FILE", "model.joblib")))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the model
    app.model = load_model()
    yield


app = FastAPI(
    lifespan=lifespan, root_path=os.getenv("TFY_SERVICE_ROOT_PATH"), docs_url="/"
)


# Define prediction endpoints
@app.post("/infer")
def predict(payload: ModelInput):

    args = [np.array(payload.input_0).astype(np.float32)]
    predictions = app.model.predict(*args)
    return {"output_0": predictions.tolist()}


@app.get("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
