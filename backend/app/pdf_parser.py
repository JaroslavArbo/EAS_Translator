import re
from pathlib import Path
import fitz

# Real paragraph/section markers used by EAS, e.g. 3.2, 3.2.9, 5.10.1.
# The parser keeps these as metadata and removes them from translation text.
MARKER_TOKEN_RE = re.compile(r"^(\d+(?:\.\d+){1,2})\.?$")
INLINE_MARKER_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+){1,2})\.?\s+(?=[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ(])")
SPACE_RE = re.compile(r"\s+")

PAGE_FURNITURE_RE = re.compile(r"^(tree\s+planting\s+standard|european\s+arboricultural\s+standards)$", re.I)
FIGURE_RE = re.compile(r"^figure\s+\d+\s*[:.]?", re.I)
TOC_RE = re.compile(r"table\s+of\s+contents", re.I)


def clean_text(text: str) -> str:
    text = text.replace("￾", "")
    text = text.replace("\u00ad", "")
    text = text.replace("- ", "")  # common hard line-break artifact: accura- te -> accurate
    text = SPACE_RE.sub(" ", text).strip()
    return text


def is_numeric_only_text(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    return re.fullmatch(r"[\d\s.,;:/\\\-–—+*()\[\]<>=%°]+", cleaned) is not None


def is_page_furniture(text: str) -> bool:
    t = clean_text(text)
    if not t:
        return True
    if PAGE_FURNITURE_RE.match(t):
        return True
    if is_numeric_only_text(t):
        return True
    return False


def segment_type_for_number(number: str) -> str:
    parts = number.split(".")
    if len(parts) >= 3:
        return "numbered_paragraph"
    if len(parts) == 2:
        return "subchapter_heading"
    return "chapter_heading"


def section_number_for(number: str) -> str:
    parts = number.split(".")
    if len(parts) >= 2:
        return ".".join(parts[:2])
    return number


def render_pages(pdf_path: str, out_dir: str, document_id: int):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    pages = []
    for index, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        image_path = str(Path(out_dir) / f"document_{document_id}_page_{index}.png")
        pix.save(image_path)
        rect = page.rect
        pages.append({"page_number": index, "image_path": image_path, "width": rect.width, "height": rect.height})
    return pages


def _union_bbox(a, b):
    if a is None:
        return b
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _line_entries(page):
    """Return visually grouped text lines with bboxes.

    PyMuPDF block order is unreliable for this two-column standard. Grouping words
    into lines and processing each column top-down keeps paragraph numbers next to
    their own text and prevents whole chapters being glued into one segment.
    """
    words = page.get_text("words")
    if not words:
        return []
    rect = page.rect
    mid = rect.width / 2.0
    buckets = {0: [], 1: []}
    for w in words:
        x0, y0, x1, y1, word, *_ = w
        col = 0 if (x0 + x1) / 2.0 < mid else 1
        buckets[col].append((x0, y0, x1, y1, word))

    entries = []
    for col, items in buckets.items():
        items.sort(key=lambda w: (round((w[1] + w[3]) / 2.0, 1), w[0]))
        lines = []
        for x0, y0, x1, y1, word in items:
            cy = (y0 + y1) / 2.0
            placed = False
            for line in lines:
                if abs(line["cy"] - cy) <= 3.2:
                    line["words"].append((x0, y0, x1, y1, word))
                    line["cy"] = (line["cy"] + cy) / 2.0
                    placed = True
                    break
            if not placed:
                lines.append({"cy": cy, "words": [(x0, y0, x1, y1, word)]})
        for line in lines:
            ws = sorted(line["words"], key=lambda w: w[0])
            text = clean_text(" ".join(w[4] for w in ws))
            bbox = (min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws))
            if text:
                entries.append({"column": col, "y": line["cy"], "x": bbox[0], "text": text, "bbox": bbox})
    return sorted(entries, key=lambda e: (e["column"], e["y"], e["x"]))


def _split_line_on_markers(line_text: str):
    """Yield (marker_or_none, content) chunks for a line.

    Handles both '5.10.1 text' and rare inline cases with multiple markers.
    """
    text = clean_text(line_text)
    if not text:
        return []
    first = text.split()[0] if text.split() else ""
    if MARKER_TOKEN_RE.match(first):
        marker = MARKER_TOKEN_RE.match(first).group(1)
        rest = clean_text(text[len(first):])
        return [(marker, rest)]

    matches = list(INLINE_MARKER_RE.finditer(text))
    if not matches:
        return [(None, text)]
    chunks = []
    prefix = clean_text(text[:matches[0].start()])
    if prefix:
        chunks.append((None, prefix))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunks.append((m.group(1), clean_text(text[m.end():end])))
    return chunks


def extract_segments(pdf_path: str):
    """Extract translation units from the PDF.

    Version 1.0 rules:
    - paragraph numbers such as 3.2.9, 3.3 or 5.10.1 are metadata only;
    - one numbered paragraph is one translation segment;
    - subchapter headings stay separate and are not glued to their paragraphs;
    - table-of-contents pages are skipped because TOC is regenerated/copied;
    - numeric-only fragments are ignored/copied, not sent to translators.
    """
    doc = fitz.open(pdf_path)
    segments = []
    order = 1
    current = None
    last_column = None

    def flush_current():
        nonlocal current, order
        if not current:
            return
        current["source_text"] = clean_text(current["source_text"])
        if current["source_text"] and not is_numeric_only_text(current["source_text"]):
            segments.append(current)
            order += 1
        current = None

    def start_segment(page_index, number, text, bbox):
        nonlocal current
        flush_current()
        text = clean_text(text)
        if is_page_furniture(text):
            text = ""
        seg_type = segment_type_for_number(number)
        current = {
            "page_number": page_index,
            "section_number": section_number_for(number),
            "paragraph_number": number if seg_type == "numbered_paragraph" else None,
            "segment_type": seg_type,
            "source_text": text,
            "bbox_x1": bbox[0], "bbox_y1": bbox[1], "bbox_x2": bbox[2], "bbox_y2": bbox[3],
            "reading_order": order,
            "is_required": True,
        }

    def append_to_current(text, bbox):
        nonlocal current
        text = clean_text(text)
        if not current or not text:
            return
        if is_page_furniture(text) or FIGURE_RE.match(text):
            return
        current["source_text"] = clean_text((current["source_text"] + " " + text).strip())
        ub = _union_bbox((current["bbox_x1"], current["bbox_y1"], current["bbox_x2"], current["bbox_y2"]), bbox)
        current["bbox_x1"], current["bbox_y1"], current["bbox_x2"], current["bbox_y2"] = ub

    for page_index, page in enumerate(doc, start=1):
        flush_current()
        page_plain = clean_text(page.get_text("text"))
        if page_index <= 5 or TOC_RE.search(page_plain):
            continue
        entries = _line_entries(page)
        last_column = None
        for entry in entries:
            text = entry["text"]
            bbox = entry["bbox"]
            column = entry["column"]
            if last_column is not None and column != last_column:
                flush_current()
            last_column = column
            if is_page_furniture(text) or FIGURE_RE.match(text):
                continue
            chunks = _split_line_on_markers(text)
            for marker, content in chunks:
                if marker:
                    start_segment(page_index, marker, content, bbox)
                else:
                    append_to_current(content, bbox)
        flush_current()

    cleaned = []
    for seg in segments:
        text = clean_text(seg["source_text"])
        if not text or is_numeric_only_text(text):
            continue
        if seg["segment_type"] == "subchapter_heading":
            m = re.search(r"\s\d+(?:\.\d+){1,2}\s", text)
            if m:
                text = clean_text(text[:m.start()])
                seg["source_text"] = text
        cleaned.append(seg)
    for i, seg in enumerate(cleaned, start=1):
        seg["reading_order"] = i
    return cleaned
