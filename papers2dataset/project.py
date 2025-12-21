import json
from pathlib import Path
from typing import Any


def list_project_files(project_dir):
    # TODO: clean up
    schema_path = project_dir / "schema.json"
    prompt_path = project_dir / "prompt.txt"
    relevance_prompt_path = project_dir / "relevance_prompt.txt"
    search_query_path = project_dir / "search_query.txt"
    return schema_path, prompt_path, relevance_prompt_path, search_query_path


def load_assets(project_dir):
    schema_path, prompt_path, relevance_prompt_path, search_query_path = (
        list_project_files(project_dir)
    )
    with open(schema_path, "r") as f:
        schema = json.load(f)
    with open(prompt_path, "r") as f:
        prompt = f.read().strip()
    with open(relevance_prompt_path, "r") as f:
        relevance_prompt = f.read().strip()
    with open(search_query_path, "r") as f:
        search_query = f.read().strip()

    return schema, prompt, relevance_prompt, search_query


def create_project(project_name: str) -> Path:
    projects_dir = Path("projects")
    project_dir = projects_dir / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "data").mkdir(exist_ok=True)
    (project_dir / "pdfs").mkdir(exist_ok=True)
    return project_dir


def save_project_assets(project_dir: Path, assets: dict[str, Any]) -> None:
    with open(project_dir / "schema.json", "w") as f:
        json.dump(assets["schema"], f, indent=2)
    with open(project_dir / "prompt.txt", "w") as f:
        f.write(assets["prompt"])
    with open(project_dir / "search_query.txt", "w") as f:
        f.write(assets["search_query"])
    with open(project_dir / "relevance_prompt.txt", "w") as f:
        f.write(assets["relevance_prompt"])
    metadata = {
        "model_used": assets.get("model_used", "unknown"),
        "description": assets.get("description", ""),
    }
    with open(project_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
