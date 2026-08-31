"""
MkDocs hook: render GitHub alert callouts as Material admonitions.

This handbook is written to read well in two places: on GitHub, where
`> [!NOTE]` blockquotes render as coloured callouts natively, and on the
MkDocs site. Material does not understand GitHub's syntax — it wants
`!!! note` — so without this hook every callout renders as a plain
blockquote with a literal "[!NOTE]" as its first line.

Rather than switching the sources to Material syntax (which would break
the GitHub rendering the READMEs and direct file views rely on), rewrite
the blockquotes into admonitions at build time.

Fenced code inside a callout is preserved: the whole body is indented by
four spaces, which is how Material nests fences inside admonitions.
"""
from __future__ import annotations

import re

# GitHub alert type -> (Material admonition type, title)
# Material has no "important" or "caution"; map them to the nearest
# type and keep GitHub's wording as an explicit title.
ALERTS = {
    "NOTE": ("note", None),
    "TIP": ("tip", None),
    "IMPORTANT": ("info", "Important"),
    "WARNING": ("warning", None),
    "CAUTION": ("danger", "Caution"),
}

ALERT_RE = re.compile(r"^>\s*\[!(" + "|".join(ALERTS) + r")\]\s*(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _strip_quote(line: str) -> str:
    """Remove one level of blockquote marker from a line."""
    if line.startswith("> "):
        return line[2:]
    if line == ">":
        return ""
    if line.startswith(">"):
        return line[1:]
    return line


def on_page_markdown(markdown, page, config, files):
    out: list[str] = []
    lines = markdown.split("\n")
    i = 0
    in_fence = False

    while i < len(lines):
        line = lines[i]

        # Never rewrite anything inside a fenced code block: chapters quote
        # this very syntax as example text.
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue

        m = None if in_fence else ALERT_RE.match(line)
        if not m:
            out.append(line)
            i += 1
            continue

        kind, title = ALERTS[m.group(1)]
        first = m.group(2).strip()

        body: list[str] = []
        if first:
            body.append(first)

        i += 1
        while i < len(lines) and (lines[i].startswith(">") or lines[i] == ">"):
            body.append(_strip_quote(lines[i]))
            i += 1

        while body and not body[-1].strip():
            body.pop()

        header = f'!!! {kind} "{title}"' if title else f"!!! {kind}"
        out.append(header)
        out.append("")
        for b in body:
            out.append(f"    {b}" if b.strip() else "")
        out.append("")

    return "\n".join(out)
