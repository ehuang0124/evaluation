# `arena/interest_analysis` — what the political shortlist actually contains

Second-stage analysis of [`arena/results/shortlist.csv`](../results/shortlist.csv)
(1,500 votes; the top-scoring 1,500 of the 5,569 votes flagged by the v1.2
political screen). It answers four questions — recurring prompt categories, the
content of the *preferred* answer, sentiment, and factual/historical accuracy —
and ends with a ranked list of research directions.

**Read [`REPORT.md`](REPORT.md) first.** Headlines:

- Only **50%** of the dataset's *strict* political tier is a load-bearing
  political prompt (150-row hand-coded sample); 63% of the shortlist's rows have
  no political prompt at all and were flagged from the response.
- **65.7%** of decisive votes go to the **longer** answer; style markers are flat;
  **admitting uncertainty loses** votes (−1.3pp, p=0.016), and **validating the
  user wins** (38 vs 20, p=0.025).
- Sentiment is mildly positive everywhere except geopolitics/conflict, where 48%
  of answers read negative; immigration shows "positive tone + heavy hedging".
- In a 23-vote hand-verified fact audit: 41% of answers correct, 50% wrong, 2
  honest declines. One-sided errors are punished (5 of 6), **shared errors are
  not** (voters still picked a winner in 5 of 8 both-wrong votes).
- **18 votes on Tiananmen/Tank Man**: 26 of 36 answers accurate; 7
  evasion/denial/party-line answers, all from Chinese-developed models (Qwen 6,
  DeepSeek 1). Voters never preferred the evasion (4 wins, 2 ties, 0 losses).

## Files

| file | purpose |
|---|---|
| `analyze.py` | pipeline over the 1,500 rows: topic/intent coding, answer-feature extraction and McNemar tests, VADER sentiment, model win rates + Bradley-Terry, sensitive-probe audit, length analysis from the repo's length file |
| `lexicons.py` | the hand-built regex lexicons (topics, intents, structure, epistemic markers, organised interests, sensitive probes) |
| `supplement.py` | paired log-odds (Monroe et al. prior), sentiment by topic, language stats, recency/sycophancy tests, summaries of the hand-coded audits, label-validation sample |
| `figures.py` | five PNG figures in `results/figures/` |
| `results/` | every CSV/JSON quoted in the report |
| `results/prompt_handcode_150.csv` | my hand codes for 150 random strict-tier rows (category, intent, political load, note) |
| `results/sensitive_handcode.csv`, `results/sensitive_votes_coded.csv` | hand codes for the Tiananmen/Tank Man probes and their vote outcomes |
| `results/factcheck_audit.csv` | 23 votes checked against public records, with verdicts and sources |
| `tests/test_interest_analysis.py` | unit tests for the statistical helpers and label logic |

## Reproduce

```bash
python arena/interest_analysis/analyze.py        # -> results/*.csv, results/overview.json
python arena/interest_analysis/supplement.py     # -> results/*.json, log-odds, by-topic sentiment
python arena/interest_analysis/figures.py        # -> results/figures/*.png
python -m unittest discover -s arena/interest_analysis/tests -v
```

Requires `pandas`, `matplotlib`, `vaderSentiment` (see `../requirements.txt`
plus the two extras). Everything is deterministic; the hand-coded files are
checked in so their numbers do not depend on re-coding. Re-running against the
full corpus requires the 3 GB source dataset, not just the excerpts — the same
caveat as `../README.md`.

## Caveat

This is a keyword-ranked, non-random sample, read through 420-character excerpts
with newlines stripped. Shares describe **this file**, not LMArena traffic;
accuracy figures come from a deliberately checkable 23-vote subset. See §0 and
§6 of the report.
