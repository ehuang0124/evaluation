# evaluation

Dataset analyses and reproducible screening pipelines.

## `arena/` — lmarena-ai/arena-human-preference-140k (English + multilingual)

Initial political-content screen of the 135,634-vote Arena human-preference
dataset (elections, voting, public policy, immigration, publicly elected or
politically active figures, parties/ideology, geopolitics). Full findings,
method, caveats and reproduction steps: [`arena/README.md`](arena/README.md).
Headline: 2,235 votes (1.65%) have a strictly political user prompt;
8,912 of 271,129 judged answers (3.29%) are on political topics at that tier.
The `/arena` folder also holds the script, the full shortlisted vote IDs, and
**full untruncated prompts** (63,635 flagged IDs; 6,820 with both complete model
answers). Explore them interactively with filters, full-text search and charts:

```bash
python arena/explorer/server.py --host 0.0.0.0 --port 8000
```

## `french-arena/` — Compar:IA (French) political-content analysis

- Summary and dataset notes: `french-arena/README.md`
- Detailed report: `french-arena/REPORT.md`
- Provisional shortlist: `french-arena/data/political_shortlist_provisional.parquet`
- Pandas screening pipeline: `french-arena/analysis/screen_political.py`
- Tests: `french-arena/tests/test_screen_political.py`

The full gated Hugging Face source could not be read from that sandbox, so a
provisional ID-only shortlist was built from a pinned public derivative of
`ministere-culture/comparia-fr-arena`: 8,739 conversations with primary topic
`Politics & Government` out of 137,293 derived French conversations with a
decisive vote (6.37%). These are review candidates, not validated labels.
The full-source exporter writes `french-arena/data/full/political_conversations.parquet`
with both visible transcripts; full exports are gitignored by default.

## Run tests

```bash
python -m pip install -r french-arena/analysis/requirements.txt
python -m unittest discover -s french-arena/tests -v
python arena/analyze_political.py --self-test
```
