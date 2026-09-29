"""Load profile for the deployed iris service.

Locust has no clean way to take custom CLI args, so the runtime arrives as env
vars — loadtest.py sets them from deployed-<runtime>.json. Standalone use:

    TFY_RUNTIME=triton TFY_SVC=iris-sk-triton-svc \\
      locust -f scripts/locustfile.py --headless -u 10 -r 2 -t 30s \\
             --host https://iris-sk-triton-svc-seldon-tf-8000.<domain>
"""

import os

from locust import HttpUser, constant_throughput, task

RUNTIME = os.environ.get("TFY_RUNTIME", "fastapi")
SVC = os.environ.get("TFY_SVC", "iris-sk-fastapi-svc")

ROW = [5.1, 3.5, 1.4, 0.2]

if RUNTIME == "fastapi":
    PATH = "/infer"
    PAYLOAD = {"input_0": [ROW]}
elif RUNTIME == "mlserver":
    # MLServer wants flat row-major data and names the input after the method.
    PATH = f"/v2/models/{SVC}/infer"
    PAYLOAD = {"inputs": [{"name": "predict", "shape": [1, 4],
                           "datatype": "FP32", "data": ROW}]}
else:
    PATH = f"/v2/models/{SVC}/infer"
    PAYLOAD = {"inputs": [{"name": "input_0", "shape": [1, 4],
                           "datatype": "FP32", "data": [ROW]}]}


class IrisUser(HttpUser):
    # One request per user per second, so RPS is a dial (users) rather than a
    # by-product of latency — which is what you want when comparing servers.
    wait_time = constant_throughput(1)

    @task
    def predict(self):
        self.client.post(PATH, json=PAYLOAD, name=PATH)
