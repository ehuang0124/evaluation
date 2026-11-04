# Conversation explorer

Run the local, dependency-free viewer:

```bash
python arena/explorer/server.py --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/ or use the Arena preview. Search is case-insensitive;
all space-separated keywords must match. Select a result to see user turns above
model A and model B. Text is displayed as plain text and is not truncated in the
detail view.

## Sources and scope

- Arena: **exactly** the IDs in `arena/results/shortlist.csv` (1,500); full
  prompt and final model responses are joined by ID from the existing
  `arena/explorer/data/conversations.jsonl.gz` extraction. If an ID is missing
  from that extraction it remains visible with text unavailable. Arena's
  extraction preserves all user turns, but only the final response on each side.
- Short answer wins or tie (±5%): the subset of the Arena ranked shortlist
  above where any of these holds (`inclusion_reason`):
  - `short_win` — the human picked the **strictly shorter** final answer (383);
  - `tie` — the vote was a tie, whatever the lengths (230);
  - `near_equal_win` — the longer answer won, but the two answers differ by
    **less than 5%** of the longer one's length, `|a − b| / max(a, b) < 0.05` (34).

  Total **647 of 1,500**. Excluded: `both_bad` votes (153) and wins by an
  answer ≥5% longer (700). Length = characters in each final answer. Search
  `reason:short_win`, `reason:tie` or `reason:near_equal_win` to narrow by
  reason. The list shows the reason, lengths and % difference; the detail marks
  the winner and each answer's length. The same rows plus length columns are
  exported to `arena/results/short_answer_wins_or_tie.csv` by
  `python arena/build_short_answer_wins_or_tie.py`.
- French: exactly the IDs in
  `french-arena/data/political_shortlist_provisional.csv` (8,739). This CSV is
  metadata-only. Without the gated source, search covers metadata and text is
  unavailable. When the separate local enriched CSV is present, it is joined by
  ID and search covers text too; unmatched IDs remain in the list. Restart the
  server after generating it. The original metadata CSV is never overwritten.

To create the French enriched file, see
[`french-arena/analysis/README.md`](../../french-arena/analysis/README.md).
French user and assistant turns are shown separately in source order, including
post-vote turns. Differences between A and B user prompts and other integrity
warnings are shown in the detail. The viewer does not load the screening
pipeline's separate Parquet export.

Verbatim texts can contain sensitive information; model outputs may be subject
to provider terms. The French full-text output is gitignored. Do not distribute
without reviewing the applicable permissions.

## API

`GET /api/query?dataset=arena|short_wins|french&q=keywords&offset=0&limit=20` returns
paginated previews; `GET /api/row?dataset=arena|short_wins|french&id=...` returns a full
record. Unknown datasets and invalid pagination return HTTP 400, unknown IDs
return 404. Python 3.9+ is required.
