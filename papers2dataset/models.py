import base64
import json
from pathlib import Path
from typing import Any

import litellm
from dotenv import load_dotenv
from litellm import APIConnectionError, RateLimitError
from loguru import logger
from pypdf import PdfReader

from papers2dataset.project import load_assets

load_dotenv()
litellm.suppress_debug_info = True
RELEVANCE_MODEL_NAME = "openrouter/allenai/olmo-3.1-32b-think:free"
DATA_EXTRACTOR_MODEL_NAME = "gemini/gemini-3-flash-preview"
# https://openrouter.ai/models?max_price=0
FALLBACK_MODELS = ["gemini/gemini-3-pro-preview", "openrouter/allenai/olmo-3.1-32b-think:free", "gemini/gemini-flash-lite-latest"]


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
            result = json.load(f)
            result["model_used"] = result.get("model_used", "cached")
            return result

    try:
        reader = PdfReader(pdf_path)
        if len(reader.pages) == 0:
            return {"cpa_compositions": [], "error": "pdf no pages", "model_used": "none"}
    except Exception as e:
        return {"cpa_compositions": [], "error": f"invalid_pdf: {str(e)}", "model_used": "none"}

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

    model_used = DATA_EXTRACTOR_MODEL_NAME
    try:
        response = await litellm.acompletion(
            model=DATA_EXTRACTOR_MODEL_NAME,
            messages=messages,
            response_format={
                "type": "json_object",
                "response_schema": cpa_schema,
            },
        )
    except (RateLimitError, APIConnectionError) as e:
        logger.warning(f"Primary model {DATA_EXTRACTOR_MODEL_NAME} failed: {str(e)}")
        # Try fallback models in sequence
        for fallback_model in FALLBACK_MODELS:
            try:
                model_used = fallback_model
                response = await litellm.acompletion(
                    model=fallback_model,
                    messages=messages,
                    response_format={
                        "type": "json_object",
                        "response_schema": cpa_schema,
                    },
                )
                break  # Success, exit the loop
            except (RateLimitError, APIConnectionError) as fallback_error:
                logger.warning(f"Fallback model {fallback_model} failed: {str(fallback_error)}")
                continue  # Try next fallback model
        else:
            # All fallback models failed
            logger.error(f"All models failed for PDF {pdf_path.name}. Last error: {str(e)}")
            return {"cpa_compositions": [], "error": f"All models failed. Last error: {str(e)}", "model_used": "none"}

    content = response.choices[0].message.content
    result = json.loads(content)
    result["model_used"] = model_used

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
    model_used = RELEVANCE_MODEL_NAME
    try:
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
    except (RateLimitError, APIConnectionError) as e:
        logger.warning(f"Primary model {RELEVANCE_MODEL_NAME} failed: {str(e)}")
        # Try fallback models in sequence
        for fallback_model in FALLBACK_MODELS:
            try:
                model_used = fallback_model
                response = await litellm.acompletion(
                    model=fallback_model,
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
                break  # Success, exit the loop
            except (RateLimitError, APIConnectionError) as fallback_error:
                logger.warning(f"Fallback model {fallback_model} failed: {str(fallback_error)}")
                continue  # Try next fallback model
        else:
            # All fallback models failed
            logger.error(f"All models failed for relevance check. Last error: {str(e)}")
            return {"has_cpa_compositions": False, "reason": f"All models failed. Last error: {str(e)}", "model_used": "none"}

    content = response.choices[0].message.content
    result = json.loads(content)
    result["model_used"] = model_used
    return result
