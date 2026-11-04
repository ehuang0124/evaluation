#!/usr/bin/env python3
"""Scale-up: re-run the four questions on the full local extracts.

Inputs (present in the repo checkout, produced by arena/extract_full_text.py):

  arena/explorer/data/prompts_all.jsonl.gz     63,635 votes, FULL prompts + metadata
  arena/explorer/data/conversations.jsonl.gz    6,820 votes, FULL prompts + FULL answers
                                                (includes ALL 2,235 strict-political-prompt votes)

This replaces the keyword-ranked 1,500-row shortlist with (a) the complete census
of strict-political-prompt votes and (b) the whole 63,635-row candidate set for
prompt-side questions. Answers are untruncated here, so structure and length are
measured directly instead of through 420-character excerpts.

    python arena/interest_analysis/scale.py

Outputs land in arena/interest_analysis/results_scale/.
"""

from __future__ import annotations

import gzip
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

import lexicons as lx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "results_scale"
PROMPTS = REPO / "arena/explorer/data/prompts_all.jsonl.gz"
CONVOS = REPO / "arena/explorer/data/conversations.jsonl.gz"


def rx(p: str) -> re.Pattern:
    return re.compile(p, re.IGNORECASE | re.MULTILINE)


TOPIC_RX = {k: rx(v) for k, v in lx.TOPICS.items()}
INTENT_RX = {k: rx(v) for k, v in lx.INTENTS.items()}
IG_RX = {k: rx(v) for k, v in lx.INTEREST_GROUPS.items()}
SENS_RX = {k: rx(v) for k, v in lx.SENSITIVE.items()}
FEAT_RX = {**{k: rx(v) for k, v in lx.STRUCTURE.items()}, **{k: rx(v) for k, v in lx.EPISTEMIC.items()}}


def labels(text: str, rxmap) -> list[str]:
    if not isinstance(text, str):
        return []
    return [k for k, r in rxmap.items() if r.search(text)]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n)


def bradley_terry(pairs, iters: int = 300) -> dict[str, float]:
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
        den = np.array([sum(n[i, j] / (p[i] + p[j]) for j in range(len(models)) if n[i, j])
                        for i in range(len(models))])
        new = np.where(den > 0, w / np.maximum(den, 1e-12), 1e-9)
        new = np.maximum(new, 1e-9)
        p = new / new.sum() * len(models)
    return {m: float(p[idx[m]]) for m in models}


# ------------------------------------------------------------------ load data
def load_jsonl(path: Path, text_cols=()) -> pd.DataFrame:
    rows = []
    with gzip.open(path, "rt") as f:
        for line in f:
            d = json.loads(line)
            d["categories"] = "|".join(d.get("categories") or [])
            rows.append(d)
    df = pd.DataFrame(rows)
    for c in ["prompt"] + list(text_cols):
        df[c] = df[c].fillna("")
    df["ts"] = pd.to_datetime(df["timestamp"])
    return df


# ------------------------------------------------------------- measurement set
def word_count(t: str) -> int:
    return len(re.findall(r"\b\w+\b", t))


def structure_counts(t: str) -> dict[str, float]:
    w = max(word_count(t), 1)
    headers = len(re.findall(r"^#{1,6}\s", t, re.M))
    bullets = len(re.findall(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+", t, re.M))
    bold = len(re.findall(r"\*\*[^*\n]{2,80}\*\*", t))
    tables = len(re.findall(r"^\|.*\|.*$", t, re.M))
    paragraphs = len([p for p in re.split(r"\n\s*\n", t) if p.strip()])
    links = len(re.findall(r"https?://|\[\d+\]", t))
    years = len(re.findall(r"\b(1[5-9]\d{2}|20[0-2]\d)\b", t))
    pcts = len(re.findall(r"\d+(?:\.\d+)?\s?%", t))
    numbers = len(re.findall(r"\b\d{1,3}(?:,\d{3})+\b|\b\d+(?:\.\d+)?\s?(?:million|billion|thousand)\b", t))
    src_head = len(re.findall(r"^#{0,4}\s*(sources?|references?|further reading|bibliography)\b", t, re.I | re.M))
    return {
        "words": w,
        "headers_per_1k": 1000 * headers / w,
        "bullets_per_1k": 1000 * bullets / w,
        "bold_per_1k": 1000 * bold / w,
        "tables_per_1k": 1000 * tables / w,
        "paragraphs_per_1k": 1000 * paragraphs / w,
        "links_per_1k": 1000 * links / w,
        "years_per_1k": 1000 * years / w,
        "pcts_per_1k": 1000 * pcts / w,
        "numbers_per_1k": 1000 * numbers / w,
        "has_sources_section": float(src_head > 0),
        "has_headers": float(headers > 0),
        "has_bullets": float(bullets > 0),
        "has_table": float(tables > 0),
        "ends_with_question": float(bool(re.search(r"\?\s*$", t))),
    }


def answer_features(t: str) -> dict[str, float]:
    d = {k: float(bool(r.search(t))) for k, r in FEAT_RX.items()}
    d.update(structure_counts(t))
    return d


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("loading extracts ...")
    prompts = load_jsonl(PROMPTS)
    convs = load_jsonl(CONVOS, ("assistant_a", "assistant_b"))

    # topic / intent / interest-group labels on the FULL prompt text
    prompts["topics"] = prompts["prompt"].map(lambda t: "|".join(labels(t, TOPIC_RX)))
    prompts["intents"] = prompts["prompt"].map(lambda t: "|".join(labels(t, INTENT_RX)))
    prompts["interest_groups"] = prompts["prompt"].map(lambda t: "|".join(labels(t, IG_RX)))
    prompts["sensitive"] = prompts["prompt"].map(lambda t: "|".join(labels(t, SENS_RX)))
    prompts[["id", "evaluation_session_id", "tier", "basis", "prompt_tier", "response_tier",
             "score", "language", "is_code", "winner", "model_a", "model_b", "timestamp",
             "prompt_chars", "topics", "intents", "interest_groups", "sensitive"]].to_csv(
        OUT / "prompts_all_labels.csv", index=False)

    census = convs[convs["prompt_tier"] == "strict"].copy()     # complete census
    print(f"votes: all={len(prompts):,}  with-answers={len(convs):,}  strict-prompt census={len(census):,}")

    # ------------------------------------------------------------------ coverage
    def prof(df: pd.DataFrame, name: str) -> dict:
        w = df["winner"].value_counts()
        dec = int(w.get("model_a", 0) + w.get("model_b", 0))
        lo, hi = wilson(dec, len(df))
        return {
            "set": name,
            "votes": int(len(df)),
            "unique_sessions": int(df["evaluation_session_id"].nunique()),
            "models": int(pd.concat([df["model_a"], df["model_b"]]).nunique()),
            "tie_rate": round(float((df["winner"] == "tie").mean()), 4),
            "both_bad_rate": round(float((df["winner"] == "both_bad").mean()), 4),
            "decisive_share": round(dec / len(df), 3),
            "en_share": round(float((df["language"] == "en").mean()), 3),
            "is_code_share": round(float(df["is_code"].mean()), 3),
            "share_political_prompt": round(float(df["prompt_tier"].isin(["strict", "probable", "broad"]).mean()), 3),
            "date_range": f"{df['ts'].min():%Y-%m-%d}..{df['ts'].max():%Y-%m-%d}",
        }

    short = pd.read_csv(REPO / "arena/results/shortlist.csv")
    short["ts"] = pd.to_datetime(short["timestamp"])
    coverage = pd.DataFrame([
        prof(short, "shortlist.csv (keyword-ranked top 1,500)"),
        prof(convs, "all 6,820 votes with full answers"),
        prof(census, "2,235 strict-political-prompt census"),
        prof(prompts, "all 63,635 flagged votes"),
    ])
    coverage.to_csv(OUT / "coverage.csv", index=False)
    print("\n", coverage.to_string(index=False))

    # ------------------------------------------------------------------- length
    length_rows = []
    for name, df in [("census_2235", census), ("answers_6820", convs)]:
        dec = df[df["winner"].isin(["model_a", "model_b"])].copy()
        dec["wall"] = np.where(dec["winner"] == "model_a", dec["assistant_a_chars"], dec["assistant_b_chars"])
        dec["llose"] = np.where(dec["winner"] == "model_a", dec["assistant_b_chars"], dec["assistant_a_chars"])
        dec["ratio"] = dec["wall"] / dec["llose"].clip(lower=1)
        dec["longer_won"] = dec["ratio"] > 1
        length_rows.append({
            "set": name,
            "decisive": int(len(dec)),
            "share_longer_won": round(float(dec["longer_won"].mean()), 4),
            "median_ratio": round(float(dec["ratio"].median()), 3),
            "median_winner_chars": round(float(dec["wall"].median()), 0),
            "median_loser_chars": round(float(dec["llose"].median()), 0),
            "share_ratio_gt_1_2": round(float((dec["ratio"] > 1.2).mean()), 4),
            "share_ratio_lt_0_8": round(float((dec["ratio"] < 0.8).mean()), 4),
        })
        dec[["id", "winner", "model_a", "model_b", "assistant_a_chars", "assistant_b_chars",
             "ratio", "longer_won", "language", "prompt_tier"]].to_csv(
            OUT / f"length_{name}.csv", index=False)
    length = pd.DataFrame(length_rows)
    length.to_csv(OUT / "length_summary.csv", index=False)
    # length effects by prompt topic and language (census)
    L = census[census["winner"].isin(["model_a", "model_b"])].merge(
        prompts[["id", "topics", "prompt_chars"]], on="id", how="left")
    L["wall"] = np.where(L["winner"] == "model_a", L["assistant_a_chars"], L["assistant_b_chars"])
    L["llose"] = np.where(L["winner"] == "model_a", L["assistant_b_chars"], L["assistant_a_chars"])
    L["longer_won"] = L["wall"] > L["llose"]
    bylen = []
    for t in list(lx.TOPICS) + ["ALL"]:
        sub = L if t == "ALL" else L[L["topics"].fillna("").str.contains(t)]
        if len(sub) < 40:
            continue
        bylen.append({"topic": t, "decisive": int(len(sub)),
                      "share_longer_won": round(float(sub["longer_won"].mean()), 3)})
    pd.DataFrame(bylen).to_csv(OUT / "length_by_topic_census.csv", index=False)
    print("\nlength:\n", length.to_string(index=False))

    # --------------------------------------------------- answer features (full text)
    feat_rows = []
    for side in ("a", "b"):
        feat_rows.append(pd.DataFrame([answer_features(t) for t in census[f"assistant_{side}"]]).add_prefix(f"{side}_"))
    F = pd.concat([census[["id", "winner", "language", "model_a", "model_b"]].reset_index(drop=True)] +
                  feat_rows, axis=1)
    F["id"] = census["id"].values
    F.to_csv(OUT / "answer_features_census.csv", index=False)

    dec = F[F["winner"].isin(["model_a", "model_b"])].copy()
    dec["win_is_a"] = dec["winner"] == "model_a"
    tests = []
    for base in [c[2:] for c in F.columns if c.startswith("a_")]:
        if base == "words":
            continue
        win = np.where(dec["win_is_a"], dec[f"a_{base}"], dec[f"b_{base}"])
        lose = np.where(dec["win_is_a"], dec[f"b_{base}"], dec[f"a_{base}"])
        binary = set(F[f"a_{base}"].dropna().unique()) <= {0.0, 1.0}
        row = {
            "feature": base,
            "winner_mean": round(float(np.nanmean(win)), 4),
            "loser_mean": round(float(np.nanmean(lose)), 4),
            "binary": binary,
        }
        if binary:
            b = int(((win == 1) & (lose == 0)).sum())
            c = int(((win == 0) & (lose == 1)).sum())
            row.update({"winner_only": b, "loser_only": c, "mcnemar_p": round(mcnemar(b, c), 4)})
        else:
            d = win - lose
            row.update({"median_diff": round(float(np.nanmedian(d)), 4),
                        "share_positive": round(float(np.nanmean(d > 0)), 4),
                        "sign_test_p": round(mcnemar(int((d > 0).sum()), int((d < 0).sum())), 4)})
        tests.append(row)
    tests = pd.DataFrame(tests).sort_values("winner_mean", ascending=False)
    tests.to_csv(OUT / "feature_tests_census.csv", index=False)
    print("\nfeature tests (census, full text):\n",
          tests[["feature", "winner_mean", "loser_mean", "binary", "mcnemar_p", "sign_test_p"]]
          .head(28).to_string(index=False))

    # ------------------------------- what survives length control (near-equal)
    # Among decisive votes whose two answers are within 10% of each other in
    # length, length cannot be doing the work, so this isolates content/style.
    ratio = (census["assistant_a_chars"] / census["assistant_b_chars"].clip(lower=1))
    near = census[(census["winner"].isin(["model_a", "model_b"])) &
                  (ratio.between(0.9, 1.111))]
    Fn = F[F["id"].isin(set(near["id"]))].copy()
    near_rows = []
    if len(Fn) > 60:
        Fn["win_is_a"] = Fn["winner"] == "model_a"
        for base in [c[2:] for c in F.columns if c.startswith("a_")]:
            if base == "words":
                continue
            win = np.where(Fn["win_is_a"], Fn[f"a_{base}"], Fn[f"b_{base}"])
            lose = np.where(Fn["win_is_a"], Fn[f"b_{base}"], Fn[f"a_{base}"])
            binary = set(F[f"a_{base}"].dropna().unique()) <= {0.0, 1.0}
            if not binary:
                continue
            b = int(((win == 1) & (lose == 0)).sum())
            c = int(((win == 0) & (lose == 1)).sum())
            near_rows.append({"feature": base, "winner_rate": round(float(win.mean()), 4),
                              "loser_rate": round(float(lose.mean()), 4),
                              "delta_pp": round(100 * float(win.mean() - lose.mean()), 2),
                              "winner_only": b, "loser_only": c,
                              "mcnemar_p": round(mcnemar(b, c), 4), "n": int(len(Fn))})
    near_df = pd.DataFrame(near_rows).sort_values("delta_pp", ascending=False)
    near_df.to_csv(OUT / "feature_tests_near_equal_length.csv", index=False)
    print(f"\nnear-equal-length decisive votes: {len(near)}")

    # ------------------------------------------ recency, validation, citations
    cut = (r"as of (my )?(last |latest )?(update|knowledge|training|information)[^.]{0,45}"
           r"(19|20)\d{2}|knowledge cutoff|my training data (only )?(goes|extends)|"
           r"as of (january|february|march|april|may|june|july|august|september|october|november|december) 20\d\d")
    agree = (r"(you'?re (absolutely |completely |quite )?(right|correct)|absolutely right|"
             r"exactly right|great point|fair point|you are correct|indeed|precisely|i agree|"
             r"that'?s a (great|sharp|excellent|insightful|very good)|good observation|"
             r"valid (point|concern)|well said|you raise|that'?s an? (important|fascinating))")
    cite = r"https?://|\[\d+\]|^#{0,4}\s*(sources?|references?|further reading)\b|according to the"
    def share(pat: str, side: str) -> pd.Series:
        return census[f"assistant_{side}"].str.contains(pat, case=False, regex=True)

    def paired_stat(pa: pd.Series, pb: pd.Series) -> dict:
        d = census[census["winner"].isin(["model_a", "model_b"])]
        w = np.where(d["winner"] == "model_a", pa[d.index], pb[d.index])
        l = np.where(d["winner"] == "model_a", pb[d.index], pa[d.index])
        b = int((w & ~l).sum())
        c = int((~w & l).sum())
        return {"share_of_answers": round(float((pa.sum() + pb.sum()) / (2 * len(census))), 4),
                "winner_only": b, "loser_only": c, "mcnemar_p": round(mcnemar(b, c), 4)}

    late = census[census["ts"] >= "2025-05-01"]
    recency = {
        "cutoff_statement": paired_stat(share(cut, "a"), share(cut, "b")),
        "validation_markers": paired_stat(share(agree, "a"), share(agree, "b")),
        "citations_or_links": paired_stat(share(cite, "a"), share(cite, "b")),
        "share_answers_mentioning_2025": round(float(
            (census["assistant_a"].str.contains("2025").sum() +
             census["assistant_b"].str.contains("2025").sum()) / (2 * len(census))), 4),
        "share_votes_after_may_2025_mentioning_2025": round(float(
            (late["assistant_a"].str.contains("2025") |
             late["assistant_b"].str.contains("2025")).mean()), 4),
        "share_answers_with_any_year": round(float(
            (census["assistant_a"].str.contains(r"\b(1[5-9]\d{2}|20[0-2]\d)\b").sum() +
             census["assistant_b"].str.contains(r"\b(1[5-9]\d{2}|20[0-2]\d)\b").sum()) / (2 * len(census))), 4),
        "median_answer_words": int(np.median([word_count(t) for t in census["assistant_a"]])),
    }
    print("\nrecency/validation/citations:\n", json.dumps(recency, indent=2))

    # ---------------------------------------------------------------- sentiment
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()

    def sent(t: str) -> dict[str, float]:
        doc = sia.polarity_scores(t)
        sents = [sia.polarity_scores(s)["compound"] for s in re.split(r"(?<=[.!?])\s+", t) if len(s) > 30][:60]
        return {"compound": doc["compound"], "neg": doc["neg"],
                "mean_sentence_compound": float(np.mean(sents)) if sents else doc["compound"]}

    en = census[census["language"] == "en"]
    rows = []
    for _, r in en.iterrows():
        rec = {"id": r["id"], "winner": r["winner"], "language": r["language"]}
        for side in ("a", "b"):
            rec.update({f"{side}_{k}": v for k, v in sent(r[f"assistant_{side}"]).items()})
        rows.append(rec)
    S = pd.DataFrame(rows)
    # attach prompt topics from the prompts table
    S = S.merge(prompts[["id", "topics"]], on="id", how="left")
    S.to_csv(OUT / "sentiment_census_en.csv", index=False)

    dec = S[S["winner"].isin(["model_a", "model_b"])].copy()
    w = np.where(dec["winner"] == "model_a", dec["a_mean_sentence_compound"], dec["b_mean_sentence_compound"])
    l = np.where(dec["winner"] == "model_a", dec["b_mean_sentence_compound"], dec["a_mean_sentence_compound"])
    d = w - l
    sent_summary = {
        "en_votes": int(len(S)),
        "mean_compound_a": round(float(S["a_compound"].mean()), 4),
        "mean_compound_b": round(float(S["b_compound"].mean()), 4),
        "mean_sentence_compound": round(float(pd.concat([S["a_mean_sentence_compound"],
                                                         S["b_mean_sentence_compound"]]).mean()), 4),
        "share_answers_compound_lt_-0.05": round(float((pd.concat([S["a_compound"], S["b_compound"]]) < -0.05).mean()), 4),
        "paired_winner_minus_loser_sentences": {
            "mean": round(float(np.mean(d)), 4),
            "winner_more_positive": int((d > 0.01).sum()),
            "winner_more_negative": int((d < -0.01).sum()),
            "sign_test_p": round(mcnemar(int((d > 0.01).sum()), int((d < -0.01).sum())), 4),
            "n": int(len(d)),
        },
    }
    # by topic
    S["topic_list"] = S["topics"].fillna("").str.split("|")
    by_topic = []
    for t in lx.TOPICS:
        m = S["topic_list"].map(lambda L: t in L)
        sub = S[m]
        if len(sub) < 30:
            continue
        vals = pd.concat([sub["a_mean_sentence_compound"], sub["b_mean_sentence_compound"]])
        by_topic.append({"topic": t, "en_votes": int(len(sub)),
                         "mean_sentence_compound": round(float(vals.mean()), 3),
                         "share_negative": round(float((vals < -0.05).mean()), 3),
                         "both_bad_rate": round(float((sub["winner"] == "both_bad").mean()), 3)})
    pd.DataFrame(by_topic).sort_values("mean_sentence_compound").to_csv(
        OUT / "sentiment_by_topic_census.csv", index=False)

    # ------------------------------------------------------------------- models
    def model_table(df: pd.DataFrame) -> pd.DataFrame:
        pairs = [(r.model_a, r.model_b) if r.winner == "model_a" else (r.model_b, r.model_a)
                 for r in df.itertuples() if r.winner in ("model_a", "model_b")]
        bt = bradley_terry(pairs)
        out = []
        for m in sorted(set(df["model_a"]) | set(df["model_b"])):
            sub = df[(df["model_a"] == m) | (df["model_b"] == m)]
            w = int(((sub["model_a"] == m) & (sub["winner"] == "model_a")).sum() +
                    ((sub["model_b"] == m) & (sub["winner"] == "model_b")).sum())
            l = int(((sub["model_a"] == m) & (sub["winner"] == "model_b")).sum() +
                    ((sub["model_b"] == m) & (sub["winner"] == "model_a")).sum())
            lo, hi = wilson(w, w + l) if (w + l) else (np.nan, np.nan)
            out.append({"model": m, "appearances": int(len(sub)), "wins": w, "losses": l,
                        "decisive": w + l,
                        "win_rate": round(w / (w + l), 4) if (w + l) else np.nan,
                        "win_rate_lo": round(lo, 4), "win_rate_hi": round(hi, 4),
                        "tie_rate": round(float((sub["winner"] == "tie").mean()), 4),
                        "both_bad_rate": round(float((sub["winner"] == "both_bad").mean()), 4),
                        "bt_strength": round(bt.get(m, np.nan), 3)})
        return pd.DataFrame(out).sort_values("win_rate", ascending=False)

    models = model_table(convs)
    models.to_csv(OUT / "model_stats_census.csv", index=False)
    m_short = pd.read_csv(REPO / "arena/interest_analysis/results/model_stats.csv")
    joined = m_short.merge(models, on="model", suffixes=("_shortlist", "_census"))
    joined = joined[(joined["decisive_shortlist"] >= 20) & (joined["decisive_census"] >= 60)]
    # Spearman without scipy: Pearson on ranks
    rank_corr = float(joined["win_rate_shortlist"].rank().corr(joined["win_rate_census"].rank()))
    print(f"\nmodel win-rate rank correlation shortlist vs census: {rank_corr:.3f} "
          f"(n={len(joined)} models with enough votes)")
    joined[["model", "decisive_shortlist", "win_rate_shortlist", "decisive_census",
            "win_rate_census", "bt_strength_census"]].to_csv(OUT / "model_rank_comparison.csv", index=False)

    # ---------------------------------------------------------- sensitive probes
    sens_prompt_counts = {k: int(prompts["prompt"].map(lambda t: bool(SENS_RX[k].search(t))).sum())
                          for k in SENS_RX}
    sens_rows = []
    for k, r in SENS_RX.items():
        sub = prompts[prompts["prompt"].map(lambda t: bool(r.search(t)))]
        if len(sub) == 0:
            continue
        sens_rows.append({"probe": k, "prompt_rows": int(len(sub)),
                          "with_answers": int(convs["id"].isin(sub["id"]).sum()),
                          "languages": int(sub["language"].nunique())})
    sens = pd.DataFrame(sens_rows).sort_values("prompt_rows", ascending=False)
    sens.to_csv(OUT / "sensitive_prompt_counts.csv", index=False)

    # answer-level coding for the two big probes, auto cues only (spot-checked by hand)
    def code_answers(row, probe_pat):
        out = []
        for side in ("a", "b"):
            t = row[f"assistant_{side}"]
            denies = bool(re.search(r"no (major |significant |widely[- ]recorded )?historical events?|"
                                    r"nothing (significant|notable)|not aware of|no such event|"
                                    r"did not (occur|happen)|is a (myth|fabrication)|unverified|"
                                    r"may (have|be) (occurred|false)|rumou?r", t, re.I))
            refuses = bool(re.search(r"i (can'?t|cannot|won'?t|am (not able|unable))|as an ai|"
                                     r"i must (decline|emphasize)|敏感|不予|无法回答|政治敏感|"
                                     r"请参考官方|官方发布|harmonious|和谐社会|长治久安|"
                                     r"伟大复兴|正确领导|坚决拥护", t, re.I))
            party = bool(re.search(r"(chinese communist party|中国共产党|中国政府)( has| always|始终|坚定不移)|"
                                   r"中华民族伟大复兴|社会主义道路|人民政府", t, re.I))
            accurate = bool(probe_pat.search(t))
            out.append({"id": row["id"], "side": side, "model": row[f"model_{side}"],
                        "winner": row["winner"], "language": row["language"],
                        "prompt_tier": row["prompt_tier"],
                        "denies": int(denies), "refuses": int(refuses), "party_line": int(party),
                        "mentions_event": int(accurate),
                        "excerpt": t[:240]})
        return out

    for probe in ("tiananmen", "taiwan_status", "holocaust"):
        pat = SENS_RX[probe]
        ids = set(prompts.loc[prompts["prompt"].map(lambda t: bool(pat.search(t))), "id"])
        sub = convs[convs["id"].isin(ids)]
        recs = []
        for _, r in sub.iterrows():
            recs.extend(code_answers(r, pat))
        if recs:
            d = pd.DataFrame(recs)
            d.to_csv(OUT / f"sensitive_answers_{probe}.csv", index=False)

    # --------------------------------------------------------------- topic table
    topic_rows = []
    for t in lx.TOPICS:
        m = prompts["topics"].str.contains(t)
        sub = prompts[m]
        csub = convs[convs["id"].isin(sub["id"])]
        a = (csub["winner"] == "model_a").sum()
        b = (csub["winner"] == "model_b").sum()
        topic_rows.append({
            "topic": t, "prompt_rows": int(len(sub)),
            "share_of_flagged": round(len(sub) / len(prompts), 4),
            "strict_prompt_rows": int((sub["prompt_tier"] == "strict").sum()),
            "votes_with_answers": int(len(csub)),
            "tie_rate": round(float((csub["winner"] == "tie").mean()), 4) if len(csub) else np.nan,
            "both_bad_rate": round(float((csub["winner"] == "both_bad").mean()), 4) if len(csub) else np.nan,
            "mean_prompt_chars": round(float(sub["prompt_chars"].mean()), 1),
        })
    topics = pd.DataFrame(topic_rows).sort_values("prompt_rows", ascending=False)
    topics.to_csv(OUT / "topic_stats_census.csv", index=False)

    summary = {
        "inputs": {"prompts_all": len(prompts), "conversations": len(convs),
                   "strict_prompt_census": int(len(census))},
        "coverage": coverage.to_dict(orient="records"),
        "length": length.to_dict(orient="records"),
        "sentiment": sent_summary,
        "sensitive_prompt_counts": sens_prompt_counts,
        "sensitive_table": sens.to_dict(orient="records"),
        "interest_group_mentions": {k: int(prompts["prompt"].map(lambda t: bool(IG_RX[k].search(t))).sum())
                                    for k in lx.INTEREST_GROUPS},
        "model_rank_correlation": {"spearman": rank_corr, "models": int(len(joined))},
        "feature_tests": tests.to_dict(orient="records"),
        "feature_tests_near_equal_length": near_df.to_dict(orient="records"),
        "recency_validation_citations": recency,
        "topics": topics.to_dict(orient="records"),
    }
    (OUT / "scale_summary.json").write_text(json.dumps(summary, indent=2))
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
