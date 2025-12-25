#!/usr/bin/env python3
"""Download PDF for an OpenAlex work.

Usage:
    python download_pdf.py W2741809807 --output pdfs/
    python download_pdf.py "https://doi.org/10.1234/example" --output pdfs/
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Install with: pip install httpx")
    sys.exit(1)


BASE_URL = "https://api.openalex.org"
_last_request = 0


def _rate_limit():
    global _last_request
    elapsed = time.time() - _last_request
    if elapsed < 0.2:
        time.sleep(0.2 - elapsed)
    _last_request = time.time()


def fetch_work(identifier: str, email: Optional[str] = None) -> Optional[dict]:
    """Fetch work metadata from OpenAlex."""
    _rate_limit()

    if identifier.startswith("W"):
        url = f"{BASE_URL}/works/{identifier}"
    elif "doi.org" in identifier:
        url = f"{BASE_URL}/works/{identifier}"
    else:
        url = f"{BASE_URL}/works/https://doi.org/{identifier}"

    params = {}
    if email:
        params["mailto"] = email

    response = httpx.get(url, params=params, timeout=30.0, follow_redirects=True)

    if response.status_code == 200:
        return response.json()
    return None


def try_download(url: str, output_path: Path) -> bool:
    """Attempt to download a PDF from URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/pdf,*/*",
    }

    try:
        _rate_limit()
        response = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)

        if response.status_code != 200:
            return False

        # Verify it's a PDF
        content = response.content
        if not content.startswith(b"%PDF"):
            return False

        output_path.write_bytes(content)
        return True

    except Exception as e:
        print(f"  Error downloading {url}: {e}", file=sys.stderr)
        return False


def get_biorxiv_pdf_url(doi: str) -> Optional[str]:
    """Get PDF URL via bioRxiv API."""
    if not doi.startswith("10.1101/"):
        return None

    url = f"https://api.biorxiv.org/details/biorxiv/{doi}"
    try:
        response = httpx.get(url, timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            if data.get("collection"):
                latest = data["collection"][-1]
                return (
                    f"https://www.biorxiv.org/content/{latest.get('doi', doi)}.full.pdf"
                )
    except Exception:
        pass
    return None


def get_unpaywall_pdf_url(doi: str, email: str) -> Optional[str]:
    """Get PDF URL via Unpaywall API."""
    url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
    try:
        response = httpx.get(url, timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            best = data.get("best_oa_location", {})
            if best.get("url_for_pdf"):
                return best["url_for_pdf"]
            for loc in data.get("oa_locations", []):
                if loc.get("url_for_pdf"):
                    return loc["url_for_pdf"]
    except Exception:
        pass
    return None


def download_pdf(
    identifier: str,
    output_dir: Path,
    email: Optional[str] = None,
) -> Optional[Path]:
    """Download PDF for an OpenAlex work."""
    email = email or os.environ.get("OPENALEX_EMAIL", "user@example.com")

    print(f"Fetching metadata for {identifier}...")
    work = fetch_work(identifier, email)

    if not work:
        print(f"Error: Could not find work {identifier}", file=sys.stderr)
        return None

    openalex_id = work.get("id", "").split("/")[-1]
    doi = work.get("doi", "")
    doi_bare = doi.split("doi.org/")[-1] if "doi.org/" in doi else doi

    filename = (
        f"{openalex_id}.pdf" if openalex_id else f"{doi_bare.replace('/', '_')}.pdf"
    )
    output_path = output_dir / filename

    if output_path.exists():
        print(f"Already exists: {output_path}")
        return output_path

    # Collect PDF URLs to try
    pdf_urls = []

    primary = work.get("primary_location") or {}
    if primary.get("pdf_url"):
        pdf_urls.append(primary["pdf_url"])

    best_oa = work.get("best_oa_location") or {}
    if best_oa.get("pdf_url"):
        pdf_urls.append(best_oa["pdf_url"])

    for loc in work.get("locations", []):
        if loc.get("pdf_url"):
            pdf_urls.append(loc["pdf_url"])

    # Deduplicate
    pdf_urls = list(dict.fromkeys(pdf_urls))

    print(f"Found {len(pdf_urls)} potential PDF URLs")

    for url in pdf_urls:
        print(f"  Trying: {url[:80]}...")
        if try_download(url, output_path):
            print(f"Success! Downloaded to {output_path}")
            return output_path

    # Try bioRxiv API
    if doi_bare and doi_bare.startswith("10.1101/"):
        print("  Trying bioRxiv API...")
        biorxiv_url = get_biorxiv_pdf_url(doi_bare)
        if biorxiv_url and try_download(biorxiv_url, output_path):
            print(f"Success! Downloaded to {output_path}")
            return output_path

    # Try Unpaywall
    if doi_bare:
        print("  Trying Unpaywall...")
        unpaywall_url = get_unpaywall_pdf_url(doi_bare, email)
        if unpaywall_url and try_download(unpaywall_url, output_path):
            print(f"Success! Downloaded to {output_path}")
            return output_path

    print(f"Failed: Could not download PDF for {identifier}", file=sys.stderr)
    return None


def main():
    parser = argparse.ArgumentParser(description="Download PDF for an OpenAlex work")
    parser.add_argument("identifier", help="OpenAlex ID (W...) or DOI")
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("."), help="Output directory"
    )
    parser.add_argument("--email", "-e", help="Email for API requests")

    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    result = download_pdf(args.identifier, args.output, args.email)

    if result:
        print(f"\nDownloaded: {result}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
