# Initial political-content analysis: Compar:IA French arena

## Bottom line

I could not complete the full `ministere-culture/comparia-fr-arena` read in this sandbox. Both `git clone` and the requested pandas read failed at the Hugging Face network/TLS boundary, and the dataset page requires gated access acceptance.

I did create a **provisional political-study shortlist** in this repo from a public, pinned derivative of the same dataset:

- **8,739 conversations** labeled by the source primary topic `Politics & Government`.
- This is **6.37%** of the derivative’s 137,293 French conversations with a decisive vote.
- Within those conversations, there are **10,074 user prompt turns** and **20,148 assistant response turns** through the retained vote.
- A separate **10,657-conversation adjacent-topic queue** is provided for review, but it is **not counted as political**.

Main dataset file:

```text
french-arena/data/political_shortlist_provisional.parquet
```

CSV copy:

```text
french-arena/data/political_shortlist_provisional.csv
```

## What was attempted

Requested read:

```python
import pandas as pd

df = pd.read_parquet(
    "hf://datasets/ministere-culture/comparia-fr-arena/comparia-fr-arena.parquet"
)
```

Result: failed before loading source rows. The sandbox could not establish a usable Hugging Face TLS connection. The public dataset page also says users must accept access conditions. I did not use the token pasted into chat; it should be revoked and replaced.

## Provisional source

Because the full gated file was unavailable, I used a public GitHub derivative that explicitly says it is derived from `ministere-culture/comparia-fr-arena`:

- Repository: `simonaszilinskas/style-control-analysis`
- Repository revision: `25a17f883945c2229736bfe17702d966bc94aa0d`
- Source revision reported by derivative: `8cd6488c5d0c3b8dfcb9339d11ae9624c84359be`
- Source publication date reported by derivative: `2026-07-08`
- Input files verified by SHA-256 before use.

The derivative contains one row per retained French conversation with a decisive vote. It includes opaque conversation IDs, timestamps, models, vote metadata, and the first source-assigned topic. It does **not** contain prompt or response text.

## Provisional findings

| Measure | Value |
|---|---:|
| Derived conversations | 137,293 |
| `Politics & Government` conversations | 8,739 |
| Politics-topic share | 6.365% |
| User prompt turns through retained vote | 10,074 |
| Assistant response turns through retained vote | 20,148 |
| Assistant responses at decisive vote only | 17,478 |
| Single-turn conversations through retained vote | 7,846 |
| Multi-turn conversations through retained vote | 893 |
| Random-mode politics-topic conversations | 6,147 |
| Custom-mode politics-topic conversations | 1,934 |
| Big-vs-small mode politics-topic conversations | 504 |
| Small-models mode politics-topic conversations | 154 |

The adjacent-topic review queue contains:

| Adjacent primary topic | Conversations |
|---|---:|
| Law & Justice | 3,890 |
| Society & Social Issues & Human Rights | 2,740 |
| Environment | 4,027 |
| Total | 10,657 |

These adjacent records are useful for recall review because immigration, public policy, or political-figure discussions may be classified outside `Politics & Government`. They are not political positives.

## What is saved in the repo

```text
french-arena/data/
  political_shortlist_provisional.parquet
  political_shortlist_provisional.csv
  adjacent_topic_review_provisional.parquet
  topic_counts_provisional.csv
  monthly_topic_counts_provisional.csv
  summary_provisional.json
  manifest_provisional.json
  LICENSE_ETALAB_2.0.txt
  README.md

analysis/
  screen_political.py
  political_rules.json
  build_provisional.py
  requirements.txt
  README.md

tests/
  test_screen_political.py
```

The provisional shortlist is ID/metadata-only. It does not publish raw user prompts or model responses.

## Full-release pipeline

I added a pandas-based pipeline to perform the broader text screening requested:

```bash
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

The pipeline screens visible user/assistant content for:

- elections and voting,
- public policy and governance,
- immigration, asylum, borders, and citizenship,
- publicly elected or politically active figures and parties.

It excludes hidden reasoning, system prompts, and tool payloads. It produces conversation-level, prompt-level, and response-level candidate datasets, with evidence snippets and review flags.

## Important limitations

1. The provisional count is based on a source topic label, not manual political validation.
2. The derivative excludes conversations without a decisive French vote.
3. The derivative only exposes the first source-assigned topic, so political conversations with another primary topic can be missed.
4. The 6.37% figure should not be extrapolated to the current full release or to French users generally.
5. Prompt/response counts are turn instances, not unique prompt strings.
6. The full text-based pipeline has been tested on fixtures, but it has not been run on the full gated source in this sandbox.

## Recommended next step

Run the full pipeline on the gated source after accepting dataset conditions and authenticating locally. Then manually review a stratified sample of shortlisted and non-shortlisted conversations to estimate precision and recall before reporting validated political prevalence.
