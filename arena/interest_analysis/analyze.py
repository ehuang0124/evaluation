#!/usr/bin/env python3
"""Descriptive analysis of the Arena political shortlist (n=1,500 votes).

Answers four research questions on the checked-in ``arena/results/shortlist.csv``
plus one screening question ("what is worth studying next?"):

  Q1  which prompt categories recur, and how do they vote?
  Q2  what is inside the *preferred* answer (structure / substance markers)?
  Q3  what sentiment and register do the answers carry?
  Q4  how fact-bearing are the answers, and are the checkable ones right?

Usage
-----
    python arena/interest_analysis/analyze.py \
        --csv arena/results/shortlist.csv \
        --out arena/interest_analysis/results

Outputs (all small, text/JSON/PNG):
    overview.json              corpus profile + vote baselines
    prompt_topics.csv          per-row auto topic/intent labels
    topic_stats.csv            topic frequency, win/tie/both_bad rates
    answer_features.csv        per-row winner-vs-loser feature deltas
    feature_tests.csv          McNemar tests on answer features
    model_stats.csv            per-model win/tie/both_bad + Bradley-Terry
    sentiment.csv              per-row sentiment + paired differences
    specificity.csv            per-row fact-bearing proxies
    sensitive_audit.csv        sensitive-history probe rows for manual coding
    figures/*.png              four summary charts
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from lexicons import (
    EPISTEMIC,
    INTEREST_GROUPS,
    INTENTS,
    SENSITIVE,
    STRUCTURE,
    TOPICS,
)

ENG = "en"


# --------------------------------------------------------------------- helpers
def rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE | re.MULTILINE)


def comp(d: dict[str, str]) -> dict[str, re.Pattern]:
    return {k: rx(v) for k, v in d.items()}


TOPIC_RX, INTENT_RX = comp(TOPICS), comp(INTENTS)
FEAT_RX = {**comp(STRUCTURE), **comp(EPISTEMIC)}
IG_RX, SENS_RX = comp(INTEREST_GROUPS), comp(SENSITIVE)


def labels(text: str, rxmap: dict[str, re.Pattern]) -> list[str]:
    if not isinstance(text, str):
        return []
    return [name for name, r in rxmap.items() if r.search(text)]


def features(text: str) -> dict[str, int]:
    return {name: int(bool(r.search(text))) for name, r in FEAT_RX.items()}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value for discordant counts b, c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2**n
    return min(1.0, 2 * tail)


def bradley_terry(pairs: list[tuple[str, str]], iters: int = 400) -> dict[str, float]:
    """MM / Zermelo iteration for Bradley-Terry strengths from (winner, loser)."""
    models = sorted({m for p in pairs for m in p})
    idx = {m: i for i, m in enumerate(models)}
    w = np.zeros(len(models))
    n = np.zeros((len(models), len(models)))
    for win, lose in pairs:
        w[idx[win]] += 1
        n[idx[win], idx[lose]] += 1
        n[idx[lose], idx[win]] += 1
    p = np.ones(len(models))
    for _ in range(iters):
        num = w.copy()
        den = np.array([sum(n[i, j] / (p[i] + p[j]) for j in range(len(models)) if n[i, j])
                        for i in range(len(models))])
        new = np.where(den > 0, num / np.maximum(den, 1e-12), 1e-9)
        new = np.maximum(new, 1e-9)
        p = new / new.sum()
        p = p * len(models)
    return {m: float(p[idx[m]]) for m in models}


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ["prompt_excerpt", "response_a_excerpt", "response_b_excerpt", "categories"]:
        df[col] = df[col].fillna("")
    df["n_cat_tags"] = df["categories"].str.count(r"\|") + (df["categories"] != "").astype(int)
    df["prompt_chars"] = df["prompt_excerpt"].str.len()
    df["ts"] = pd.to_datetime(df["timestamp"])
    df["month"] = df["ts"].dt.to_period("M").astype(str)
    df["political_prompt"] = df["prompt_tier"].isin(["strict", "probable", "broad"])
    df["lang_group"] = np.where(df["language"] == ENG, "en",
                       np.where(df["language"] == "zh", "zh", "other"))
    return df


# ------------------------------------------------------------------ Q1: topics
def q1_topics(df: pd.DataFrame, out: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    ctx = df["prompt_excerpt"] + " \n " + df["response_a_excerpt"] + " \n " + df["response_b_excerpt"]
    df["topics"] = ctx.map(lambda t: "|".join(labels(t, TOPIC_RX)))
    df["prompt_topics"] = df["prompt_excerpt"].map(lambda t: "|".join(labels(t, TOPIC_RX)))
    df["intents"] = df["prompt_excerpt"].map(lambda t: "|".join(labels(t, INTENT_RX)))
    df["interest_groups"] = ctx.map(lambda t: "|".join(labels(t, IG_RX)))
    df["sensitive"] = ctx.map(lambda t: "|".join(labels(t, SENS_RX)))
    # labels only: the excerpts already live in arena/results/shortlist.csv, so
    # this file stays small and does not duplicate model output text.
    df[["id", "evaluation_session_id", "tier", "basis", "prompt_tier", "winner",
        "topics", "prompt_topics", "intents", "interest_groups", "sensitive"]].to_csv(
        out / "prompt_topics.csv", index=False)

    rows = []
    for topic in TOPICS:
        m = df["topics"].str.contains(topic)
        sub = df[m]
        n = len(sub)
        if n == 0:
            continue
        a = (sub["winner"] == "model_a").sum()
        b = (sub["winner"] == "model_b").sum()
        tie = (sub["winner"] == "tie").sum()
        bad = (sub["winner"] == "both_bad").sum()
        dec = a + b
        lo, hi = wilson(dec, n) if n else (np.nan, np.nan)
        rows.append({
            "topic": topic,
            "rows": n,
            "share_of_rows": round(n / len(df), 4),
            "strict_prompt_rows": int(sub["prompt_tier"].eq("strict").sum()),
            "tie_rate": round(tie / n, 4),
            "both_bad_rate": round(bad / n, 4),
            "decisive_rate": round(dec / n, 4),
            "mean_screen_score": round(float(sub["score"].mean()), 2),
            "mean_prompt_chars": round(float(sub["prompt_chars"].mean()), 1),
        })
    topics_df = pd.DataFrame(rows).sort_values("rows", ascending=False)
    topics_df.to_csv(out / "topic_stats.csv", index=False)

    prows = []
    for topic in TOPICS:
        m = df["prompt_topics"].str.contains(topic)
        sub = df[m]
        if len(sub) == 0:
            continue
        prows.append({
            "topic": topic, "rows": len(sub),
            "share_of_prompts": round(len(sub) / len(df), 4),
            "strict_prompt_rows": int(sub["prompt_tier"].eq("strict").sum()),
            "tie_rate": round((sub["winner"] == "tie").mean(), 4),
            "both_bad_rate": round((sub["winner"] == "both_bad").mean(), 4),
        })
    prompt_topics_df = pd.DataFrame(prows).sort_values("rows", ascending=False)
    prompt_topics_df.to_csv(out / "prompt_topic_stats.csv", index=False)

    intent_rows = []
    for name in INTENTS:
        m = df["intents"].str.contains(name)
        sub = df[m]
        intent_rows.append({
            "intent": name,
            "rows": len(sub),
            "share": round(len(sub) / len(df), 4),
            "tie_rate": round((sub["winner"] == "tie").mean(), 4) if len(sub) else np.nan,
            "both_bad_rate": round((sub["winner"] == "both_bad").mean(), 4) if len(sub) else np.nan,
        })
    intents_df = pd.DataFrame(intent_rows).sort_values("rows", ascending=False)
    intents_df.to_csv(out / "prompt_intent_stats.csv", index=False)
    return topics_df, intents_df, prompt_topics_df


# ------------------------------------------------- Q2: preferred answer content
def q2_answer_features(df: pd.DataFrame, out: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    feats_a = pd.DataFrame([features(t) for t in df["response_a_excerpt"]], index=df.index).add_prefix("a_")
    feats_b = pd.DataFrame([features(t) for t in df["response_b_excerpt"]], index=df.index).add_prefix("b_")
    f = pd.concat([df[["id", "winner", "model_a", "model_b", "topics", "language"]], feats_a, feats_b], axis=1)
    f["chars_a"] = df["response_a_excerpt"].str.len()
    f["chars_b"] = df["response_b_excerpt"].str.len()
    f["chars_truncated"] = ((f["chars_a"] >= 419) | (f["chars_b"] >= 419)).astype(int)
    f.to_csv(out / "answer_features.csv", index=False)

    dec = f[f["winner"].isin(["model_a", "model_b"])].copy()
    dec["win_is_a"] = dec["winner"] == "model_a"
    rows = []
    for base in FEAT_RX:
        win = np.where(dec["win_is_a"], dec["a_" + base], dec["b_" + base])
        lose = np.where(dec["win_is_a"], dec["b_" + base], dec["a_" + base])
        only_win = int(((win == 1) & (lose == 0)).sum())
        only_lose = int(((win == 0) & (lose == 1)).sum())
        rows.append({
            "feature": base,
            "winner_rate": round(float(win.mean()), 4),
            "loser_rate": round(float(lose.mean()), 4),
            "delta_pp": round(100 * float(win.mean() - lose.mean()), 2),
            "winner_only": only_win,
            "loser_only": only_lose,
            "mcnemar_p": mcnemar_exact(only_win, only_lose),
            "n_decisive": len(dec),
        })
    tests = pd.DataFrame(rows).sort_values("delta_pp", ascending=False)
    tests.to_csv(out / "feature_tests.csv", index=False)
    return f, tests


# -------------------------------------------------------- Q4: fact-bearing proxy
def q4_specificity(df: pd.DataFrame, out: Path) -> pd.DataFrame:
    """Per-row proxies for checkable content and for hedging/citation behaviour."""
    rows = []
    for _, r in df.iterrows():
        rec = {"id": r["id"], "winner": r["winner"], "topics": r["topics"],
               "language": r["language"], "political_prompt": bool(r["political_prompt"])}
        for side in ("a", "b"):
            t = r[f"response_{side}_excerpt"]
            rec[f"{side}_years"] = len(re.findall(r"\b(1[5-9]\d{2}|20[0-2]\d)\b", t))
            rec[f"{side}_numbers"] = len(re.findall(r"\b\d{1,3}(?:[,\s]\d{3})*(?:\.\d+)?%?", t))
            rec[f"{side}_pct"] = len(re.findall(r"\d\s?%", t))
            rec[f"{side}_named_inst"] = len(set(m.group(0).lower() for m in
                                                 re.finditer(r"\b(Congress|Parliament|Supreme Court|UN|NATO|EU|"
                                                             r"IMF|World Bank|WHO|OPEC|FBI|CIA|Pentagon|White House|"
                                                             r"Kremlin|Ministry|Commission|Senate|House of Representatives)\b", t)))
            rec[f"{side}_cites"] = int(bool(re.search(r"\[\d+\]|https?://|according to|source:|"
                                                     r"as reported by|\([12]\d{3}\)", t, re.I)))
            rec[f"{side}_hedges"] = len(re.findall(r"\b(however|may|might|could|reportedly|allegedly|"
                                                   r"estimates?|approximately|roughly|arguably|unclear|"
                                                   r"disputed|contested)\b", t, re.I))
        rec["winner_more_years"] = (rec["a_years"] > rec["b_years"]) - (rec["a_years"] < rec["b_years"])
        rows.append(rec)
    spec = pd.DataFrame(rows)
    spec.to_csv(out / "specificity.csv", index=False)
    return spec


# -------------------------------------------------------------- Q3: sentiment
def q3_sentiment(df: pd.DataFrame, out: Path) -> pd.DataFrame:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    sia = SentimentIntensityAnalyzer()

    def score(t: str) -> dict[str, float]:
        s = sia.polarity_scores(t)
        return {"neg": s["neg"], "neu": s["neu"], "pos": s["pos"], "compound": s["compound"]}

    rows = []
    for _, r in df.iterrows():
        rec = {"id": r["id"], "winner": r["winner"], "language": r["language"],
               "lang_group": r["lang_group"], "topics": r["topics"]}
        for side in ("a", "b"):
            rec.update({f"{side}_{k}": v for k, v in score(r[f"response_{side}_excerpt"]).items()})
            t = r[f"response_{side}_excerpt"]
            rec[f"{side}_alarm_terms"] = len(re.findall(EPISTEMIC["alarm_language"], t, re.I))
            rec[f"{side}_moral_terms"] = len(re.findall(EPISTEMIC["moral_language"], t, re.I))
            rec[f"{side}_hedge_terms"] = len(re.findall(EPISTEMIC["hedge"], t, re.I))
            rec[f"{side}_empathy"] = int(bool(re.search(EPISTEMIC["empathy"], t, re.I)))
        rows.append(rec)
    sent = pd.DataFrame(rows)
    sent.to_csv(out / "sentiment.csv", index=False)
    return sent


# ------------------------------------------------------------- model standings
def model_table(df: pd.DataFrame, out: Path) -> pd.DataFrame:
    pairs = [(r.model_a, r.model_b) if r.winner == "model_a" else (r.model_b, r.model_a)
             for r in df.itertuples() if r.winner in ("model_a", "model_b")]
    bt = bradley_terry(pairs)
    rows = []
    for m in sorted(set(df["model_a"]) | set(df["model_b"])):
        sub = df[(df["model_a"] == m) | (df["model_b"] == m)]
        w = ((sub["model_a"] == m) & (sub["winner"] == "model_a")).sum() + \
            ((sub["model_b"] == m) & (sub["winner"] == "model_b")).sum()
        l = ((sub["model_a"] == m) & (sub["winner"] == "model_b")).sum() + \
            ((sub["model_b"] == m) & (sub["winner"] == "model_a")).sum()
        tie = (sub["winner"] == "tie").sum()
        bad = (sub["winner"] == "both_bad").sum()
        n = len(sub)
        lo, hi = wilson(w, w + l) if (w + l) else (np.nan, np.nan)
        rows.append({
            "model": m, "appearances": n, "wins": int(w), "losses": int(l),
            "ties": int(tie), "both_bad": int(bad),
            "decisive": int(w + l),
            "win_rate": round(w / (w + l), 4) if (w + l) else np.nan,
            "win_rate_lo": round(lo, 4), "win_rate_hi": round(hi, 4),
            "tie_rate": round(tie / n, 4), "both_bad_rate": round(bad / n, 4),
            "bt_strength": round(bt.get(m, np.nan), 4),
        })
    stats = pd.DataFrame(rows).sort_values("win_rate", ascending=False)
    stats.to_csv(out / "model_stats.csv", index=False)
    return stats


# ----------------------------------------------------- sensitive-prompt audit
def sensitive_audit(df: pd.DataFrame, out: Path) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        hits = [s for s, pat in SENS_RX.items() if pat.search(
            r["prompt_excerpt"] + " " + r["response_a_excerpt"] + " " + r["response_b_excerpt"])]
        if not hits:
            continue
        for side in ("a", "b"):
            t = r[f"response_{side}_excerpt"]
            rows.append({
                "id": r["id"], "probe": "|".join(hits), "language": r["language"],
                "tier": r["tier"], "side": side, "model": r[f"model_{side}"],
                "winner": r["winner"], "prompt": r["prompt_excerpt"][:160].replace("\n", " "),
                "excerpt": t[:420],
                # auto cues only; the coding column below is set by hand
                "cues_denial": int(bool(re.search(
                    r"no (major |significant |widely recorded )?(historical )?events?|"
                    r"nothing (significant|notable)|not aware of|"
                    r"did not (occur|happen)|is a (myth|fabrication)|"
                    r"not (a )?real|no such event|unverified|rumou?r", t, re.I))),
                "cues_refusal": int(bool(re.search(
                    r"i (can'?t|cannot|won'?t|am (not able|unable))|as an ai|"
                    r"敏感|敏感话题|不予|无法回答|政治敏感|请参考官方|官方发布|"
                    r"i must (decline|emphasize)|not appropriate|inappropriate", t, re.I))),
                "cues_partylines": int(bool(re.search(
                    r"中国共产党|中国政府|社会主义|中华民族伟大复兴|正确领导|"
                    r"坚决拥护|长治久安|和谐稳定|communist party of china (has|always)|"
                    r"the chinese government has always", t, re.I))),
                "cues_accurate": int(bool(re.search(
                    r"(tiananmen|六四|天安门)|1989", t, re.I))),
                "cues_toll": int(bool(re.search(
                    r"(hundreds|thousands|death toll|伤亡|死亡|killed|died|massacre|清场)", t, re.I))),
            })
    au = pd.DataFrame(rows)
    au.to_csv(out / "sensitive_audit.csv", index=False)
    return au


# ------------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="arena/results/shortlist.csv")
    ap.add_argument("--out", default="arena/interest_analysis/results")
    args = ap.parse_args()
    out = Path(args.out)
    (out / "figures").mkdir(parents=True, exist_ok=True)

    df = load(Path(args.csv))
    print(f"loaded {len(df)} rows")

    topics_df, intents_df, prompt_topics_df = q1_topics(df, out)
    feats, tests = q2_answer_features(df, out)
    sent = q3_sentiment(df, out)
    spec = q4_specificity(df, out)
    models = model_table(df, out)
    audit = sensitive_audit(df, out)

    # ------------------------------------------------- length (repo length file)
    # arena/results/short_answer_wins_tie_or_both_bad.csv holds true character
    # counts for the 417 decisive votes in the shortlist whose shorter answer won
    # or whose longer answer won by <5%; by construction it excludes long-answer
    # wins above 5%, so it also tells us how many of those exist.
    length = {}
    lf = Path("arena/results/short_answer_wins_tie_or_both_bad.csv")
    if lf.exists():
        L = pd.read_csv(lf)
        decisive_rows = int(df["winner"].isin(["model_a", "model_b"]).sum())
        short_win = int((L["inclusion_reason"] == "short_win").sum())
        near_equal = int((L["inclusion_reason"] == "near_equal_win").sum())
        long_win_5pct = decisive_rows - short_win - near_equal
        L["winner_chars"] = L["winner_chars"].astype(float)
        L["loser_chars"] = L["loser_chars"].astype(float)
        L["length_ratio"] = L["winner_chars"] / L["loser_chars"]
        length = {
            "decisive_votes": decisive_rows,
            "in_length_file": int(len(L)),
            "short_answer_wins": short_win,
            "longer_wins_under_5pct": near_equal,
            "longer_wins_5pct_or_more_derived": long_win_5pct,
            "share_decisive_to_longer_answer": round((long_win_5pct + near_equal) / decisive_rows, 4),
            "median_winner_to_loser_length_ratio_when_short_wins":
                round(float(L.loc[L["inclusion_reason"] == "short_win", "length_ratio"].median()), 3),
            "median_chars_winner_short_wins":
                round(float(L.loc[L["inclusion_reason"] == "short_win", "winner_chars"].median()), 0),
            "median_chars_loser_short_wins":
                round(float(L.loc[L["inclusion_reason"] == "short_win", "loser_chars"].median()), 0),
        }
        L[["id", "winner", "inclusion_reason", "winner_chars", "loser_chars",
           "length_ratio"]].to_csv(out / "length_analysis.csv", index=False)

    # tie / both_bad diagnostics
    tie_bad = {}
    for cat in ("tie", "both_bad"):
        sub = df[df["winner"] == cat]
        if len(sub) == 0:
            continue
        fa = pd.DataFrame([features(t) for t in sub["response_a_excerpt"]])
        fb = pd.DataFrame([features(t) for t in sub["response_b_excerpt"]])
        tie_bad[cat] = {
            "rows": int(len(sub)),
            "share_political_prompt": round(float(sub["political_prompt"].mean()), 4),
            "share_code": round(float(sub["is_code"].mean()), 4),
            "both_refusal": int((fa["refusal"].eq(1) & fb["refusal"].eq(1)).sum()),
            "one_refusal": int(fa["refusal"].ne(fb["refusal"]).sum()),
            "both_hedge_and_both_sides": int((fa["hedge"].eq(1) & fb["hedge"].eq(1) &
                                              fa["both_sides"].eq(1) & fb["both_sides"].eq(1)).sum()),
            "both_no_numbers_dates": int((fa["numbers_dates"].eq(0) & fb["numbers_dates"].eq(0)).sum()),
            "top_topics": sub["topics"].str.split("|").explode().value_counts().head(5).to_dict(),
        }

    # ---------------------------------------------------------------- overview
    win_counts = df["winner"].value_counts().to_dict()
    decisive = win_counts.get("model_a", 0) + win_counts.get("model_b", 0)
    side_bias = win_counts.get("model_b", 0) / decisive

    lang_top = df["language"].value_counts().head(12).to_dict()
    overview = {
        "rows": len(df),
        "unique_sessions": int(df["evaluation_session_id"].nunique()),
        "unique_prompts": int(df["prompt_excerpt"].nunique()),
        "date_range": [str(df["ts"].min()), str(df["ts"].max())],
        "screening_score_note": "score = 3*strong_term_strength + n_category_tags + n_weak_terms; "
                                "it is a keyword-screen score, NOT a human quality rating",
        "screening_score": {"min": int(df["score"].min()), "median": float(df["score"].median()),
                            "max": int(df["score"].max()),
                            "tier_median": df.groupby("tier")["score"].median().to_dict()},
        "winner_counts": win_counts,
        "tie_rate": round(win_counts.get("tie", 0) / len(df), 4),
        "both_bad_rate": round(win_counts.get("both_bad", 0) / len(df), 4),
        "position_b_bias_among_decisive": round(side_bias, 4),
        "tier": df["tier"].value_counts().to_dict(),
        "basis": df["basis"].value_counts().to_dict(),
        "prompt_tier": df["prompt_tier"].value_counts().to_dict(),
        "response_tier": df["response_tier"].value_counts().to_dict(),
        "share_rows_political_prompt": round(float(df["political_prompt"].mean()), 4),
        "share_rows_political_prompt_strict": round(float(df["prompt_tier"].eq("strict").mean()), 4),
        "is_code_share": round(float(df["is_code"].mean()), 4),
        "is_code_by_basis": df.groupby("basis")["is_code"].mean().round(4).to_dict(),
        "language_top": lang_top,
        "english_share": round(float((df["language"] == ENG).mean()), 4),
        "month": df["month"].value_counts().sort_index().to_dict(),
        "tag_counts": df["categories"].str.split("|").explode().value_counts().to_dict(),
        "mean_tag_count": round(float(df["n_cat_tags"].mean()), 2),
        "prompt_chars_median": float(df["prompt_chars"].median()),
        "responses_at_excerpt_cap": int(((df["response_a_excerpt"].str.len() >= 419) |
                                         (df["response_b_excerpt"].str.len() >= 419)).sum()),
        "top_topics": topics_df.head(10).to_dict(orient="records"),
        "interest_group_mentions": {
            k: int(df["interest_groups"].str.contains(k).sum()) for k in INTEREST_GROUPS
        },
        "sensitive_probe_rows": int((df["sensitive"] != "").sum()),
        "sensitive_probe_counts": df.loc[df["sensitive"] != "", "sensitive"]
                                    .str.split("|").explode().value_counts().to_dict(),
        "feature_tests": tests.to_dict(orient="records"),
        "decisive_votes_used": int(decisive),
        "length": length,
        "tie_both_bad_diagnostics": tie_bad,
        "prompt_topic_stats": prompt_topics_df.to_dict(orient="records"),
        "corpus_baselines_135k": {
            "overall_rows": 135634,
            "overall_tie_rate": round(21532 / 135634, 4),
            "overall_both_bad_rate": round(15754 / 135634, 4),
            "strict_political_prompt_rows": 2235,
            "strict_political_prompt_tie_rate": round(311 / 2235, 4),
            "strict_political_prompt_both_bad_rate": round(297 / 2235, 4),
            "note": "from arena/results/summary.json (by_winner block)",
        },
    }

    # sentiment summaries
    en = sent[sent["lang_group"] == "en"]
    dec = en[en["winner"].isin(["model_a", "model_b"])].copy()
    dec["win_compound"] = np.where(dec["winner"] == "model_a", dec["a_compound"], dec["b_compound"])
    dec["lose_compound"] = np.where(dec["winner"] == "model_a", dec["b_compound"], dec["a_compound"])
    d = dec["win_compound"] - dec["lose_compound"]
    pos_w = int((d > 0.02).sum())
    neg_w = int((d < -0.02).sum())
    overview["sentiment"] = {
        "english_rows": int(len(en)),
        "mean_compound_a": round(float(sent["a_compound"].mean()), 4),
        "mean_compound_b": round(float(sent["b_compound"].mean()), 4),
        "mean_negative_share": round(float(sent[["a_neg", "b_neg"]].mean().mean()), 4),
        "share_answers_compound_lt_-0.05": round(float(((sent["a_compound"] < -0.05).sum() +
                                                        (sent["b_compound"] < -0.05).sum()) /
                                                       (2 * len(sent))), 4),
        "paired_winner_minus_loser": {
            "mean": round(float(d.mean()), 4),
            "median": round(float(d.median()), 4),
            "winner_more_positive": pos_w,
            "winner_more_negative": neg_w,
            "mcnemar_p": mcnemar_exact(pos_w, neg_w),
            "n": int(len(d)),
        },
        "by_winner": sent.groupby("winner")[["a_compound", "b_compound"]].mean().round(4).to_dict(),
        "alarm_terms_mean": round(float(sent[["a_alarm_terms", "b_alarm_terms"]].mean().mean()), 3),
        "moral_terms_mean": round(float(sent[["a_moral_terms", "b_moral_terms"]].mean().mean()), 3),
        "hedge_terms_mean": round(float(sent[["a_hedge_terms", "b_hedge_terms"]].mean().mean()), 3),
        "empathy_share": round(float((sent["a_empathy"] + sent["b_empathy"]).mean() / 2), 4),
    }

    # specificity / fact-bearing proxies
    spec_en = spec
    overview["specificity"] = {
        "share_answers_with_year": round(float(((spec["a_years"] > 0).sum() +
                                                (spec["b_years"] > 0).sum()) / (2 * len(spec))), 4),
        "share_answers_with_pct": round(float(((spec["a_pct"] > 0).sum() +
                                               (spec["b_pct"] > 0).sum()) / (2 * len(spec))), 4),
        "share_answers_with_citation_cue": round(float(((spec["a_cites"] > 0).sum() +
                                                        (spec["b_cites"] > 0).sum()) / (2 * len(spec))), 4),
        "mean_years_per_answer": round(float(spec[["a_years", "b_years"]].mean().mean()), 2),
        "mean_hedges_per_answer": round(float(spec[["a_hedges", "b_hedges"]].mean().mean()), 2),
    }

    # model table summary
    strong = models[(models["decisive"] >= 25)].copy()
    overview["models"] = {
        "n_models": int(models["model"].nunique()),
        "models_with_25plus_decisive": int(len(strong)),
        "top10_by_win_rate": strong.sort_values("win_rate", ascending=False).head(10)[
            ["model", "decisive", "win_rate", "win_rate_lo", "win_rate_hi", "bt_strength"]
        ].to_dict(orient="records"),
        "bottom10_by_win_rate": strong.sort_values("win_rate").head(10)[
            ["model", "decisive", "win_rate", "bt_strength"]
        ].to_dict(orient="records"),
    }

    (out / "overview.json").write_text(json.dumps(overview, indent=2, default=str))
    print(json.dumps({k: overview[k] for k in ["rows", "winner_counts", "tie_rate",
                                               "both_bad_rate", "share_rows_political_prompt"]},
                     indent=2))
    print("\ntopics:\n", topics_df.head(12).to_string(index=False))
    print("\nintents:\n", intents_df.to_string(index=False))
    print("\nfeature tests:\n", tests.head(20).to_string(index=False))
    print("\ninterest groups:", overview["interest_group_mentions"])
    print("\nsensitive:", overview["sensitive_probe_counts"])
    print("\nsentiment:", json.dumps(overview["sentiment"]["paired_winner_minus_loser"], indent=2))
    print("\nspecificity:", json.dumps(overview["specificity"], indent=2))
    print("\naudit rows:", len(audit), "| files in", out)


if __name__ == "__main__":
    main()
