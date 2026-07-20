#!/usr/bin/env python
"""Render .claude_docs markdown artifacts to standalone styled HTML.

Usage:
    python scripts/render_claude_docs_html_tool.py .claude_docs/FILE.md [...more]

Writes FILE.html next to each input (same basename). Tables, fenced code and
TOC-friendly headings supported via python-markdown extensions; styling is
inline (no external assets) and readable in both light and dark themes.
"""
import sys
from pathlib import Path

import markdown

CSS = """
:root { color-scheme: light dark; }
body { font: 16px/1.6 -apple-system, 'Segoe UI', Roboto, sans-serif;
       max-width: 60rem; margin: 2rem auto; padding: 0 1.25rem; }
h1, h2, h3 { line-height: 1.25; }
h1 { border-bottom: 2px solid #8884; padding-bottom: .4rem; }
h2 { border-bottom: 1px solid #8883; padding-bottom: .25rem; margin-top: 2.2rem; }
table { border-collapse: collapse; margin: 1rem 0; display: block; overflow-x: auto; }
th, td { border: 1px solid #8886; padding: .35rem .7rem; text-align: left; }
th { background: #8882; }
code { background: #8882; padding: .1rem .35rem; border-radius: 4px;
       font-size: .9em; }
pre { background: #8881; border: 1px solid #8883; border-radius: 6px;
      padding: .8rem 1rem; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { border-left: 4px solid #8886; margin-left: 0; padding-left: 1rem;
             color: #888; }
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body>{body}</body></html>
"""


def render(md_path: Path) -> Path:
    text = md_path.read_text()
    title = next((line.lstrip('# ').strip() for line in text.splitlines()
                  if line.startswith('# ')), md_path.stem)
    body = markdown.markdown(text, extensions=['tables', 'fenced_code', 'sane_lists'])
    out = md_path.with_suffix('.html')
    out.write_text(TEMPLATE.format(title=title, css=CSS, body=body))
    return out


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        print('wrote', render(Path(arg)))
