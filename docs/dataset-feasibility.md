# Can `lmarena-ai/arena-human-preference-140k` support a study of human preference votes on public-interest topics?

**Short answer.** Yes for a narrow question — *"which model responses do users prefer when they ask about public-interest subjects?"* No, not as released, for *"what does the public think about these subjects?"* The blocker is not sample size, it is that the dataset contains **no voter attributes and no stance labels**. Every vote is a relative quality judgment between two anonymous-at-collection-time models answering one self-selected prompt.

This memo records what the data actually contains (verified against the dataset card), which framings are viable, and the specific confounds to control before any number from it should be believed.

---

## 1. What the release actually contains

| Field | Type | Notes for this study |
|---|---|---|
| `id` | string (uuid) | one row = one vote |
| `model_a`, `model_b` | string, 53 values | **models are de-anonymized** in this release |
| `winner` | `model_a` \| `model_b` \| `tie` \| `both_bad` | 4 classes; `both_bad` is its own outcome, not a tie |
| `evaluation_session_id` | string (uuid) | ~115k sessions for 135,634 votes → pseudo-rater, **within one sitting only** |
| `evaluation_order` | int, 1–28 | `>1` means prior turns exist; topic of the vote may be set by turn 1 |
| `conversation_a`, `conversation_b` | list of turns | full text of both responses in this order |
| `full_conversation` | list of turns | includes prior-order context (models are **re-sampled** each order) |
| `conv_metadata` | dict | token counts, header/list/bold counts → style control |
| `category_tag` | dict | `math`, `creative_writing`, `instruction_following`, `criteria_v0.1` (complexity, creativity, domain_knowledge, problem_solving, real_world, specificity, technical_accuracy). **No topic tags.** |
| `language` | string, 126 values | |
| `is_code` | bool | |
| `timestamp` | timestamp, 2025-04-17 → 2025-07-24 | a single ~14-week window |

- 135,634 rows, 1.61 GB, one `train` split.
- License: user prompts CC-BY-4.0; **model outputs are governed by the respective providers' terms of use** — this constrains redistributing response text, not analyzing it.
- There is no `is_refusal` column (the older 100k release had one), so refusal/hedging behavior must be derived with a judge.

**The single most important gap:** `category_tag` is a capability/quality taxonomy. "Public interest" is not in it and is not derivable from it. Any topic conditioning is work you do yourself.

---

## 2. Feasibility by framing

| Framing | Verdict | Why |
|---|---|---|
| **A. Topic-conditional model quality / leaderboard.** Which models win more often on climate, health, elections prompts; how tie and `both_bad` rates differ from the global baseline. | **Viable** | Topic can be labeled from the first user turn; outcome is already there; style covariates exist; model identity is known. |
| **B. "What do people prefer models to say about X?"** e.g. do users prefer responses that hedge on a contested policy, or that take a confident side. | **Viable only with extra annotation** | You must judge each response for stance/hedging, then regress `winner` on the stance *difference* within a battle. Doable, ~2×135k judge calls if you label everything; sampling is cheaper. |
| **C. Public opinion about issues** ("voters on the left prefer…", "Americans think…"). | **Not supported** | No demographics, no country, no stable cross-session rater ID, no survey weights, no stance vote. `evaluation_session_id` is an anonymous sitting, often a single vote, not a person you can characterize. |
| **D. Trend/event study** (pre/post an election, a policy event, a model release). | **Weak** | 14 weeks, one release, and the model lineup changes within the window, so any time trend is confounded with which models were live. The older `arena-human-preference-100k` has `tstamp` + `question_id` and a longer span if calendar time matters. |
| **E. Cross-language / cross-region comparison.** | **Partly** | 126 languages, and `language` is the best available proxy for audience. But per-language × per-topic cells get thin fast, and language ≠ country ≠ political lean. |

---

## 3. Threats to validity, and what to do about each

1. **Self-selected prompts, not a sample of the public.** Users bring their own questions. Prevalence of a topic here measures *what this user base asks*, not what the public cares about. Do not report topic shares as "public interest". Mitigation: frame every estimate as conditional on the prompt distribution; never weight to a population you cannot construct.
2. **Preference ≠ agreement.** A vote means "B was more helpful/correct/pleasant for my prompt", not "B matches my politics". If model A argues for a policy and B against it, the winner mostly reflects confidence, structure, and detail. Mitigation: only make stance claims with the response-level annotation in framing B, and validate a few hundred by hand.
3. **Style and length confounds.** Verbosity and markdown formatting move votes substantially on this kind of data. `conv_metadata` gives you `sum_assistant_*_tokens`, header counts, list counts, bold counts per side. Mitigation: include token-count and markdown-feature differences as covariates, or run the style-controlled variant of the ranking.
4. **Position bias.** Small but real, and detectable in-sample. Mitigation: estimate the A-side advantage directly from your subset (share of decided battles won by `model_a`, with a binomial test) and include a side term; also check it separately per topic, since it can differ.
5. **Model-mix confounding.** A topic's apparent winner may just be the stronger model. Mid-window model launches mean a topic over-represented in July is judged by a different lineup than one over-represented in April. Mitigation: topic × model-pair fixed effects, or compare only within battles where both models appear in both topics.
6. **Multi-vote sessions are not independent.** Users cast up to 28 votes in a session, and later turns inherit earlier context. Mitigation: cluster bootstrap CIs by `evaluation_session_id`; report `evaluation_order == 1` results as the clean primary specification and multi-turn as a robustness check.
7. **Topic label error is the dominant bias risk.** A regex or embedding classifier on 500-token prompts will misfire on irony, comparisons ("is X policy better than Y?"), and non-English text. Mitigation: pre-register the taxonomy and the classifier, hand-check ≥150 sampled prompts per topic, report precision, and report results under two labelers.

---

## 4. Power: do the arithmetic before you commit

135,634 votes sounds ample; topic conditioning divides it fast.

- If public-interest prompts are 5–10% of the corpus, that is roughly **7k–14k votes**.
- Across ~10 policy domains, that is **~700–1,400 votes per domain**, spread over 53 models and 126 languages.
- At ~1,000 battles per domain, a given model appears in maybe 30–60 of them. That is enough to compare a handful of models on a topic, **not** enough to rank 53 models per topic, and nowhere near enough to slice by language.

Practical consequence: design around **pooled contrasts** (does topic X favor long/hedged/confident answers; do tie and `both_bad` rates shift by topic) rather than per-model-per-topic leaderboards. Decide the comparison set up front — e.g. the 8–10 models with the most battles — instead of all 53.

---

## 5. Recommended design if you proceed

1. **Pre-register** a taxonomy of 8–12 public-interest domains and the inclusion rule (first user turn only, `evaluation_order == 1`, non-code, length ≥ N tokens).
2. **Two-stage labeling:** cheap keyword/embedding prefilter → LLM or human adjudication on the candidates. Keep a held-out hand-labeled set of ~500 to report precision/recall. Store labels in a versioned file, not inline in the analysis script.
3. **Primary outcomes:** (a) `both_bad` rate, (b) `tie` rate, (c) side-adjusted Bradley–Terry ratings per domain for the pre-selected model set, (d) optional stance/hedging annotation for framing B.
4. **Controls:** token and markdown deltas from `conv_metadata`, `model_a` side term, `language == "en"` as a separate stratum, `category_tag.criteria_v0.1.domain_knowledge` / `real_world` as capability controls.
5. **Inference:** cluster bootstrap by `evaluation_session_id`, 1,000+ resamples; report CIs, not just point estimates.
6. **Report the negative controls:** the same pipeline on a non-political capability tag (e.g. `math`) should reproduce known leaderboard ordering — if it does not, the pipeline is broken.

Implemented in this repo:

- `scripts/topic_prevalence.py` — steps 1–2 triage: schema, first-turn prompts, a `v0.1`
  domain lexicon, per-domain coverage and tie / `both_bad` / position descriptives. No
  controls, no CIs.
- `scripts/build_topics.py` — writes the label file and a stratified hand-check sample
  (`handcheck_sample.csv`) for measuring lexicon precision.
- `scripts/fit_topic_bt.py` — steps 3–6: one joint logistic model with shared Bradley–Terry
  strengths, topic×model deviations, a slot-A term, and style covariates; cluster bootstrap
  over sessions; `--simulate` validates parameter recovery on synthetic data.

Specification and validation details: [`topic-bt-model.md`](topic-bt-model.md). Its
simulation implies that at ~9,000 battles per topic with 10 models, per-cell topic deltas
carry roughly ±0.12 log-odds (≈ ±20 Elo) of error — plan for large effects only.

---

## 6. Honest bottom line

- The dataset **can** answer: *"On public-interest prompts, which responses do arena users prefer, and does that differ from ordinary prompts in ways beyond length and formatting?"*
- The dataset **cannot** answer: *"What does the public prefer politically?"* — the votes are about answer quality, and the voters are unobservable. Any paper that reports this dataset as evidence of public opinion on issues is misusing it.
- If the target is genuinely public opinion on issues, the right instrument is a **purpose-built stimulus set** — same prompt, controlled divergent stances, same models — collected through side-by-side voting or a survey panel. This corpus can supply the prompts and the model pairs for that instrument.
