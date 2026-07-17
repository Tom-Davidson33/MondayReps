"""Render ReportContext -> HTML via Jinja2, then inline CSS for Outlook if premailer
is available (Outlook ignores much of a <style> block)."""
from __future__ import annotations
from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from contracts import ReportContext


def render(ctx: ReportContext) -> str:
    env = Environment(
        loader=FileSystemLoader(str(config.TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    # bar-width helpers used by the template
    env.globals["wind_pct"] = lambda mw: max(2, min(100, round(100 * mw / ctx.wind_bar_scale)))
    env.globals["curve_pct"] = lambda p: max(2, min(100, round(100 * p / ctx.gas_curve_scale)))
    html = env.get_template("report.html.j2").render(c=ctx)

    try:
        from premailer import transform  # optional; pip install premailer
        html = transform(html, keep_style_tags=True)
    except Exception:
        pass  # preview still works; production Outlook prefers the inlined version
    return html


def render_to_file(ctx: ReportContext) -> str:
    html = render(ctx)
    out = config.OUTPUT_DIR / "tom_monday_report.html"
    out.write_text(html, encoding="utf-8")
    return str(out)
