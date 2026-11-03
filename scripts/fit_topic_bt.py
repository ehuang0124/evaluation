#!/usr/bin/env python3
"""Topic-conditional, style- and position-adjusted Bradley-Terry ratings.

Model
-----
One logistic regression over decided battles (winner in {model_a, model_b}):

    logit P(model_a wins) =
          (1[a = k] - 1[b = k]) * beta_k                    # global BT strength
        + (1[a = k] - 1[b = k]) * delta_{t,k} * 1[t != ref]  # topic-specific deviation
        + gamma                                              # slot-A advantage (position bias)
        + sum_j phi_j * (style_a,j - style_b,j)              # length / markdown controls

`beta_k` is a model's strength on the reference topic (`general`: prompts that hit no
public-interest domain). `delta_{t,k}` is how much that model's log-odds shift on topic t
relative to general prompts -- the estimand of interest. Everything is estimated jointly,
so a topic that happens to be dominated by one pair of models cannot masquerade as a
topic effect; the shared `beta_k` absorbs model strength and `gamma` absorbs position.

Inference is a cluster bootstrap over `evaluation_session_id`, because a session casts
several dependent votes and treating them as independent understates the CIs.

Ties and `both_bad` are dropped from the fit (standard for BT) but their rates are
reported separately -- on contested topics, "both bad" is itself an interesting outcome.

Usage
-----
    python scripts/fit_topic_bt.py --simulate            # validate recovery, no data needed
    python scripts/fit_topic_bt.py --limit 30000         # quick real-data run
    python scripts/fit_topic_bt.py --max-models 12 --bootstrap 500
    python scripts/fit_topic_bt.py --local data/*.parquet --labelled labels.parquet
"""

from __future__ import annotations

import argparse
import glob
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

from arena_features import (
    GENERAL_TOPIC,
    HF_COLUMNS,
    LEXICON_VERSION,
    STYLE_FEATURES,
    TOPIC_PRIORITY,
    prepare,
)

DATASET = "lmarena-ai/arena-human-preference-140k"
ELO_SCALE = 400.0 / math.log(10.0)  # arena's alpha: log-odds -> Elo points


# --------------------------------------------------------------------------- data
def load_frame(args) -> pd.DataFrame:
    if args.labelled:
        return pd.read_parquet(args.labelled)
    if args.local:
        paths = [p for pattern in args.local for p in (glob.glob(pattern) or [pattern])]
        df = pd.read_parquet(paths)
        return df[[c for c in HF_COLUMNS if c in df.columns]]
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("pip install datasets pandas pyarrow scipy")
    try:
        ds = load_dataset(args.dataset, split="train", columns=HF_COLUMNS)
    except TypeError:
        ds = load_dataset(args.dataset, split="train")
        ds = ds.remove_columns([c for c in ds.column_names if c not in HF_COLUMNS])
    if args.limit:
        ds = ds.select(range(min(args.limit, len(ds))))
    return ds.to_pandas()


def select_analysis_set(frame: pd.DataFrame, args) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Restrict to decided battles among the chosen models and topics."""
    if "topic" not in frame:
        frame = prepare(frame, args.reference_topic)

    wanted_topics = [t.strip() for t in args.topics.split(",")] if args.topics else [
        t for t in TOPIC_PRIORITY
    ]
    topics = [t for t in wanted_topics if t in set(frame["topic"])]
    topics = sorted(topics) + [args.reference_topic]
    if args.reference_topic not in set(frame["topic"]):
        sys.exit(f"reference topic {args.reference_topic!r} not present in the data")

    counts = pd.concat([frame["model_a"], frame["model_b"]]).value_counts()
    models = list(counts.head(args.max_models).index)
    if args.exclude_models:
        drop = {m.strip() for m in args.exclude_models.split(",")}
        models = [m for m in models if m not in drop]
    if len(models) < 3:
        sys.exit("need at least 3 models")

    keep = (
        frame["decided"]
        & frame["model_a"].isin(models)
        & frame["model_b"].isin(models)
        & frame["topic"].isin(topics)
    )
    sub = frame.loc[keep].reset_index(drop=True)
    if sub.empty:
        sys.exit("no battles left after filtering")
    if args.min_topic_battles:
        keep_topics = [t for t in topics if (sub["topic"] == t).sum() >= args.min_topic_battles]
        if args.reference_topic not in keep_topics:
            keep_topics.append(args.reference_topic)
        dropped = sorted(set(topics) - set(keep_topics))
        if dropped:
            print(f"dropping topics with < {args.min_topic_battles} decided battles: {dropped}")
        topics = [t for t in topics if t in keep_topics]
        sub = sub[sub["topic"].isin(topics)].reset_index(drop=True)
    return sub, models, topics


def build_design(
    frame: pd.DataFrame,
    models: list[str],
    topics: list[str],
    reference_model: str,
    reference_topic: str,
    style_features: list[str],
) -> tuple[sparse.csr_matrix, np.ndarray, list[str]]:
    # Compact 0-based positions over the non-reference levels (enumerate over the full
    # list would leave a gap where the reference sits, and overflow the design matrix).
    model_pos = {m: i for i, m in enumerate([m for m in models if m != reference_model])}
    topic_pos = {t: i for i, t in enumerate([t for t in topics if t != reference_topic])}
    n_main = len(model_pos)
    n_int = len(topic_pos) * n_main

    names = [f"rating::{m}" for m in model_pos]
    names += [f"delta::{t}::{m}" for t in topic_pos for m in model_pos]
    names += ["side"]
    names += [f"style::{s}" for s in style_features]

    n = len(frame)
    row_idx = np.arange(n)
    a = frame["model_a"].map(model_pos).to_numpy(dtype=float)
    b = frame["model_b"].map(model_pos).to_numpy(dtype=float)
    t = frame["topic"].map(topic_pos).to_numpy(dtype=float)

    data, rows, cols = [], [], []

    def add(mask: np.ndarray, col_ids: np.ndarray, value: float) -> None:
        rows.append(row_idx[mask])
        cols.append(col_ids[mask])
        data.append(np.full(int(mask.sum()), value))

    mask_a, mask_b = ~np.isnan(a), ~np.isnan(b)
    add(mask_a, a, 1.0)
    add(mask_b, b, -1.0)

    has_topic = ~np.isnan(t)
    add(mask_a & has_topic, n_main + t * n_main + a, 1.0)
    add(mask_b & has_topic, n_main + t * n_main + b, -1.0)

    add(np.ones(n, dtype=bool), np.full(n, float(n_main + n_int)), 1.0)  # side

    for j, feature in enumerate(style_features):
        col = n_main + n_int + 1 + j
        values = frame[f"style::{feature}"].to_numpy(dtype=float)
        rows.append(row_idx)
        cols.append(np.full(n, float(col)))
        data.append(values)

    X = sparse.csr_matrix(
        (np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n, len(names)),
    )
    return X, frame["y"].to_numpy(dtype=float), names


# --------------------------------------------------------------------------- model
def fit_irls(
    X: sparse.csr_matrix,
    y: np.ndarray,
    sample_weight: np.ndarray | None = None,
    l2: float = 1.0,
    max_iter: int = 100,
    tol: float = 1e-9,
) -> tuple[np.ndarray, float]:
    """Ridge-penalized logistic regression by damped Newton (IRLS)."""
    n, p = X.shape
    sw = np.ones(n) if sample_weight is None else np.asarray(sample_weight, dtype=float)
    theta = np.zeros(p)

    def loss(candidate: np.ndarray) -> float:
        eta = X @ candidate
        return float(np.sum(sw * (np.logaddexp(0.0, eta) - y * eta)) + 0.5 * l2 * candidate @ candidate)

    current = loss(theta)
    for _ in range(max_iter):
        eta = X @ theta
        mu = 1.0 / (1.0 + np.exp(-eta))
        w = sw * mu * (1.0 - mu)
        grad = np.asarray(X.T @ (sw * (y - mu))).ravel() - l2 * theta
        hess = (X.T @ X.multiply(w[:, None])).toarray() + l2 * np.eye(p)
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(hess, grad, rcond=None)[0]
        scale = 1.0
        accepted = False
        while scale > 1e-8:
            candidate = theta + scale * step
            candidate_loss = loss(candidate)
            if candidate_loss < current:
                theta, current, accepted = candidate, candidate_loss, True
                break
            scale *= 0.5
        if not accepted:
            break
        if np.max(np.abs(scale * step)) < tol:
            break
    return theta, current


def cluster_bootstrap(
    X: sparse.csr_matrix,
    y: np.ndarray,
    clusters: np.ndarray,
    n_boot: int,
    l2: float,
    seed: int = 0,
    verbose: bool = True,
) -> np.ndarray:
    """Resample sessions (not rows) with replacement; returns (n_boot, n_params)."""
    codes, uniques = pd.factorize(clusters)
    n_clusters = len(uniques)
    counts_matrix = np.zeros((n_boot, n_clusters), dtype=np.int32)
    rng = np.random.default_rng(seed)
    # multinomial over clusters == resampling clusters with replacement
    for b in range(n_boot):
        counts_matrix[b] = rng.multinomial(n_clusters, np.full(n_clusters, 1.0 / n_clusters))
    thetas = np.zeros((n_boot, X.shape[1]))
    for b in range(n_boot):
        row_w = counts_matrix[b][codes].astype(float)
        mask = row_w > 0
        theta, _ = fit_irls(X[mask], y[mask], row_w[mask], l2=l2)
        thetas[b] = theta
        if verbose and (b + 1) % 50 == 0:
            print(f"  bootstrap {b + 1}/{n_boot}", flush=True)
    return thetas


def summarize(
    theta: np.ndarray,
    boot: np.ndarray | None,
    names: list[str],
    models: list[str],
    topics: list[str],
    reference_model: str,
    reference_topic: str,
    frame: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    def ci(lo_hi: tuple[float, float] | None) -> tuple[float, float]:
        return lo_hi if lo_hi else (float("nan"), float("nan"))

    if boot is not None:
        lo, hi = np.percentile(boot, 2.5, axis=0), np.percentile(boot, 97.5, axis=0)
    else:
        lo = hi = np.full(len(theta), np.nan)

    index = {name: i for i, name in enumerate(names)}

    ratings = []
    for model in [reference_model] + [m for m in models if m != reference_model]:
        if model == reference_model:
            beta = l_beta = h_beta = 0.0
        else:
            i = index[f"rating::{model}"]
            beta, l_beta, h_beta = theta[i], lo[i], hi[i]
        ratings.append(
            {
                "model": model,
                "reference_topic": reference_topic,
                "log_odds": round(float(beta), 4),
                "elo": round(1000.0 + ELO_SCALE * float(beta), 1),
                "elo_lo": round(1000.0 + ELO_SCALE * float(l_beta), 1),
                "elo_hi": round(1000.0 + ELO_SCALE * float(h_beta), 1),
                "battles": int(((frame["model_a"] == model) | (frame["model_b"] == model)).sum()),
            }
        )

    deltas = []
    for topic in topics:
        if topic == reference_topic:
            continue
        for model in models:
            n_model_topic = int(
                (((frame["model_a"] == model) | (frame["model_b"] == model)) & (frame["topic"] == topic)).sum()
            )
            if model == reference_model:
                deltas.append(
                    {"topic": topic, "model": model, "delta_log_odds": 0.0, "delta_lo": 0.0,
                     "delta_hi": 0.0, "elo_delta": 0.0, "ci_excludes_zero": False,
                     "battles": n_model_topic, "is_reference_model": True}
                )
                continue
            i = index[f"delta::{topic}::{model}"]
            deltas.append(
                {
                    "topic": topic,
                    "model": model,
                    "delta_log_odds": round(float(theta[i]), 4),
                    "delta_lo": round(float(lo[i]), 4),
                    "delta_hi": round(float(hi[i]), 4),
                    "elo_delta": round(ELO_SCALE * float(theta[i]), 1),
                    "ci_excludes_zero": bool(np.isfinite(lo[i]) and (lo[i] > 0 or hi[i] < 0)),
                    "battles": n_model_topic,
                    "is_reference_model": False,
                }
            )

    covariates = pd.DataFrame(
        [
            {
                "term": name,
                "coef": round(float(theta[index[name]]), 4),
                "lo": round(float(lo[index[name]]), 4),
                "hi": round(float(hi[index[name]]), 4),
            }
            for name in ["side"] + [f"style::{s}" for s in STYLE_FEATURES]
            if name in index
        ]
    )

    return {
        "ratings": pd.DataFrame(ratings).sort_values("elo", ascending=False),
        "deltas": pd.DataFrame(deltas).sort_values(["topic", "delta_log_odds"], ascending=[True, False]),
        "covariates": covariates,
    }


# --------------------------------------------------------------------------- simulation
def simulate(n_battles: int = 8000, seed: int = 0) -> tuple[pd.DataFrame, dict]:
    """Synthetic release with known parameters, to validate the estimator."""
    rng = np.random.default_rng(seed)
    models = [
        "alpha", "bravo", "charlie", "delta", "echo", "foxtrot",
        "golf", "hotel", "india", "juliet",
    ]
    topics = [GENERAL_TOPIC, "climate_environment", "health_public_health", "elections_politics"]
    prompts = {
        GENERAL_TOPIC: ["Compare Tormenta20 with DnD5e", "Write a haiku about autumn"],
        "climate_environment": ["What should the emissions target be for 2035?",
                                "Is carbon capture worth the subsidy?"],
        "health_public_health": ["Should the vaccine mandate cover schoolchildren?",
                                 "How should public health agencies handle opioid prescribing?"],
        "elections_politics": ["How do I read the election polling for the senate race?",
                               "Was the referendum campaign fair?"],
    }
    beta = dict(zip(models, np.linspace(0.8, -0.8, len(models))))
    deltas = {
        "climate_environment": dict(zip(models, np.linspace(0.4, -0.4, len(models)))),
        "health_public_health": dict(zip(models, np.linspace(-0.3, 0.3, len(models)))),
        "elections_politics": dict(zip(models, np.zeros(len(models)))),
    }
    style_true = {"log_tokens": 0.35, "bold": 0.05, "list": 0.0, "header": 0.0}
    side_true = 0.06

    rows = []
    for _ in range(n_battles):
        a, b = rng.choice(models, size=2, replace=False)
        topic = rng.choice(topics, p=[0.6, 0.15, 0.15, 0.10])
        tokens_a, tokens_b = rng.lognormal(6.0, 0.6), rng.lognormal(6.0, 0.6)
        bold_a, bold_b = rng.poisson(6), rng.poisson(6)
        style = {
            "log_tokens": math.log1p(tokens_a) - math.log1p(tokens_b),
            "bold": math.log1p(bold_a) - math.log1p(bold_b),
            "list": 0.0,
            "header": 0.0,
        }
        eta = beta[a] - beta[b] + side_true + sum(style_true[k] * v for k, v in style.items())
        if topic != GENERAL_TOPIC:
            eta += deltas[topic][a] - deltas[topic][b]
        y = int(rng.random() < 1.0 / (1.0 + math.exp(-eta)))
        rows.append(
            {
                "id": f"sim-{len(rows)}",
                "model_a": a,
                "model_b": b,
                "winner": "model_a" if y else "model_b",
                "evaluation_session_id": f"sess-{len(rows) // 3}",
                "evaluation_order": 1,
                "conversation_a": [
                    {"role": "user", "content": [{"type": "text", "text": str(rng.choice(prompts[topic]))}]}
                ],
                "conv_metadata": {
                    "sum_assistant_a_tokens": tokens_a,
                    "sum_assistant_b_tokens": tokens_b,
                    "bold_count_a": {"**": bold_a},
                    "bold_count_b": {"**": bold_b},
                    "list_count_a": {"ordered": 0, "unordered": 0},
                    "list_count_b": {"ordered": 0, "unordered": 0},
                    "header_count_a": {"h1": 0, "h2": 0},
                    "header_count_b": {"h1": 0, "h2": 0},
                },
                "language": "en",
                "timestamp": "2025-05-01T00:00:00",
                "is_code": False,
            }
        )
    truth = {"beta": beta, "deltas": deltas, "style": style_true, "side": side_true,
             "models": models, "topics": topics}
    return pd.DataFrame(rows), truth


# Regression guards, not precision claims. A structural bug (bad reference coding,
# non-compact design columns) shifts estimates by ~0.7 log-odds and trips these
# immediately; ordinary finite-sample noise sits well inside them.
BETA_TOLERANCE = 0.10
DELTA_TOLERANCE = 0.30


def run_simulation(n_battles: int, l2: float) -> None:
    raw, truth = simulate(n_battles)
    frame = prepare(raw, GENERAL_TOPIC)
    models = truth["models"]
    topics = truth["topics"]
    X, y, names = build_design(frame, models, topics, models[0], GENERAL_TOPIC, STYLE_FEATURES)
    theta, _ = fit_irls(X, y, l2=l2)
    index = {n: i for i, n in enumerate(names)}

    # Estimates are relative to the reference model (whose rating is pinned at 0 and
    # whose topic delta is pinned at 0), so compare against differences from it.
    ref = models[0]
    worst = 0.0
    print("== parameter recovery (noise-free design, finite sample) ==")
    for model in models[1:]:
        err = abs(theta[index[f"rating::{model}"]] - (truth["beta"][model] - truth["beta"][ref]))
        worst = max(worst, err)
    print(f"  max |beta error|      : {worst:.4f}")
    worst_delta = 0.0
    for topic in topics[1:]:
        for model in models[1:]:
            target = truth["deltas"][topic][model] - truth["deltas"][topic][ref]
            err = abs(theta[index[f"delta::{topic}::{model}"]] - target)
            worst_delta = max(worst_delta, err)
    print(f"  max |delta error|     : {worst_delta:.4f}")
    print(f"  side coef recovered   : {theta[index['side']]:+.4f} (true {truth['side']:+.2f})")
    for feature, value in truth["style"].items():
        print(f"  style {feature:11s}: {theta[index[f'style::{feature}']]:+.4f} (true {value:+.2f})")
    print(f"  battles fitted        : {len(y):,}   parameters: {len(theta)}")
    print("  per-topic battles     : " + ", ".join(
        f"{t}={int((frame['topic'] == t).sum()):,}" for t in topics))
    print("  note: delta error is larger than beta error because each delta is identified")
    print("        off one topic's battles, not the whole corpus -- see memo section 4.")
    if worst > BETA_TOLERANCE or worst_delta > DELTA_TOLERANCE:
        sys.exit(
            f"FAIL: beta error {worst:.3f} (tol {BETA_TOLERANCE}) or delta error "
            f"{worst_delta:.3f} (tol {DELTA_TOLERANCE}) -- at this sample size that is a "
            "design/identifiability bug, not noise"
        )
    print(f"OK: beta within {BETA_TOLERANCE}, delta within {DELTA_TOLERANCE} log-odds "
          "(residual error is finite-sample noise; it shrinks roughly as 1/sqrt(N))")


# --------------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--local", nargs="*", default=None, help="local parquet file(s)")
    p.add_argument("--labelled", default=None, help="parquet produced by build_topics.py")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--topics", default=None, help="comma-separated topics; default all public-interest domains")
    p.add_argument("--reference-topic", default=GENERAL_TOPIC)
    p.add_argument("--max-models", type=int, default=12, help="fit only the N most-battled models")
    p.add_argument("--exclude-models", default=None, help="comma-separated model names to drop")
    p.add_argument("--min-topic-battles", type=int, default=300, help="drop topics thinner than this")
    p.add_argument("--bootstrap", type=int, default=200, help="cluster bootstrap replicates (0 = skip)")
    p.add_argument("--l2", type=float, default=1.0, help="ridge penalty (counts as pseudo-observations)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--outdir", default="outputs")
    p.add_argument("--simulate", action="store_true", help="validate the estimator on synthetic data")
    p.add_argument("--simulate-n", type=int, default=60000, help="battles in the simulation check")
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.simulate:
        run_simulation(n_battles=args.simulate_n, l2=args.l2)
        return

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    raw = load_frame(args)
    frame = prepare(raw, args.reference_topic) if "topic" not in raw else raw
    sub, models, topics = select_analysis_set(frame, args)

    # Pin the most-battled model at 1000: it has the tightest estimate, so anchoring on it
    # minimizes how much the reference choice inflates CIs elsewhere.
    appearances = pd.concat([sub["model_a"], sub["model_b"]]).value_counts()
    reference_model = next((m for m in appearances.index if m in models), models[0])

    X, y, names = build_design(sub, models, topics, reference_model, args.reference_topic, STYLE_FEATURES)
    print("== design ==")
    print(f"  lexicon              {LEXICON_VERSION}")
    print(f"  battles fitted       {len(y):,} (decided only)")
    print(f"  models               {len(models)} (reference: {reference_model})")
    print(f"  topics               {len(topics)} (reference: {args.reference_topic})")
    print(f"  parameters           {len(names)}")
    print(f"  sessions             {sub['evaluation_session_id'].nunique():,}")

    theta, loss = fit_irls(X, y, l2=args.l2)
    print(f"  penalized log-loss   {loss:,.1f}")

    boot = None
    if args.bootstrap:
        print(f"== cluster bootstrap over sessions ({args.bootstrap} replicates) ==")
        boot = cluster_bootstrap(X, y, sub["evaluation_session_id"].to_numpy(), args.bootstrap, args.l2, args.seed)

    tables = summarize(theta, boot, names, models, topics, reference_model, args.reference_topic, sub)
    for name, table in tables.items():
        table.to_csv(outdir / f"topic_bt_{name}.csv", index=False)

    wide = tables["deltas"].pivot(index="model", columns="topic", values="delta_log_odds")
    wide.to_csv(outdir / "topic_bt_delta_matrix.csv")

    print("\n== adjusted strength on the reference topic (Elo-like, reference model = 1000) ==")
    print(tables["ratings"][["model", "elo", "elo_lo", "elo_hi", "battles"]].to_string(index=False))

    print("\n== topic-specific shifts vs. reference topic (log-odds, 95% cluster-bootstrap CI) ==")
    print(tables["deltas"].to_string(index=False))

    print("\n== side and style coefficients ==")
    print(tables["covariates"].to_string(index=False))
    print("  positive style coef = longer/more-markdown answers win more, i.e. the adjustment matters")
    print(f"\nWrote CSVs to {outdir.resolve()}")


if __name__ == "__main__":
    main()
