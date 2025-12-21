import json


def list_project_files(project_dir):
    schema_path = project_dir / "schema.json"
    prompt_path = project_dir / "prompt.txt"
    return schema_path, prompt_path


def load_assets(project_dir):
    schema_path, prompt_path = list_project_files(project_dir)

    with open(schema_path, "r") as f:
        schema = json.load(f)

    with open(prompt_path, "r") as f:
        prompt = f.read().strip()

    return schema, prompt
