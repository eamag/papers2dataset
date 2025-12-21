import base64
import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from litellm import Router
from loguru import logger
import pymupdf

from papers2dataset.project import load_assets

load_dotenv()
# litellm.suppress_debug_info = True
# TODO: move to config
RELEVANCE_MODEL_NAME = "openrouter/allenai/olmo-3.1-32b-think:free"
DATA_EXTRACTOR_MODEL_NAME = "gemini/gemini-3-pro-preview"
PROJECT_GENERATOR_MODEL_NAME = "gemini/gemini-3-pro-preview"
# https://openrouter.ai/models?max_price=0
FALLBACK_MODELS = [
    "openrouter/tngtech/deepseek-r1t2-chimera:free",
    "openrouter/z-ai/glm-4.5-air:free",
    "openrouter/allenai/olmo-3.1-32b-think:free",
    # "gemini/gemini-flash-lite-latest",
    "gemini/gemini-3-flash-preview",
]

model_list = [
    {
        "model_name": "data_extractor",
        "litellm_params": {"model": DATA_EXTRACTOR_MODEL_NAME},
    },
    {
        "model_name": "relevance_checker",
        "litellm_params": {"model": RELEVANCE_MODEL_NAME},
    },
    {
        "model_name": "project_generator",
        "litellm_params": {"model": PROJECT_GENERATOR_MODEL_NAME},
    },
]
for model in FALLBACK_MODELS:
    model_list.append({"model_name": model, "litellm_params": {"model": model}})

# TODO: figure out what's wrong with fallbacks here
router = Router(
    model_list=model_list,
    fallbacks=[
        {"data_extractor": FALLBACK_MODELS},
        {"relevance_checker": FALLBACK_MODELS},
        {"project_generator": FALLBACK_MODELS},
    ],
    num_retries=1,
    cooldown_time=30,
)


async def extract_cpa_from_pdf(
    pdf_path: Path,
    project_dir: Path,
) -> dict[str, Any]:
    schema, prompt, _, _ = load_assets(project_dir)
    data_dir = project_dir / "data"
    data_dir.mkdir(exist_ok=True)
    res_file = data_dir / f"{pdf_path.stem}.json"
    if res_file.exists():
        with open(res_file, "r") as f:
            result = json.load(f)
            result["model_used"] = result.get("model_used", "cached")
            return result

    try:
        doc = pymupdf.open(pdf_path)
        if len(doc) == 0:
            return {"error": "pdf no pages", "model_used": "none"}
        doc.close()
    except Exception as e:
        return {"error": f"invalid_pdf: {str(e)}", "model_used": "none"}

    pdf_bytes = pdf_path.read_bytes()
    encoded_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "file",
                    "file": {
                        "file_data": f"data:application/pdf;base64,{encoded_pdf}",
                    },
                },
            ],
        }
    ]

    logger.debug(f"Extracting data from {pdf_path.name}")
    response = await router.acompletion(
        model="data_extractor",
        messages=messages,
        response_format={
            "type": "json_object",
            "response_schema": schema,
        },
    )

    content = response.choices[0].message.content
    result = json.loads(content)
    result["model_used"] = response.model

    with open(data_dir / f"{pdf_path.stem}.json", "w") as f:
        json.dump(result, f, indent=2)
    return result


async def check_paper_relevance(
    paper: dict[str, Any],
    project_dir: Path,
) -> dict[str, Any]:
    _, _, relevance_prompt, _ = load_assets(project_dir)
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
    prompt = relevance_prompt.format(title=title, abstract=abstract)
    logger.debug(f"Checking relevance of {title}")
    response = await router.acompletion(
        model="relevance_checker",
        messages=[{"role": "user", "content": prompt}],
        response_format={
            "type": "json_object",
            "response_schema": {
                "type": "object",
                "properties": {
                    "is_relevant": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["is_relevant"],
            },
        },
    )

    content = response.choices[0].message.content
    result = json.loads(content)
    result["model_used"] = response.model
    return result


async def generate_project_assets(
    project_description: str,
) -> dict[str, Any]:
    prompt = f"""
You are helping to create a dataset from academic papers. Based on the project description, generate all necessary assets for automated data extraction.

PROJECT DESCRIPTION: {project_description}

Your task is to create:

1. JSON SCHEMA: Design a comprehensive JSON schema for extracting structured data from papers. The schema should:
   - Use JSON Schema draft 7 format
   - Include all relevant data fields for the topic area
   - Have clear, descriptive field names
   - Use appropriate data types (string, number, boolean, array, object)
   - Include detailed descriptions for each field
   - Define required fields that must be present
   - Handle nested objects/arrays where appropriate
   - Be flexible enough to handle variations in how papers present data

2. EXTRACTION PROMPT: Create a detailed prompt that will be given to an LLM along with PDF paper. The prompt should:
   - Clearly explain what data to extract
   - Provide context about the research domain
   - Give specific guidelines for handling missing or ambiguous data
   - Explain any domain-specific terminology
   - Include examples of what good vs bad extractions look like
   - Specify the exact format expected
   - Be thorough enough to ensure consistent, high-quality extractions

3. SEARCH QUERY: Generate an optimal search query for academic databases that will:
   - Find relevant papers for this dataset
   - Use appropriate academic terminology
   - Focuses on breadth to get good coverage, does NOT restrics search by using exact word search operators
   - Include key concepts, methodologies, and domain terms
   - Be suitable for OpenAlex, Semantic Scholar, arXiv, Google Scholar, etc.
   - Consider synonyms and related terms

4. RELEVANCE PROMPT: Create a prompt for a paper relevance filtering function that:
   - Takes paper title and abstract as input
   - Determines if the full paper likely contains extractable data for this dataset
   - Makes sure the model tries to judge relevance by guessing information in the full paper and doesn't focus on abstract only
   - Returns a boolean relevance and reasoning using "is_relevant" and "reason" fields
   - Helps filter papers before full PDF processing
   - Should be conservative but not overly restrictive

5. PROJECT NAME: Generate a short, descriptive project name that:
   - Is lowercase with underscores only
   - Reflects the core topic
   - Is filesystem-safe
   - Is memorable and descriptive

Return a JSON object with exactly these keys:
{{
    "schema": <JSON schema as a string>,
    "prompt": <detailed extraction prompt string>,
    "search_query": <optimal search query string>,
    "relevance_prompt": <paper relevance filtering prompt string>,
    "project_name": <short safe project name string>
}}

Make sure each generated asset is comprehensive, well-structured, and immediately usable for automated dataset creation.
"""

    logger.debug("Generating project assets using router")
    response = await router.acompletion(
        model="project_generator",
        messages=[{"role": "user", "content": prompt}],
        response_format={
            "type": "json_object",
            "response_schema": {
                "type": "object",
                "properties": {
                    "schema": {"type": "string"},
                    "prompt": {"type": "string"},
                    "search_query": {"type": "string"},
                    "relevance_prompt": {"type": "string"},
                    "project_name": {"type": "string"},
                },
                "required": [
                    "schema",
                    "prompt",
                    "search_query",
                    "relevance_prompt",
                    "project_name",
                ],
            },
        },
    )

    content = response.choices[0].message.content
    result = json.loads(content)
    result["model_used"] = response.model

    if isinstance(result.get("schema"), str):
        try:
            result["schema"] = json.loads(result["schema"])
        except json.JSONDecodeError:
            logger.warning("Failed to parse schema string, keeping as string")

    return result
