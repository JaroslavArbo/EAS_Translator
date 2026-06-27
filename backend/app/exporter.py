from pathlib import Path
from html import escape

HTML_TEMPLATE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 48px auto; line-height: 1.45; }}
h1 {{ color: #244b32; }}
.segment {{ margin: 0 0 14px 0; }}
.number {{ font-weight: bold; color: #244b32; margin-right: 8px; }}
.heading {{ font-size: 1.35em; font-weight: bold; margin-top: 28px; color: #244b32; }}
.warning {{ background: #fff3cd; padding: 10px; border: 1px solid #ffeeba; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="warning">MVP export. Nejde ještě o finální sazbu PDF.</p>
{body}
</body>
</html>"""

def export_project_html(title: str, target_language: str, rows: list[dict], out_path: str):
    parts = []
    for row in rows:
        text = row.get("translated_text") or f"[MISSING TRANSLATION] {row.get('source_text', '')}"
        number = row.get("paragraph_number") or row.get("section_number") or ""
        if row.get("segment_type") in {"chapter_heading", "subchapter_heading"}:
            parts.append(f'<div class="heading"><span class="number">{escape(number)}</span>{escape(text)}</div>')
        else:
            parts.append(f'<p class="segment"><span class="number">{escape(number)}</span>{escape(text)}</p>')
    html = HTML_TEMPLATE.format(lang=target_language, title=escape(title), body="\n".join(parts))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path
