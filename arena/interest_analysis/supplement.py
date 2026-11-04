#!/usr/bin/env python3
"""Supplementary analyses for the Arena political shortlist.

  * paired log-odds (Monroe/Colaresi/Quinn prior) of the words that separate
    winning from losing answers inside the same vote
  * sentiment / register by topic
  * language effects (Chinese-language political prompts)
  * a 40-row audit sample for hand-validating the automatic topic labels

Run after analyze.py:

    python arena/interest_analysis/supplement.py
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RES = HERE / "results"

STOP = set("""a an the of to in and or is are was were be been being for on with that this it as at by from
not you your i we they he she his her their our what which who how why do does did can could should would will
may might about if then than there here into other more most some such no yes very much many also just only
all any but so because while when where each every these those them its it's i'm don't doesn't isn't aren't
has have had having one two three first second new now also like just get got make made way well even still
s t re ve ll d m""".split())

TOKEN = re.compile(r"[a-z][a-z'\-]{2,}")


def words(t: str) -> list[str]:
    return [w for w in TOKEN.findall(t.lower()) if w not in STOP]


def log_odds(win_docs: list[list[str]], lose_docs: list[list[str]], prior: float = 0.01) -> pd.DataFrame:
    """Weighted log-odds ratio with informative Dirichlet prior (Monroe et al. 2008)."""
    cw, cl = Counter(), Counter()
    for d in win_docs:
        cw.update(d)
    for d in lose_docs:
        cl.update(d)
    vocab = [w for w in set(cw) | set(cl) if (cw[w] + cl[w]) >= 12]
    nw, nl = sum(cw.values()), sum(cl.values())
    tot = Counter()
    tot.update(cw)
    tot.update(cl)
    n = nw + nl
    rows = []
    for w in vocab:
        aw = tot[w]
        a0 = prior * n
        yw = cw[w]
        yl = cl[w]
        # posterior means with prior
        pw = (yw + a0 * (aw / n)) / (nw + a0)
        pl = (yl + a0 * (aw / n)) / (nl + a0)
        delta = math.log(pw / (1 - pw)) - math.log(pl / (1 - pl))
        var = 1 / (yw + a0 * aw / n) + 1 / (yl + a0 * aw / n)
        rows.append({"token": w, "win_count": yw, "lose_count": yl,
                     "log_odds": round(delta, 4), "z": round(delta / math.sqrt(var), 3)})
    return pd.DataFrame(rows).sort_values("log_odds", ascending=False)



# --------------------------------------------------- recency & sycophancy tests
def recency_and_validation(df: pd.DataFrame) -> dict:
    """Two measurables that matter for Q2/Q4: how current answers look, and
    whether answers that validate the user's premise are rewarded."""
    import math as _m

    def mcnemar(b: int, c: int) -> float:
        n = b + c
        if n == 0:
            return 1.0
        k = min(b, c)
        return min(1.0, 2 * sum(_m.comb(n, i) for i in range(k + 1)) / 2**n)

    cut = (r"as of (my )?(last |latest )?(update|knowledge|training|information)[^.]{0,45}"
           r"(19|20)\d{2}|knowledge cutoff|as of (january|february|march|april|may|june|july|"
           r"august|september|october|november|december) 20\d\d")
    agree = (r"(you'?re (absolutely |completely |quite )?(right|correct)|absolutely|"
             r"exactly right|great point|fair point|you are correct|indeed|precisely|"
             r"i agree|that'?s a (great|sharp|excellent|insightful|very good)|"
             r"good observation|valid (point|concern)|well said|you raise)")
    ca = df["response_a_excerpt"].str.contains(cut, case=False, regex=True)
    cb = df["response_b_excerpt"].str.contains(cut, case=False, regex=True)
    aa = df["response_a_excerpt"].str.contains(agree, case=False, regex=True)
    ab = df["response_b_excerpt"].str.contains(agree, case=False, regex=True)

    dec = df[df["winner"].isin(["model_a", "model_b"])]
    def paired(xa, xb):
        w = np.where(dec["winner"] == "model_a", xa[dec.index], xb[dec.index])
        l = np.where(dec["winner"] == "model_a", xb[dec.index], xa[dec.index])
        b, c = int((w & ~l).sum()), int((~w & l).sum())
        return {"winner_only": b, "loser_only": c, "mcnemar_p": round(mcnemar(b, c), 4)}

    years = {}
    for y in ("2023", "2024", "2025"):
        years[y] = round(float((df["response_a_excerpt"].str.contains(y).sum() +
                                df["response_b_excerpt"].str.contains(y).sum()) / (2 * len(df))), 3)
    df = df.assign(ts=pd.to_datetime(df["timestamp"]))
    late = df[df["ts"] >= "2025-05-01"]
    return {
        "cutoff_statement_share_of_answers": round(float((ca.sum() + cb.sum()) / (2 * len(df))), 4),
        "cutoff_statement_paired": paired(ca, cb),
        "validation_marker_share_of_answers": round(float((aa.sum() + ab.sum()) / (2 * len(df))), 4),
        "validation_marker_paired": paired(aa, ab),
        "year_mention_share_of_answers": years,
        "share_votes_after_may_2025_mentioning_2025": round(float(
            (late["response_a_excerpt"].str.contains("2025") |
             late["response_b_excerpt"].str.contains("2025")).mean()), 3),
        "share_votes_mentioning_2024_not_2025": round(float(
            ((df["response_a_excerpt"].str.contains("2024") |
              df["response_b_excerpt"].str.contains("2024")) &
             ~(df["response_a_excerpt"].str.contains("2025") |
               df["response_b_excerpt"].str.contains("2025"))).mean()), 3),
    }

def label_validation() -> dict:
    """Agreement between the automatic prompt coder and my 150 hand codes,
    plus the precision of the dataset's own strict political tier."""
    hp = RES / "prompt_handcode_150.csv"
    if not hp.exists():
        return {}
    h = pd.read_csv(hp)
    h["auto"] = h["prompt_topics"].fillna("").ne("")
    Y = h["load"].eq("Y")
    P = h["load"].eq("P")
    tp = int((h["auto"] & Y).sum())
    fp = int((h["auto"] & ~Y & ~P).sum())
    fn = int((~h["auto"] & Y).sum())
    return {
        "hand_coded_rows": int(len(h)),
        "load_bearing_political": int(Y.sum()),
        "load_bearing_share": round(float(Y.mean()), 3),
        "partial": int(P.sum()),
        "not_political": int((~Y & ~P).sum()),
        "dataset_strict_tier_precision": round(float(Y.mean()), 3),
        "auto_coder_precision": round(tp / (tp + fp), 3),
        "auto_coder_recall": round(tp / (tp + fn), 3),
        "auto_coder_tp_fp_fn_tn": [tp, fp, fn, int((~h["auto"] & ~Y & ~P).sum())],
        "category_counts": h[Y]["category"].value_counts().to_dict(),
        "intent_counts": h[Y]["intent"].value_counts().to_dict(),
    }


def factcheck_summary() -> dict:
    """Summarise the hand-verified fact audit (results/factcheck_audit.csv)."""
    fp = RES / "factcheck_audit.csv"
    if not fp.exists():
        return {}
    au = pd.read_csv(fp)

    def cls(v):
        for k in ("correct", "declines", "wrong", "unverified"):
            if str(v).startswith(k):
                return k
        return str(v)

    au["cA"] = au["answer_a_verdict"].map(cls)
    au["cB"] = au["answer_b_verdict"].map(cls)
    one = au[((au.cA == "correct") & (au.cB == "wrong")) | ((au.cB == "correct") & (au.cA == "wrong"))]
    bw = au[(au.cA == "wrong") & (au.cB == "wrong")]
    bc = au[(au.cA == "correct") & (au.cB == "correct")]
    out = {
        "votes_audited": int(len(au)),
        "answers_audited": int(2 * len(au)),
        "answers_correct": int(((au.cA == "correct").sum() + (au.cB == "correct").sum())),
        "answers_wrong": int(((au.cA == "wrong").sum() + (au.cB == "wrong").sum())),
        "answers_decline": int(((au.cA == "declines").sum() + (au.cB == "declines").sum())),
        "answers_unverified": int(((au.cA == "unverified").sum() + (au.cB == "unverified").sum())),
        "both_correct_votes": int(len(bc)),
        "both_correct_outcomes": bc["winner"].value_counts().to_dict(),
        "one_sided_votes": int(len(one)),
        "one_sided_correct_won": int(((one.cA == "correct") & (one.winner == "model_a")).sum() +
                                     ((one.cB == "correct") & (one.winner == "model_b")).sum()),
        "both_wrong_votes": int(len(bw)),
        "both_wrong_outcomes": bw["winner"].value_counts().to_dict(),
        "models_with_a_wrong_answer": sorted(set(au.loc[au.cA == "wrong", "model_a"]) |
                                             set(au.loc[au.cB == "wrong", "model_b"])),
    }
    return out


def sensitive_summary() -> dict:
    """Summarise the hand-coded Tiananmen / Tank Man audit."""
    hp, vp = RES / "sensitive_handcode.csv", RES / "sensitive_votes_coded.csv"
    if not hp.exists() or not vp.exists():
        return {}
    h = pd.read_csv(hp).merge(pd.read_csv(vp)[["id", "pair", "winner"]], on="id", how="left")
    good = {"ACCURATE", "ACCURATE_RANGE"}
    h["kind"] = np.where(h["label"].isin(good), "answers",
                np.where(h["label"] == "CLARIFIES", "clarifies", "evades/refuses/denies"))
    vs = pd.read_csv(vp)
    acc_vs_non = vs[vs["pair"].isin(["accurate vs evasion/refusal", "evasion/refusal vs accurate"])]
    acc_wins = int((acc_vs_non["pair"].str.startswith("accurate") & acc_vs_non["winner"].eq("model_a")).sum() +
                   (acc_vs_non["pair"].str.startswith("evasion") & acc_vs_non["winner"].eq("model_b")).sum())
    return {
        "votes": int(vs["id"].nunique()),
        "responses_coded": int(len(h)),
        "answers": int((h["kind"] == "answers").sum()),
        "evades_refuses_denies": int((h["kind"] == "evades/refuses/denies").sum()),
        "clarifies": int((h["kind"] == "clarifies").sum()),
        "answer_rate": round(float((h["kind"] == "answers").mean()), 3),
        "deflection_by_model": h[h["kind"] != "answers"]["model"].value_counts().to_dict(),
        "votes_accurate_vs_deflection": int(len(acc_vs_non)),
        "accurate_answer_wins": acc_wins,
        "accurate_answer_ties": int((acc_vs_non["winner"] == "tie").sum()),
        "accurate_answer_losses": int(len(acc_vs_non) - acc_wins - (acc_vs_non["winner"] == "tie").sum()),
    }


def main() -> None:
    al = pd.read_csv(RES / "answer_features.csv")
    df = pd.read_csv(HERE.parent / "results" / "shortlist.csv")
    df["prompt_excerpt"] = df["prompt_excerpt"].fillna("")
    ov = json.loads((RES / "overview.json").read_text())

    # ---- paired log-odds on decisive votes -----------------------------------
    dec = df[df["winner"].isin(["model_a", "model_b"])]
    win_docs, lose_docs = [], []
    for _, r in dec.iterrows():
        a, b = r["response_a_excerpt"], r["response_b_excerpt"]
        if r["winner"] == "model_a":
            win_docs.append(words(a))
            lose_docs.append(words(b))
        else:
            win_docs.append(words(b))
            lose_docs.append(words(a))
    lo = log_odds(win_docs, lose_docs)
    lo.to_csv(RES / "winner_loser_logodds.csv", index=False)
    print("top winner words:\n", lo.head(25).to_string(index=False))
    print("\ntop loser words:\n", lo.tail(25).to_string(index=False))

    # ---- sentiment / register by topic --------------------------------------
    sent = pd.read_csv(RES / "sentiment.csv")
    sent["topic_list"] = sent["topics"].fillna("").str.split("|")
    rows = []
    for topic in ["public_policy", "geopolitics_conflict", "elections_voting",
                  "political_figures", "political_theory", "political_history",
                  "parties_ideology", "immigration", "creative_roleplay",
                  "media_info", "civic_practical", "business_tech", "other_personal"]:
        m = sent["topic_list"].map(lambda L: topic in L)
        sub = sent[m & (sent["lang_group"] == "en")]
        if len(sub) < 15:
            continue
        rows.append({
            "topic": topic, "en_rows": int(len(sub)),
            "mean_compound": round(float(pd.concat([sub["a_compound"], sub["b_compound"]]).mean()), 3),
            "share_negative_lt_-0.05": round(float((pd.concat([sub["a_compound"], sub["b_compound"]]) < -0.05).mean()), 3),
            "alarm_terms": round(float(pd.concat([sub["a_alarm_terms"], sub["b_alarm_terms"]]).mean()), 3),
            "moral_terms": round(float(pd.concat([sub["a_moral_terms"], sub["b_moral_terms"]]).mean()), 3),
            "hedges": round(float(pd.concat([sub["a_hedge_terms"], sub["b_hedge_terms"]]).mean()), 3),
            "empathy_share": round(float((sub["a_empathy"] + sub["b_empathy"]).mean() / 2), 3),
            "tie_rate": round(float((sub["winner"] == "tie").mean()), 3),
            "both_bad_rate": round(float((sub["winner"] == "both_bad").mean()), 3),
        })
    st = pd.DataFrame(rows).sort_values("mean_compound")
    st.to_csv(RES / "sentiment_by_topic.csv", index=False)
    print("\nsentiment by topic:\n", st.to_string(index=False))

    # ---- language effects ----------------------------------------------------
    lang = df.groupby("language").agg(
        rows=("id", "size"),
        tie_rate=("winner", lambda s: round(float((s == "tie").mean()), 3)),
        both_bad_rate=("winner", lambda s: round(float((s == "both_bad").mean()), 3)),
        strict_prompt_rate=("prompt_tier", lambda s: round(float((s == "strict").mean()), 3)),
    ).sort_values("rows", ascending=False)
    lang.to_csv(RES / "language_stats.csv")

    zh = df[df["language"].str.startswith("zh")]
    print(f"\nChinese rows: {len(zh)} | tie {(zh['winner']=='tie').mean():.3f} "
          f"| both_bad {(zh['winner']=='both_bad').mean():.3f} "
          f"| English tie {(df[df.language=='en']['winner']=='tie').mean():.3f} "
          f"| both_bad {(df[df.language=='en']['winner']=='both_bad').mean():.3f}")

    # ---- audit sample for hand-validating automatic labels -------------------
    lab = pd.read_csv(RES / "prompt_topics.csv").merge(
        df[["id", "prompt_excerpt"]], on="id", how="left")
    samp = lab.sample(40, random_state=20251104)[
        ["id", "prompt_excerpt", "topics", "intents", "prompt_topics", "prompt_tier", "winner"]]
    samp["prompt_excerpt"] = samp["prompt_excerpt"].str.slice(0, 220).str.replace("\n", " ", regex=False)
    samp.to_csv(RES / "label_validation_sample.csv", index=False)
    print("\nwrote label_validation_sample.csv (40 rows)")

    sv = sensitive_summary()
    print("\nsensitive-history audit:\n", json.dumps(sv, indent=2))
    (RES / "sensitive_summary.json").write_text(json.dumps(sv, indent=2))
    lv = label_validation()
    fc = factcheck_summary()
    print("\nlabel validation:\n", json.dumps(lv, indent=2))
    print("\nfact-check audit:\n", json.dumps(fc, indent=2))
    (RES / "label_validation.json").write_text(json.dumps(lv, indent=2))
    (RES / "factcheck_summary.json").write_text(json.dumps(fc, indent=2))

    rec = recency_and_validation(df)
    print("\nrecency & validation:\n", json.dumps(rec, indent=2))
    (RES / "supplement.json").write_text(json.dumps({
        "top_winner_tokens": lo.head(20).to_dict(orient="records"),
        "top_loser_tokens": lo.tail(20).to_dict(orient="records"),
        "chinese_rows": int(len(zh)),
        "recency_and_validation": rec,
    }, indent=2))


if __name__ == "__main__":
    main()
