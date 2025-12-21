import asyncio
from papers2dataset.openalex_client import (
    fetch_work,
    fetch_pdf,
    fetch_cited_works,
    fetch_citing_works,
    fetch_related_works,
)
from papers2dataset.models import extract_cpa_from_pdf, check_paper_relevance
from papers2dataset.bfs_queue import BFSQueue
from loguru import logger


async def process_one_paper(pid, q: BFSQueue, project_dir, semaphore):
    async with semaphore:
        paper = await asyncio.to_thread(fetch_work, pid)
        if not paper:
            logger.warning(f"Failed to fetch metadata for {pid}")
            q.mark_failed(pid, "metadata_fetch_failed")
            return

        pdf_path = await fetch_pdf(paper, project_dir)
        if pdf_path is None:
            logger.warning(f"Failed to download PDF for {paper['id']}")
            q.mark_failed(pid, "no_pdf")
            return

        res = await check_paper_relevance(paper, project_dir)
        if not res["is_relevant"]:
            reason_skipped = f"Paper {paper.get('id')} is not relevant because {res.get('reason')}, model used: {res.get('model_used')}"
            logger.warning(reason_skipped)
            q.mark_skipped(pid, reason_skipped)
            return

        resp = await extract_cpa_from_pdf(pdf_path, project_dir)
        if resp.get("error"):
            error_text = f"Failed to extract CPA from PDF for {paper['id']}, error: {resp['error']}, model used: {resp.get('model_used')}"
            logger.warning(error_text)
            q.mark_failed(pid, error_text)
            return

        related_task = asyncio.to_thread(fetch_related_works, pid)
        cited_task = asyncio.to_thread(fetch_cited_works, pid)
        citing_task = asyncio.to_thread(fetch_citing_works, pid)

        related, cited, citing = await asyncio.gather(
            related_task, cited_task, citing_task
        )

        new_ids = [x.get("id", "").split("/")[-1] for x in related + cited + citing]
        q.add_many(new_ids)
        q.mark_processed(pid)
        logger.success(f"Processed {paper['id']}")
