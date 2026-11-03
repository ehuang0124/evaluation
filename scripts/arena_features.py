"""Shared feature extraction for the arena-human-preference-140k analysis.

Kept in one module so the triage script (topic_prevalence.py) and the modelling script
(fit_topic_bt.py) cannot drift apart on prompt parsing, topic labels, or style features.

Three jobs:
  * pull the first user turn out of a conversation column;
  * assign one public-interest topic per battle from a versioned lexicon;
  * turn `conv_metadata` into antisymmetric (a - b) style covariates.
"""

from __future__ import annotations

import math
import re
from typing import Any

GENERAL_TOPIC = "general"

# Versioned, recall-oriented lexicon. Bump LEXICON_VERSION on any edit and report it
# alongside results -- topic labels are the dominant source of bias in this design.
LEXICON_VERSION = "v0.1"

# Priority order used when a prompt matches several domains. Ordering is a judgment
# call: the specific beats the general (elections before policy, health before policy).
TOPIC_PRIORITY = [
    "elections_politics",
    "immigration",
    "climate_environment",
    "health_public_health",
    "civil_rights_law",
    "foreign_affairs_security",
    "tech_regulation",
    "economy_labor",
    "education",
    "policy_governance",
]

TOPIC_PATTERNS: dict[str, str] = {
    "elections_politics": (
        r"\b(?:election|elections|electoral|vote|votes|voting|ballot|ballots|candidate|"
        r"candidates|president|presidential|parliament|parliamentary|congress|congressional|"
        r"senate|senator|democrat|democrat party|democratic party|republican|prime minister|"
        r"chancellor|coalition|referendum|gerrymander\w*|impeach\w*)\b"
    ),
    "policy_governance": (
        r"\b(?:policy|policies|legislation|legislative|bill|lawmakers?|regulation|regulatory|"
        r"government|governance|public sector|tax|taxes|taxation|subsid\w+|welfare|"
        r"social security|bureaucrac\w+|constitution\w*)\b"
    ),
    "health_public_health": (
        r"\b(?:vaccin\w+|pandemic|epidemic|public health|medicare|medicaid|nhs|healthcare|"
        r"health care|insulin|opioid\w*|abortion|mental health|drug approval|fda|who)\b"
    ),
    "climate_environment": (
        r"\b(?:climate change|global warming|emissions?|carbon|greenhouse|renewable\w*|"
        r"solar|wind power|fossil fuel\w*|net zero|biodiversity|deforestation|"
        r"pollution|epa|paris agreement)\b"
    ),
    "immigration": (
        r"\b(?:immigra\w+|migrant\w*|asylum|refugee\w*|border control|deport\w+|"
        r"visa|green card|citizenship|undocumented)\b"
    ),
    "economy_labor": (
        r"\b(?:inflation|recession|unemployment|minimum wage|monetary policy|interest rates?|"
        r"central bank|federal reserve|tariffs?|trade war|gig economy|union\w*|"
        r"housing crisis|rent control|inequality|cost of living)\b"
    ),
    "education": (
        r"\b(?:public school\w*|curriculum|student loans?|tuition|school district|"
        r"education policy|standardized test\w*|teachers? union|charter school\w*)\b"
    ),
    "foreign_affairs_security": (
        r"\b(?:war|warfare|invasion|ceasefire|sanctions?|nato|united nations|terroris\w+|"
        r"genocide|military aid|arms deal|nuclear weapon\w*|geopolitic\w*)\b"
    ),
    "civil_rights_law": (
        r"\b(?:free speech|first amendment|second amendment|gun control|discrimination|"
        r"affirmative action|lgbtq?\w*|same-sex|supreme court|judicial|voting rights|"
        r"police reform|death penalty|civil liberties)\b"
    ),
    "tech_regulation": (
        r"\b(?:ai regulation|data privacy|gdpr|antitrust|section 230|content moderation|"
        r"surveillance|encryption|net neutrality|deepfake\w*|copyright|open source)\b"
    ),
}

_COMPILED = {topic: re.compile(pattern, re.IGNORECASE) for topic, pattern in TOPIC_PATTERNS.items()}

# Style covariates, all antisymmetric (a minus b). Log1p keeps long responses from
# dominating, and differences are what identify a battle.
STYLE_FEATURES = ["log_tokens", "bold", "list", "header"]

HF_COLUMNS = [
    "id",
    "model_a",
    "model_b",
    "winner",
    "evaluation_session_id",
    "evaluation_order",
    "conversation_a",
    "conv_metadata",
    "language",
    "timestamp",
    "is_code",
]


def first_user_text(conversation: Any) -> str:
    """Text of the first user turn.

    Duck-types the container: `Dataset.to_pandas()` hands back lists in some datasets
    versions and numpy object arrays in others.
    """
    if conversation is None or isinstance(conversation, (str, bytes, dict)):
        return ""
    for turn in conversation:
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        content = turn.get("content")
        if isinstance(content, str):
            return content.strip()
        chunks = []
        for block in content or []:
            if isinstance(block, dict):
                text = block.get("text")
                if text:
                    chunks.append(text)
            elif isinstance(block, str):
                chunks.append(block)
        if chunks:
            return "\n".join(chunks).strip()
    return ""


def topic_flags(text: str) -> dict[str, bool]:
    return {topic: bool(rx.search(text)) for topic, rx in _COMPILED.items()}


def label_prompt(text: str) -> tuple[str, dict[str, bool]]:
    """Single topic label: first match in TOPIC_PRIORITY, else GENERAL_TOPIC."""
    flags = topic_flags(text)
    for topic in TOPIC_PRIORITY:
        if flags[topic]:
            return topic, flags
    return GENERAL_TOPIC, flags


def label_topic(text: str) -> str:
    return label_prompt(text)[0]


def _count(meta: dict, key: str, sub: str | None = None) -> float:
    value = meta.get(key)
    if isinstance(value, dict):
        value = value.get(sub) if sub else sum(v for v in value.values() if isinstance(v, (int, float)))
    return float(value) if isinstance(value, (int, float)) else 0.0


def style_features(meta: Any) -> dict[str, float]:
    """Antisymmetric style deltas (a - b) from conv_metadata; zeros if unavailable."""
    if not isinstance(meta, dict):
        return dict.fromkeys(STYLE_FEATURES, 0.0)
    tokens_a = _count(meta, "sum_assistant_a_tokens")
    tokens_b = _count(meta, "sum_assistant_b_tokens")
    bold_a = _count(meta, "bold_count_a")
    bold_b = _count(meta, "bold_count_b")
    list_a = _count(meta, "list_count_a")
    list_b = _count(meta, "list_count_b")
    header_a = _count(meta, "header_count_a")
    header_b = _count(meta, "header_count_b")
    return {
        "log_tokens": math.log1p(tokens_a) - math.log1p(tokens_b),
        "bold": math.log1p(bold_a) - math.log1p(bold_b),
        "list": math.log1p(list_a) - math.log1p(list_b),
        "header": math.log1p(header_a) - math.log1p(header_b),
    }


def prepare(df, general_topic: str = GENERAL_TOPIC) -> "pd.DataFrame":
    """Add prompt / topic / flag / outcome / style columns. Requires pandas."""
    import pandas as pd  # local import keeps the pure helpers importable without pandas

    out = df.copy()
    out["prompt"] = out["conversation_a"].map(first_user_text)
    labels = out["prompt"].map(label_prompt)
    out["topic"] = labels.map(lambda pair: pair[0])
    flag_frame = pd.DataFrame(list(labels.map(lambda pair: pair[1])), index=out.index)
    out = pd.concat([out, flag_frame.add_prefix("flag::")], axis=1)
    out["decided"] = out["winner"].isin(["model_a", "model_b"])
    out["y"] = (out["winner"] == "model_a").astype(int)
    style = out["conv_metadata"].map(style_features) if "conv_metadata" in out else None
    if style is not None:
        style_frame = pd.DataFrame(list(style), index=out.index)
        for feature in STYLE_FEATURES:
            out[f"style::{feature}"] = style_frame[feature].astype(float)
    else:
        for feature in STYLE_FEATURES:
            out[f"style::{feature}"] = 0.0
    out["is_general_topic"] = out["topic"] == general_topic
    return out
