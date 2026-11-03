# evaluation

Working notes and tooling for studying LMArena's `lmarena-ai/arena-human-preference-140k`
(135,634 human preference votes, 53 models, 126 languages, 2025-04-17 → 2025-07-24).

## Read this first

[`docs/dataset-feasibility.md`](docs/dataset-feasibility.md) — what this dataset can and
cannot support for a study of **human preference votes on public-interest topics**.

Short version: it supports *"which model answers do users prefer on public-interest
prompts"*; it does **not** support *"what does the public think about these issues"*
(no voter attributes, no stance labels, self-selected prompts, quality-only judgments).

## Tooling

`scripts/topic_prevalence.py` — triage only. Reports the corpus summary, keyword-based
topic prevalence over a starter 10-domain lexicon, tie / `both_bad` / position-bias
rates per domain, and naive per-model win rates per domain. No controls, no CIs, no
causal claims.

```bash
pip install datasets pandas pyarrow
python scripts/topic_prevalence.py --limit 20000     # quick look (streams a subset)
python scripts/topic_prevalence.py                  # full 1.6 GB release
python scripts/topic_prevalence.py --first-order-only
python scripts/topic_prevalence.py --local data/*.parquet --outdir outputs
```

Writes `corpus_summary.csv`, `topic_prevalence.csv`, `topic_outcomes.csv`,
`model_wins_by_topic.csv` to `--outdir` (default `outputs/`).

## Status

Scoping stage. Before any result leaves this repo: hand-label ~150 prompts per
candidate domain to measure lexicon precision, then fix the pre-registered taxonomy
and model comparison set (see memo §4 on power and §5 on design).
