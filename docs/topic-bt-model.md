# Methods note: topic-conditional Bradley–Terry with style and position controls

Implements the design in `dataset-feasibility.md` §5 for framing A — *which model answers
do users prefer on public-interest prompts, relative to ordinary prompts, after accounting
for length, markdown, position, and model strength?*

Code: `scripts/fit_topic_bt.py`. Self-test: `python scripts/fit_topic_bt.py --simulate`.

## Specification

One ridge-penalized logistic regression over all decided battles
(`winner ∈ {model_a, model_b}`; ties and `both_bad` are dropped but reported separately):

```
logit P(model_a wins) = (1[a=k] − 1[b=k]) · β_k                 shared BT strength
                      + (1[a=k] − 1[b=k]) · δ_{t,k} · 1[t ≠ ref] topic-specific shift
                      + γ                                        slot-A advantage
                      + Σ_j φ_j (style_{a,j} − style_{b,j})      length / markdown controls
```

- **`β_k`** is model *k*'s strength on the reference topic (`general`: prompts that match no
  public-interest domain). Reported as Elo-like points, `1000 + (400/ln 10)·β`, with the
  most-battled model pinned at 1000.
- **`δ_{t,k}`** is the estimand: how much model *k*'s log-odds shift on topic *t* relative to
  general prompts. Because every battle contributes to the shared `β`, a topic populated by
  a narrow model pair cannot fake a topic effect — the pair's strength is already absorbed.
- **`γ`** absorbs position bias instead of leaving it in the topic deltas.
- **Style covariates** are antisymmetric `log1p` counts of assistant tokens, bold spans,
  list items, and headers, taken from `conv_metadata`. Positive `φ` means longer or
  more-markdown answers win more often, i.e. the control is doing real work.

Identifiability: the reference model is dropped from the model block and the reference
topic from the interaction block. Fitting is damped Newton (IRLS) with a ridge penalty of
`l2` pseudo-observations (default 1.0, negligible at realistic N but keeps thin cells finite).

Uncertainty: **cluster bootstrap over `evaluation_session_id`** (default 200 replicates,
percentile CIs). Sessions cast several dependent votes, so row-level bootstraps understate
uncertainty. `--bootstrap 0` skips it.

## Validation

`--simulate` generates a synthetic release with known `β`, `δ`, `φ`, `γ`, runs the same
preprocessing path (prompt → topic label → style features → design matrix), fits, and
compares. Two regression guards, deliberately loose because they target structural bugs
rather than precision: β within 0.10, δ within 0.30 log-odds. A design bug — non-compact
columns, bad reference coding — shifts estimates by ~0.7 and trips them immediately.

Known failure modes this check has caught:
- **Reference coding.** Estimates are identified only up to the reference model and
  reference topic, so a checker must compare `β_k − β_ref` and `δ_{t,k} − δ_{t,ref}`,
  not the raw truth values. Comparing raw values reports a phantom 0.76 "error".

## What the simulation implies about power

At 60,000 battles with 10 models and ~9,000 battles per topic, mean |δ error| is ~0.065
log-odds (max ~0.17 across 27 cells). That is roughly 900 battles per model-topic cell,
giving ±0.12-ish log-odds (≈ ±20 Elo) per-cell CIs. Consequences for the real study:

- **Only large topic shifts are detectable.** A model that is 50 Elo better on climate than
  on general prompts will show up; a 10–15 Elo shift will not, at typical per-topic counts.
- **Restrict the model set before looking at results.** Fitting 53 models multiplies cells
  without adding information and invites reading noise. `--max-models 10` or so, chosen on
  battle counts, not on preliminary topic results.
- **Report CIs, never bare ranks.** With these widths, adjacent models in a topic ordering
  are almost always statistically indistinguishable.

## Reading the outputs

| File | Contents |
|---|---|
| `topic_bt_ratings.csv` | per-model Elo on the reference topic, CI, battle count |
| `topic_bt_deltas.csv` | `δ_{t,k}` in log-odds and Elo, CI, `ci_excludes_zero`, battles per cell |
| `topic_bt_delta_matrix.csv` | models × topics, wide format for plotting |
| `topic_bt_covariates.csv` | side term and style coefficients with CIs |

Report alongside any of these: lexicon version, hand-check precision per topic, the
excluded-model and excluded-topic lists, number of ties and `both_bad` per topic, and the
share of the corpus the labeled topics cover. Without those, the numbers are not
interpretable.

## Limitations that no control fixes

- Topic labels come from a regex on the first user turn. Precision is unknown until the
  hand-check in `handcheck_sample.csv` is filled in; a prompt can be political without
  containing any keyword, so δ is estimated on a *detected* subsample, not all such prompts.
- Only the first user turn is labeled. Later turns inherit context, so multi-turn battles
  are included but their topic can drift; `--first-order-only`-style filtering at label
  time is the robustness check.
- Votes are quality judgments about one user's own prompt, not endorsements of a position.
  Nothing here recovers the voter's politics (§3 of the memo).
- `winner` is a coarse outcome; magnitude of preference is unobserved.
