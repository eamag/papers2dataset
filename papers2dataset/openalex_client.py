import json
import os
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin
import httpx
from loguru import logger
from curl_cffi.requests import AsyncSession

BASE_URL = "https://api.openalex.org"
_last_request_time = 0
_min_request_interval = 0.1  # 10 req/sec


def _get_email() -> str:
    """Get email for polite pool from environment."""
    email = os.environ.get("OPENALEX_EMAIL", "")
    if not email:
        logger.debug("Warning: OPENALEX_EMAIL not set. Rate limited to 1 req/sec.")
        global _min_request_interval
        _min_request_interval = 1.0
    return email


def _rate_limit():
    """Enforce rate limiting between requests."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _min_request_interval:
        time.sleep(_min_request_interval - elapsed)
    _last_request_time = time.time()


def _make_request(
    url: str, params: Optional[dict] = None, max_retries: int = 5
) -> Optional[dict]:
    """Make a request with rate limiting and exponential backoff."""
    _rate_limit()

    email = _get_email()
    if params is None:
        params = {}
    if email:
        params["mailto"] = email

    for attempt in range(max_retries):
        try:
            response = httpx.get(
                url, params=params, timeout=30.0, follow_redirects=True
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            elif response.status_code == 429:
                # Rate limited - back off
                wait_time = 2**attempt
                logger.debug(f"Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
            elif response.status_code >= 500:
                # Server error - retry with backoff
                wait_time = 2**attempt
                logger.debug(
                    f"Server error {response.status_code}, waiting {wait_time}s..."
                )
                time.sleep(wait_time)
            else:
                logger.debug(
                    f"Unexpected status {response.status_code}: {response.text[:200]}"
                )
                return None

        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                logger.debug(f"Timeout, waiting {wait_time}s...")
                time.sleep(wait_time)
        except httpx.HTTPError as e:
            logger.debug(f"Request error: {e}")
            return None

    logger.debug(f"Failed after {max_retries} retries")
    return None


def fetch_work(identifier: str, save: bool = True) -> Optional[dict]:
    if identifier.startswith("W"):
        url = f"{BASE_URL}/works/{identifier}"
        cache_key = identifier
    elif identifier.startswith("https://openalex.org/"):
        # Full OpenAlex URL
        openalex_id = identifier.split("/")[-1]
        url = f"{BASE_URL}/works/{openalex_id}"
        cache_key = openalex_id
    elif "doi.org" in identifier:
        # DOI URL
        url = f"{BASE_URL}/works/{identifier}"
        cache_key = identifier.replace("https://doi.org/", "").replace("/", "_")
    else:
        # Bare DOI
        url = f"{BASE_URL}/works/https://doi.org/{identifier}"
        cache_key = identifier.replace("/", "_")
    return _make_request(url)


def fetch_cited_works(openalex_id: str, max_results: int = 200) -> list[dict]:
    """
    Fetch works cited BY this paper (its references).

    Uses the referenced_works field from the work metadata.

    Args:
        openalex_id: OpenAlex ID (e.g., W1234567890)
        max_results: Maximum number of references to fetch details for

    Returns:
        List of work metadata dicts
    """
    # First get the work to find its references
    work = fetch_work(openalex_id, save=True)
    if not work:
        return []

    referenced_ids = work.get("referenced_works", [])
    if not referenced_ids:
        return []

    # Limit to max_results
    referenced_ids = referenced_ids[:max_results]

    # Batch fetch using pipe operator (up to 50 per request)
    results = []
    for i in range(0, len(referenced_ids), 50):
        batch = referenced_ids[i : i + 50]
        # Extract just the IDs (they come as full URLs)
        batch_ids = [url.split("/")[-1] if "/" in url else url for url in batch]

        filter_value = "|".join(batch_ids)
        url = f"{BASE_URL}/works"
        params = {"filter": f"openalex_id:{filter_value}", "per-page": 50}

        data = _make_request(url, params)
        if data and "results" in data:
            results.extend(data["results"])

    return results


def fetch_citing_works(openalex_id: str, max_results: int = 200) -> list[dict]:
    """
    Fetch works that CITE this paper.

    Args:
        openalex_id: OpenAlex ID (e.g., W1234567890)
        max_results: Maximum number of citing works to fetch

    Returns:
        List of work metadata dicts
    """
    # Use filter to find works citing this one
    url = f"{BASE_URL}/works"
    params = {
        "filter": f"cites:{openalex_id}",
        "per-page": min(max_results, 200),
        "sort": "cited_by_count:desc",  # Get most cited first
    }

    data = _make_request(url, params)
    if data and "results" in data:
        return data["results"]

    return []


def fetch_related_works(openalex_id: str, max_results: int = 50) -> list[dict]:
    """
    Fetch works related to this paper.

    Uses the related_works field from the work metadata.

    Args:
        openalex_id: OpenAlex ID
        max_results: Maximum number of related works to fetch

    Returns:
        List of work metadata dicts
    """
    # First get the work to find its related works
    work = fetch_work(openalex_id, save=True)
    if not work:
        return []

    related_ids = work.get("related_works", [])
    if not related_ids:
        return []

    # Limit to max_results
    related_ids = related_ids[:max_results]

    # Batch fetch
    results = []
    for i in range(0, len(related_ids), 50):
        batch = related_ids[i : i + 50]
        batch_ids = [url.split("/")[-1] if "/" in url else url for url in batch]

        filter_value = "|".join(batch_ids)
        url = f"{BASE_URL}/works"
        params = {"filter": f"openalex_id:{filter_value}", "per-page": 50}

        data = _make_request(url, params)
        if data and "results" in data:
            results.extend(data["results"])

    return results


def search_works(query: str, max_results: int = 25) -> list[dict]:
    url = f"{BASE_URL}/works"
    params = {
        "search": query,
        "per-page": min(max_results, 200),
    }

    return _make_request(url, params)


async def _try_download_pdf(url: str, pdf_path: Path) -> bool:
    # Base headers - Referer will be updated based on URL domain
    base_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    # Set appropriate Referer based on URL domain
    if "ncbi.nlm.nih.gov" in url or "pmc.ncbi.nlm.nih.gov" in url:
        base_headers["Referer"] = "https://www.ncbi.nlm.nih.gov/"
    else:
        base_headers["Referer"] = "https://openalex.org/"

    _rate_limit()

    try:
        async with AsyncSession() as session:
            # For PMC URLs, first visit the article page to establish session/cookies
            # This helps with PDF downloads that require session state
            if "pmc/articles" in url:
                # Extract article ID and visit the landing page first
                match = re.search(r'/pmc/articles/(PMC\d+)', url)
                if match:
                    pmc_id = match.group(1)
                    landing_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"
                    try:
                        # Visit landing page to establish session (cookies preserved in session)
                        await session.get(
                            landing_url,
                            headers=base_headers,
                            timeout=30,
                            impersonate="chrome110",
                            allow_redirects=True,
                        )
                        logger.debug(f"Established session via landing page: {landing_url}")
                    except Exception as e:
                        logger.debug(f"Could not visit landing page, continuing anyway: {e}")
            
            # Use allow_redirects=True to let curl_cffi handle redirects and preserve cookies
            # This is important for PMC URLs that require session state
            response = await session.get(
                url,
                headers=base_headers,
                timeout=30,
                impersonate="chrome110",
                allow_redirects=True,  # Let curl_cffi handle redirects and cookies
                stream=True,
            )
            
            # Check the final URL after redirects for debugging
            final_url = getattr(response, "url", url)
            if final_url != url:
                logger.debug(f"Resolved redirect: {url} -> {final_url}")
            
            if response.status_code == 200:
                # Download the file - don't check Content-Type as redirects can be misleading
                with open(pdf_path, "wb") as f:
                    async for chunk in response.aiter_content(chunk_size=8192):
                        if not chunk:
                            continue
                        f.write(chunk)

                # Validate PDF magic bytes (the definitive check)
                with open(pdf_path, "rb") as f:
                    first_bytes = f.read(4)
                    if first_bytes != b"%PDF":
                        # Log first few bytes for debugging
                        f.seek(0)
                        preview = f.read(100).decode("utf-8", errors="ignore")
                        logger.debug(
                            f"Downloaded file is not a valid PDF (magic bytes: {first_bytes!r}, preview: {preview[:50]}) for {final_url}"
                        )
                        pdf_path.unlink()  # Delete invalid file
                        return False

                # Log Content-Type for debugging, but don't reject based on it
                content_type = response.headers.get("content-type", "").lower()
                if content_type and "application/pdf" not in content_type:
                    logger.debug(
                        f"Note: URL returned Content-Type {content_type} but file is valid PDF (magic bytes check passed) for {final_url}"
                    )

                return True
            else:
                logger.debug(
                    f"Failed to download PDF: {final_url}, status code: {response.status_code}"
                )
                return False

    except Exception as e:
        logger.debug(f"Error downloading PDF: {e} {url}")
        # Clean up partial file if it exists
        if pdf_path.exists():
            pdf_path.unlink()
        pass

    return False


def _get_biorxiv_pdf_url(doi: str) -> Optional[str]:
    if not doi.startswith("10.1101/"):
        return None
    url = f"https://api.biorxiv.org/details/biorxiv/{doi}"
    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        if response.status_code == 200:
            data = response.json()
            if data.get("collection") and len(data["collection"]) > 0:
                latest = data["collection"][-1]
                biorxiv_doi = latest.get("doi", doi)
                return f"https://www.biorxiv.org/content/{biorxiv_doi}.full.pdf"
        else:
            logger.debug(
                f"bioRxiv API returned status code {response.status_code} for {doi}"
            )
    except Exception as e:
        logger.debug(f"Error getting bioRxiv PDF URL: {e} {doi}")
    return None


def _get_pmc_pdf_url(pmcid: str) -> Optional[str]:
    if not pmcid:
        return None
    pmcid_clean = pmcid.replace("PMC", "") if pmcid.startswith("PMC") else pmcid
    url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMC{pmcid_clean}"
    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        if response.status_code == 200:
            import re

            match = re.search(r'href="(https://[^"]+\.pdf)"', response.text)
            if match:
                return match.group(1)
            match = re.search(r'href="(ftp://[^"]+\.pdf)"', response.text)
            if match:
                ftp_url = match.group(1)
                return ftp_url.replace("ftp://", "https://")
        else:
            logger.debug(
                f"PMC API returned status code {response.status_code} for {pmcid}"
            )
    except Exception as e:
        logger.debug(f"Error getting PMC PDF URL: {e} {pmcid}")
    return None


def _get_unpaywall_pdf_url(doi: str) -> Optional[str]:
    email = os.environ.get("OPENALEX_EMAIL", "user@example.com")
    url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        if response.status_code == 200:
            data = response.json()
            best = data.get("best_oa_location", {})
            if best and best.get("url_for_pdf"):
                return best["url_for_pdf"]
            for loc in data.get("oa_locations", []):
                if loc.get("url_for_pdf"):
                    return loc["url_for_pdf"]
        else:
            logger.debug(
                f"Unpaywall API returned status code {response.status_code} for {doi}"
            )
    except Exception as e:
        logger.debug(f"Error getting Unpaywall PDF URL: {e} {doi}")
    return None


async def fetch_pdf(work: dict, project_dir: Path) -> Optional[Path]:
    openalex_id = (
        work.get("id", "").split("/")[-1]
        if "/" in work.get("id", "")
        else work.get("id", "")
    )
    doi = work.get("doi", "")
    doi_bare = doi.split("doi.org/")[-1] if doi and "doi.org/" in doi else doi

    filename = f"{openalex_id or doi_bare.replace('/', '_')}.pdf"
    pdf_dir = project_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / filename

    if pdf_path.exists():
        return pdf_path

    pdf_urls = []
    pmcid = None

    primary = work.get("primary_location", {})
    if primary and primary.get("pdf_url"):
        pdf_urls.append(primary["pdf_url"])

    best_oa = work.get("best_oa_location", {})
    if best_oa and best_oa.get("pdf_url"):
        pdf_urls.append(best_oa["pdf_url"])

    for loc in work.get("locations", []):
        if loc.get("pdf_url"):
            pdf_urls.append(loc["pdf_url"])
        landing = loc.get("landing_page_url") or ""
        if "pmc/articles" in landing:
            pmc_id = landing.split("/")[-1]
            pdf_urls.append(
                f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"
            )
            if not pmcid:
                pmcid = pmc_id

    pdf_urls = list(dict.fromkeys(pdf_urls))
    logger.debug(f"found pdf urls {pdf_urls}")
    for url in pdf_urls:
        if await _try_download_pdf(url, pdf_path):
            logger.debug(f"Downloaded: {pdf_path}")
            return pdf_path
        else:
            logger.debug(f"Downloading {url} failed")

    if doi_bare and doi_bare.startswith("10.1101/"):
        biorxiv_url = _get_biorxiv_pdf_url(doi_bare)
        if biorxiv_url:
            if await _try_download_pdf(biorxiv_url, pdf_path):
                logger.debug(f"Downloaded via bioRxiv API: {pdf_path}")
                return pdf_path
            else:
                logger.debug(f"Downloading {biorxiv_url} failed")

    if pmcid:
        pmc_url = _get_pmc_pdf_url(pmcid)
        if pmc_url:
            if await _try_download_pdf(pmc_url, pdf_path):
                logger.debug(f"Downloaded via PMC OA API: {pdf_path}")
                return pdf_path
            else:
                logger.debug(f"Downloading {pmc_url} failed")

    if doi_bare:
        unpaywall_url = _get_unpaywall_pdf_url(doi_bare)
        if unpaywall_url:
            if await _try_download_pdf(unpaywall_url, pdf_path):
                logger.debug(f"Downloaded via Unpaywall: {pdf_path}")
                return pdf_path
            else:
                logger.debug(f"Downloading {unpaywall_url} failed")

    logger.debug(f"Could not download PDF for {openalex_id}")
    return None
