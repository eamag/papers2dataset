import asyncio
from papers2dataset.openalex_client import fetch_work, fetch_pdf, fetch_cited_works, fetch_citing_works, fetch_related_works
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

        res = await check_paper_relevance(paper)
        if not res['has_cpa_compositions']:
            logger.warning(f"Paper {paper.get('id')} is not relevant because {res.get('reason')}")
            q.mark_skipped(pid, res.get('reason'))
            return

        resp = await extract_cpa_from_pdf(pdf_path, project_dir)
        if resp.get("error"):
            logger.warning(f"Failed to extract CPA from PDF for {paper['id']}")
            q.mark_failed(pid, resp['error'])
            return

        related_task = asyncio.to_thread(fetch_related_works, pid)
        cited_task = asyncio.to_thread(fetch_cited_works, pid)
        citing_task = asyncio.to_thread(fetch_citing_works, pid)
        
        related, cited, citing = await asyncio.gather(related_task, cited_task, citing_task)

        new_ids = [x.get("id", "").split('/')[-1] for x in related + cited + citing]
        q.add_many(new_ids)
        q.mark_processed(pid)
        logger.success(f"Processed {paper['id']}")