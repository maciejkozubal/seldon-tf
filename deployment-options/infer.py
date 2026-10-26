"""Test: inference call against the deployed service. HOST="" hits localhost."""
import requests

from _env import env

HOST = env("HOST", "")
url = f"https://{HOST}/infer" if HOST else "http://localhost:8000/infer"
r = requests.post(url, json={"input_0": [[5.1, 3.5, 1.4, 0.2]]}, timeout=30)
print(r.status_code, r.text[:200])
