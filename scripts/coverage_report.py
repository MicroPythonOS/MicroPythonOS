#!/usr/bin/env python3
"""Generate an HTML coverage report from a coverage JSON file.

Usage:
    python3 scripts/coverage_report.py cov.json
    python3 scripts/coverage_report.py cov.json -o coverage/index.html
"""
import argparse
import html
import json
import os
import sys


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
FS_ROOT = os.path.join(REPO_ROOT, "internal_filesystem")

CSS = """\
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #1a1a2e; color: #e0e0e0; margin: 0; padding: 0; }
.header { background: #16213e; padding: 40px 20px; text-align: center; }
.big-pct { font-size: 80px; font-weight: 700; line-height: 1; }
.subtitle { font-size: 16px; color: #999; margin-top: 8px; }
.pct-low { color: #f44336; }
.pct-mid { color: #ff9800; }
.pct-high { color: #4caf50; }
.container { max-width: 1100px; margin: 0 auto; padding: 20px; }
table { width: 100%; border-collapse: collapse; margin-top: 20px; }
th { background: #2a2a3e; padding: 10px 12px; text-align: left; font-size: 13px;
     text-transform: uppercase; letter-spacing: 0.5px; color: #999; position: sticky; top: 0; }
td { padding: 8px 12px; border-bottom: 1px solid #2a2a3e; font-size: 14px; }
tr:hover td { background: #1f1f33; }
.bar-outer { background: #333; border-radius: 3px; height: 14px; width: 120px; overflow: hidden; }
.bar-inner { height: 100%; border-radius: 3px; }
.pct-cell { min-width: 60px; }
details { margin: 0; }
details > summary { list-style: none; cursor: pointer; }
details > summary::-webkit-details-marker { display: none; }
details > summary::before { content: '+ '; color: #666; font-weight: bold; display: inline-block; width: 16px; }
details[open] > summary::before { content: '- '; }
.source-panel { background: #0d0d1a; border: 1px solid #2a2a3e; border-top: none; padding: 0; }
.source-panel pre { margin: 0; padding: 0; }
.source-table { margin: 0; }
.source-table td { padding: 2px 8px; border: none; font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
                    font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; }
.source-table tr:hover td { background: inherit; }
.ln { color: #555; text-align: right; padding-right: 10px; user-select: none; min-width: 40px; width: 40px; }
.ln .hc { font-size: 10px; color: #444; }
.uncovered { background: rgba(244, 67, 54, 0.18); }
.covered-1 { background: rgba(76, 175, 80, 0.12); }
.covered-2 { background: rgba(76, 175, 80, 0.24); }
.covered-3 { background: rgba(76, 175, 80, 0.40); }
.covered-4 { background: rgba(76, 175, 80, 0.60); }

"""  # noqa: E501


def _class_for_hits(hits):
    if hits == 0:
        return "uncovered"
    if hits <= 3:
        return "covered-1"
    if hits <= 9:
        return "covered-2"
    if hits <= 49:
        return "covered-3"
    return "covered-4"


def _pct_class(pct):
    if pct < 50:
        return "pct-low"
    if pct < 80:
        return "pct-mid"
    return "pct-high"


def _read_source(relpath):
    path = os.path.join(FS_ROOT, relpath)
    try:
        with open(path) as f:
            return f.readlines()
    except (OSError, IOError):
        return []


def _build_file_rows(files_data):
    rows = []
    for fn, info in sorted(files_data.items()):
        total = info.get("total_lines", 0)
        lines_hit = info.get("lines", {})
        covered = len(lines_hit)
        pct = round(covered / total * 100, 1) if total > 0 else 100.0
        rows.append((pct, fn, total, covered, lines_hit))
    rows.sort(key=lambda r: r[0])
    return rows


def generate(data, out_file=None):
    summary = data.get("summary", {})
    files = data.get("files", {})
    sorted_rows = _build_file_rows(files)

    global_pct = summary.get("pct", 0.0)
    total_lines = summary.get("total_lines", 0)
    covered_lines = summary.get("covered_lines", 0)
    num_files = summary.get("files", 0)

    pct_class = _pct_class(global_pct)

    parts = [
        "<!DOCTYPE html>",
        '<html><head><meta charset="utf-8">',
        "<title>MicroPythonOS Coverage Report</title>",
        "<style>", CSS, "</style>",
        "</head><body>",
        '<div class="header">',
        '<div class="big-pct {}">{:.1f}%</div>'.format(pct_class, global_pct),
        '<div class="subtitle">{:,} / {:,} lines covered across {} files</div>'.format(
            covered_lines, total_lines, num_files,
        ),
        "</div>",
        '<div class="container">',
        "<table>",
        "<thead><tr>",
        "<th>File</th>",
        "<th></th>",
        "<th style='text-align:right'>Coverage</th>",
        "<th style='text-align:right'>Lines</th>",
        "</tr></thead>",
        "<tbody>",
    ]

    for pct, fn, total, covered, lines_hit in sorted_rows:
        pct_class_file = _pct_class(pct)
        bar_color = "#4caf50" if pct >= 50 else "#ff9800" if pct >= 30 else "#f44336"
        parts.append(
            "<tr><td colspan='4' style='padding:0;border:none'><details>"
            "<summary style='display:flex;align-items:center;padding:8px 12px'>"
            "<span style='flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{}</span>".format(
                html.escape(fn),
            )
        )
        parts.append(
            '<div class="bar-outer"><div class="bar-inner" style="width:{:.1f}%;background:{}"></div></div>'.format(
                pct, bar_color,
            )
        )
        parts.append(
            '<span class="pct-cell {}" style="text-align:right;padding-left:10px">{:.1f}%</span>'.format(
                pct_class_file, pct,
            )
        )
        parts.append(
            '<span style="text-align:right;width:70px;display:inline-block">{}/{}'.format(
                covered, total,
            )
        )
        parts.append("</summary>")
        parts.append('<div class="source-panel">')

        source_lines = _read_source(fn)
        if source_lines:
            parts.append('<table class="source-table">')
            for i, line in enumerate(source_lines, 1):
                hits = lines_hit.get(str(i), 0)
                cls = _class_for_hits(hits)
                hc_str = " <span class='hc'>{}</span>".format(hits) if hits > 0 else ""
                parts.append(
                    '<tr class="{}"><td class="ln">{}{}</td><td>{}</td></tr>'.format(
                        cls, i, hc_str, html.escape(line.rstrip("\n")),
                    )
                )
            parts.append("</table>")
        else:
            parts.append('<div style="padding:10px;color:#666">source not found</div>')

        parts.append("</div></details></td></tr>")

    parts.extend(["</tbody>", "</table>", "</div>", "</body></html>"])

    output = "\n".join(parts)
    if out_file:
        os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
        with open(out_file, "w") as f:
            f.write(output)
    else:
        sys.stdout.write(output)


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML coverage report from coverage JSON",
    )
    parser.add_argument("input", help="Coverage JSON file from test_runner.py --coverage-save")
    parser.add_argument("-o", "--output", default=None, help="Output HTML file (default: stdout)")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    generate(data, out_file=args.output)


if __name__ == "__main__":
    main()
