"""4. Deploy: python 5_deploy.py docker|git|local

The arg is the IMAGE axis. The MODEL axis was decided in step 3 and is read off
serving/model/. Only those two lines change; the rest is the same manifest.
"""
import sys
from pathlib import Path
from truefoundry.deploy import (ArtifactsDownload, Build, DockerFileBuild, GitSource,
                                Image, LocalSource, Port, PythonBuild, Resources,
                                Pip, Service, TrueFoundryArtifactSource)

from _env import env

mode = sys.argv[1]
PORT = int(env("PORT"))
FQN = "" if Path("serving/model").is_dir() else env("MODEL_FQN")   # baked by step 3 = 2B
CMD = f"uvicorn server:app --host 0.0.0.0 --port {PORT}"

WS = sys.argv[2] if sys.argv[2:3] else env("WS")

# one service per combination, so the variants never overwrite each other
# model: tfy = from the registry, baked = inside the image
# image: own = you built it (4.1), tfy-git / tfy-local = TrueFoundry built it (4.2 / 4.3)
IMG = "own" if mode == "docker" else f"tfy-{mode}"
NAME = f"{env('SERVICE_BASE')}-{'tfy' if FQN else 'baked'}-image-{IMG}"
HOST = env("HOST_TEMPLATE").replace("{name}", NAME).replace("{ws}", WS.split(":")[-1])

image = {
    # 4.1: you built and pushed it, the platform only points at it
    "docker": lambda: Image(image_uri=env("IMAGE_DIGEST", "") or env("IMAGE")),
    # 4.2: the platform clones the repo and builds there, method = Dockerfile
    "git": lambda: Build(
        build_source=GitSource(repo_url=env("GIT_REPO_URL"), ref=env("GIT_REF"),
                               branch_name=env("GIT_BRANCH")),
        build_spec=DockerFileBuild(dockerfile_path=env("GIT_DOCKERFILE_PATH"),
                                   build_context_path=env("GIT_BUILD_CONTEXT")),
    ),
    # 4.3: the SDK uploads serving/, method = buildpack, no Dockerfile
    "local": lambda: Build(
        build_source=LocalSource(project_root_path="serving", local_build=False),
        build_spec=PythonBuild(
            python_version="3.12", command=CMD,
            python_dependencies=Pip(requirements_path="requirements.txt")),
    ),
}[mode]()

Service(
    name=NAME,
    image=image,
    # 2A only: the platform downloads the model, caches it, exports the path as MODEL_PATH
    artifacts_download=ArtifactsDownload(artifacts=[TrueFoundryArtifactSource(
        artifact_version_fqn=FQN, download_path_env_variable="MODEL_PATH")]) if FQN else None,
    env={"MODEL_FILE": env("MODEL_FILE")},   # server.py reads the filename from here
    ports=[Port(port=PORT, host=HOST)],
    resources=Resources(cpu_request=0.5, cpu_limit=0.5,
                        memory_request=1000, memory_limit=1000),
    replicas=1,
).deploy(workspace_fqn=WS)
print(f"deployed: https://{HOST}")
