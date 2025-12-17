import base64
import json
import sys
from pathlib import Path
from typing import Any

import litellm
from dotenv import load_dotenv

load_dotenv()


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


def extract_cpa_from_pdf(
    pdf_path: Path,
    project_dir: Path,
) -> dict[str, Any]:
    cpa_schema, extraction_prompt = load_assets(project_dir)
    data_dir = project_dir / "data"
    data_dir.mkdir(exist_ok=True)
    res_file = data_dir / f"{pdf_path.stem}.json"
    if res_file.exists():
        with open(res_file, "r") as f:
            return json.load(f)
    pdf_bytes = pdf_path.read_bytes()
    encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": extraction_prompt},
                {
                    "type": "file",
                    "file": {
                        "file_data": f"data:application/pdf;base64,{encoded_pdf}",
                    },
                },
            ],
        }
    ]

    response = litellm.completion(
        model="gemini/gemini-3-flash-preview",
        messages=messages,
        response_format={
            "type": "json_object",
            "response_schema": cpa_schema,
        },
    )

    content = response.choices[0].message.content
    result = json.loads(content)

    with open(data_dir / f"{pdf_path.stem}.json", "w") as f:
        json.dump(result, f, indent=2)
    return result


def check_paper_relevance(
    paper: dict[str, Any],
    model: str = "gemini/gemini-flash-lite-latest",
) -> dict[str, Any]:
    title = paper.get("title", "")
    abstract = ""
    if paper.get("abstract_inverted_index"):
        index = paper["abstract_inverted_index"]
        word_list = []
        for word, positions in index.items():
            for pos in positions:
                word_list.append((pos, word))
        word_list.sort()
        abstract = " ".join([w[1] for w in word_list])

    prompt = f"""
    Title: {title}
    Abstract: {abstract}
    
    You have the title and abstract of a paper. Based on this, guess if full paper mentions specific Cryoprotectant Agent (CPA) mixtures or compositions and experimental data for them. 
    We are looking for papers that define chemical mixtures (e.g. DMSO + Glycerol) and test them.
    """
    print(prompt)
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={
            "type": "json_object",
            "response_schema": {
                "type": "object",
                "properties": {
                    "has_cpa_compositions": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["has_cpa_compositions"],
            },
        },
    )

    content = response.choices[0].message.content
    return json.loads(content)
