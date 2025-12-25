# Workflow Reference

Detailed workflow for building datasets from academic papers using subagents.

## Phase 1: Project Setup

### Gather Requirements

From the user, determine:

1. **Goal**: What dataset to create (e.g., "compound toxicity data")
2. **Domain**: Research area and terminology
3. **Data fields**: What to extract (compounds, concentrations, effects, etc.)
4. **Starting point**: Search terms or specific seed papers

### Generate Project Assets

Create these files based on user's description. You can assume the agent will handle this creation natively or by asking the user to confirm the content.

| File | Purpose | Content |
|------|---------|---------|
| `prompt.txt` | PDF extraction instructions | What to extract, output format, edge cases |
| `relevance_prompt.txt` | Paper filtering | Criteria with `{title}` and `{abstract}` placeholders |
| `search_query.txt` | OpenAlex query | Domain-specific search terms |
| `bfs_queue.json` | Queue state | Initially empty: `{"queue": [], "processed": [], "skipped": {}, "failed": {}}` |
| `schema.json` | JSON Schema | Structure of the data to extract |

### Example Prompt Generation

**User says**: "I want to extract cryoprotectant toxicity data from papers"

**Generate prompt.txt**:

```
Extract all cryoprotectant agent (CPA) toxicity measurements from this paper.

For each data point, record:
- compound_name: Name of the CPA (e.g., DMSO, glycerol, ethylene glycol)
- concentration: Numeric value
- concentration_unit: Unit (M, mM, %, v/v, w/v)
- cell_type: Cell or tissue type tested
- viability: Cell viability percentage if reported
- exposure_time: Duration of exposure
- temperature: Temperature during exposure
- source_reference: Table or figure reference

Guidelines:
- Only extract explicitly measured values, not literature citations
- Focus on experimental results sections
- If a range is given, record min and max separately
```

**Generate relevance_prompt.txt**:

```
Given this paper, determine if it likely contains cryoprotectant toxicity data.

Title: {title}
Abstract: {abstract}

Relevant if:
- Describes experiments measuring cell viability with CPAs
- Reports toxicity or cytotoxicity of cryoprotectants
- Contains quantitative data (concentrations, viability %)

NOT relevant if:
- Review article summarizing other papers
- Protocol paper without original measurements
- Unrelated to cryopreservation

Return: {"is_relevant": true/false, "reason": "..."}
```

## Phase 2: Initial Search

Query OpenAlex to seed the queue.

**Mechanism**:

1. Run `python scripts/search_openalex.py "<query>" --output bfs_queue.json`
2. OR use `uv` to run a customized script if you have it installed.
3. OR use a dedicated subagent to search and populate `bfs_queue.json` manually.

**OpenAlex Query**:

```
GET https://api.openalex.org/works?search=cryoprotectant+toxicity&per-page=25&mailto=email
```

Parse response, extract IDs like `W2741809807`, add to `bfs_queue.json` in the `queue` list.

## Phase 3: Process Queue (Loop with Subagents)

Pop paper from `bfs_queue.json` (first item in `queue`).

**Subagent Pipeline**:

### 3a. PDF Download (Subagent: `pdf-downloader`)

**Task**:

```
Download PDF for OpenAlex work ID: W2741809807

1. Fetch metadata: GET https://api.openalex.org/works/W2741809807
2. Try PDF URLs in this order:
   - best_oa_location.pdf_url
   - primary_location.pdf_url
   - locations[].pdf_url
3. Save to: projects/<name>/pdfs/W2741809807.pdf
4. If not found, try bioRxiv/Unpaywall sources if applicable.

Return: {"success": true, "path": "..."} or {"success": false, "reason": "..."}
```

**On failure**: Mark `failed: no_pdf` in `bfs_queue.json`.
**On success**: Proceed to 3b.

### 3b. Relevance Check (Subagent: `relevance-checker`)

**Task**:

```
Check if this paper is relevant.

Input:
- Title: [from OpenAlex metadata]
- Abstract: [reconstructed from abstract_inverted_index]
- Criteria: [contents of relevance_prompt.txt]

Return: {"is_relevant": true/false, "reason": "..."}
```

**If not relevant**: Mark `skipped: <reason>` in `bfs_queue.json`.
**If relevant**: Proceed to 3c.

### 3c. Data Extraction (Subagent: `data-extractor`)

**Task** (Use a highly capable "thinking" model):

```
Read PDF and extract data.

Input:
- PDF path: projects/<name>/pdfs/W2741809807.pdf
- Instructions: [contents of prompt.txt]
- Schema: [contents of schema.json]

Output: Valid JSON abiding by the schema.
```

**Action**: Save result to `projects/<name>/data/W2741809807.json`.

### 3d. Citation Traversal (Subagent: `citation-traverser`)

**Task**:

```
Find related papers to expand the dataset.

Input: OpenAlex ID W2741809807

Actions:
1. Fetch work metadata again (or use cached).
2. Extract `referenced_works` (papers it cites).
3. Search for papers citing this one: GET https://api.openalex.org/works?filter=cites:W2741809807
4. (Optional) Browse `related_works`.

Return: List of new OpenAlex IDs.
```

**Action**:

1. Load `bfs_queue.json`.
2. Filter out IDs that are already in `queue`, `processed`, `skipped`, or `failed`.
3. Append unique new ones to `queue`.
4. Move current ID `W2741809807` to `processed`.
5. Save `bfs_queue.json`.

## Phase 4: Repeat

Loop back to the start of Phase 3 until `queue` is empty or user intervenes.
