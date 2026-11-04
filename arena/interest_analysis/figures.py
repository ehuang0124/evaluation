#!/usr/bin/env python3
"""Four summary figures for the shortlist analysis (matplotlib, no seaborn)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
FIG = RES / "figures"
FIG.mkdir(parents=True, exist_ok=True)

INK = "#1f2933"
ACCENT = "#2b6cb0"
WARN = "#c05621"
GREY = "#9aa5b1"
plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": GREY, "axes.labelcolor": INK,
    "text.color": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150,
})


def fig_outcomes() -> None:
    ov = json.loads((RES / "overview.json").read_text())
    w = ov["winner_counts"]
    n = ov["rows"]
    labels = ["model_a", "model_b", "tie", "both_bad"]
    vals = [w.get(k, 0) / n * 100 for k in labels]
    base = [35.8, 36.7, 15.9, 11.6]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    x = np.arange(len(labels))
    ax.bar(x - 0.19, vals, 0.36, color=ACCENT, label="shortlist (n=1,500)")
    ax.bar(x + 0.19, base, 0.36, color=GREY, label="all 135,634 votes")
    for i, v in enumerate(vals):
        ax.text(x[i] - 0.19, v + 0.4, f"{v:.1f}", ha="center", fontsize=8, color=ACCENT)
    for i, v in enumerate(base):
        ax.text(x[i] + 0.19, v + 0.4, f"{v:.1f}", ha="center", fontsize=8, color=GREY)
    ax.set_xticks(x)
    ax.set_xticklabels(["A wins", "B wins", "tie", "both bad"])
    ax.set_ylabel("% of votes")
    ax.set_title("Vote outcomes: political shortlist vs whole corpus", loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.set_ylim(0, 46)
    fig.tight_layout()
    fig.savefig(FIG / "outcomes.png")
    plt.close(fig)


def fig_topics() -> None:
    h = pd.read_csv(RES / "prompt_handcode_150.csv")
    counts = (h[h.load == "Y"]["category"].value_counts())
    names = {
        "POLICY_DOMESTIC": "Domestic policy / regulation",
        "POLFIG_LOOKUP": "Politician facts & officeholders",
        "ELECTIONS": "Elections & campaigns",
        "GEOPOLITICS": "Geopolitics & conflict",
        "IDEOLOGY_THEORY": "Ideology, parties, political theory",
        "INSTITUTIONS_LAW": "Institutions, law, constitutions",
        "POLITICAL_HISTORY": "Political history",
        "IMMIGRATION": "Immigration / citizenship",
        "MEDIA_DISCOURSE": "Media & political discourse",
        "CIVIC_PRACTICE": "Civic practice (how to vote)",
        "CREATIVE": "Creative writing with a political frame",
    }
    counts.index = [names.get(i, i) for i in counts.index]
    counts = counts[counts.index != "Creative writing with a political frame"]
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    y = np.arange(len(counts))[::-1]
    ax.barh(y, counts.values, color=ACCENT, height=0.65)
    ax.set_yticks(y)
    ax.set_yticklabels(counts.index, fontsize=9)
    for yi, v in zip(y, counts.values):
        ax.text(v + 0.25, yi, str(v), va="center", fontsize=8, color=INK)
    ax.set_xlabel("prompts (of 75 political prompts hand-coded from a 150-row sample)")
    ax.set_title("What people actually ask (dataset strict tier, hand-coded sample)", loc="left", fontsize=11)
    ax.set_xlim(0, max(counts.values) + 2)
    fig.tight_layout()
    fig.savefig(FIG / "prompt_categories.png")
    plt.close(fig)


def fig_features() -> None:
    t = pd.read_csv(RES / "feature_tests.csv")
    t = t[t["feature"] != "url"].copy()
    t = t.sort_values("delta_pp")
    labels = {
        "bold": "bold formatting", "numbered_list": "numbered list",
        "emoji": "emoji", "bullet_list": "bullet list", "disclaimer": "disclaimer",
        "table": "table", "numbers_dates": "numbers / dates", "hedge": "hedging",
        "lead_heading": "opens with heading", "empathy": "empathy / praise",
        "alarm_language": "alarm / threat words", "caveat": "explicit caveat",
        "citation_cue": "citation cue", "direct_answer": "bare yes/no opener",
        "comparison": "comparison", "conclusion": "summary closer",
        "moral_language": "moral language", "causal_explanation": "'because' reasoning",
        "named_institution": "named institution", "recommendation": "recommendation",
        "counterargument": "counterargument", "question_to_user": "ends with a question",
        "both_sides": "'both sides'", "refusal": "refusal",
        "example": "worked example", "second_person": "addresses 'you'",
        "uncertainty_admission": "admits uncertainty", "first_person": "'I' / 'my'",
    }
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    colors = [ACCENT if p < 0.05 else GREY for p in t["mcnemar_p"]]
    ax.barh([labels.get(f, f) for f in t["feature"]], t["delta_pp"], color=colors, height=0.7)
    ax.axvline(0, color=INK, lw=0.8)
    for i, (d, p) in enumerate(zip(t["delta_pp"], t["mcnemar_p"])):
        if p < 0.05:
            ax.text(d + (0.15 if d >= 0 else -0.15), i, f"p={p:.3f}",
                    va="center", ha="left" if d >= 0 else "right", fontsize=7, color=ACCENT)
    ax.set_xlabel("winner − loser, percentage points (1,117 decisive votes)")
    ax.set_title("What the winning answer has that the loser does not",
                 loc="left", fontsize=11)
    ax.set_xlim(-3.2, 5.4)
    fig.tight_layout()
    fig.savefig(FIG / "answer_features.png")
    plt.close(fig)


def fig_sentiment() -> None:
    st = pd.read_csv(RES / "sentiment_by_topic.csv").sort_values("mean_compound")
    names = {
        "geopolitics_conflict": "Geopolitics / conflict", "political_history": "Political history",
        "political_figures": "Politicians", "creative_roleplay": "Creative writing",
        "media_info": "Media & discourse", "parties_ideology": "Parties / ideology",
        "political_theory": "Political theory", "elections_voting": "Elections",
        "public_policy": "Public policy", "civic_practical": "Civic practice",
        "other_personal": "Personal / other", "business_tech": "Business & tech",
        "immigration": "Immigration",
    }
    st["label"] = st["topic"].map(lambda x: names.get(x, x))
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 4.0), sharey=True)
    y = np.arange(len(st))
    axes[0].barh(y, st["mean_compound"], color=[WARN if v < 0 else ACCENT for v in st["mean_compound"]])
    axes[0].axvline(0, color=INK, lw=0.8)
    axes[0].set_title("Mean VADER compound (English answers)", loc="left", fontsize=10)
    axes[0].set_xlabel("compound (−1 … +1)")
    axes[1].barh(y, st["share_negative_lt_-0.05"] * 100, color=GREY)
    axes[1].set_title("% of answers with compound < −0.05", loc="left", fontsize=10)
    axes[1].set_xlabel("% of answers")
    axes[1].set_xlim(0, 60)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(st["label"], fontsize=8.5)
    for ax in axes:
        ax.grid(axis="x", color="#e4e7eb", lw=0.6)
        ax.set_axisbelow(True)
    fig.suptitle("Sentiment register by topic (991 English rows, 1,982 answers)", x=0.01, ha="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "sentiment_by_topic.png")
    plt.close(fig)


def fig_sensitive() -> None:
    h = pd.read_csv(RES / "sensitive_handcode.csv")
    fam = {
        "qwen3-235b-a22b-no-thinking": "Qwen", "qwen3-235b-a22b": "Qwen", "qwq-32b": "Qwen",
        "deepseek-r1-0528": "DeepSeek", "deepseek-v3-0324": "DeepSeek",
        "gemini-2.5-pro": "Google", "gemini-2.5-flash": "Google",
        "gemini-2.0-flash-001": "Google",
        "claude-3-5-sonnet-20241022": "Anthropic", "claude-opus-4-20250514": "Anthropic",
        "claude-sonnet-4-20250514-thinking-32k": "Anthropic",
        "claude-3-5-haiku-20241022": "Anthropic",
        "chatgpt-4o-latest-20250326": "OpenAI", "gpt-4.1-2025-04-14": "OpenAI",
        "gpt-4.1-mini-2025-04-14": "OpenAI", "o3-mini": "OpenAI",
        "llama-4-maverick-03-26-experimental": "Meta", "llama-4-maverick-17b-128e-instruct": "Meta",
        "llama-3.3-70b-instruct": "Meta", "mistral-medium-2505": "Mistral",
        "command-a-03-2025": "Cohere", "grok-4-0709": "xAI",
    }
    h["family"] = h["model"].map(fam).fillna("other")
    h["kind"] = np.where(h["label"].isin(["ACCURATE", "ACCURATE_RANGE"]), "answers the question",
                np.where(h["label"] == "CLARIFIES", "asks for clarification", "evades / refuses / denies"))
    tab = pd.crosstab(h["family"], h["kind"])
    order = tab.sum(axis=1).sort_values(ascending=False).index
    tab = tab.loc[order]
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    left = np.zeros(len(tab))
    for col, color in [("answers the question", ACCENT), ("asks for clarification", GREY),
                       ("evades / refuses / denies", WARN)]:
        if col in tab:
            ax.barh(np.arange(len(tab)), tab[col], left=left, color=color, label=col, height=0.6)
            left += tab[col].values
    ax.set_yticks(np.arange(len(tab)))
    ax.set_yticklabels(tab.index)
    ax.invert_yaxis()
    ax.set_xlabel("responses to Tiananmen / Tank Man probes (n=36, 18 votes)")
    ax.set_title("Sensitive-history probes: who answers, who deflects", loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "sensitive_probe.png")
    plt.close(fig)


if __name__ == "__main__":
    fig_outcomes()
    fig_topics()
    fig_features()
    fig_sentiment()
    fig_sensitive()
    print("figures written to", FIG)
