# Political content in `arena-human-preference-140k` — initial screen

**Dataset:** `lmarena-ai/arena-human-preference-140k`, split `train`, revision
`6322995ab34d7c2693e3f47dd13fa5caa0789a74 (main, 2025-08-01)`. **Rows scanned:** 135,634 of 135,634 votes
(2,326s on a GitHub-hosted runner, 2026-11-03T22:33:12.682754+00:00).
Each row is one human preference vote on **two model answers** to one user conversation.

## Bottom line

- **2,235 votes (1.65%) contain a clearly political user prompt** —
  a specific reference to an election, voting, a public-policy issue, immigration,
  a political figure/party, or a geopolitical conflict. Adding corroborated
  weaker signals raises this to **2,932 (2.16%)**; the
  loose, one-word upper bound is **10,658 (7.86%)**.
- Because each political prompt is answered by two models, that is
  **4,468 answers to strict-political prompts** out of 271,129 judged
  answers (1.65%). **6,493** answers contain strong
  political wording themselves (3,334 votes
  where the answers are the only signal); the union is
  **8,912 political answers (3.29%)**, or
  **39,202 (14.46%)** at the probable tier.
- **5,569 votes (4.11%) contain
  political text anywhere** (prompt or either answer) at the strict tier, and
  **27,873 (20.55%)** at
  the probable tier. Treat the strict number as a lower bound and the broad
  number (63,635, 46.92%) as a
  deliberately noisy upper bound.

> These are *screening estimates*, not human gold labels. A keyword screen
> over- and under-counts; see "Precision & limitations" below.

## Data provenance — real prompts and real responses?

**Yes.** This is a release of live LMArena "text arena" battles collected
2025-04-17 to 2025-07-24, not synthetic data: human-written user prompts,
real outputs from 53 named models, and real human votes
(`model_a` / `model_b` / `tie` / `both_bad`). The official card says "user
votes collected in the text-only category" and licenses *user prompts* under
CC-BY-4.0 while *model outputs* stay under each provider's terms — a
distinction that only makes sense for genuine user and model text. Each row's
`conversation_a` / `conversation_b` contains the full message text, and
`full_conversation` contains the whole multi-turn history. This scan read that
actual text for all 135,634 rows, not just tags or IDs.

Caveats on "real": text-only battles only (no image/multimodal prompts); a
curated, time-bounded export with machine-added tags (language, is_code,
category_tag, style counts); rows are **votes**, so the same user prompt and
earlier turns recur across rows; models were anonymous to voters at vote time
and are named only in the release; in multi-turn sessions earlier answers come
from whichever models were sampled in prior votes. Prompts are not guaranteed
de-identified, and responses are unfiltered model generations including
refusals, mistakes and `both_bad` outcomes.

Because prompts are CC-BY-4.0 but model outputs carry provider-specific terms
(and the corpus is ~3 GB in memory), this repo stores **excerpts only**:
`shortlist.csv` has real prompt and both real answer excerpts (420 chars each)
for 1,500 rows, `audit_sample.csv` has 240 more; `matched_ids.csv.gz` holds
IDs + metadata with no text. Re-running `analyze_political.py` streams the
full, untruncated text for any of those IDs.

Sources: [dataset card](https://huggingface.co/datasets/lmarena-ai/arena-human-preference-140k),
[release notes](https://news.lmarena.ai/opendata-july2025/).

## How the labeling works

`arena/analyze_political.py` compiles a 667-term lexicon into three
tiers, applied separately to **all user turns** of `conversation_a` (the prompt),
and to the **two judged assistant turns** (last message of `conversation_a` and
`conversation_b`):

| Tier | Prompt rule | Response rule |
| --- | --- | --- |
| `strict` | ≥1 unambiguous strong political term | ≥2 distinct *topic-specific* strong terms (or a dense cluster in a short answer), **or** the prompt itself is strict |
| `probable` | ≥2 weak terms from ≥2 topic groups | one uncorroborated strong term, ≥2 weak terms from ≥2 groups, **or** the prompt is probable |
| `broad` | one weak/ambiguous term | one weak/ambiguous term; high-recall, many false positives |

Topic groups: `elections`, `voting`, `public_policy`, `immigration`,
`political_figures`, `parties_ideology`, `geopolitics`, plus
`non_english_politics` (unambiguous political vocabulary in 15+ other
languages — Polish, Russian, Chinese, German, French, Spanish, Portuguese,
Turkish, Persian, Arabic, Korean, Japanese, Vietnamese, Indonesian, Dutch,
Czech, Hebrew, Italian). Guards downgrade technical false positives such as
"leader election" (Raft) and "majority vote" (ML ensembling), and generic
governance words mentioned once in a long answer.

A response is also labeled political when the prompt is political, even if the
model's wording avoids every keyword: `responses_contextual_*`. The three
response counts are reported separately (`direct`, `contextual`, `union`).

## Headline counts

| Tier | Votes w/ political prompt | % of votes | Unique political prompts | Political answers | % of answers | Votes w/ any political text | % of votes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Strict** — high precision | 2,235 | 1.65% | 2,021 | 8,912 | 3.29% | 5,569 | 4.11% |
| **Probable** — corroborated weak signals | 2,932 | 2.16% | 2,666 | 39,202 | 14.46% | 27,873 | 20.55% |
| **Broad** — high-recall upper bound | 10,658 | 7.86% | 9,837 | 98,897 | 36.48% | 63,635 | 46.92% |

Other useful cuts:

- Current-turn-only strict prompts: **1,959**
  (vs 2,235 when all conversation turns are considered).
- Repeated prompts: 2,021 unique strict prompt texts across
  2,235 votes — a session can generate several votes on one prompt.
- Votes where the political signal comes only from the answer:
  **3,334** (strict).
- Of the 2,235 strict-prompt votes, **1,984**
  also contain political wording in an answer and
  **251** are flagged from the prompt alone.
- Top strong terms in political prompts: `NATO` (20), `constitution` (24), `election` (47), `elections` (34), `fdr` (24), `geopolitical` (28), `government` (305), `governments` (25), `immigration` (27), `legislation` (22), `mayor` (36), `parliament` (22).

## Topic mix (strict + probable prompt rows)

| Topic | Rows | % of probable-tier prompt rows |
| --- | ---: | ---: |
| `elections` | 566 | 19.30% |
| `geopolitics` | 517 | 17.63% |
| `immigration` | 370 | 12.62% |
| `non_english_politics` | 636 | 21.69% |
| `parties_ideology` | 924 | 31.51% |
| `political_figures` | 266 | 9.07% |
| `public_policy` | 1,271 | 43.35% |
| `voting` | 191 | 6.51% |

(Categories overlap, so the column does not sum to 100%. Total category hits: 4,741.)

## Where political content appears

### Language (top groups with ≥100 rows)

| Language | Rows | Any strict | strict % | Any probable | probable % |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ar` | 391 | 4 | 1.02% | 23 | 5.88% |
| `bn` | 193 | 2 | 1.04% | 14 | 7.25% |

Non-English rates are not directly comparable to English: the multilingual
lexicon is much smaller, so non-English political prompts are under-counted.

### Code vs non-code prompts

| Flag | Rows | Any strict | Any probable |
| --- | ---: | ---: | ---: |
| `code` | 39,363 | 1.51% | 16.72% |
| `non_code` | 96,271 | 5.17% | 22.12% |

### Vote outcome

| Winner | Rows | Any strict | Any probable |
| --- | ---: | ---: | ---: |
| `both_bad` | 15,754 | 3.94% | 17.45% |
| `model_a` | 48,563 | 4.10% | 21.07% |
| `model_b` | 49,785 | 4.28% | 21.35% |
| `tie` | 21,532 | 3.84% | 19.81% |

### By month

| Month | Rows | Any strict |
| --- | ---: | ---: |
| `2025-04` | 8,686 | 4.37% |
| `2025-05` | 28,033 | 4.36% |
| `2025-06` | 53,447 | 4.19% |
| `2025-07` | 45,468 | 3.80% |

## Precision & limitations


### Indicative precision spot-check

30 rows with a `strict` **prompt** label were sampled from the ranked shortlist
and judged by hand (`results/prompt_spotcheck.csv`): **17/30 (57%)** were
clearly political. Wilson 95% interval **[39%, 73%]**. Applied
mechanically to the 2,235 strict-prompt votes, that suggests roughly
**1,266** votes (876–1,623)
a human would likely keep — but this is a small, score-ranked, single-judge
sample, and the screen also *misses* political prompts without keywords, so
treat it as an order-of-magnitude sanity check, not a corrected estimate.

Typical false positives: "HOA president", "vote for me vs another AI", a
medical question about abortion, "mayor" meaning "largest" in Spanish, a
corporate "policy", and government boilerplate scraped into a prompt. The
`probable` tier is substantially noisier still: most sampled `probable` rows
were answers that mentioned a government, law or a country in passing.

`results/audit_sample.csv` contains a 240-row random sample (flagged / broad-only / unflagged) for a proper human audit; `python arena/audit_precision.py print` renders a labeled sheet. No full human gold-label pass has been done yet.

Known limitations of this first pass:

1. **Lexicon, not semantics.** Satire, historical fiction, homework about a
   president, a math problem featuring a king, or a business "policy" can be
   flagged; oblique political questions with no keyword are missed. The
   `probable` and especially `broad` tiers contain many incidental mentions.
2. **Long answers are noisy.** A 5,000-character answer mentioning a government
   once is not a political response. Response-side hits require corroboration,
   but `broad` still counts them; use `strict`/`probable` for decisions.
3. **Multilingual coverage is partial.** ~47% of rows are not English.
4. **One conversation, several votes.** Unique-prompt counts deduplicate by
   normalized text; session-level dedup would be stricter still.
5. **"Political" is a judgment call**, not a dataset field. The category_tag
   column of the source dataset has math / creative-writing / instruction-
   following tags, but no political tag, so no ground truth is available.
6. **Only the current-turn answers** are counted as responses; earlier turns
   are duplicated across `conversation_a` / `conversation_b` and are excluded
   from the response denominator to avoid double counting.

Suggested next step: human-label `results/shortlist.csv` (or the full
`results/matched_ids.csv.gz`), measure inter-rater agreement, then either
tune the lexicon or use those labels to train/validate a classifier.

## Full text & interactive explorer

The scan itself only kept 420-character excerpts. `arena/extract_full_text.py`
streams the corpus once more and materializes the **complete, untruncated**
text in `arena/explorer/data/`:

| File | Rows | Contents |
| --- | ---: | --- |
| `prompts_all.jsonl.gz` | 63,635 | full prompt + all user turns for **every** flagged vote ID |
| `conversations.jsonl.gz` | 6,820 | core political shortlist: full prompt + **both full model answers** |
| `manifest.json`, `extract.log` | — | provenance and runner log |
| `results/shortlist_full_prompts.csv` (local, gitignored) | 6,820 | the same full prompts in a directly viewable CSV |

Text is verbatim (`content[].text`), with no truncation, paraphrase or
redaction; every `shortlist.csv` excerpt was verified as a prefix of its full
prompt. Because these are real user prompts they can contain pasted API keys or
personal data (push protection flagged a Mapbox token), so the plain CSV is
generated locally rather than committed. 1,276 core prompts exceed 420
characters (longest: 110,289) and 1,049 are multi-turn. User prompts are
CC-BY-4.0; model outputs remain under their providers' terms.

`arena/explorer/` is a dependency-free web UI (Python stdlib server + vanilla
JS/SVG charts): filters, full-text/regex search, tier × evidence-basis chart,
topic / language / monthly / vote / model / match-strength visualizations, a
detail drawer with the full prompt and both complete answers, and CSV export
containing the `prompt_full_untruncated` column.

```bash
python arena/explorer/server.py --host 0.0.0.0 --port 8000   # live preview on :8000
```

See `arena/explorer/README.md` for the API and regeneration instructions.

## Reproduce

```bash
pip install -r arena/requirements.txt
python arena/analyze_political.py --self-test                       # lexicon checks, no download
python arena/analyze_political.py --output-dir /tmp/smoke --max-rows 1000
python arena/analyze_political.py --output-dir arena/results      # full 135,634-row scan
python arena/make_report.py                                       # regenerate this README
python arena/audit_precision.py print > /tmp/audit_sheet.txt      # manual review sheet
```

The script streams the corpus exactly as supplied in the request:

```python
from datasets import load_dataset
ds = load_dataset("lmarena-ai/arena-human-preference-140k")
```

`.github/workflows/political-scan.yml` runs the same script on a GitHub-hosted
runner (needed because this sandbox cannot reach `huggingface.co`) and commits
`arena/results/` back to the branch. Edit `arena/RUN_SCAN` to set a row limit
(`0` or empty = full scan) and push to re-run.

## Files

| File | Contents |
| --- | --- |
| `arena/analyze_political.py` | the screening script (lexicon + aggregation) |
| `arena/extract_full_text.py` | materializes full, untruncated prompts + answers |
| `arena/explorer/` | interactive explorer: `server.py`, `index.html`, `app.js`, `styles.css`, `README.md` |
| `arena/explorer/data/*.jsonl.gz` | full-text shortlist data (63,635 prompts + 6,820 conversations) |
| `arena/make_report.py` | regenerates this README from `summary.json` |
| `arena/audit_precision.py` | manual precision/recall audit helper |
| `arena/requirements.txt` | runtime dependencies |
| `arena/RUN_SCAN` | row limit for the CI run (`0` = all) |
| `arena/results/summary.json` | all counts, topic/language/time breakdowns, methodology |
| `arena/results/shortlist.csv` | 1,500 ranked flagged rows with prompt/answer excerpts |
| `arena/results/shortlist_full_prompts.csv` | 6,820 core rows with **full, untruncated prompts** — generated locally / via explorer export, gitignored because real prompts can contain pasted credentials |
| `arena/results/matched_ids.csv.gz` | **all** flagged vote IDs with tier, basis, topics (full shortlist for labeling) |
| `arena/results/audit_sample.csv` | 240-row random sample for manual precision/recall checks |
| `arena/results/prompt_spotcheck.csv` | 30 hand-judged strict-prompt rows (indicative precision) |
| `arena/results/run.log`, `run_meta.json` | provenance and runner log |

The two row-level counters `rows_prompt_only_strict` and
`rows_prompt_with_direct_response_signal` were recomputed from
`matched_ids.csv.gz` after the scan, because script v1.2.0 accidentally used
the prompt-propagated response tier there. The checked-in script (v1.2.1)
computes them directly; re-running reproduces the same numbers.
