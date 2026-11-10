"""Publish the server as a Hugging Face Docker Space (free hosting with public HTTPS).

    HF_TOKEN=hf_... python deploy/huggingface/push.py restrepo71/impactu-mcp

Creates the Space if needed, uploads the Dockerfile, pyproject.toml and src/ with a README that carries the Space
settings, and sets the variables the server reads. The connector URL is https://<owner>-<name>.hf.space/mcp.
Run it again after every change to redeploy.
"""

import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]

FRONT_MATTER = """---
title: ImpactU MCP
emoji: 🔎
colorFrom: green
colorTo: blue
sdk: docker
app_port: 8000
pinned: false
license: mit
short_description: MCP connector for Claude to query ImpactU (Colombia)
---

"""


def main(repo_id: str) -> None:
    owner, name = repo_id.split("/")
    host = f"{owner}-{name}".lower().replace("_", "-") + ".hf.space"
    api = HfApi()
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        readme = Path(tmp) / "README.md"
        readme.write_text(FRONT_MATTER + (ROOT / "README.md").read_text().replace(
            "https://mcp.impactu.colav.co/mcp", f"https://{host}/mcp", 1))
        api.upload_file(path_or_fileobj=readme, path_in_repo="README.md", repo_id=repo_id, repo_type="space")
    api.upload_folder(folder_path=ROOT, repo_id=repo_id, repo_type="space",
                      allow_patterns=["Dockerfile", "pyproject.toml", "src/**"],
                      ignore_patterns=["**/__pycache__/**"], delete_patterns=["src/**"],
                      commit_message="Deploy from GitHub checkout")

    variables = {"MCP_PUBLIC_HOSTS": host, "IMPACTU_API_BASE": "https://api.dev.impactu.colav.co", "WORKERS": "2"}
    for key, value in variables.items():
        api.add_space_variable(repo_id, key, value)
    print(f"Space: https://huggingface.co/spaces/{repo_id}\nConnector URL: https://{host}/mcp")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "restrepo71/impactu-mcp")
