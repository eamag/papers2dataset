# AI agents that read papers and create datasets

AlphaFold exists because PDB exists, but most of the time the dataset you need is not there. Some data only exists as text in papers, and it takes too long to manually search and extract one data point at a time. This project helps to automate data extraction from open access papers, using AI agents to walk the citation graph and creating a CSV with data and sources.

## Agent Skill (Claude, Codex, etc.)

This tool can be installed as an Agent Skill, compatible with **Claude Code**, **OpenAI Codex**, and other agents supporting the Agent Skills standard.

### Installation

```bash
curl -sSL https://raw.githubusercontent.com/eamag/papers2dataset/main/install.py | python3
```

- Installs to `~/.claude/skills/papers2dataset` (default)
- Installs to `~/.codex/skills/papers2dataset` (if detected)
- Sets up a dedicated `uv` virtual environment for isolation.

To install to a specific location (e.g. for VS Code or Cursor):

```bash
python3 install.py --target-dir ~/.my-agent/skills
```

### Features

- **Subagent Pattern**: Uses specialized agents for search, extraction, and graph traversal
- **Paper Search**: Finds relevant papers on OpenAlex
- **PDF Extraction**: Downloads and extracts structured data using thinking models
- **Citation Graph**: Recursively finds related papers

## Getting started

- Clone the repo `git clone https://github.com/eamag/papers2dataset.git`
- Install dependencies `cd papers2dataset && uv sync`
- Set up environment variables `cp .env.example .env` and add your API keys to `.env`.
- Create a new project:
  - Using vibe-creator `papers2dataset vibe "I want to create a dataset consisting of links to new datasets in organ cryopreservation that were NOT uploaded to HuggingFace. My goal is to run AI agents on it later to centralize all the data about cryopreservation of organs, so I can help undergraduate students to come up with new projects."`. This will setup everything and you just need to wait. See an example in projects folder.
  - Doing each step at a time. Here you can edit each step, like suggested dataset schema, initial papers, screening criterias, adjustments after initial results etc. See a section below for details
- Create a dataset and upload to HuggingFace with `papers2dataset export --project <project name> --public`

### Step by step guide

- Create a project: `papers2dataset "<what dataset you want to create, your goal and some details>"`. This will create a new project at `projects` folder with a suggested dataset schema, prompt for data extraction and initial papers search query. Review these files and edit them, or check model logs and rerun with an improved initial prompt.
- Search initial papers: `papers2dataset search --project <project name>`. This will query OpenAlex using search_query.txt and will put first pdfs into `<project name>/pdfs` folder. You can also find initial papers manually on OpenAlex and put them in there with OpenAlex id as a file name. For this example I also did <https://platform.edisonscientific.com/trajectories/d6984cba-546c-4b38-a9c3-e9e05864f675> and <https://asta.allen.ai/share/695fd5e2-a114-4238-b457-7957543c6bd2> and found doi from references in OpenAlex.
- Run the extraction: `papers2dataset extract --project <project name>`. You may want to run it several times with different parameters, see `--help`. This will populate `<project name>/data` folder with json files.
- When you got enough data, combine it into a csv and upload to huggingface: `papers2dataset export --project <project name> --public`

## TODO

- [ ] Clean up duplicates, see <https://news.ycombinator.com/item?id=45877576>
- [ ] Go over all failed to download pdfs and add appropriate API calls. Comply with robots.txt (are AI agents robots?)
- [ ] Use <https://github.com/blackadad/paper-scraper> and <https://github.com/allenai/asta-paper-finder> (and better <https://asta.allen.ai/> and <https://platform.edisonscientific.com/> when they start providing references in the api) to screen papers
- [ ] Something better than BFS for scheduling papers, maybe semantic search?
- [ ] Record a terminal GIF
- [ ] Add tests

## Note

This tool is designed to work with Open Access repositories. Users are responsible for ensuring they have the rights to text-mine non-OA content. Programmatically downloading papers is a grey area. Please use this package responsibly, respecting copyright and fair use laws.
