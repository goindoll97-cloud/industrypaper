# -*- coding: utf-8 -*-
"""
Study 2 publication figures: where the Hybrid architecture adds value.

Main message
------------
The Hybrid system is not better because it uses a different/better LLM.
It uses the same frozen LLM for ambiguous cases, but avoids LLM inference
when deterministic chemical identity resolution is sufficient.

Run from study2_eval_v2:
    python 06_visualize_retrieval_results.py

Expected inputs
---------------
intermediate/retrieval_predictions_scored.csv
intermediate/retrieval_metrics_summary.csv
intermediate/retrieval_metrics_by_gold_category.csv
intermediate/retrieval_metrics.json
data/retrieval_GOLD.csv
intermediate/llm_only_calls.csv
intermediate/hybrid_review_calls.csv
review/retrieval_gold_manual_review.csv

Outputs
-------
PNG figures only (presentation-ready):
figures/fig1_overall_accuracy.png
figures/fig2_routing_subset_accuracy.png
figures/fig3_llm_escalation_paired_outcomes.png
figures/fig4_deterministic_subset_errors.png
figures/fig5_efficiency_cost_time.png
figures/fig6_accuracy_by_source_category.png
figures/fig7_shared_llm_failure_types.png

No CSV/Excel/SVG files are written by this presentation version.

Important interpretation
------------------------
Figures 2-4 are the key figures for the architectural argument:
1) deterministic subset: Hybrid resolves 49 cases without LLM;
2) same 49 cases still expose LLM-only to avoidable stochastic error;
3) ambiguous 63 cases use the same LLM in both systems and therefore
   show very similar performance;
4) Hybrid's value is routing, determinism, reproducibility and lower
   LLM use, not a claim that its LLM component is intrinsically better.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Manual qualitative coding of the 17 observed LLM-only errors.
# This coding is used only for descriptive error-mechanism figures.
# It is NOT an automated classifier.
# ---------------------------------------------------------------------
PRIMARY_ERROR_TYPE = {
    "RQ-0003": "Chemical identity/speciation misinterpretation",
    "RQ-0023": "Chemical identity/speciation misinterpretation",
    "RQ-0037": "Chemical identity/speciation misinterpretation",
    "RQ-0039": "Chemical identity/speciation misinterpretation",
    "RQ-0061": "Chemical identity/speciation misinterpretation",
    "RQ-0075": "Chemical identity/speciation misinterpretation",

    "RQ-0008": "Regulatory scope over-extension",
    "RQ-0011": "Regulatory scope over-extension",
    "RQ-0034": "Regulatory scope over-extension",
    "RQ-0053": "Regulatory scope over-extension",
    "RQ-0089": "Regulatory scope over-extension",

    "RQ-0001": "Reason-decision inconsistency",
    "RQ-0017": "Reason-decision inconsistency",
    "RQ-0060": "Reason-decision inconsistency",
    "RQ-0101": "Reason-decision inconsistency",
    "RQ-0104": "Reason-decision inconsistency",
    "RQ-0110": "Reason-decision inconsistency",
}


# ---------------------------------------------------------------------
# Visual identity: one fixed color per system, used in EVERY figure.
# Orange/blue pair is colour-blind safe (Okabe-Ito family).
# ---------------------------------------------------------------------
COLORS = {
    "LLM_ONLY": "#E07B39",        # warm orange
    "HYBRID": "#2C6E9E",          # deep blue
    "LLM_ONLY_LIGHT": "#F4C9A8",
    "HYBRID_LIGHT": "#A9C8E0",
    "NEUTRAL": "#8C8C8C",
    "NEUTRAL_LIGHT": "#D3D3D3",
    "NEUTRAL_DARK": "#4D4D4D",
    "TEXT": "#222222",
    "GRID": "#E6E6E6",
}
SYSTEM_LABEL = {"LLM_ONLY": "LLM-only", "HYBRID": "Hybrid"}


def apply_style() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 10.5,
        "axes.titlesize": 12.5,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.titlepad": 14,
        "axes.labelsize": 10.5,
        "axes.labelcolor": COLORS["TEXT"],
        "axes.edgecolor": "#9A9A9A",
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.axisbelow": True,
        "xtick.color": COLORS["TEXT"],
        "ytick.color": COLORS["TEXT"],
        "xtick.major.size": 0,
        "ytick.major.size": 3,
        "ytick.major.width": 0.6,
        "legend.frameon": False,
        "legend.fontsize": 10,
        "svg.fonttype": "none",   # editable text in SVG
        "savefig.facecolor": "white",
    })


def pct(x: float) -> float:
    return 100.0 * float(x)


def save_figure(fig, out_base: Path) -> None:
    """Save presentation-ready PNG only."""
    fig.savefig(out_base.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def style_axis(ax, grid_axis: str = "y") -> None:
    ax.grid(axis=grid_axis, color=COLORS["GRID"], linewidth=0.8)
    if grid_axis == "x":
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
    else:
        ax.spines["bottom"].set_color("#9A9A9A")


def percent_axis(ax, top: float = 100.0, headroom: float = 14.0) -> None:
    """0-100 % ticks, with extra room above for value labels."""
    ax.set_ylim(0, top + headroom)
    ax.set_yticks(np.arange(0, top + 1, 20))
    ax.set_yticklabels([f"{int(t)}" for t in np.arange(0, top + 1, 20)])


def bar_kwargs(color: str) -> dict:
    return dict(color=color, edgecolor="white", linewidth=1.2, zorder=3)


def annotate_vertical(ax, bars, suffix="", decimals=1, color=None) -> None:
    for bar in bars:
        value = float(bar.get_height())
        label = f"{value:.{decimals}f}{suffix}"
        ax.annotate(
            label,
            (bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
            color=color or COLORS["TEXT"],
        )


def top_legend(ax, ncol: int = 2) -> None:
    ax.legend(
        loc="lower right",
        bbox_to_anchor=(1.0, 1.0),
        ncol=ncol,
        handlelength=1.1,
        handleheight=1.1,
        columnspacing=1.4,
        borderaxespad=0.3,
    )


def load_inputs(root: Path):
    inter = root / "intermediate"
    review_dir = root / "review"

    paths = {
        "metrics": inter / "retrieval_metrics.json",
        "summary": inter / "retrieval_metrics_summary.csv",
        "bycat": inter / "retrieval_metrics_by_gold_category.csv",
        "scored": inter / "retrieval_predictions_scored.csv",
        "llm_calls": inter / "llm_only_calls.csv",
        "hy_calls": inter / "hybrid_review_calls.csv",
        "review": review_dir / "retrieval_gold_manual_review.csv",
        # Needed only for presentation-style performance by the three original
        # benchmark source categories (PARENT_SALT / CHEMICAL_GROUP / MIXTURE).
        "gold": root / "data" / "retrieval_GOLD.csv",
    }

    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Required Study 2 result files are missing:\n  "
            + "\n  ".join(missing)
        )

    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8-sig"))
    summary = pd.read_csv(paths["summary"])
    bycat = pd.read_csv(paths["bycat"])
    scored = pd.read_csv(paths["scored"])
    llm_calls = pd.read_csv(paths["llm_calls"])
    hy_calls = pd.read_csv(paths["hy_calls"])
    review = pd.read_csv(paths["review"])
    gold = pd.read_csv(paths["gold"])

    return metrics, summary, bycat, scored, llm_calls, hy_calls, review, gold


def truthy_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def build_paired_tables(
    scored: pd.DataFrame,
    llm_calls: pd.DataFrame,
    hy_calls: pd.DataFrame,
    review: pd.DataFrame,
):
    scored = scored.copy()
    scored["correct"] = truthy_series(scored["correct"])

    hy = scored[scored["system"].eq("HYBRID")].copy()
    lo = scored[scored["system"].eq("LLM_ONLY")].copy()

    if len(hy) != 112 or len(lo) != 112:
        raise RuntimeError(
            f"Expected 112 rows per system; got HYBRID={len(hy)}, "
            f"LLM_ONLY={len(lo)}"
        )

    det_ids = set(
        hy.loc[
            hy["decision_source"].eq("DETERMINISTIC_GATE"), "query_id"
        ]
    )
    review_ids = set(
        hy.loc[
            hy["decision_source"].eq("LLM_AFTER_GATE_REVIEW"), "query_id"
        ]
    )

    if len(det_ids) != 49 or len(review_ids) != 63:
        raise RuntimeError(
            "Frozen routing counts changed. "
            f"Expected deterministic=49 and LLM-review=63; "
            f"got {len(det_ids)} and {len(review_ids)}."
        )

    if det_ids & review_ids or len(det_ids | review_ids) != 112:
        raise RuntimeError("Hybrid routing subsets are not a clean partition.")

    # Human-only names/CAS are used only after scoring, for error analysis tables.
    review_meta = review[
        ["query_id", "cas_inputs", "source_candidate_names_human_only"]
    ].drop_duplicates("query_id")

    # -----------------------------------------------------------------
    # 49 deterministic-routing queries: compare Hybrid vs LLM-only
    # -----------------------------------------------------------------
    det_h = hy[hy["query_id"].isin(det_ids)][
        [
            "query_id",
            "gold_target_id",
            "gold_category",
            "predicted_outcome",
            "correct",
            "gate_reason",
        ]
    ].rename(
        columns={
            "predicted_outcome": "hybrid_prediction",
            "correct": "hybrid_correct",
        }
    )

    det_l = lo[lo["query_id"].isin(det_ids)][
        ["query_id", "predicted_outcome", "correct"]
    ].rename(
        columns={
            "predicted_outcome": "llm_only_prediction",
            "correct": "llm_only_correct",
        }
    )

    deterministic = (
        det_h.merge(det_l, on="query_id", validate="one_to_one")
        .merge(review_meta, on="query_id", how="left", validate="one_to_one")
        .sort_values("query_id")
        .reset_index(drop=True)
    )
    deterministic["llm_error_prevented_by_hybrid"] = (
        deterministic["hybrid_correct"]
        & ~deterministic["llm_only_correct"]
    )

    # -----------------------------------------------------------------
    # 63 ambiguous queries: both systems use the same frozen LLM setup
    # but through independent calls.
    # -----------------------------------------------------------------
    rev_h = hy[hy["query_id"].isin(review_ids)][
        [
            "query_id",
            "gold_target_id",
            "gold_category",
            "predicted_outcome",
            "correct",
            "gate_reason",
        ]
    ].rename(
        columns={
            "predicted_outcome": "hybrid_llm_prediction",
            "correct": "hybrid_llm_correct",
        }
    )

    rev_l = lo[lo["query_id"].isin(review_ids)][
        ["query_id", "predicted_outcome", "correct"]
    ].rename(
        columns={
            "predicted_outcome": "llm_only_prediction",
            "correct": "llm_only_correct",
        }
    )

    llm_meta = llm_calls[
        ["query_id", "confidence", "reason"]
    ].rename(
        columns={
            "confidence": "llm_only_confidence",
            "reason": "llm_only_reason",
        }
    )

    hy_meta = hy_calls[
        ["query_id", "confidence", "reason"]
    ].rename(
        columns={
            "confidence": "hybrid_llm_confidence",
            "reason": "hybrid_llm_reason",
        }
    )

    paired = (
        rev_h.merge(rev_l, on="query_id", validate="one_to_one")
        .merge(llm_meta, on="query_id", how="left", validate="one_to_one")
        .merge(hy_meta, on="query_id", how="left", validate="one_to_one")
        .merge(review_meta, on="query_id", how="left", validate="one_to_one")
        .sort_values("query_id")
        .reset_index(drop=True)
    )

    def paired_class(r):
        l = bool(r["llm_only_correct"])
        h = bool(r["hybrid_llm_correct"])
        if l and h:
            return "Both correct"
        if (not l) and (not h):
            return "Both wrong"
        if l and (not h):
            return "LLM-only only correct"
        return "Hybrid-LLM only correct"

    paired["paired_correctness"] = paired.apply(paired_class, axis=1)
    paired["same_prediction"] = (
        paired["llm_only_prediction"].astype(str)
        == paired["hybrid_llm_prediction"].astype(str)
    )

    shared_failures = paired[
        paired["paired_correctness"].eq("Both wrong")
    ].copy()

    # Manual error coding is based on the frozen LLM-only error review.
    missing_manual = sorted(
        set(shared_failures["query_id"]) - set(PRIMARY_ERROR_TYPE)
    )
    if missing_manual:
        raise RuntimeError(
            "Shared LLM failures lack manual error coding: "
            + ", ".join(missing_manual)
        )
    shared_failures["primary_error_type"] = (
        shared_failures["query_id"].map(PRIMARY_ERROR_TYPE)
    )

    prevented = deterministic[
        deterministic["llm_error_prevented_by_hybrid"]
    ].copy()

    return deterministic, paired, shared_failures, prevented


# ---------------------------------------------------------------------
# Figure 1: overall benchmark accuracy
# ---------------------------------------------------------------------
def figure_overall_accuracy(summary: pd.DataFrame, outdir: Path) -> None:
    systems = ["LLM_ONLY", "HYBRID"]
    values = []
    for system in systems:
        row = summary.loc[summary["system"].eq(system)]
        values.append(pct(row["exact_accuracy"].iloc[0]))

    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    x = np.arange(len(systems))
    for xi, system, v in zip(x, systems, values):
        bars = ax.bar(xi, v, 0.58, **bar_kwargs(COLORS[system]))
        annotate_vertical(ax, bars, "%", 1, color=COLORS[system])
    ax.set_xticks(x, [SYSTEM_LABEL[s] for s in systems])
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel("Exact retrieval accuracy (%)")
    percent_axis(ax)
    ax.set_title("Overall retrieval accuracy (n=112)")
    style_axis(ax)
    fig.tight_layout()
    save_figure(fig, outdir / "fig1_overall_accuracy")


# ---------------------------------------------------------------------
# Figure 2: core architecture figure
# Compare accuracy within the two routing subsets.
# ---------------------------------------------------------------------
def figure_routing_subset_accuracy(
    deterministic: pd.DataFrame,
    paired: pd.DataFrame,
    outdir: Path,
) -> None:
    subset_labels = [
        f"Deterministic-eligible\n(n={len(deterministic)})",
        f"LLM-escalated\n(n={len(paired)})",
    ]

    llm_values = [
        pct(deterministic["llm_only_correct"].mean()),
        pct(paired["llm_only_correct"].mean()),
    ]
    hybrid_values = [
        pct(deterministic["hybrid_correct"].mean()),
        pct(paired["hybrid_llm_correct"].mean()),
    ]

    x = np.arange(2)
    width = 0.36

    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    b1 = ax.bar(x - width/2, llm_values, width, label="LLM-only",
                **bar_kwargs(COLORS["LLM_ONLY"]))
    b2 = ax.bar(x + width/2, hybrid_values, width, label="Hybrid",
                **bar_kwargs(COLORS["HYBRID"]))
    ax.set_ylabel("Exact retrieval accuracy (%)")
    percent_axis(ax)
    ax.set_xticks(x, subset_labels)
    ax.set_title("Accuracy by Hybrid routing subset")
    top_legend(ax)
    annotate_vertical(ax, b1, "%", 1, color=COLORS["LLM_ONLY"])
    annotate_vertical(ax, b2, "%", 1, color=COLORS["HYBRID"])

    # In-bar note: Hybrid answers this subset without any LLM call.
    hb = b2[0]
    ax.text(
        hb.get_x() + hb.get_width() / 2,
        hb.get_height() / 2,
        "No LLM\ncall",
        ha="center",
        va="center",
        fontsize=9,
        fontweight="bold",
        color="white",
        zorder=4,
    )
    style_axis(ax)
    fig.tight_layout()
    save_figure(fig, outdir / "fig2_routing_subset_accuracy")


# ---------------------------------------------------------------------
# Figure 3: paired outcome of independent LLM calls on the SAME 63 cases
# ---------------------------------------------------------------------
def figure_llm_escalation_paired_outcomes(
    paired: pd.DataFrame,
    outdir: Path,
) -> None:
    order = [
        "Both correct",
        "Both wrong",
        "LLM-only only correct",
        "Hybrid-LLM only correct",
    ]
    labels = [
        "Both\ncorrect",
        "Both\nwrong",
        "LLM-only\nonly correct",
        "Hybrid-LLM\nonly correct",
    ]
    # Agreement = neutral greys; disagreement = the system's own colour.
    colors = [
        COLORS["NEUTRAL_LIGHT"],
        COLORS["NEUTRAL_DARK"],
        COLORS["LLM_ONLY"],
        COLORS["HYBRID"],
    ]
    counts = (
        paired["paired_correctness"]
        .value_counts()
        .reindex(order)
        .fillna(0)
        .astype(int)
    )

    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    bars = ax.bar(labels, counts.values, 0.62, color=colors,
                  edgecolor="white", linewidth=1.2, zorder=3)
    for bar, c in zip(bars, colors):
        label_color = COLORS["NEUTRAL_DARK"] if c == COLORS["NEUTRAL_LIGHT"] else c
        annotate_vertical(ax, [bar], "", 0, color=label_color)
    ax.set_ylabel("Number of queries")
    ax.set_ylim(0, max(counts.values) * 1.15 + 1)
    ax.set_title(f"Paired outcomes on the {len(paired)} LLM-escalated queries")
    style_axis(ax)
    fig.tight_layout()
    save_figure(fig, outdir / "fig3_llm_escalation_paired_outcomes")


# ---------------------------------------------------------------------
# Figure 4: errors within the 49 cases that Hybrid can resolve
# deterministically. This directly visualizes avoidable LLM exposure.
# ---------------------------------------------------------------------
def figure_deterministic_subset_errors(
    deterministic: pd.DataFrame,
    outdir: Path,
) -> None:
    systems = ["LLM_ONLY", "HYBRID"]
    error_counts = [
        int((~deterministic["llm_only_correct"]).sum()),
        int((~deterministic["hybrid_correct"]).sum()),
    ]

    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    x = np.arange(len(systems))
    ymax = max(3, max(error_counts) + 1)
    for xi, system, v in zip(x, systems, error_counts):
        bars = ax.bar(xi, v, 0.58, **bar_kwargs(COLORS[system]))
        annotate_vertical(ax, bars, "", 0, color=COLORS[system])
        if v == 0:
            # Show a thin baseline so a zero bar is still visibly "there".
            ax.plot([xi - 0.29, xi + 0.29], [0, 0], color=COLORS[system],
                    linewidth=3, solid_capstyle="butt", zorder=4)
    ax.set_xticks(x, [SYSTEM_LABEL[s] for s in systems])
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel("Number of errors")
    ax.set_ylim(0, ymax * 1.15)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.set_title(f"Errors in the {len(deterministic)} deterministic-eligible queries")
    style_axis(ax)
    fig.tight_layout()
    save_figure(fig, outdir / "fig4_deterministic_subset_errors")


# ---------------------------------------------------------------------
# Figure 5: efficiency remains relevant even if future LLM accuracy rises
# ---------------------------------------------------------------------
def figure_efficiency(metrics: dict, outdir: Path) -> None:
    """Presentation figure using actual logged LLM usage, time, and API cost.

    IMPORTANT:
    - "LLM processing time" is the SUM of elapsed_sec recorded for successful
      LLM API calls.
    - It is NOT the complete end-to-end runtime of the Hybrid pipeline,
      because deterministic/RDKit processing time is not included in the
      frozen call logs.
    - API cost uses Claude Sonnet 5 standard prices:
        input  = $2 per 1M tokens
        output = $10 per 1M tokens
    """
    eff = metrics["efficiency"]

    llm_stats = eff["LLM_ONLY"]
    hy_stats = eff["HYBRID_LLM_ESCALATIONS"]

    # ---------------------------------------------------------------
    # Actual values recorded in the frozen LLM call logs
    # ---------------------------------------------------------------
    llm_calls = int(llm_stats["ok_calls"])
    hy_calls = int(hy_stats["ok_calls"])

    llm_input = int(llm_stats["input_tokens"])
    hy_input = int(hy_stats["input_tokens"])

    llm_output = int(llm_stats["output_tokens"])
    hy_output = int(hy_stats["output_tokens"])

    llm_time_sec = float(llm_stats.get("elapsed_sec", 0.0))
    hy_time_sec = float(hy_stats.get("elapsed_sec", 0.0))

    # Claude Sonnet 5 standard API price (USD per 1M tokens)
    INPUT_PRICE_PER_M = 2.0
    OUTPUT_PRICE_PER_M = 10.0

    llm_cost = (
        llm_input / 1_000_000 * INPUT_PRICE_PER_M
        + llm_output / 1_000_000 * OUTPUT_PRICE_PER_M
    )
    hy_cost = (
        hy_input / 1_000_000 * INPUT_PRICE_PER_M
        + hy_output / 1_000_000 * OUTPUT_PRICE_PER_M
    )

    def reduction(old, new):
        return 100.0 * (1.0 - new / old) if old else float("nan")

    call_reduction = reduction(llm_calls, hy_calls)
    input_reduction = reduction(llm_input, hy_input)
    time_reduction = reduction(llm_time_sec, hy_time_sec)
    cost_reduction = reduction(llm_cost, hy_cost)

    # ---------------------------------------------------------------
    # Four-panel presentation figure
    # ---------------------------------------------------------------
    fig, axes = plt.subplots(1, 4, figsize=(14.8, 4.8))

    system_colors = [COLORS["LLM_ONLY"], COLORS["HYBRID"]]
    system_labels = ["LLM-only", "Hybrid"]

    # ---------------------------------------------------------------
    # Panel 1: LLM calls
    # ---------------------------------------------------------------
    ax = axes[0]
    vals = [llm_calls, hy_calls]
    bars = ax.bar(
        system_labels, vals, 0.58,
        color=system_colors,
        edgecolor="white", linewidth=1.2, zorder=3
    )
    for bar, v, c in zip(bars, vals, system_colors):
        ax.annotate(
            f"{v:,}",
            (bar.get_x() + bar.get_width()/2, v),
            xytext=(0, 4), textcoords="offset points",
            ha="center", va="bottom", fontsize=10.5,
            fontweight="bold", color=c
        )
    ax.set_title("AI calls")
    ax.set_ylabel("Number of calls")
    ax.set_ylim(0, max(vals) * 1.22)
    ax.text(
        0.5, 0.93, f"-{call_reduction:.1f}%",
        transform=ax.transAxes, ha="center", va="top",
        fontsize=12, fontweight="bold", color=COLORS["HYBRID"]
    )
    style_axis(ax)

    # ---------------------------------------------------------------
    # Panel 2: input tokens
    # ---------------------------------------------------------------
    ax = axes[1]
    vals = [llm_input / 1_000_000, hy_input / 1_000_000]
    raw_vals = [llm_input, hy_input]
    bars = ax.bar(
        system_labels, vals, 0.58,
        color=system_colors,
        edgecolor="white", linewidth=1.2, zorder=3
    )
    for bar, v, raw, c in zip(bars, vals, raw_vals, system_colors):
        ax.annotate(
            f"{raw/1_000_000:.3f}M",
            (bar.get_x() + bar.get_width()/2, v),
            xytext=(0, 4), textcoords="offset points",
            ha="center", va="bottom", fontsize=10.5,
            fontweight="bold", color=c
        )
    ax.set_title("Input tokens")
    ax.set_ylabel("Million tokens")
    ax.set_ylim(0, max(vals) * 1.22)
    ax.text(
        0.5, 0.93, f"-{input_reduction:.1f}%",
        transform=ax.transAxes, ha="center", va="top",
        fontsize=12, fontweight="bold", color=COLORS["HYBRID"]
    )
    style_axis(ax)

    # ---------------------------------------------------------------
    # Panel 3: summed LLM processing time
    # ---------------------------------------------------------------
    ax = axes[2]
    vals = [llm_time_sec / 60.0, hy_time_sec / 60.0]
    bars = ax.bar(
        system_labels, vals, 0.58,
        color=system_colors,
        edgecolor="white", linewidth=1.2, zorder=3
    )
    for bar, v, c in zip(bars, vals, system_colors):
        ax.annotate(
            f"{v:.2f} min",
            (bar.get_x() + bar.get_width()/2, v),
            xytext=(0, 4), textcoords="offset points",
            ha="center", va="bottom", fontsize=10.5,
            fontweight="bold", color=c
        )
    ax.set_title("LLM processing time")
    ax.set_ylabel("Summed elapsed time (min)")
    ax.set_ylim(0, max(vals) * 1.22)
    ax.text(
        0.5, 0.93, f"-{time_reduction:.1f}%",
        transform=ax.transAxes, ha="center", va="top",
        fontsize=12, fontweight="bold", color=COLORS["HYBRID"]
    )
    style_axis(ax)

    # ---------------------------------------------------------------
    # Panel 4: API cost
    # ---------------------------------------------------------------
    ax = axes[3]
    vals = [llm_cost, hy_cost]
    bars = ax.bar(
        system_labels, vals, 0.58,
        color=system_colors,
        edgecolor="white", linewidth=1.2, zorder=3
    )
    for bar, v, c in zip(bars, vals, system_colors):
        ax.annotate(
            f"${v:.2f}",
            (bar.get_x() + bar.get_width()/2, v),
            xytext=(0, 4), textcoords="offset points",
            ha="center", va="bottom", fontsize=10.5,
            fontweight="bold", color=c
        )
    ax.set_title("API cost")
    ax.set_ylabel("USD")
    ax.set_ylim(0, max(vals) * 1.22)
    ax.text(
        0.5, 0.93, f"-{cost_reduction:.1f}%",
        transform=ax.transAxes, ha="center", va="top",
        fontsize=12, fontweight="bold", color=COLORS["HYBRID"]
    )
    style_axis(ax)

    fig.suptitle(
        "Efficiency of selective LLM use",
        x=0.02, ha="left", fontsize=14, fontweight="bold"
    )
    fig.text(
        0.5, 0.012,
        "LLM time is the sum of recorded API-call elapsed time; "
        "it does not include deterministic/RDKit processing time. "
        "API cost = input × $2/M + output × $10/M.",
        ha="center", va="bottom", fontsize=8.8, color=COLORS["NEUTRAL_DARK"]
    )
    fig.tight_layout(rect=[0, 0.065, 1, 0.92])
    save_figure(fig, outdir / "fig5_efficiency_cost_time")


# ---------------------------------------------------------------------
# Figure 6: category accuracy
# ---------------------------------------------------------------------
def build_source_category_performance(
    scored: pd.DataFrame,
    gold: pd.DataFrame,
    root: Path,
) -> pd.DataFrame:
    """Summarize accuracy over the three ORIGINAL benchmark categories.

    Preferred source: ``retrieval_GOLD.csv`` column ``source_categories``.
    Compatibility fallback: older frozen retrieval_GOLD files may not contain
    that column.  In that case reconstruct the category from ``source_case_ids``
    and the frozen Validation V2 ``validation_master_INPUT.csv``.
    """
    if "query_id" not in gold.columns:
        raise RuntimeError(
            "retrieval_GOLD.csv lacks query_id; cannot build category performance."
        )

    # ---------------------------------------------------------------
    # Preferred path: source_categories was saved directly in GOLD.
    # ---------------------------------------------------------------
    if "source_categories" in gold.columns:
        src = gold[["query_id", "source_categories"]].drop_duplicates("query_id").copy()
        src["source_categories"] = src["source_categories"].astype(str).str.strip()

    # ---------------------------------------------------------------
    # Backward-compatible path for older retrieval_GOLD.csv versions.
    # Reconstruct source category from source_case_ids + Validation V2.
    # ---------------------------------------------------------------
    else:
        if "source_case_ids" not in gold.columns:
            raise RuntimeError(
                "retrieval_GOLD.csv has neither source_categories nor source_case_ids. "
                f"Available columns: {list(gold.columns)}"
            )

        master_path = root.parent / "validation_v2" / "data" / "validation_master_INPUT.csv"
        if not master_path.exists():
            raise FileNotFoundError(
                "source_categories is absent from retrieval_GOLD.csv, and the fallback "
                "Validation V2 master file was not found:\n  " + str(master_path)
            )

        master = pd.read_csv(master_path, dtype=str).fillna("")
        needed = {"case_id", "category"}
        missing = needed - set(master.columns)
        if missing:
            raise RuntimeError(
                "validation_master_INPUT.csv lacks required columns: "
                + ", ".join(sorted(missing))
            )

        case_to_cat = (
            master[["case_id", "category"]]
            .drop_duplicates("case_id")
            .set_index("case_id")["category"]
            .to_dict()
        )

        rebuilt = []
        for _, r in gold[["query_id", "source_case_ids"]].drop_duplicates("query_id").iterrows():
            case_ids = [x.strip() for x in str(r["source_case_ids"]).split("|") if x.strip()]
            cats = sorted({case_to_cat.get(cid, "") for cid in case_ids if case_to_cat.get(cid, "")})
            if len(cats) != 1:
                raise RuntimeError(
                    f"Could not uniquely reconstruct category for {r['query_id']}: "
                    f"source_case_ids={case_ids}, categories={cats}"
                )
            rebuilt.append({
                "query_id": r["query_id"],
                "source_categories": cats[0],
            })
        src = pd.DataFrame(rebuilt)
        print(
            "[INFO] source_categories was not present in retrieval_GOLD.csv; "
            "reconstructed it from source_case_ids and validation_master_INPUT.csv."
        )

    allowed = {"PARENT_SALT", "CHEMICAL_GROUP", "MIXTURE"}
    multi = src["source_categories"].str.contains(r"\|", regex=True, na=False)
    if multi.any():
        bad = src.loc[multi, ["query_id", "source_categories"]]
        raise RuntimeError(
            "Some retrieval queries originate from more than one benchmark "
            "category, so a mutually exclusive 3-category plot would be ambiguous:\n"
            + bad.to_string(index=False)
        )

    unexpected = sorted(set(src["source_categories"]) - allowed)
    if unexpected:
        raise RuntimeError(
            "Unexpected source categories: " + ", ".join(unexpected)
        )

    s = scored.copy()
    s["correct"] = truthy_series(s["correct"])

    # If scored already happens to contain a stale/partial source_categories column,
    # remove it so the authoritative metadata joined below is used consistently.
    if "source_categories" in s.columns:
        s = s.drop(columns=["source_categories"])

    s = s.merge(src, on="query_id", how="left", validate="many_to_one")
    if s["source_categories"].isna().any():
        missing_ids = sorted(s.loc[s["source_categories"].isna(), "query_id"].unique())
        raise RuntimeError(
            "Some scored queries lack source category metadata: "
            + ", ".join(missing_ids)
        )

    perf = (
        s.groupby(["system", "source_categories"], as_index=False)
        .agg(
            n_queries=("query_id", "nunique"),
            n_correct=("correct", "sum"),
            exact_accuracy=("correct", "mean"),
        )
    )
    perf["n_errors"] = perf["n_queries"] - perf["n_correct"]
    perf["accuracy_percent"] = 100.0 * perf["exact_accuracy"]

    order_map = {"PARENT_SALT": 0, "CHEMICAL_GROUP": 1, "MIXTURE": 2}
    sys_map = {"LLM_ONLY": 0, "HYBRID": 1}
    perf["_cat_order"] = perf["source_categories"].map(order_map)
    perf["_sys_order"] = perf["system"].map(sys_map)
    perf = (
        perf.sort_values(["_cat_order", "_sys_order"])
        .drop(columns=["_cat_order", "_sys_order"])
        .reset_index(drop=True)
    )
    return perf


def annotate_accuracy_with_counts(ax, bars, accuracies, corrects, totals,
                                  color=None) -> None:
    for bar, acc, cor, total in zip(bars, accuracies, corrects, totals):
        x = bar.get_x() + bar.get_width() / 2
        ax.annotate(
            f"{float(acc):.1f}%",
            (x, float(acc)),
            xytext=(0, 15),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
            color=color or COLORS["TEXT"],
        )
        ax.annotate(
            f"({int(cor)}/{int(total)})",
            (x, float(acc)),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8.5,
            color=COLORS["NEUTRAL_DARK"],
        )


def figure_category_accuracy(
    scored: pd.DataFrame,
    gold: pd.DataFrame,
    root: Path,
    outdir: Path,
) -> pd.DataFrame:
    """PPT-friendly accuracy comparison for the three benchmark categories."""
    perf = build_source_category_performance(scored, gold, root)

    cats = ["PARENT_SALT", "CHEMICAL_GROUP", "MIXTURE"]
    labels = ["Parent / salt", "Chemical group", "Mixture"]

    def rows_for(system: str) -> pd.DataFrame:
        d = perf[perf["system"].eq(system)].set_index("source_categories")
        missing = [c for c in cats if c not in d.index]
        if missing:
            raise RuntimeError(
                f"Missing {system} category results: {', '.join(missing)}"
            )
        return d.reindex(cats)

    lo = rows_for("LLM_ONLY")
    hy = rows_for("HYBRID")

    tick_labels = [
        f"{lab}\n(n={int(n)})" for lab, n in zip(labels, hy["n_queries"].values)
    ]

    x = np.arange(len(cats))
    width = 0.36

    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    b1 = ax.bar(x - width/2, lo["accuracy_percent"].values, width,
                label="LLM-only", **bar_kwargs(COLORS["LLM_ONLY"]))
    b2 = ax.bar(x + width/2, hy["accuracy_percent"].values, width,
                label="Hybrid", **bar_kwargs(COLORS["HYBRID"]))
    ax.set_ylabel("Exact retrieval accuracy (%)")
    percent_axis(ax, headroom=18)
    ax.set_xticks(x, tick_labels)
    ax.set_title("Accuracy by benchmark category")
    top_legend(ax)

    annotate_accuracy_with_counts(
        ax, b1,
        lo["accuracy_percent"].values,
        lo["n_correct"].values,
        lo["n_queries"].values,
        color=COLORS["LLM_ONLY"],
    )
    annotate_accuracy_with_counts(
        ax, b2,
        hy["accuracy_percent"].values,
        hy["n_correct"].values,
        hy["n_queries"].values,
        color=COLORS["HYBRID"],
    )

    style_axis(ax)
    fig.tight_layout()
    save_figure(fig, outdir / "fig6_accuracy_by_source_category")
    return perf


# ---------------------------------------------------------------------
# Figure 7: the 14 cases independently missed by BOTH LLM calls
# This is more informative than plotting LLM-only errors alone.
# ---------------------------------------------------------------------
def figure_shared_llm_failure_types(
    shared_failures: pd.DataFrame,
    outdir: Path,
) -> None:
    order = [
        "Chemical identity/speciation misinterpretation",
        "Regulatory scope over-extension",
        "Reason-decision inconsistency",
    ]
    labels = [
        "Chemical identity /\nspeciation misinterpretation",
        "Regulatory scope\nover-extension",
        "Reason–decision\ninconsistency",
    ]
    counts = (
        shared_failures["primary_error_type"]
        .value_counts()
        .reindex(order)
        .fillna(0)
        .astype(int)
    )
    total = int(counts.sum())

    # Shared by both systems' LLM calls -> neutral colour, not a system colour.
    fig, ax = plt.subplots(figsize=(8.0, 3.9))
    bars = ax.barh(labels, counts.values, 0.58,
                   **bar_kwargs(COLORS["NEUTRAL_DARK"]))
    ax.set_xlabel("Number of shared LLM failures")
    ax.set_title(
        f"Error mechanisms among cases missed by both LLM calls (n={total})"
    )
    ax.invert_yaxis()
    ax.set_xlim(0, max(counts.values) * 1.25 + 0.5)
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))

    for bar in bars:
        v = int(bar.get_width())
        share = f" ({100*v/total:.0f}%)" if total else ""
        ax.annotate(
            f"{v}{share}",
            (v, bar.get_y() + bar.get_height()/2),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            ha="left",
            fontsize=10,
            fontweight="bold",
            color=COLORS["NEUTRAL_DARK"],
        )

    style_axis(ax, grid_axis="x")
    fig.tight_layout()
    save_figure(fig, outdir / "fig7_shared_llm_failure_types")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Path to study2_eval_v2 (default: script directory)",
    )
    args = parser.parse_args()

    apply_style()
    root = args.root.resolve()
    outdir = root / "figures"
    outdir.mkdir(parents=True, exist_ok=True)

    (
        metrics,
        summary,
        bycat,
        scored,
        llm_calls,
        hy_calls,
        review,
        gold,
    ) = load_inputs(root)

    (
        deterministic,
        paired,
        shared_failures,
        prevented,
    ) = build_paired_tables(scored, llm_calls, hy_calls, review)

    # Presentation version: no CSV/Excel outputs; figures only.

    # Figures
    figure_overall_accuracy(summary, outdir)
    figure_routing_subset_accuracy(deterministic, paired, outdir)
    figure_llm_escalation_paired_outcomes(paired, outdir)
    figure_deterministic_subset_errors(deterministic, outdir)
    figure_efficiency(metrics, outdir)
    category_perf = figure_category_accuracy(scored, gold, root, outdir)
    figure_shared_llm_failure_types(shared_failures, outdir)

    # Console QC / manuscript-ready numbers
    det_llm_acc = deterministic["llm_only_correct"].mean()
    det_hyb_acc = deterministic["hybrid_correct"].mean()
    rev_llm_acc = paired["llm_only_correct"].mean()
    rev_hyb_acc = paired["hybrid_llm_correct"].mean()

    pair_counts = paired["paired_correctness"].value_counts()

    print("=" * 76)
    print("Study 2 Hybrid architecture visualization complete")
    print("=" * 76)

    print("\n[Routing subset performance]")
    print(
        f"Deterministic-eligible n={len(deterministic)}: "
        f"LLM-only={deterministic['llm_only_correct'].sum()}/{len(deterministic)} "
        f"({100*det_llm_acc:.1f}%), "
        f"Hybrid={deterministic['hybrid_correct'].sum()}/{len(deterministic)} "
        f"({100*det_hyb_acc:.1f}%)"
    )
    print(
        f"LLM-escalated n={len(paired)}: "
        f"LLM-only={paired['llm_only_correct'].sum()}/{len(paired)} "
        f"({100*rev_llm_acc:.1f}%), "
        f"Hybrid-LLM={paired['hybrid_llm_correct'].sum()}/{len(paired)} "
        f"({100*rev_hyb_acc:.1f}%)"
    )

    print("\n[Paired outcomes on same 63 LLM-escalated queries]")
    for key in [
        "Both correct",
        "Both wrong",
        "LLM-only only correct",
        "Hybrid-LLM only correct",
    ]:
        print(f"{key}: {int(pair_counts.get(key, 0))}")

    print("\n[Deterministic gate]")
    print(
        f"LLM-only errors in deterministic-eligible subset: "
        f"{int((~deterministic['llm_only_correct']).sum())}"
    )
    print(
        f"Hybrid errors in deterministic-eligible subset: "
        f"{int((~deterministic['hybrid_correct']).sum())}"
    )
    print(
        f"Observed LLM errors prevented by deterministic routing: "
        f"{len(prevented)}"
    )

    if len(prevented):
        cols = [
            "query_id",
            "cas_inputs",
            "source_candidate_names_human_only",
            "gold_target_id",
            "llm_only_prediction",
            "hybrid_prediction",
            "gate_reason",
        ]
        print("\n[Cases where deterministic routing avoided an observed LLM-only error]")
        print(prevented[cols].to_string(index=False))

    print("\n[Shared hard cases]")
    print(
        f"Both independent LLM calls wrong: "
        f"{len(shared_failures)}/{len(paired)}"
    )
    print(
        shared_failures["primary_error_type"]
        .value_counts()
        .to_string()
    )

    print("\n[Performance by the three original benchmark categories]")
    pretty = category_perf.copy()
    pretty["correct/total"] = (
        pretty["n_correct"].astype(int).astype(str)
        + "/"
        + pretty["n_queries"].astype(int).astype(str)
    )
    pretty["accuracy"] = pretty["accuracy_percent"].map(lambda x: f"{x:.1f}%")
    print(
        pretty[["source_categories", "system", "correct/total", "accuracy"]]
        .to_string(index=False)
    )

    print(f"\n[OUT] PNG figures only -> {outdir}")


if __name__ == "__main__":
    main()
