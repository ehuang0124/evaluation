#!/usr/bin/env python3
"""Regenerate ``arena/README.md`` from the committed scan results.

    python arena/make_report.py

Keeps the written findings in sync with whatever ``analyze_political.py`` last
produced.  Needs only the standard library.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = HERE / "results"
summary = json.loads((R / "summary.json").read_text(encoding="utf-8"))
meta = json.loads((R / "run_meta.json").read_text(encoding="utf-8"))
c = summary["counts"]
N = summary["rows_scanned"]
RESP = c.get("responses_judged", 2 * N)
UP = summary["unique_prompts_by_tier"]


def pct(x, d):
    return f"{100 * x / d:.2f}%" if d else "n/a"


def n(x):
    return f"{x:,}"


# Optional manual-audit numbers (produced by audit_precision.py score).
audit_line = ("`results/audit_sample.csv` contains a 240-row random sample "
              "(flagged / broad-only / unflagged) for a proper human audit; "
              "`python arena/audit_precision.py print` renders a labeled sheet. "
              "No full human gold-label pass has been done yet.")

spot_file = R / "prompt_spotcheck.csv"
spot_line = ""
if spot_file.exists():
    lab = list(csv.DictReader(spot_file.open(encoding="utf-8", newline="")))
    k = sum(int(r["label"]) for r in lab)
    nn = len(lab)
    p = k / nn
    z = 1.96
    d = 1 + z * z / nn
    centre = (p + z * z / (2 * nn)) / d
    half = z * math.sqrt(p * (1 - p) / nn + z * z / (4 * nn * nn)) / d
    lo, hi = max(0, centre - half), min(1, centre + half)
    _sp = c.get("rows_prompt_strict", 0)
    spot_line = f"""
### Indicative precision spot-check

30 rows with a `strict` **prompt** label were sampled from the ranked shortlist
and judged by hand (`results/prompt_spotcheck.csv`): **{k}/{nn} ({p:.0%})** were
clearly political. Wilson 95% interval **[{lo:.0%}, {hi:.0%}]**. Applied
mechanically to the {n(_sp)} strict-prompt votes, that suggests roughly
**{round(_sp * p):,}** votes ({round(_sp*lo):,}–{round(_sp*hi):,})
a human would likely keep — but this is a small, score-ranked, single-judge
sample, and the screen also *misses* political prompts without keywords, so
treat it as an order-of-magnitude sanity check, not a corrected estimate.

Typical false positives: "HOA president", "vote for me vs another AI", a
medical question about abortion, "mayor" meaning "largest" in Spanish, a
corporate "policy", and government boilerplate scraped into a prompt. The
`probable` tier is substantially noisier still: most sampled `probable` rows
were answers that mentioned a government, law or a country in passing.

{audit_line}
"""

rows = []
for tier, label in (("strict", "**Strict** — high precision"),
                    ("probable", "**Probable** — corroborated weak signals"),
                    ("broad", "**Broad** — high-recall upper bound")):
    rows.append(
        f"| {label} | {n(c.get(f'rows_prompt_{tier}',0))} | {pct(c.get(f'rows_prompt_{tier}',0),N)} | "
        f"{n(UP.get(tier,0))} | {n(c.get(f'responses_union_{tier}',0))} | "
        f"{pct(c.get(f'responses_union_{tier}',0),RESP)} | "
        f"{n(c.get(f'rows_any_{tier}',0))} | {pct(c.get(f'rows_any_{tier}',0),N)} |"
    )
tier_table = "\n".join(rows)

cat_total = sum(summary["categories_prompt_strict_or_probable"].values())
cat_rows = "\n".join(
    f"| `{k}` | {n(v)} | {pct(v, max(1, c.get('rows_prompt_probable', 1)))} |"
    for k, v in summary["categories_prompt_strict_or_probable"].items()
)

lang_rows = []
for lang, d in list(summary["by_language"].items())[:12]:
    if d["rows"] < 100:
        continue
    lang_rows.append(
        f"| `{lang}` | {n(d['rows'])} | {n(d.get('any_strict',0))} | "
        f"{pct(d.get('any_strict',0),d['rows'])} | {n(d.get('any_probable',0))} | "
        f"{pct(d.get('any_probable',0),d['rows'])} |"
    )
lang_table = "\n".join(lang_rows)

win_rows = []
for w, d in sorted(summary["by_winner"].items()):
    win_rows.append(f"| `{w}` | {n(d['rows'])} | {pct(d.get('any_strict',0),d['rows'])} | "
                    f"{pct(d.get('any_probable',0),d['rows'])} |")
win_table = "\n".join(win_rows)

code_rows = []
for k, d in sorted(summary["by_is_code"].items()):
    code_rows.append(f"| `{k}` | {n(d['rows'])} | {pct(d.get('any_strict',0),d['rows'])} | "
                     f"{pct(d.get('any_probable',0),d['rows'])} |")
code_table = "\n".join(code_rows)

month_rows = []
for m, d in sorted(summary["by_month"].items()):
    if d["rows"] == 0:
        continue
    month_rows.append(f"| `{m}` | {n(d['rows'])} | {pct(d.get('any_strict',0),d['rows'])} |")
month_table = "\n".join(month_rows)

top_terms = ", ".join(f"`{k}` ({v:,})" for k, v in
                      list(summary["top_strong_terms_prompt"].items())[:12])

strict_p = c.get("rows_prompt_strict", 0)
prob_p = c.get("rows_prompt_probable", 0)
broad_p = c.get("rows_prompt_broad", 0)
union_s = c.get("responses_union_strict", 0)
union_p = c.get("responses_union_probable", 0)
ctx_s = c.get("responses_contextual_strict", 0)
direct_s = c.get("responses_direct_strict", 0)

text = f"""# Political content in `arena-human-preference-140k` — initial screen

**Dataset:** `lmarena-ai/arena-human-preference-140k`, split `train`, revision
`{meta['dataset_revision']}`. **Rows scanned:** {n(N)} of 135,634 votes
({meta['elapsed_seconds']:,.0f}s on a GitHub-hosted runner, {meta['generated_at_utc']}).
Each row is one human preference vote on **two model answers** to one user conversation.

## Bottom line

- **{n(strict_p)} votes ({pct(strict_p,N)}) contain a clearly political user prompt** —
  a specific reference to an election, voting, a public-policy issue, immigration,
  a political figure/party, or a geopolitical conflict. Adding corroborated
  weaker signals raises this to **{n(prob_p)} ({pct(prob_p,N)})**; the
  loose, one-word upper bound is **{n(broad_p)} ({pct(broad_p,N)})**.
- Because each political prompt is answered by two models, that is
  **{n(ctx_s)} answers to strict-political prompts** out of {n(RESP)} judged
  answers ({pct(ctx_s,RESP)}). **{n(direct_s)}** answers contain strong
  political wording themselves ({n(c.get('rows_response_only_strict',0))} votes
  where the answers are the only signal); the union is
  **{n(union_s)} political answers ({pct(union_s,RESP)})**, or
  **{n(union_p)} ({pct(union_p,RESP)})** at the probable tier.
- **{n(c.get('rows_any_strict',0))} votes ({pct(c.get('rows_any_strict',0),N)}) contain
  political text anywhere** (prompt or either answer) at the strict tier, and
  **{n(c.get('rows_any_probable',0))} ({pct(c.get('rows_any_probable',0),N)})** at
  the probable tier. Treat the strict number as a lower bound and the broad
  number ({n(c.get('rows_any_broad',0))}, {pct(c.get('rows_any_broad',0),N)}) as a
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
actual text for all {n(N)} rows, not just tags or IDs.

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

`arena/analyze_political.py` compiles a {meta['term_count']}-term lexicon into three
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
{tier_table}

Other useful cuts:

- Current-turn-only strict prompts: **{n(c.get('rows_current_prompt_strict',0))}**
  (vs {n(strict_p)} when all conversation turns are considered).
- Repeated prompts: {n(UP.get('strict',0))} unique strict prompt texts across
  {n(strict_p)} votes — a session can generate several votes on one prompt.
- Votes where the political signal comes only from the answer:
  **{n(c.get('rows_response_only_strict',0))}** (strict).
- Of the {n(strict_p)} strict-prompt votes, **{n(c.get('rows_prompt_with_direct_response_signal',0))}**
  also contain political wording in an answer and
  **{n(c.get('rows_prompt_only_strict',0))}** are flagged from the prompt alone.
- Top strong terms in political prompts: {top_terms}.

## Topic mix (strict + probable prompt rows)

| Topic | Rows | % of probable-tier prompt rows |
| --- | ---: | ---: |
{cat_rows}

(Categories overlap, so the column does not sum to 100%. Total category hits: {n(cat_total)}.)

## Where political content appears

### Language (top groups with ≥100 rows)

| Language | Rows | Any strict | strict % | Any probable | probable % |
| --- | ---: | ---: | ---: | ---: | ---: |
{lang_table}

Non-English rates are not directly comparable to English: the multilingual
lexicon is much smaller, so non-English political prompts are under-counted.

### Code vs non-code prompts

| Flag | Rows | Any strict | Any probable |
| --- | ---: | ---: | ---: |
{code_table}

### Vote outcome

| Winner | Rows | Any strict | Any probable |
| --- | ---: | ---: | ---: |
{win_table}

### By month

| Month | Rows | Any strict |
| --- | ---: | ---: |
{month_table}

## Precision & limitations

{spot_line}
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

Text is verbatim (`content[].text`), with no truncation, paraphrase or
redaction; every `shortlist.csv` excerpt was verified as a prefix of its full
prompt. 1,276 core prompts exceed 420 characters (longest: 110,289) and 1,049
are multi-turn. User prompts are CC-BY-4.0; model outputs remain under their
providers' terms.

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
| `arena/results/shortlist.csv` | {n(min(meta['shortlist_cap'], c.get('rows_any_probable',0)))} ranked flagged rows with prompt/answer excerpts |
| `arena/results/matched_ids.csv.gz` | **all** flagged vote IDs with tier, basis, topics (full shortlist for labeling) |
| `arena/results/audit_sample.csv` | 240-row random sample for manual precision/recall checks |
| `arena/results/prompt_spotcheck.csv` | 30 hand-judged strict-prompt rows (indicative precision) |
| `arena/results/run.log`, `run_meta.json` | provenance and runner log |

The two row-level counters `rows_prompt_only_strict` and
`rows_prompt_with_direct_response_signal` were recomputed from
`matched_ids.csv.gz` after the scan, because script v1.2.0 accidentally used
the prompt-propagated response tier there. The checked-in script (v1.2.1)
computes them directly; re-running reproduces the same numbers.
"""
(HERE / "README.md").write_text(text, encoding="utf-8")
print(f"wrote {HERE / 'README.md'} ({len(text):,} chars)")
