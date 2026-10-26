"""Shared config. Loads .env (expanding ${VAR}) and writes keys back into it."""
import os, re
from pathlib import Path
from dotenv import load_dotenv, dotenv_values

load_dotenv()
for _ in range(3):                                  # python-dotenv expands ${VAR}, not $VAR
    for k in dotenv_values(".env"):
        os.environ[k] = os.path.expandvars(os.environ[k])


def env(key, default=None):
    return os.environ[key] if default is None else os.environ.get(key, default)


def set_env(key, value, quiet=False):
    """Upsert KEY=value in .env, so the next step picks it up."""
    p, line = Path(".env"), f"{key}={value}"
    t = p.read_text()
    t = (re.sub(rf"(?m)^#?\s*{key}=.*$", lambda _: line, t)
         if re.search(rf"(?m)^#?\s*{key}=", t) else t.rstrip() + f"\n{line}\n")
    p.write_text(t)
    os.environ[key] = value
    if not quiet:
        print(f"   {line}")
