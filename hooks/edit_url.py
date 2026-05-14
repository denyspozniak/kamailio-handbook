"""
MkDocs hook: rewrite Edit-URL for the per-language landing pages.

The landing pages are staged in CI from README.md → index.md (so README.md
stays canonical for GitHub direct viewing and index.md is the mkdocs site's
section landing). Because index.md isn't committed to the repo, MkDocs'
auto-computed edit_url (edit/main/docs/<lang>/index.md) 404s when clicked.

Override edit_url for those pages to point at the committed README.md.
"""
from __future__ import annotations
import os


def on_page_context(context, page, config, nav):
    src = page.file.src_path.replace(os.sep, "/")
    if src.endswith("index.md") and page.edit_url:
        page.edit_url = page.edit_url.replace("/index.md", "/README.md")
    return context
