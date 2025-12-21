from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from huggingface_hub import HfApi

load_dotenv()


DATA_DIR = Path(__file__).parent / "data"
OUTPUT_CSV = Path(__file__).parent / "cpas.csv"


def _norm_val(val: Any) -> Any:
    """Keep primitives as-is; serialize nested structures to JSON strings."""
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return val


def _find_list_of_dicts(obj: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    result: list[tuple[str, list[dict[str, Any]]]] = []
    for k, v in obj.items():
        if isinstance(v, list) and all(isinstance(x, dict) for x in v):
            result.append((k, v))
    return result


def _pick_primary_container(data: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Decide which list-of-dicts to iterate over for rows.
    Returns (records, outer_context).
    """
    if isinstance(data, list) and all(isinstance(x, dict) for x in data):
        return data, {}
    if isinstance(data, dict):
        list_fields = _find_list_of_dicts(data)
        if list_fields:
            chosen_key, records = list_fields[0]
            outer_ctx = {k: v for k, v in data.items() if k != chosen_key}
            return records, outer_ctx
    return [], {}


def export_csv() -> None:
    headers: list[str] = ["source"]
    rows: list[dict[str, Any]] = []

    def add_headers_from_row(row: dict[str, Any]) -> None:
        for key in row.keys():
            if key not in headers:
                headers.append(key)

    for path in sorted(DATA_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        primary_records, outer_ctx = _pick_primary_container(data)

        if not primary_records:
            # Treat whole payload as a single record.
            primary_records = [data] if isinstance(data, dict) else []
            outer_ctx = {}

        outer_flat = {f"file_{k}": _norm_val(v) for k, v in outer_ctx.items()}

        for record in primary_records:
            if not isinstance(record, dict):
                continue

            row: dict[str, Any] = {"source": path.stem}
            row.update(outer_flat)
            row.update({f"record_{k}": _norm_val(v) for k, v in record.items()})

            add_headers_from_row(row)
            rows.append(row)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def publish_to_hf(
    repo_id: str,
    *,
    token: str | None = None,
    private: bool = True,
    tags: Iterable[str] | None = None,
) -> None:
    export_csv()

    hf_token = token or os.getenv("HF_TOKEN")
    if not hf_token:
        raise ValueError("Hugging Face token required: pass token= or set HF_TOKEN env var")
    api = HfApi(token=hf_token)
    
    # Get username and construct full repo_id
    user_info = api.whoami()
    username = user_info["name"]
    full_repo_id = f"{username}/{repo_id}"
    
    repo_url = api.create_repo(repo_id=full_repo_id, repo_type="dataset", private=private, exist_ok=True)

    tag_list = list(tags or [])
    base_tags = ["cryopreservation", "tabular", "papers2dataset"]
    for t in base_tags:
        if t not in tag_list:
            tag_list.append(t)

    card = f"""---
language:
- en
tags:
{chr(10).join([f"- {t}" for t in tag_list])}
task_categories:
- tabular-classification
- tabular-regression
- text-retrieval
dataset_info:
  source: local export from papers2dataset
  format: csv
private: {str(private).lower()}
---

# {full_repo_id}

Auto-generated CSV using papers2dataset tool.
"""

    api.upload_file(
        path_or_fileobj=OUTPUT_CSV,
        path_in_repo=OUTPUT_CSV.name,
        repo_id=full_repo_id,
        repo_type="dataset",
    )

    api.upload_file(
        path_or_fileobj=card.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=full_repo_id,
        repo_type="dataset",
    )


if __name__ == "__main__":
    export_csv()
    publish_to_hf("cryoprotective-agents", tags=["cryoprotective-agents", "cryonics", "biology"])
