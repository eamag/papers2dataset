import asyncio
import sys
from pathlib import Path
import click
from loguru import logger
from tqdm.asyncio import tqdm

from papers2dataset.models import generate_project_assets
from papers2dataset.project import create_project, save_project_assets, load_assets
from papers2dataset.openalex_client import search_works, fetch_pdf
from papers2dataset.extractor import process_one_paper
from papers2dataset.bfs_queue import BFSQueue
from papers2dataset.export_csv import publish_to_hf


def configure_logging(log_level: str = "DEBUG"):
    """Configure logger with specified level."""
    logger.remove()
    logger.add(sys.stderr, level=log_level)


@click.group()
@click.option(
    "--log-level", default="DEBUG", help="Logging level (DEBUG, INFO, WARNING, ERROR)"
)
@click.pass_context
def cli(ctx, log_level):
    """AI agents that read papers and create datasets."""
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = log_level
    configure_logging(log_level)


async def create_project_async(description: str):
    """Create project from description."""
    logger.info(f"Creating project for: {description}")

    assets = await generate_project_assets(description)

    if "error" in assets:
        logger.error(f"Failed to generate assets: {assets['error']}")
        sys.exit(1)

    project_name = assets["project_name"]
    logger.info(f"Using generated project name: {project_name}")

    project_dir = create_project(project_name)

    assets["description"] = description
    save_project_assets(project_dir, assets)

    logger.success(f"Project created at: {project_dir}")
    return project_dir, assets


async def search_papers_async(project: str, max_papers: int = 20):
    """Search and download papers for project."""
    projects_dir = Path("projects")
    project_dir = projects_dir / project

    if not project_dir.exists():
        logger.error(f"Project {project} not found at {project_dir}")
        sys.exit(1)

    _, _, _, search_query = load_assets(project_dir)
    results = search_works(search_query, max_results=max_papers)

    if not results:
        logger.warning("No papers found")
        return

    papers = results.get("results", [])
    logger.info(f"Found {len(papers)} papers")

    downloaded = 0
    for paper in papers[:max_papers]:
        pdf_path = await fetch_pdf(paper, project_dir)
        if pdf_path is None:
            logger.warning(f"Couldn't download {paper.get('id', '')}")
            continue
        downloaded += 1
    logger.success(f"Downloaded {downloaded}/{max_papers} PDFs to {project_dir}/pdfs/")


async def extract_data_async(
    project: str, max_concurrent: int = 5, num_items: int = 30
):
    """Extract data from papers for project."""
    projects_dir = Path("projects")
    project_dir = projects_dir / project
    q = BFSQueue(project_dir / "bfs_queue.json")
    if len(q.queue) == 0:
        initial_papers = [x.stem for x in (project_dir / "pdfs").glob("*.pdf")]
        q.add_many(initial_papers)
        logger.info(f"Added {len(initial_papers)} to the queue")

    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = []
    for _ in range(num_items):
        pid = q.pop()
        if not pid:
            break
        tasks.append(process_one_paper(pid, q, project_dir, semaphore))
    await tqdm.gather(*tasks)


@cli.command()
@click.argument("description", type=str)
def create(description: str):
    asyncio.run(create_project_async(description))


@cli.command()
@click.option("--project", required=True, help="Project name")
@click.option(
    "--max-concurrent", default=5, help="How many papers to process in parallel"
)
@click.option("--num-items", default=30, help="Number of papers to process")
def extract(project: str, max_concurrent: int, num_items: int):
    asyncio.run(extract_data_async(project, max_concurrent, num_items))


@cli.command()
@click.option("--project", required=True, help="Project name")
@click.option("--public", default=False, help="Publish to HF as a public repo")
def export(project: str, public: bool):
    projects_dir = Path("projects")
    project_dir = projects_dir / project
    data_dir = project_dir / "data"
    # TODO: custom tags and description using LLM
    repo_url = publish_to_hf(data_dir, project, private=not public)
    logger.success(f"Published to HuggingFace at {repo_url}")


@cli.command()
@click.option("--project", required=True, help="Project name")
@click.option("--max-papers", default=20, help="Maximum number of papers to download")
def search(project: str, max_papers: int):
    asyncio.run(search_papers_async(project, max_papers))


@cli.command()
@click.argument("description", type=str)
def vibe(description: str):
    """Create project and run full pipeline automatically."""

    async def run_vibe_async():
        project_dir, assets = await create_project_async(description)
        project_name = assets["project_name"]

        logger.info("Generated files:")
        logger.info(f"  - {project_dir}/schema.json")
        logger.info(f"  - {project_dir}/prompt.txt")
        logger.info(f"  - {project_dir}/search_query.txt")
        logger.info(f"  - {project_dir}/relevance_prompt.txt")
        logger.info(f"  - {project_dir}/metadata.json")

        logger.info("\n=== Step 2: Searching papers ===")
        await search_papers_async(project_name)

        logger.info("\n=== Step 3: Extracting data ===")
        await extract_data_async(project_name)

        logger.info("\n=== Step 4: Exporting to HuggingFace ===")
        projects_dir = Path("projects")
        project_dir = projects_dir / project_name
        data_dir = project_dir / "data"
        repo_url = publish_to_hf(data_dir, project_name)
        logger.success(f"Published to HuggingFace at {repo_url}")


    asyncio.run(run_vibe_async())


if __name__ == "__main__":
    cli()
