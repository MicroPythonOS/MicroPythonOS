#!/usr/bin/env python3
"""Minify and inline WebREPL assets into webrepl_inlined_minified.html."""
from __future__ import annotations

import re
from pathlib import Path


def _is_alphanum(ch: str) -> bool:
    return ch.isalnum() or ch in "_$\\"


def jsmin(js: str) -> str:
    """Minify JavaScript by stripping comments and collapsing whitespace safely."""
    out: list[str] = []
    i = 0
    length = len(js)
    state = "code"
    quote = ""

    def peek(offset: int = 1) -> str:
        idx = i + offset
        if idx >= length:
            return ""
        return js[idx]

    def push_char(ch: str) -> None:
        out.append(ch)

    while i < length:
        ch = js[i]
        nxt = peek(1)

        if state == "code":
            if ch == "/" and nxt == "/":
                state = "line_comment"
                i += 2
                continue
            if ch == "/" and nxt == "*":
                state = "block_comment"
                i += 2
                continue
            if ch in ("'", '"'):
                state = "string"
                quote = ch
                push_char(ch)
                i += 1
                continue
            if ch == "`":
                state = "template"
                push_char(ch)
                i += 1
                continue
            if ch.isspace():
                if out:
                    last = out[-1]
                    if last in "{}[]();,":
                        i += 1
                        continue
                    if last != " ":
                        push_char(" ")
                i += 1
                continue
            if ch in "{}[]();,":
                if out and out[-1] == " ":
                    out.pop()
                push_char(ch)
                i += 1
                continue
            push_char(ch)
            i += 1
            continue

        if state == "line_comment":
            if ch in ("\n", "\r"):
                if out and out[-1] != " ":
                    out.append(" ")
                state = "code"
            i += 1
            continue

        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                i += 2
            else:
                i += 1
            continue

        if state == "string":
            push_char(ch)
            if ch == "\\" and nxt:
                push_char(nxt)
                i += 2
                continue
            if ch == quote:
                state = "code"
            i += 1
            continue

        if state == "template":
            push_char(ch)
            if ch == "\\" and nxt:
                push_char(nxt)
                i += 2
                continue
            if ch == "`":
                state = "code"
            i += 1
            continue

    return "".join(out).strip()


def cssmin(css: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,>])\s*", r"\1", css)
    return css.strip()


def inline_assets() -> None:
    base_dir = Path(__file__).parent
    html_path = base_dir / "webrepl.html"
    out_path = base_dir / "webrepl_inlined_minified.html"

    html = html_path.read_text(encoding="utf-8")
    css = cssmin((base_dir / "webrepl.css").read_text(encoding="utf-8"))
    term_js = jsmin((base_dir / "term.js").read_text(encoding="utf-8"))
    file_saver_js = jsmin((base_dir / "FileSaver.js").read_text(encoding="utf-8"))
    webrepl_js = jsmin((base_dir / "webrepl.js").read_text(encoding="utf-8"))

    replacements = [
        (r"<link\s+rel=\"stylesheet\"\s+href=\"webrepl\.css\"\s*/?>", f"<style>{css}</style>"),
        (r"<script\s+src=\"term\.js\"\s*>\s*</script>", f"<script>{term_js}</script>"),
        (r"<script\s+src=\"FileSaver\.js\"\s*>\s*</script>", f"<script>{file_saver_js}</script>"),
        (r"<script\s+src=\"webrepl\.js\"\s*>\s*</script>", f"<script>{webrepl_js}</script>"),
    ]

    for pattern, replacement in replacements:
        new_html, count = re.subn(
            pattern,
            lambda _match, rep=replacement: rep,
            html,
            flags=re.IGNORECASE,
        )
        if count != 1:
            raise RuntimeError(
                f"Expected to replace exactly one tag for pattern: {pattern}; replaced {count}"
            )
        html = new_html

    out_path.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    inline_assets()
