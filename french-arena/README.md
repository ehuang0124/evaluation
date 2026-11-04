# French Compar:IA political-study shortlist

## Findings summary

- Full gated `ministere-culture/comparia-fr-arena` read was **not completed** in this sandbox: Hugging Face access is gated and unavailable from this environment.
- The checked-in shortlist is a **provisional ID/metadata-only** artifact; it does not contain the full conversations.
- The full-source pipeline now writes both model transcripts into `data/full/political_conversations.parquet` once run on an authorized source file. That text-bearing dataset has not been generated here because the full source is unavailable.
- The derivative sample contains **137,293** French conversations with a decisive vote.
- **8,739** conversations have source primary topic `Politics & Government` (**6.37%**).
- Within those conversations: **10,074** user prompt turns and **20,148** assistant response turns through the retained vote; **17,478** assistant responses at the decisive vote only.
- A separate **10,657**-conversation adjacent-topic review queue is included, but it is **not counted as political**.
- These are topic-label review candidates, not manually validated political labels, and should not be extrapolated to the full current release.

## Main files

| Path | Purpose |
|---|---|
| `data/political_shortlist_provisional.parquet` | Checked-in provisional ID/metadata shortlist, one row per `comparison_id` (no prompt/response text). |
| `data/political_shortlist_provisional.csv` | CSV copy of the provisional shortlist. |
| `data/full/political_conversations.parquet` | Generated full-text shortlist: one row per conversation with `model_a`, `model_b`, `full_conversation_a`, and `full_conversation_b`. This local raw-text export is gitignored and is not currently generated in this checkout. |
| `data/adjacent_topic_review_provisional.parquet` | Lower-priority adjacent-topic review queue, not political positives. |
| `data/summary_provisional.json` | Machine-readable counts and caveats. |
| `data/manifest_provisional.json` | SHA-256 hashes for provisional artifacts. |
| `analysis/screen_political.py` | Pandas pipeline for full-source text screening. |
| `analysis/build_provisional.py` | Rebuilds provisional artifacts from the pinned public derivative. |
| `analysis/political_rules.json` | French/English candidate rules. |
| `tests/test_screen_political.py` | Unit and fixture tests. |
| `REPORT.md` | Detailed initial report. |

## Reproduce provisional shortlist

```bash
git clone https://github.com/simonaszilinskas/style-control-analysis.git /tmp/style-control-analysis
git -C /tmp/style-control-analysis checkout 25a17f883945c2229736bfe17702d966bc94aa0d

python french-arena/analysis/build_provisional.py \
  --reference-dir /tmp/style-control-analysis \
  --output-dir french-arena/data
```

## Screen full source with pandas

```bash
python -m pip install -r french-arena/analysis/requirements.txt

python french-arena/analysis/screen_political.py \
  --input hf://datasets/ministere-culture/comparia-fr-arena/comparia-fr-arena.parquet \
  --output-dir french-arena/data/full
```

For the exact pandas reader:

```bash
python french-arena/analysis/screen_political.py \
  --input hf://datasets/ministere-culture/comparia-fr-arena/comparia-fr-arena.parquet \
  --output-dir french-arena/data/full \
  --direct-pandas
```

Full raw exports are gitignored by default because they may contain user-generated text and be large.

## Tests

```bash
python -m unittest discover -s french-arena/tests -v
```
