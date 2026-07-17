"""
Email-safe chart rendering (matplotlib -> PNG). Plotly needs JS and won't render in
email, so we pre-render PNGs and embed them. Two charts:
  1. curve_7d.png     — 7-day GSH implied gas forward curve ($/GJ)
  2. pelican_daily.png — Pelican daily gas usage (TJ bars, coloured by run reason)
                          with the implied SA1 price line on a second axis.
"""
from __future__ import annotations
import base64
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import config

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10,
    "axes.edgecolor": "#cfd6dd", "axes.linewidth": 0.8,
    "axes.grid": True, "grid.color": "#eef1f4", "grid.linewidth": 0.8,
    "figure.dpi": 130,
})


def _b64(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def curve_chart(curve) -> str:
    """curve: list[CurvePoint] (label, price, is_min, is_max) -> base64 PNG data URI."""
    out = config.SNAPSHOT_DIR / "curve_7d.png"
    labels = [c.label for c in curve]
    prices = [c.price for c in curve]
    fig, ax = plt.subplots(figsize=(6.6, 2.4))
    ax.plot(labels, prices, color="#0f6bb0", lw=2, marker="o", ms=5, zorder=3)
    for c in curve:
        if c.is_min:
            ax.annotate(f"${c.price:.2f}", (c.label, c.price), textcoords="offset points",
                        xytext=(0, -14), ha="center", color="#2e7d32", fontweight="bold", fontsize=9)
        if c.is_max:
            ax.annotate(f"${c.price:.2f}", (c.label, c.price), textcoords="offset points",
                        xytext=(0, 8), ha="center", color="#c62828", fontweight="bold", fontsize=9)
    ax.set_ylabel("$/GJ")
    ax.margins(x=0.04)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout(pad=0.4)
    fig.savefig(out, transparent=False, facecolor="white")
    plt.close(fig)
    return _b64(out)


def pelican_chart(days) -> str:
    """days: list[PelicanDay] (label, tj, reason, rrp_avg, rrp_max) -> base64 PNG data URI."""
    out = config.SNAPSHOT_DIR / "pelican_daily.png"
    labels = [d.label for d in days]
    tj = [d.tj for d in days]
    rrp = [d.rrp_max for d in days]
    cols = [config.RUN_REASON_COLOURS.get(str(d.reason).upper(), config.RUN_REASON_DEFAULT) for d in days]

    fig, ax = plt.subplots(figsize=(6.6, 2.7))
    ax.bar(labels, tj, color=cols, zorder=3, width=0.62)
    ax.set_ylabel("Gas usage (TJ/day)")
    ax.margins(x=0.04)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    ax2 = ax.twinx()
    ax2.plot(labels, rrp, color="#1a2129", lw=1.6, marker="D", ms=4, zorder=4)
    ax2.set_ylabel("Implied SA1 price ($/MWh)")
    ax2.grid(False)
    ax2.spines["top"].set_visible(False)

    # legend of run reasons actually present
    seen = {}
    for d in days:
        k = str(d.reason).upper()
        seen[k] = config.RUN_REASON_COLOURS.get(k, config.RUN_REASON_DEFAULT)
    handles = [Patch(facecolor=c, label=k.title()) for k, c in seen.items()]
    handles.append(plt.Line2D([0], [0], color="#1a2129", marker="D", ms=4, label="Implied price"))
    ax.legend(handles=handles, loc="upper left", fontsize=8, frameon=False, ncol=2)

    fig.tight_layout(pad=0.4)
    fig.savefig(out, transparent=False, facecolor="white")
    plt.close(fig)
    return _b64(out)
