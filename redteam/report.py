"""Write the JSON and HTML security reports.

Model replies can contain live HTML/JS (that is literally what we test for),
so EVERYTHING that comes from the target is html-escaped before it goes into
the HTML report.
"""
import json
from html import escape
from pathlib import Path

CSS = """
body{font-family:system-ui,sans-serif;margin:2rem;color:#111;background:#fafafa}
h1{margin-bottom:.2rem} .meta{color:#555;margin-bottom:1.5rem}
.badge{display:inline-block;padding:.3rem .8rem;border-radius:6px;color:#fff;font-weight:700}
.PASS{background:#16a34a}.FAIL{background:#dc2626}.ERROR{background:#d97706}
table{border-collapse:collapse;width:100%;margin:1rem 0;background:#fff}
th,td{border:1px solid #ddd;padding:.5rem .6rem;text-align:left;vertical-align:top;font-size:.9rem}
th{background:#f0f0f0} td.breach{background:#fee2e2;font-weight:700}
pre{white-space:pre-wrap;margin:0;font-size:.8rem;max-width:42rem}
"""


def write_reports(report_dir, meta, summary, results):
    out = Path(report_dir)
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / "report.json"
    json_path.write_text(
        json.dumps({"meta": meta, "summary": summary, "results": results}, indent=2),
        encoding="utf-8",
    )

    html_path = out / "report.html"
    html_path.write_text(render_html(meta, summary, results), encoding="utf-8")
    return json_path, html_path


def render_html(meta, summary, results) -> str:
    cat_rows = "".join(
        f"<tr><td>{escape(cat)}</td><td>{c['attempts']}</td><td>{c['successful']}</td>"
        f"<td>{c['blocked']}</td><td>{c['asr']:.0%}</td></tr>"
        for cat, c in summary["by_category"].items()
    )
    detail_rows = "".join(
        "<tr>"
        f"<td>{escape(r['id'])}</td><td>{escape(r['category'])}</td>"
        f"<td class='{'breach' if r['success'] else ''}'>"
        f"{'ERROR' if r['error'] else ('BREACH' if r['success'] else 'ok')}</td>"
        f"<td><pre>{escape(r['prompt'])}</pre></td>"
        f"<td><pre>{escape(r['reply'] or r['error'] or '')}</pre></td>"
        f"<td>{escape(r['evidence'])}</td>"
        "</tr>"
        for r in results
    )
    reasons = "".join(f"<li>{escape(x)}</li>" for x in summary["reasons"])
    status = escape(summary["status"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>AI Red-Team Report</title><style>{CSS}</style></head><body>
<h1>AI Red-Team Report</h1>
<div class="meta">Target {escape(meta['target'])} &middot; {escape(meta['timestamp'])}
&middot; repeats {meta['repeats']}</div>
<p><span class="badge {status}">GATE: {status}</span>
&nbsp; Attack success rate <b>{summary['attack_success_rate']:.0%}</b>
({summary['successful_attacks']}/{summary['total_attempts']}),
limit {summary['max_asr']:.0%}</p>
<ul>{reasons}</ul>
<h2>By category</h2>
<table><tr><th>Category</th><th>Attempts</th><th>Successful</th><th>Blocked</th><th>ASR</th></tr>
{cat_rows}</table>
<h2>Details</h2>
<table><tr><th>ID</th><th>Category</th><th>Result</th><th>Prompt</th><th>Reply</th><th>Evidence</th></tr>
{detail_rows}</table>
</body></html>"""
