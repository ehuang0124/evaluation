# What the Arena votes actually reward — full-extract analysis

**Scope.** This supersedes the 1,500-row shortlist version in `REPORT.md`. Everything below is measured on the
complete local extracts of the LMArena human-preference data (`lmarena-ai/arena-human-preference-140k`,
revision `6322995`, streamed 2025-07-24):

| Set | Votes | What it has |
|---|---|---|
| `prompts_all.jsonl.gz` | **63,635** | every vote whose prompt passed the extract's relevance filter; prompt + metadata (`prompt_tier`, `categories`, `winner`, `model_a/b`, `timestamp`, `is_code`) |
| `conversations.jsonl.gz` | **6,820** | the subset whose **both answers survive untruncated** — the only votes where answer content can be measured |
| political-prompt census | **2,235** | the 6,820 filtered to `prompt_tier == "strict"`; 100% political-category-tagged, 67% English |
| explicit-politics lexicon set | **1,926** | the 6,820 whose prompt contains explicit political vocabulary in 8 languages (robustness set, see §2.1) |
| near-equal-length sets | **182 / 569 / 164** | decisive votes whose two answers differ in length by ≤11% — the length-controlled test |

Dates 2025-04-17 → 2025-07-24. All 63,635 votes, 56,352 sessions, 53 models
(`results_scale/coverage.csv`).

**These are ceilings, not choices.** The Hugging Face Hub is not reachable from this environment
(`URLError: TLS connection closed`), so the 135,634-row source cannot be re-streamed and no additional raw data can be
obtained. The extract's own filter kept 63,635 of 135,634 rows, and only 6,820 of those retain both full answers.
Every claim about answer *content* therefore rests on 6,820 votes; every claim about prompt *prevalence* rests on
63,635.

---

## Bottom line

1. **Length is the dominant driver of victory, and it explains most of the formatting story.** Among 5,052 decisive votes with full answers, a one-log-unit increase in relative answer length adds **+9.5 percentage points** of win probability (coefficient 0.138, §3.2). The longer answer wins **63.8%** of decisive votes.
2. **Once length is held constant, cosmetic formatting mostly evaporates.** Bold — the single most-cited "winning format" in the shortlist report — has a length-adjusted effect of **−0.3pp (p = 0.85)**, and the census's near-equal-length +7.7pp bold advantage **fails to replicate** in the two larger near-equal samples (+0.6pp, p = 1.00; −1.4pp, p = 0.48). Bullets, numbered lists and emoji are likewise indistinguishable from zero.
3. **What survives length control is evidence density and legibility, not decoration:** numbers/dates **+6.5pp** (p < 1e-5), citations/links **+5.7pp** (p = 0.013), Markdown section headers **+4.1pp** (p = 0.0003), named institutions **+3.5pp** (p = 0.014).
4. **Tone: flatter and slightly more negative wins.** With length controlled, a one-unit relative rise in VADER compound lowers win probability by **3.8pp** (p = 0.0017, n = 3,382 English decisive votes). Warm, upbeat answers lose.
5. **Validation theatre is not rewarded, but citing is.** Explicit "my knowledge cutoff is…" statements are symmetric between winners and losers (25 vs 29, p = 0.68) and self-validation markers lean null (55 vs 42, p = 0.22); citations/links favour winners (80 vs 53, p = 0.024).
6. **Sensitive prompts are the one place where answer content, not style, decides votes.** Across 45 Tiananmen votes, **14.8% of answers deflect** (5 refusals, 4 evasions, 3 party-line recitations, 1 denial) — **every one of them from a Qwen or DeepSeek model**, and **none from any other vendor in 88 answers**. Where one side deflected and the other answered, the answering side went **9 wins, 2 ties, 0 losses**.
7. **The "special interest" that is actually visible in this data is not a lobby — it is verbosity and state-aligned model behaviour.** Organized interest-group advocacy barely exists in arena prompts (31 business-lobby, 12 union, 6 gun, 2 media-owner prompts in 63,635). What is measurable and consequential is (a) a systematic length premium, (b) a legibility premium, and (c) a vendor-specific refusal regime on Chinese political topics that voters reliably punish.

---

## 1. What is in the data (Q1: prompt categories)

### 1.1 Coverage

| Set | Votes | Sessions | Models | Tie | Both bad | Decisive | English | Code |
|---|---|---|---|---|---|---|---|---|
| 63,635 flagged | 63,635 | 56,352 | 53 | 15.4% | 11.0% | 73.6% | 75.1% | 33.6% |
| 6,820 with full answers | 6,820 | 6,357 | 52 | 14.9% | 11.0% | 74.1% | 66.9% | 14.5% |
| 2,235 strict-tier census | 2,235 | 2,145 | 52 | 13.9% | 13.3% | 72.8% | 67.0% | 12.1% |

The census is more contested than the corpus: ties and both-bad are both higher (13.9% / 13.3% vs 15.4% / 11.0%),
because political prompts are where voters most often find both answers unacceptable.

### 1.2 How political is the arena, really?

Three different measurements disagree, and the honest answer is a range (`scale_summary.json`,
`strict_tier_handcheck_30.csv`):

| Measure | Share of 63,635 | Comment |
|---|---|---|
| ≥1 political `categories` tag (upstream tagger) | **16.7%** | upper bound — the tagger is context-free, see below |
| explicit political vocabulary in the prompt (8-language lexicon) | **6.2%** | lower bound — covers only languages I coded |
| `prompt_tier ∈ {strict, probable}` | **4.6%** | the dataset's own tier field |

I hand-checked 30 randomly drawn `strict`-tier prompts (`strict_tier_handcheck_30.csv`): **14 clearly political, 2
politics-adjacent (UK visa, labour dispute), 14 false positives**. The false positives are instructive — "What's the
deal with everyone in finance being a 'Vice President'" is tagged `political_figures` + `public_policy`; "how can I
make the seeker inside a transparent blue ice block" is tagged `parties_ideology` + `voting`; "How does LMArena
voting work" is tagged `public_policy` + `voting`. The tagger fires on *words* (`vote`, `finance`, `president`,
`government`) regardless of context.

**Revised estimate: roughly 5–10% of arena votes are political prompts, best single estimate ~8%.** The earlier
report's "16.7% political" figure should be read as a tagged upper bound, not a measurement. This matters for the
substantive framing: political deliberation is a *minority* use of the arena, which is itself a finding — the corpus
is dominated by coding (33.6%) and personal/creative tasks.

The tier noise is close to classical misclassification and does not drive the aggregate results: I rebuilt the two
headline tests on the 1,926-vote explicit-politics lexicon set and both replicate (§3.3).

### 1.3 Topic mix (census, `topic_stats_census.csv`)

| Topic | Votes with answers | Tie | Both bad | Mean prompt chars |
|---|---|---|---|---|
| public_policy | 628 | 15.9% | 10.0% | 1,995 |
| geopolitics_conflict | 453 | 13.9% | 9.9% | 860 |
| other_personal (politics-adjacent) | 441 | 12.2% | 11.1% | 2,525 |
| elections_voting | 425 | 10.4% | 14.4% | **5,641** |
| civic_practical | 419 | 14.8% | 10.5% | 3,610 |
| media_info | 385 | 13.0% | **15.1%** | 2,850 |
| creative_roleplay | 329 | 16.1% | 10.0% | 1,396 |
| business_tech | 840 | 13.1% | 10.7% | 1,658 |
| parties_ideology | 266 | 15.8% | 6.8% | 1,969 |
| political_figures | 244 | 10.7% | **24.2%** | 688 |
| immigration | 239 | 10.0% | 14.6% | **7,813** |
| political_history | 233 | 15.4% | 14.2% | 1,061 |
| political_theory | 196 | 14.8% | 9.2% | 2,126 |
| institutions_constitution | 139 | 15.1% | 6.5% | 2,654 |

Two structural observations:

- **`political_figures` is the both-bad capital of the corpus (24.2%).** Short "who is X / what did Y say" prompts with a 688-character mean are the single most likely to produce two unsatisfactory answers — a factuality failure mode, not a style failure mode.
- **`immigration` and `elections_voting` have absurd mean prompt lengths (7,813 and 5,641 chars)** because they are dominated by multi-turn sessions where every prior turn is re-sent. Turn-level deduplication is required before any prompt-length analysis of those topics; I do not use prompt length as a predictor anywhere below for this reason.

### 1.4 Issue-domain counts (63,635 votes, `issue_domain_counts_63635.csv`)

| Domain (keyword) | Votes | Share of all | Share of explicit-politics set |
|---|---|---|---|
| China-related | 757 | 1.19% | 19.1% |
| India | 660 | 1.04% | 16.7% |
| War / conflict | 579 | 0.91% | 14.6% |
| US institutions/actors | 461 | 0.72% | 11.7% |
| Elections / voting | 421 | 0.66% | 10.6% |
| Labour / unions | 404 | 0.63% | 10.2% |
| Ukraine / Russia | 390 | 0.61% | 9.9% |
| EU | 161 | 0.25% | 4.1% |
| Israel / Gaza | 151 | 0.24% | 3.8% |
| Immigration | 150 | 0.24% | 3.8% |
| Climate / energy | 103 | 0.16% | 2.6% |
| Tariffs / trade | 100 | 0.16% | 2.5% |
| Healthcare | 100 | 0.16% | 2.5% |
| Welfare / social policy | 63 | 0.10% | 1.6% |
| Brazil | 60 | 0.09% | 1.5% |
| Taxes / budget | 50 | 0.08% | 1.3% |
| Media trust / misinformation | 36 | 0.06% | 0.9% |
| AI regulation | 25 | 0.04% | 0.6% |
| Gun policy | 6 | 0.01% | 0.2% |
| Abortion | 4 | 0.01% | 0.1% |

**China is the single largest political subject in the corpus**, ahead of India, war, and US domestic politics. That
single fact motivates §5.

### 1.5 Recursive prompts

Exact-string repetition is low but real, and the top repeats are diagnostic
(`results_scale/prompts_all_labels.csv`): a 66-citizen salary puzzle (14 votes — a false positive of the strict
screen), a tariff-calculation question (12), a 🦹 "trusted confidant" jailbreak template (12), "wie won de
amerikaanse verkiezingen?" (8, Dutch), a French satirical-sketch request (8), a dietary-recommendation prompt (8).
The recurring pattern is **template prompts replayed across many voters**, not organized campaigns: no prompt family
exceeds ~0.6% of the corpus, and none shows the burst structure of coordinated activity.

---

## 2. Method

### 2.1 Measurement choices

- **Full text only.** All answer features are computed on untruncated `assistant_a` / `assistant_b` from `conversations.jsonl.gz`. Excerpt-level (420-char) measurement, which the shortlist pipeline used, understates structure and inflates negativity (VADER 0.22 on excerpts vs 0.50 on full text).
- **Paired tests.** Every style claim is a McNemar-style comparison of *the same voter's* two answers: winner-only vs loser-only discordant pairs, exact binomial two-sided p. This removes prompt difficulty and voter harshness as confounders.
- **Length control.** Two independent strategies: (a) restriction — decisive votes with answer-length ratio in [0.9, 1.111]; (b) regression — linear probability model of "A won" on log(length_A/length_B) plus the feature difference, HC1 standard errors, n = 5,052 decisive votes (`length_adjusted_effects_6820.csv`). The two agree except where noted.
- **Robustness set.** The 1,926-vote explicit-politics lexicon set, built independently of the dataset's tier field, to show results are not artefacts of the upstream tagger (§1.2).

### 2.2 What is *not* gold

- `categories`, `prompt_tier`, `response_tier`, `basis` are **upstream screening labels**, keyword-driven, ~47% precise on my 30-prompt check.
- Style features are regex lexicons (`lexicons.py`, extended in `scale.py`), not human annotations.
- VADER is a general-purpose lexicon; it misreads policy language (“sanctions”, “strike”, “cut”) and is only valid comparatively, within pairs.
- No claim of a global accuracy rate. The earlier 46-claim audit in `REPORT.md` is a hand sample and stays a hand sample.

---

## 3. What the winning answer contains (Q2)

### 3.1 Length

| Set | Decisive | Longer answer won | Median ratio | Median winner | Median loser | Ratio >1.2 | Ratio <0.8 |
|---|---|---|---|---|---|---|---|
| census (2,235) | 1,627 | **59.8%** | 1.247 | 2,645 chars | 1,874 chars | 51.4% | 28.8% |
| all with answers (6,820) | 5,052 | **63.8%** | 1.309 | 3,173 chars | 2,316 chars | 54.5% | 25.2% |

Length-adjusted premium: **+9.5pp per doubling of relative length** (log-ratio coefficient 0.138, HC1, n = 5,052).
Median answer is 302 words.

By topic, the longer answer wins (`length_by_topic_census.csv`): political_theory 71.7%, parties_ideology 66.9%,
institutions 63.5%, public_policy 62.6%, geopolitics 62.1%, civic_practical 62.1%, business_tech 58.9%, immigration
59.8%, elections 56.2%, political_figures 56.5%, political_history 55.6%, **other_personal 50.4%**.

The gradient is the interesting part: length pays most where the task is *analytical* (theory, ideology,
institutions) and least where the task is *personal/relational*, where a long answer reads as evasion. Political
history is the weakest political topic (55.6%) — chronological narrative seems to be rewarded for accuracy, not bulk.

### 3.2 Formatting: the length-control correction

**Uncontrolled (census, n = 1,627 decisive, `feature_tests_census.csv`)** — this is what a naive analysis finds:

| Feature | Winner | Loser | p |
|---|---|---|---|
| bold | 75.5% | 68.1% | <1e-4 |
| bullets | 70.3% | 61.8% | <1e-4 |
| headers | 46.3% | 37.5% | <1e-4 |
| numbers/dates | 44.8% | 39.2% | <1e-4 |
| emoji | 14.5% | 8.9% | <1e-4 |
| numbered list | — | — | 0.0002 |
| named institution | — | — | 0.0018 |
| alarm language | — | — | 0.0004 |
| Null: hedge 0.44, second person 0.70, question-to-user 0.57, example 0.83, counterargument 0.60, links 0.62 |

**Length-adjusted (n = 5,052, `length_adjusted_effects_6820.csv`)** — this is what survives:

| Feature | Effect on win probability | p | Verdict |
|---|---|---|---|
| numbers / dates | **+6.5pp** | <1e-5 | robust |
| citations / links / sources | **+5.7pp** | 0.013 | robust |
| Markdown headers | **+4.1pp** | 0.0003 | robust |
| named institution | **+3.5pp** | 0.014 | robust |
| both-sides framing | +1.1pp | 0.78 | null |
| numbered list | +0.8pp | 0.46 | null |
| bullets | +0.3pp | 0.79 | null |
| **bold** | **−0.3pp** | 0.85 | **null — was a length artefact** |
| hedge | −0.4pp | 0.83 | null |
| disclaimer ("as an AI", "consult a professional") | −6.4pp | 0.12 | negative, underpowered |

**Near-equal-length replication** (`feature_tests_near_equal_length.csv` and the two larger replication samples):

| Sample | n | bold | numbered | both-sides | disclaimer |
|---|---|---|---|---|---|
| census near-equal | 182 | +7.7pp (**p = 0.029**) | +5.5 (p = 0.23) | −5.0 (p = 0.064) | −5.0 (**p = 0.012**) |
| explicit-politics near-equal | 164 | **+0.6 (p = 1.00)** | +6.1 (p = 0.25) | −3.7 (p = 0.38) | −3.1 (p = 0.063) |
| all-votes near-equal | 569 | **−1.4 (p = 0.48)** | +5.3 (**p = 0.046**) | −3.5 (**p = 0.042**) | −1.1 (p = 0.18) |

**Correction to the shortlist report.** The 1,500-row report claimed bold increased win probability (p = 0.022), and
that claim propagated into the §3.2 census table above. It does not hold up: with length controlled in 5,052 votes
bold is −0.3pp, and the one near-equal sample that showed +7.7pp is contradicted by both larger samples. What is
left of "formatting" is the legibility bundle — numbers, citations, headers, institutions — plus a modest, only
sometimes-significant penalty for explicit disclaimers and both-sides hedging.

### 3.3 Recency, validation, citations (`scale_summary.json → recency_validation_citations`)

| Marker | Share of answers | Winner-only | Loser-only | p |
|---|---|---|---|---|
| "my knowledge cutoff / as of my training" | 2.5% | 25 | 29 | 0.68 |
| self-validation ("this is accurate / correct") | 5.1% | 55 | 42 | 0.22 |
| citation / link / named source | 6.3% | 80 | 53 | **0.024** |

On the independent 1,926-vote lexicon set the citation effect is stronger: **68 vs 37, p = 0.003**.

Recency pressure is real but modest: 7.7% of answers mention "2025", rising to 11% for votes after 1 May 2025;
32.4% mention any year at all. **There is no sycophancy signature in the recency data** — models that announce their
cutoff do not win more (25 vs 29), and models that assert their own correctness do not win more (55 vs 42). Voters do
not appear to reward either epistemic humility theatre or confidence theatre; they reward the answer that cites.

### 3.4 Sentiment (Q3)

Census, 1,498 English votes with full text (`sentiment_census_en.csv`): mean compound A 0.4977 / B 0.4662;
sentence-level mean 0.1476; 20.4% of answers score below −0.05. Paired winner − loser sentence compound = **−0.026**,
winner more negative in 540 votes vs 471 (p = 0.032).

Replication on all 3,382 decisive English votes: winner mean compound **0.4571** vs loser **0.4862**; with length
controlled, a one-unit relative rise in compound lowers win probability by **3.8pp** (p = 0.0017).

Topic gradient (sentence-level compound / share of answers below −0.05): political_history 0.014 / 0.343,
geopolitics 0.016 / 0.356, political_figures 0.030, elections 0.055, immigration 0.062 — versus business_tech 0.212.
The most negative-surfacing political topics are the ones with the highest both-bad rates; voters punish both
excessive alarm *and* excessive reassurance, and the corpus's most negative topics are its most failure-prone ones.

---

## 4. Fact-checking and historical accuracy (Q4)

Three separate measurements, deliberately not blended:

**(a) Verification language.** Only 6.3% of answers cite anything, and 2.5% state a cutoff. Arena answers are
overwhelmingly *unsourced prose*. The cite-more-wins result (§3.3) means the rare sourced answer is rewarded — but
the base rate is so low that the arena cannot be described as a fact-checking environment.

**(b) Hand claim audit (shortlist, `REPORT.md` §6).** 46 checkable claims: 19 correct, 23 wrong, 4 unresolvable. Both
answers wrong → both_bad in 5 of 8 decisive cases; one-sided-correct won 5 of 6. Small, hand-built, and not
extrapolable to 63,635 votes; it does suggest that when one answer is right and the other wrong, voters detect it.

**(c) Sensitive-topic audit at census scale** — the one place where content is measurable against ground truth.

### 4.1 Prompt counts (`sensitive_prompt_counts.csv`)

| Probe | Votes with prompt | Votes with answers | Languages |
|---|---|---|---|
| Taiwan status / sovereignty | 129 | 84 | 9 |
| Tiananmen / 1989 | 53 | 45 | 6 |
| Xi Jinping leadership | 20 | 19 | — |
| Holocaust | 13 | 11 | — |
| Tibet | 7 | 5 | — |
| Xinjiang / Uyghur | 3 | 2 | — |
| Armenian genocide | 3 | 1 | — |
| Nanking, Holodomor, Srebrenica | 0 | 0 | — |

### 4.2 Tiananmen: hand-coded, 45 votes / 90 answers (`sensitive_handcode_90.csv`)

Every one of the 90 answers was read in full and labelled. Coding scheme: `ANSWERS` (gives the substance),
`REFUSAL` (declines), `PARTY_LINE` (recites PRC state framing), `EVASION` (answers adjacent questions, omits the
event), `DENIAL` ("no such historical events"), `CLARIFIES` (asks which event / disambiguates), `OTHER_TOPIC`
(prompt matched by date or name but is not about Tiananmen — 2 Circle SEC-filing questions).

| Label | Answers | Share of 88 relevant |
|---|---|---|
| ANSWERS | 73 | 83.0% |
| REFUSAL | 5 | 5.7% |
| EVASION | 4 | 4.5% |
| PARTY_LINE | 3 | 3.4% |
| DENIAL | 1 | 1.1% |
| CLARIFIES | 2 | — |

**Deflections: 13 of 88 (14.8%)**, and they are **entirely a Chinese-vendor phenomenon**:

| Model | Deflections | Type |
|---|---|---|
| qwen3-30b-a3b | 4 | refusal ×2, evasion ×2 |
| qwen3-235b-a22b-no-thinking | 3 | evasion ×2, party line ×1 |
| deepseek-r1-0528 | 3 | party line ×3 |
| qwen3-235b-a22b | 2 | party line ×1, denial ×1 |
| qwq-32b | 1 | evasion |

**Zero deflections from Claude, GPT, Gemini, Grok, Llama, Mistral, Command, Nova, or Gemma** — 60+ answers from
other vendors all state the event. This is not a general "safety filter" story: it is a specific, vendor-scoped
information regime.

Deflection is also **language-conditioned**, in the direction you would predict:

| Prompt language | Answers | Answer rate |
|---|---|---|
| en | 30 | **100%** |
| ja | 2 | 100% |
| und | 14 | 71% |
| zh | 32 | 78% |
| zh-Hant | 10 | **60%** |

The same model that answers in English often declines or recites in Chinese — i.e. the behaviour is keyed to the
prompt's language, not to a fixed policy. (One caveat: the shortlist audit found a single `gemini-2.5-flash` refusal
on a *Tank Man photograph* image prompt. That vote is not in the 6,820 and cannot be re-verified here.)

**Vote outcomes.** Of 44 Tiananmen votes: 31 had two substantive answers, 2 had neither, and **11 were one-sided**
(one answer deflects, one answers). In those 11: **answering side won 9, tied 2, lost 0**. Voters never rewarded a
deflection. This is the cleanest available evidence that, for this audience, *content beats compliance*.

### 4.3 Taiwan status: a different failure mode (`sensitive_handcode_taiwan_20.csv`)

Auto-coding Taiwan answers for PRC framing is unreliable — the phrases appear inside neutrally reported positions
("Beijing asserts that Taiwan is an inalienable part of China"), so I hand-coded a random 20-vote subsample
(40 answers):

| Stance | Answers |
|---|---|
| BALANCED (presents the dispute, both claims attributed) | 17 |
| PRC_LINE (asserts Taiwan is part of China / not a country, boilerplate) | 7 |
| FACTUAL (answers the operational question — capital, presidents, history) | 5 |
| CRITIQUE_PRC_CLAIM | 2 |
| ANALYTIC / ASSERTS_NOT_PRC | 3 |
| OTHER_TOPIC | 6 |

**21% of substantive answers (7/34) are state-line boilerplate.** Two of the seven are near-identical PRC press
releases ("Taiwan is an inalienable part of China, and there is no such thing as a so-called 'capital'").

Vote outcomes in the subsample: **3 votes paired PRC_LINE against BALANCED — BALANCED won all 3**. Two votes had
PRC_LINE on both sides — the voters returned one `both_bad` and one `tie`. On the auto-coded full 84 votes, the 17
discordant PRC-vs-non-PRC votes split 7–7–3, i.e. no detectable advantage either way.

So Tiananmen and Taiwan are **two different phenomena**, and conflating them is the mistake to avoid:

- **Tiananmen:** near-total compliance from Western vendors, near-total deflection from Qwen/DeepSeek, strongly language-conditioned, and **deflection never wins**. A censorship/refusal story.
- **Taiwan:** PRC framing appears across many vendors (Nova, Gemma, Command, Gemini, Llama as well as Qwen/DeepSeek), usually as one voice among several, and **it does not win votes; when it is the only thing on offer, voters reject both answers**. A state-media-style *training data* story, not a refusal story.

---

## 5. Special interests worth further study

Ranked by evidence strength, not by rhetorical appeal. Vote counts and effect sizes are as measured above; where a
finding is a keyword count, it is labelled as such.

**1. The length premium (special interest: whoever can afford output tokens).** +9.5pp per doubling; 63.8% of decisive
votes go to the longer answer; holds in every political topic. There is no organized constituency for verbosity, but
the *distributional* consequence is identical to regulatory capture: evaluation systems that reward length select for
models whose cost profile favours long outputs, and they penalize terse, correct answers. This is the single most
policy-relevant finding in the dataset and it is robust to every control I can run locally.

**2. Legibility over decoration.** Numbers/dates +6.5pp, citations +5.7pp, headers +4.1pp, named institutions
+3.5pp — and bold, bullets, emoji at zero. The winning answer looks like a **briefing note** (headed, dated,
attributed, sourced), not like a designed slide. Anyone building eval rubrics or training preferences from arena data
should expect the rubric to encode "briefing-note-ness".

**3. The negative-tone gradient.** Winners are flatter (0.457 vs 0.486) and slightly more negative (p = 0.0017 with
length control). Politics is the corpus's most negative domain, and its most negative topics are also its most
failure-prone. Worth a dedicated study: does negativity *cause* wins, or does it covary with the analytical register
that wins?

**4. Chinese-vendor information regimes (strongest content finding).** 14.8% of Tiananmen answers deflect, all from
Qwen/DeepSeek, and deflections lose 0–9–2 when paired with a direct answer. This is the cleanest measurement in the
corpus of a vendor-level policy that is (a) visible, (b) language-conditioned, and (c) *not* preferred by the
audience. It gives a template for auditing other vendor-scoped topics: Tibet, Xinjiang, Xi leadership, Nanking have
too few votes here (3, 3, 20, 0) to replicate at this extract size — that is the top data request if more votes
become available.

**5. State-line boilerplate in training data (Taiwan).** 21% of Taiwan answers are PRC boilerplate, spread across
many vendors — evidence that state framing enters through training corpora, not through API filters. Voters do not
reward it. This is a training-data-provenance story and deserves a dedicated, larger probe (84 votes here).

**6. The absence of organized interest groups.** Keyword counts across 63,635 prompts: tech platforms 1,215, NGOs
and think tanks 164, business lobbies 31, finance 30, pharma 27, religious 25, unions 12, guns 4, fossil fuels 3,
media owners 2, ethnic/foreign lobbies 1. Even allowing for heavy false-positive inflation in the tech-platform
count (any mention of "Google", "Meta", "platform", "algorithm"), **classic organized interests are essentially
absent from arena prompts** — two orders of magnitude below technology. The finding is the *asymmetry*: the arena is
a venue where platform/technology interests are discussed constantly and where unions, gun groups, industry
associations, and religious lobbies are nearly invisible. Whether that reflects the user base or the modality is an
open question this data cannot answer.

**7. Model-level reproduction.** Win-rate ranks in the 1,500-row shortlist and the 2,235-vote census correlate at
**0.900 across 41 models** (`model_rank_comparison.csv`), so the *ordering* is a real property of the data, not
sampling noise — but magnitudes move a lot. Census leaders: grok-4-0709 78.1% (64 decisive), gemini-2.5-pro 73.1%
(453), chatgpt-4o-latest 66.6% (290), deepseek-r1-0528 66.4% (315), o3 65.9% (390), gemini-2.5-flash 61.8% (359).
Trailers: mistral-small-3.1 19.6% (97), llama-3.3-70b 26.4% (167), claude-3-5-haiku 27.5% (222). Note that
`deepseek-r1-0528` is a top-quartile model *and* the source of three party-line Tiananmen recitations — competence
and compliance are orthogonal here, which is itself worth studying.

**8. Both-bad geography.** `political_figures` at 24.2% both-bad is the corpus's factuality failure mode: short
lookup questions about people. Media/information prompts are next (15.1%). Any "which topics can models not handle"
study should start there, not with the stylometric features.

---

## 6. Limitations

- **No new data.** The 140k source is unreachable; 63,635 prompts and 6,820 full-answer votes are the ceiling of what can be measured here.
- **Answer-content analyses cover 11% of votes.** The 6,820 are the most politically dense subset (52.9% political-tagged vs 16.7% overall), so length and style effects are estimated on a political-heavy subsample and may not generalize to coding or creative tasks.
- **Upstream labels are screens, not gold** (~47% precision on my 30-prompt check). All headline results are replicated on an independently built lexicon set, but topic-level percentages inherit this noise.
- **Regex style features and VADER** are crude instruments; they can establish direction and relative magnitude, not fine-grained stylistic claims.
- **Hand codings are single-coder** (90 Tiananmen answers, 20 Taiwan votes, 30 tier prompts, 46 claims). No inter-coder reliability statistic exists; counts are exact, interpretation is mine.
- **No bootstrap CIs** on most estimates; tests are exact McNemar/binomial where paired, HC1 OLS where adjusted. With 34 features tested across several samples, one or two nominal p ≈ 0.03 results are expected by chance — which is precisely why the bold result was retired.
- **Multi-turn prompts are re-sent in full**, so prompt-length statistics for `immigration` and `elections_voting` are inflated and unused.

## 7. Reproduce

```bash
cd arena/interest_analysis
python3 scale.py          # writes results_scale/ (~140 s): coverage, length, features, near-equal
                          # tests, recency/citations, sentiment, sensitive probes, topics, models
```

Outputs referenced above, all in `arena/interest_analysis/results_scale/`:

| File | Contents |
|---|---|
| `coverage.csv` | the four sets, their rates and date ranges |
| `length_summary.csv`, `length_by_topic_census.csv` | length effects |
| `feature_tests_census.csv`, `feature_tests_near_equal_length.csv` | paired style tests |
| `length_adjusted_effects_6820.csv` | length-controlled LME-style effects, n = 5,052 |
| `recency_validation_citations` (in `scale_summary.json`) | cutoff/validation/citation tests |
| `sentiment_census_en.csv`, `sentiment_by_topic_census.csv`, `sentiment_all_en_6820.csv` | tone |
| `sensitive_prompt_counts.csv`, `sensitive_handcode_90.csv`, `sensitive_summary_45votes.json`, `sensitive_handcode_taiwan_20.csv` | sensitive probes |
| `issue_domain_counts_63635.csv`, `topic_stats_census.csv` | prompt categories |
| `model_stats_census.csv`, `model_rank_comparison.csv` | model-level results |
| `strict_tier_handcheck_30.csv` | hand-check of the upstream tier labels |
