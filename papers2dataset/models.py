import base64
import json
from pathlib import Path
from typing import Any
from pypdf import PdfReader
from papers2dataset.project import load_assets
import litellm
from dotenv import load_dotenv

load_dotenv()
litellm.suppress_debug_info = True
RELEVANCE_MODEL_NAME = "openrouter/allenai/olmo-3.1-32b-think:free"


async def extract_cpa_from_pdf(
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

    try:
        reader = PdfReader(pdf_path)
        if len(reader.pages) == 0:
            return {"cpa_compositions": [], "error": "pdf no pages"}
    except Exception as e:
        return {"cpa_compositions": [], "error": f"invalid_pdf: {str(e)}"}

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

    response = await litellm.acompletion(
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


async def check_paper_relevance(
    paper: dict[str, Any],
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

You have the title and abstract of a paper. Based on this, guess if THE FULL PAPER mentions specific Cryoprotectant Agent (CPA) mixtures or compositions and experimental data for them. 
We are looking for papers that define CPAs and extract information about them to create a dataset.
These CPAs can be molecules, proteins, mixtures of both, or any other type of chemical composition and they don't have to be mentioned in abstract, you have to decide if they will be mentioned in other sections of the full paper like methods, results, etc.

Return a JSON object with the following fields:
- has_cpa_compositions: boolean
- reason: string
"""
    response = await litellm.acompletion(
        model=RELEVANCE_MODEL_NAME,
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
