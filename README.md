# evaluation

Working notes and tooling for studying LMArena's `lmarena-ai/arena-human-preference-140k`
(135,634 human preference votes, 53 models, 126 languages, 2025-04-17 → 2025-07-24).

## Read this first

- [`docs/dataset-feasibility.md`](docs/dataset-feasibility.md) — what this dataset can and
  cannot support for a study of **human preference votes on public-interest topics**.
- [`docs/topic-bt-model.md`](docs/topic-bt-model.md) — the model specification, validation,
  and what the simulation implies about statistical power.

Short version: it supports *"which model answers do users prefer on public-interest
prompts, relative to ordinary prompts"*; it does **not** support *"what does the public
think about these issues"* (no voter attributes, no stance labels, self-selected prompts,
quality-only judgments).

## Pipeline

```bash
pip install -r requirements.txt

# 0. validate the estimator, no data needed (~10 s)
python scripts/fit_topic_bt.py --simulate

# 1. triage: how many votes are plausibly about each domain?
python scripts/topic_prevalence.py --limit 20000

# 2. build topic labels + a sample to hand-check precision
python scripts/build_topics.py --first-order-only --sample-per-topic 150

# 3. adjusted, topic-conditional ratings with clustered CIs
python scripts/fit_topic_bt.py --labelled outputs/labelled.parquet --max-models 10 --bootstrap 200
```

| Script | Role |
|---|---|
| `scripts/arena_features.py` | shared prompt parsing, `v0.1` topic lexicon, `conv_metadata` style features |
| `scripts/topic_prevalence.py` | triage: coverage, tie / `both_bad` / position rates per domain, naive win rates |
| `scripts/build_topics.py` | writes `labelled.parquet` and `handcheck_sample.csv` (precision audit) |
| `scripts/fit_topic_bt.py` | ridge logistic BT with topic×model interactions, side + style controls, session-clustered bootstrap |

Outputs land in `outputs/` (gitignored).

## Status and guardrails

Scoping + pipeline stage; no substantive results yet. Before anything leaves this repo
these must exist: hand-checked lexicon precision per domain, the pre-registered model
comparison set, the tie / `both_bad` counts per domain, and cluster-bootstrap CIs. The
`--simulate` check is a regression guard for structural bugs, not evidence of precision.
