#!/usr/bin/env python3
"""Search OpenAlex for papers and populate a BFS queue.

Usage:
    python search_openalex.py "cryoprotectant toxicity" --output bfs_queue.json --max-results 25
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Install with: pip install httpx")
    print(
        "Or use uv: curl -LsSf https://astral.sh/uv/install.sh | sh && uv pip install httpx"
    )
    sys.exit(1)


BASE_URL = "https://api.openalex.org"
_last_request = 0


def _rate_limit(has_email: bool):
    global _last_request
    min_interval = 0.1 if has_email else 1.0
    elapsed = time.time() - _last_request
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_request = time.time()


def search_works(
    query: str, max_results: int = 25, email: Optional[str] = None
) -> list[dict]:
    """Search OpenAlex for works matching the query."""
    email = email or os.environ.get("OPENALEX_EMAIL")
    _rate_limit(bool(email))

    params = {"search": query, "per-page": min(max_results, 200)}
    if email:
        params["mailto"] = email

    url = f"{BASE_URL}/works?" + "&".join(f"{k}={v}" for k, v in params.items())
    response = httpx.get(url, timeout=30.0, follow_redirects=True)

    if response.status_code != 200:
        print(f"Error: API returned status {response.status_code}", file=sys.stderr)
        return []

    return response.json().get("results", [])


def load_queue(path: Path) -> dict:
    """Load existing queue or create empty one."""
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {"queue": [], "processed": [], "skipped": {}, "failed": {}}


def save_queue(path: Path, data: dict):
    """Save queue to file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Search OpenAlex and populate BFS queue"
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("bfs_queue.json"),
        help="Queue file path",
    )
    parser.add_argument(
        "--max-results", "-n", type=int, default=25, help="Max results (default: 25)"
    )
    parser.add_argument("--email", "-e", help="Email for polite pool (10 req/sec)")

    args = parser.parse_args()

    print(f"Searching OpenAlex for: {args.query}")
    results = search_works(args.query, args.max_results, args.email)

    if not results:
        print("No results found.")
        return

    # Extract OpenAlex IDs
    paper_ids = []
    for work in results:
        oa_id = work.get("id", "").split("/")[-1]
        if oa_id.startswith("W"):
            paper_ids.append(oa_id)

    print(f"Found {len(paper_ids)} papers")

    # Load existing queue and add new IDs
    queue_data = load_queue(args.output)
    existing = (
        set(queue_data["queue"])
        | set(queue_data["processed"])
        | set(queue_data["skipped"].keys())
        | set(queue_data["failed"].keys())
    )

    added = 0
    for pid in paper_ids:
        if pid not in existing:
            queue_data["queue"].append(pid)
            existing.add(pid)
            added += 1

    save_queue(args.output, queue_data)
    print(f"Added {added} new papers to queue: {args.output}")
    print(f"Queue now has {len(queue_data['queue'])} pending papers")


if __name__ == "__main__":
    main()
