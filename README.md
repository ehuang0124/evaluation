# evaluation

Dataset analyses and reproducible screening pipelines.

## `arena/` — lmarena-ai/arena-human-preference-140k (English + multilingual)

Initial political-content screen of the 135,634-vote Arena human-preference
dataset (elections, voting, public policy, immigration, publicly elected or
politically active figures, parties/ideology, geopolitics). Full findings,
method, caveats and reproduction steps: [`arena/README.md`](arena/README.md).
Headline from the initial v1.2 scan: 2,235 votes (1.65%) have a strictly
political user prompt; 8,912 of 271,129 judged answers (3.29%) are on political
topics at that tier. The English taxonomy has since been broadened in v1.3 for
civic engagement, public discourse and public-interest debates; checked-in result
counts/IDs have not yet been refreshed against that revision. The `/arena` folder
also holds the script, the full shortlisted vote IDs, and
**full untruncated prompts** (63,635 flagged IDs; 6,820 with both complete model
answers). Explore the full-text shortlist alongside the French metadata shortlist with keyword search and side-by-side responses:

```bash
python arena/explorer/server.py --host 0.0.0.0 --port 8000
```

The explorer's **Short answer wins, tie or both bad (±5%)** dataset narrows the
Arena ranked shortlist to 800 votes where the shorter answer won (383), the vote
was a tie (230) or both_bad (153), or the longer answer won by less than 5% in
length (34); exported to `arena/results/short_answer_wins_tie_or_both_bad.csv`.

## `arena/interest_analysis/` — what the political shortlist actually contains

Second-stage analysis of the 1,500-vote shortlist: recurring prompt categories
(hand-coded sample of 150), what the *preferred* answer contains, sentiment by
topic, and a hand-verified fact-check of 23 officeholder/legislation votes plus a
Tiananmen/Tank Man compliance audit. Report: [`arena/interest_analysis/REPORT.md`](arena/interest_analysis/REPORT.md).
Headline: only 50% of the dataset's *strict* political tier is a load-bearing
political prompt, the longer answer wins 66% of decisive votes, admitting
uncertainty loses votes, and all 7 evasion/denial answers on contested history
came from Chinese-developed models.

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
python arena/interest_analysis/analyze.py
python arena/interest_analysis/supplement.py
python arena/interest_analysis/figures.py
python -m unittest discover -s arena/interest_analysis/tests -v
```
