# Compar:IA political-study shortlist

This directory contains a **provisional, ID-only political-review shortlist** derived from the French Compar:IA arena, plus a reproducible pandas pipeline for screening the full gated release.

## Current status

- Full `ministere-culture/comparia-fr-arena` Parquet read: **not completed in this sandbox** because the source is gated and unavailable here.
- The checked-in provisional shortlist is **ID/metadata-only** and has no prompt or response text.
- The full-text pipeline is ready to write both model transcripts to `french-arena/data/full/political_conversations.parquet` when run on an authorized source file; that transcript dataset is not generated in this checkout.
- Provisional shortlist: **completed** from a public, pinned derivative of the same dataset.
  - Derivative: `simonaszilinskas/style-control-analysis`
  - Derivative revision: `25a17f883945c2229736bfe17702d966bc94aa0d`
  - Source revision reported by derivative: `8cd6488c5d0c3b8dfcb9339d11ae9624c84359be`
  - Source publication date reported by derivative: `2026-07-08`

## Provisional headline counts

| Quantity | Count |
|---|---:|
| Conversations in derived sample | 137,293 |
| Conversations with source primary topic `Politics & Government` | 8,739 |
| Share of derived sample | 6.37% |
| User prompt turns through retained vote, in those conversations | 10,074 |
| Assistant response turns through retained vote, in those conversations | 20,148 |
| Assistant responses at the decisive vote only | 17,478 |
| Single-turn conversations through retained vote | 7,846 |
| Multi-turn conversations through retained vote | 893 |
| Separate adjacent-topic review queue, **not counted as political** | 10,657 |

These are **topic-label candidates**, not text-validated political labels. The derivative contains no prompt or response text.

## Files

| File | Description |
|---|---|
| `political_shortlist_provisional.parquet` | Main provisional dataset: one row per `comparison_id`, source topic `Politics & Government`. |
| `political_shortlist_provisional.csv` | CSV copy of the same ID/metadata review queue. |
| `adjacent_topic_review_provisional.parquet` | Separate lower-priority queue from Law & Justice, Society & Social Issues & Human Rights, and Environment. These are **not** political positives. |
| `topic_counts_provisional.csv` | Primary-topic distribution in the derived sample. |
| `monthly_topic_counts_provisional.csv` | Monthly conversation counts and politics-topic share in the derived sample. |
| `summary_provisional.json` | Machine-readable provisional counts and caveats. |
| `manifest_provisional.json` | SHA-256 hashes and byte sizes for provisional artifacts. |
| `LICENSE_ETALAB_2.0.txt` | License text inherited from the public derivative. |

## Provisional schema

Each shortlist row contains:

- `comparison_id`: join key back to the source dataset.
- `timestamp`, `source_primary_topic`, `mode`.
- `model_a`, `model_b`, `winner`, `vote_turn`.
- `user_turns_through_vote`, `assistant_responses_through_vote`, `responses_at_decisive_vote`.
- `final_turn`, `post_vote_turns`.
- `source_dataset`, `source_revision`, `derived_repository_revision`.
- `review_status`, `shortlist_reason`, `candidate_topics`, `review_priority`.

No raw user prompts, model responses, hidden reasoning, or system prompts are included in the provisional files.

## Full-release screening pipeline

The full pipeline is in `french-arena/analysis/screen_political.py`. It uses pandas for tabular screening and can read either:

```python
import pandas as pd

df = pd.read_parquet(
    "hf://datasets/ministere-culture/comparia-fr-arena/comparia-fr-arena.parquet"
)
```

or a local Parquet file. Because the source file is about 9.5 GB, the default command streams Parquet batches into pandas instead of loading the entire file into memory. Use `--direct-pandas` if you specifically want `pd.read_parquet(...)` and have enough RAM.

```bash
python -m pip install -r french-arena/analysis/requirements.txt

# Default: stream batches into pandas
python french-arena/analysis/screen_political.py \
  --input hf://datasets/ministere-culture/comparia-fr-arena/comparia-fr-arena.parquet \
  --output-dir french-arena/data/full

# Exact pandas reader, higher memory use
python french-arena/analysis/screen_political.py \
  --input hf://datasets/ministere-culture/comparia-fr-arena/comparia-fr-arena.parquet \
  --output-dir french-arena/data/full \
  --direct-pandas

# Local file
python french-arena/analysis/screen_political.py \
  --input /path/to/comparia-fr-arena.parquet \
  --output-dir french-arena/data/full
```

For Hugging Face access, accept the dataset conditions and authenticate locally, for example with `huggingface-cli login` or an `HF_TOKEN` environment variable. Do not commit tokens. The token pasted into chat should be revoked and replaced.

### Full-run outputs

The full pipeline writes to `french-arena/data/full/`, which is gitignored by default because it can contain raw user-generated text and be large:

- `political_conversations.parquet`: one row per shortlisted `comparison_id`. It includes `model_a`, `model_b`, and both full visible transcripts in `full_conversation_a` and `full_conversation_b`. Each transcript is an ordered list of `{role, content}` messages. The transcript snapshot comes from the conversation's highest source turn; message counts and `conversation_export_status` / `conversation_export_complete` flag any shortfall.
- `political_prompts.parquet`: one row per unique `comparison_id + turn` in shortlisted conversations.
- `political_responses.parquet`: one row per assistant response in shortlisted conversations.
- `review_queue.csv`: conversation-level review queue.
- `topic_counts.csv`: unique shortlisted conversations, prompt-turn instances, and assistant-response instances by candidate topic.
- `summary.json`: counts, percentages, provenance, and caveats.
- `manifest.json`: output hashes.

Read the conversation-level text dataset with pandas:

```python
import pandas as pd

conversations = pd.read_parquet(
    "french-arena/data/full/political_conversations.parquet"
)
print(conversations[[
    "comparison_id", "model_a", "model_b",
    "full_conversation_a", "full_conversation_b",
    "conversation_export_status",
]].head())
```

### Screening scope

The rule-based screen is intentionally high-recall and covers:

1. Elections and voting.
2. Public policy and governance.
3. Immigration, asylum, borders, and citizenship.
4. Publicly elected or politically active figures, parties, and political organizations.

It screens only visible user/assistant `content`. It excludes `reasoning_content`, system prompts, and tool payloads. Generic terms such as “vote”, “policy”, and “migration” require civic context to reduce obvious false positives. Surname matches are candidate signals and require review.

## Recommended review protocol

Before reporting prevalence:

1. Sample at least 200–500 shortlisted conversations, stratified by `review_priority` and topic.
2. Label each conversation as political / not political / ambiguous.
3. Record which topic(s) apply and whether the signal came from the prompt, response, or source metadata.
4. Estimate precision of the candidate filter.
5. Sample non-shortlisted conversations to estimate recall, especially for adjacent topics and figurative political language.
6. Only then report validated political prompt/response/conversation counts.

## Attribution and license

Source dataset: Ministère de la Culture / Compar:IA, `ministere-culture/comparia-fr-arena`.
Public derivative: Simonas Zilinskas, Maayeesha Farzana, Christophe Benavent, `simonaszilinskas/style-control-analysis`, revision `25a17f883945c2229736bfe17702d966bc94aa0d`.

The provisional artifacts are derived from Open Licence 2.0 / Etalab 2.0 material. See `LICENSE_ETALAB_2.0.txt`. The source dataset also lists CC-BY-4.0 and notes possible third-party claims over model outputs.
