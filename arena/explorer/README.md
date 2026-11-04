# Political Content Explorer

An interactive, dependency-free explorer for the political shortlist of
`lmarena-ai/arena-human-preference-140k`. It shows the **complete, untruncated**
user prompts (and, for the core shortlist, both complete model answers), with
filters, full-text search, CSV export and live visualizations.

## Run it

```bash
python arena/explorer/server.py --host 0.0.0.0 --port 8000
# then open http://localhost:8000/  (Arena serves this as a live preview)
```

Only the Python standard library is needed. The server binds `0.0.0.0` and all
API calls are same-origin relative URLs, so it works behind the preview proxy.

## Data

| File | Rows | Contents |
| --- | ---: | --- |
| `data/prompts_all.jsonl.gz` | 63,635 | **full, untruncated prompt** for every flagged vote ID (strict / probable / broad tiers), all user turns, and metadata |
| `data/conversations.jsonl.gz` | 6,820 | the core political shortlist: full prompt + all user turns + **both full model answers**, verbatim |
| `data/manifest.json` | — | dataset revision, extraction time, counts, sizes, provenance |
| `data/extract.log` | — | runner log |

Core shortlist = all `strict` rows ∪ all rows with a political prompt ∪ the
ranked 1,500-row `shortlist.csv` (see `arena/extract_full_text.py`). 1,276 of
the core prompts are longer than the 420-character excerpt in `shortlist.csv`;
the longest is 110,289 characters. 1,049 core rows are multi-turn.

**Fidelity:** text is copied verbatim from `content[].text` — no truncation,
paraphrase, redaction or regeneration. Every `shortlist.csv` excerpt was
verified to be a prefix of the corresponding full prompt.

**Licensing:** user prompts are CC-BY-4.0; model outputs are governed by the
terms of use of the respective model providers. The full text is included here
for research review of this shortlist; check provider terms before redistributing
the answer text.

## UI features

- **Filters:** data scope, tier, evidence basis (prompt / response / both),
  topic, language, vote outcome, model, code flag, date range, minimum match
  score. Full-text search across prompts, all user turns and both answers
  (`re:` prefix enables a regular expression).
- **Charts (SVG, no external libraries):** tier × evidence-basis stacked bars,
  topic mix, language distribution, monthly volume, vote outcome, top models,
  match-strength histogram. All recompute from the current filter selection.
- **Table:** sortable by match strength / date / prompt length / random, 25 rows
  per page. Click a row to open the detail drawer.
- **Detail drawer:** `Prompt (full)` with every user turn labelled, `Answer A
  (full)`, `Answer B (full)`, and `Metadata` tabs; copy-to-clipboard and exact
  character counts.
- **Export CSV:** downloads all rows matching the current filters with a
  `prompt_full_untruncated` column.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/bootstrap` | manifest, corpus summary, filter options, data counts |
| `GET /api/query?...` | filtered rows + all facet counts for the charts |
| `GET /api/row?id=...` | one row with full text |
| `GET /api/export?...` | CSV of all matching rows with full prompts |

Query parameters: `scope` (`core` / `all`), `q`, `tier`, `basis`, `topic`,
`lang`, `winner`, `model`, `code`, `date_from`, `date_to`, `min_score`, `sort`,
`limit`, `offset`.

## Regenerating the data

`arena/extract_full_text.py` streams the whole dataset once (~2.5 min) and
rebuilds the two `.jsonl.gz` files from the committed scan results. This sandbox
cannot reach `huggingface.co`, so `.github/workflows/extract-full-text.yml` runs
it on a GitHub-hosted runner and commits `arena/explorer/data/` back to the
branch. To re-run, change `arena/RUN_EXTRACT` and push (do **not** use
`[skip ci]`), or use "Run workflow" in the Actions tab.

```bash
python -m pip install -r arena/requirements.txt
python arena/extract_full_text.py --output-dir arena/explorer/data
```
