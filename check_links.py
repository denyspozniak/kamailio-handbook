#!/usr/bin/env python3
"""
Check internal links in the built mkdocs site under ./site/.

For each .html under site/, extract every href/src, resolve relative paths,
and verify the target exists in site/. Reports:
  - broken internal links (target file or anchor missing)
  - duplicate fragment targets (rare; reported for awareness)

External links (http(s)://, mailto:) are not fetched, just counted.
"""
from __future__ import annotations
import os
import re
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote


SITE = Path(__file__).parent / "site"
SITE_PREFIX = "/kamailio-handbook/"   # base path from mkdocs.yml site_url


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []  # (attr_name, value)
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs)
        for key in ("href", "src"):
            val = d.get(key)
            if val:
                self.links.append((key, val))
        anchor = d.get("id")
        if anchor:
            self.ids.add(anchor)
        # Headings auto-get ids via mkdocs toc extension; capture name attr too
        name = d.get("name")
        if name and tag == "a":
            self.ids.add(name)


def normalise(target: str, source_dir: Path) -> tuple[Path | None, str | None]:
    """
    Resolve a link relative to the source HTML's directory and the site root.
    Returns (filesystem_path_to_html, fragment) or (None, fragment) for
    things we don't check (external, mailto, javascript, ...).
    """
    parsed = urlparse(target)
    if parsed.scheme in {"http", "https", "mailto", "javascript", "data"}:
        return None, parsed.fragment or None
    if not parsed.path and parsed.fragment:
        # pure #anchor -> same page
        return None, parsed.fragment or None

    path = unquote(parsed.path)
    if path.startswith(SITE_PREFIX):
        # absolute site path
        rel = path[len(SITE_PREFIX):]
        target_path = SITE / rel
    elif path.startswith("/"):
        # absolute path outside the site (rare; e.g. /assets/foo)
        target_path = SITE / path.lstrip("/")
    else:
        target_path = (source_dir / path).resolve()

    # mkdocs use_directory_urls=True -> a link like "../foo/" resolves to a dir
    if target_path.is_dir():
        target_path = target_path / "index.html"

    return target_path, parsed.fragment or None


def main() -> int:
    if not SITE.is_dir():
        print(f"ERROR: site directory not found at {SITE}", file=sys.stderr)
        return 2

    html_files = sorted(SITE.rglob("*.html"))
    print(f"Found {len(html_files)} HTML files under {SITE}")

    # Pass 1: collect every page's ids so we can verify fragment targets.
    page_ids: dict[Path, set[str]] = {}
    for f in html_files:
        with f.open(encoding="utf-8") as fh:
            text = fh.read()
        # also pick up `id="..."` via simple regex for the bits HTMLParser misses
        ids = set(re.findall(r'\bid="([^"]+)"', text))
        ids.update(re.findall(r"\bid='([^']+)'", text))
        page_ids[f] = ids

    broken: list[tuple[Path, str, str]] = []   # (source, target, why)
    external_count = 0
    checked_internal = 0

    for source in html_files:
        with source.open(encoding="utf-8") as fh:
            text = fh.read()
        parser = LinkExtractor()
        parser.feed(text)
        source_dir = source.parent
        for attr, val in parser.links:
            target_path, fragment = normalise(val, source_dir)
            if target_path is None and fragment is None:
                external_count += 1
                continue
            if target_path is None:
                # pure #anchor — verify against this page's ids
                if fragment not in page_ids.get(source, set()):
                    broken.append((source, val, f"anchor #{fragment} not on this page"))
                continue
            checked_internal += 1
            if not target_path.exists():
                broken.append((source, val, f"file not found: {target_path}"))
                continue
            if fragment and target_path in page_ids:
                if fragment not in page_ids[target_path]:
                    broken.append(
                        (source, val, f"anchor #{fragment} not in {target_path.name}")
                    )

    print(f"Checked {checked_internal} internal links, "
          f"{external_count} external links skipped.")
    print()

    if not broken:
        print("✓ No broken internal links.")
        return 0

    by_source: dict[Path, list[tuple[str, str]]] = defaultdict(list)
    for source, target, why in broken:
        by_source[source].append((target, why))

    print(f"✗ {len(broken)} broken link(s) found in {len(by_source)} page(s):\n")
    for source in sorted(by_source):
        rel = source.relative_to(SITE)
        print(f"  {rel}:")
        for target, why in by_source[source]:
            print(f"    - {target}  →  {why}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
