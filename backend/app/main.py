from datetime import datetime
from pathlib import Path
import csv
import io
import re
from difflib import SequenceMatcher

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .ai import extract_candidate_terms, suggest_translation, translate_term
from .database import Base, SessionLocal, engine, get_db
from .exporter import export_project_html
from .languages import LANGUAGES
from .models import Document, DocumentPage, GlossaryOccurrence, GlossaryTerm, Segment, Translation, TranslationProject
from .pdf_parser import extract_segments, render_pages
from .schemas import GlossaryTermCreate, GlossaryTermOut, GlossaryTermUpdate, LanguageOut, SegmentLocationOut, SegmentOut, TranslationUpdate

Base.metadata.create_all(bind=engine)

app = FastAPI(title="EAS Translation Engine", version="1.9.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "storage"
SAMPLES = STORAGE / "samples"
PAGES = STORAGE / "pages"
UPLOADS = STORAGE / "uploads"
EXPORTS = STORAGE / "exports"
FRONTEND = ROOT.parent / "frontend"

OLD_STANDARD_FILENAME = "02-Planting.pdf"
CURRENT_STANDARD_FILENAME = "TREE PLANTING STANDARDS 2nd edition 2026 FINAL.pdf"

for folder in (SAMPLES, PAGES, UPLOADS, EXPORTS):
    folder.mkdir(parents=True, exist_ok=True)

if FRONTEND.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
app.mount("/pages", StaticFiles(directory=str(PAGES)), name="pages")

NUMERIC_ONLY_RE = re.compile(r"^[\s\d.,:;()\[\]{}+\-–—/*%<>=_]+$")
KEY_RE = re.compile(r"^(\d+(?:\.\d+)*)(?:\s+|\t+|;|,)(.*)$")


def clean_text(value: str | None) -> str:
    text = str(value or "").replace("\u00ad", "").replace("\u200b", "").replace("￾", " ")
    text = re.sub(r"(?<=[A-Za-z])[-‐‑‒–—]\s+(?=[a-z])", "", text)
    text = re.sub(r"(?<=[A-Za-z])\s+[-‐‑‒–—]\s+(?=[a-z])", "", text)
    return re.sub(r"\s+", " ", text).strip()


def is_numeric_only(value: str | None) -> bool:
    value = str(value or "").strip()
    return bool(value) and bool(NUMERIC_ONLY_RE.fullmatch(value))


def segment_key(segment: Segment) -> str | None:
    return segment.paragraph_number or segment.section_number


def comparable(value: str | None) -> str:
    return clean_text(value).lower()


def similar(a: str | None, b: str | None, threshold: float = 0.96) -> bool:
    aa, bb = comparable(a), comparable(b)
    if not aa or not bb:
        return False
    return aa == bb or SequenceMatcher(None, aa, bb).ratio() >= threshold


def get_current_document(db: Session) -> Document | None:
    return db.query(Document).filter(Document.title == "Tree Planting Standard 2026").first()


def create_document_from_pdf(path: Path, title: str, db: Session) -> Document:
    import fitz
    pdf = fitz.open(str(path))
    doc = Document(title=title, edition="2026" if "2026" in title else "2022", source_language="en", uploaded_file_path=str(path), page_count=pdf.page_count)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    for page in render_pages(str(path), str(PAGES), doc.id):
        db.add(DocumentPage(document_id=doc.id, **page))
    db.commit()
    for seg in extract_segments(str(path)):
        db.add(Segment(document_id=doc.id, **seg))
    db.commit()
    return doc


def prepare_builtins(db: Session) -> dict:
    current = SAMPLES / CURRENT_STANDARD_FILENAME
    previous = SAMPLES / OLD_STANDARD_FILENAME
    if not current.exists() or not previous.exists():
        raise HTTPException(status_code=400, detail="Copy both source PDFs into backend/storage/samples first.")
    doc = get_current_document(db)
    if not doc:
        doc = create_document_from_pdf(current, "Tree Planting Standard 2026", db)
    return {"status": "ready", "document_id": doc.id, "segments": db.query(Segment).filter(Segment.document_id == doc.id).count()}


def ensure_project_rows(project: TranslationProject, db: Session):
    for segment in db.query(Segment).filter(Segment.document_id == project.document_id).all():
        row = db.query(Translation).filter_by(project_id=project.id, segment_id=segment.id).first()
        if row:
            continue
        if is_numeric_only(segment.source_text):
            db.add(Translation(project_id=project.id, segment_id=segment.id, translated_text=segment.source_text, status="copied"))
        else:
            db.add(Translation(project_id=project.id, segment_id=segment.id, status="not_started"))
    db.commit()


def source_map(path: Path) -> dict[str, str]:
    result = {}
    for seg in extract_segments(str(path)):
        key = seg.get("paragraph_number") or seg.get("section_number")
        if key:
            result[key] = seg.get("source_text") or ""
    return result


def parse_translation_file(path: Path) -> dict[str, list[str]]:
    if path.suffix.lower() == ".pdf":
        out: dict[str, list[str]] = {}
        for seg in extract_segments(str(path)):
            key = seg.get("paragraph_number") or seg.get("section_number")
            text = clean_text(seg.get("source_text"))
            if key and text and not is_numeric_only(text):
                out.setdefault(key, []).append(text)
        return out
    text = path.read_text(encoding="utf-8", errors="ignore")
    out: dict[str, list[str]] = {}
    if path.suffix.lower() == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            key = row.get("paragraph_number") or row.get("section") or row.get("number")
            val = row.get("translated_text") or row.get("translation") or row.get("text")
            if key and val:
                out.setdefault(key.strip(), []).append(clean_text(val))
        return out
    key = None
    parts: list[str] = []
    for line in text.splitlines():
        m = KEY_RE.match(line.strip())
        if m:
            if key and parts:
                out.setdefault(key, []).append(clean_text(" ".join(parts)))
            key = m.group(1)
            parts = [m.group(2)]
        elif key:
            parts.append(line.strip())
    if key and parts:
        out.setdefault(key, []).append(clean_text(" ".join(parts)))
    return out


def glossary_items(project_id: int, db: Session) -> list[dict]:
    return [
        {"source_term": t.source_term, "target_term": t.target_term}
        for t in db.query(GlossaryTerm).filter_by(project_id=project_id).order_by(GlossaryTerm.source_term.asc()).all()
        if t.target_term
    ]


def upsert_term(project: TranslationProject, source_term: str, target_term: str | None, db: Session, segment_id: int | None = None):
    source_term = clean_text(source_term).lower()
    if not source_term or len(source_term) < 3:
        return None
    term = db.query(GlossaryTerm).filter_by(project_id=project.id, source_term=source_term, target_language=project.target_language).first()
    if not term:
        term = GlossaryTerm(project_id=project.id, source_term=source_term, target_term=target_term, target_language=project.target_language, status="suggested")
        db.add(term)
        db.flush()
    elif target_term and not term.target_term:
        term.target_term = target_term
        term.status = "confirmed"
    if segment_id:
        exists = db.query(GlossaryOccurrence).filter_by(term_id=term.id, segment_id=segment_id).first()
        if not exists:
            db.add(GlossaryOccurrence(term_id=term.id, segment_id=segment_id, confidence=0.7))
    return term


def build_glossary(project: TranslationProject, db: Session):
    rows = db.query(Segment, Translation).join(Translation, Translation.segment_id == Segment.id).filter(Translation.project_id == project.id).all()
    for segment, translation in rows:
        for item in extract_candidate_terms(segment.source_text, project.target_language):
            target = item.get("target_term") or translate_term(item.get("source_term", ""), project.target_language)
            upsert_term(project, item.get("source_term", ""), target, db, segment.id)
    db.commit()


@app.get("/")
def root():
    return {"name": "EAS Translation Engine", "version": "1.9.0", "ui": "/app"}


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.9.0"}


@app.get("/languages", response_model=list[LanguageOut])
def languages():
    return LANGUAGES


@app.post("/standards/prepare")
def prepare(db: Session = Depends(get_db)):
    return prepare_builtins(db)


@app.get("/documents")
def documents(db: Session = Depends(get_db)):
    prepare_builtins(db)
    return db.query(Document).all()


@app.post("/projects/open")
def open_project(target_language: str, db: Session = Depends(get_db)):
    data = prepare_builtins(db)
    project = db.query(TranslationProject).filter_by(document_id=data["document_id"], target_language=target_language).first()
    if not project:
        project = TranslationProject(document_id=data["document_id"], target_language=target_language)
        db.add(project)
        db.commit()
        db.refresh(project)
    ensure_project_rows(project, db)
    return {"id": project.id, "document_id": project.document_id, "target_language": project.target_language, "status": project.status}


@app.get("/projects")
def projects(db: Session = Depends(get_db)):
    return db.query(TranslationProject).all()


@app.get("/projects/{project_id}/segments", response_model=list[SegmentOut])
def project_segments(project_id: int, filter: str = "needs_work", db: Session = Depends(get_db)):
    rows = db.query(Segment, Translation).join(Translation, Translation.segment_id == Segment.id).filter(Translation.project_id == project_id).order_by(Segment.reading_order.asc()).all()
    out = []
    for s, t in rows:
        if filter == "needs_work" and t.status in {"approved", "imported", "copied"}:
            continue
        out.append(SegmentOut(id=s.id, page_number=s.page_number, section_number=s.section_number, paragraph_number=s.paragraph_number, segment_type=s.segment_type, source_text=s.source_text, reading_order=s.reading_order, translated_text=t.translated_text, translation_status=t.status, translation_id=t.id))
    return out


@app.get("/segments/{segment_id}/location", response_model=SegmentLocationOut)
def segment_location(segment_id: int, db: Session = Depends(get_db)):
    segment = db.get(Segment, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
    page = db.query(DocumentPage).filter_by(document_id=segment.document_id, page_number=segment.page_number).first()
    return SegmentLocationOut(segment_id=segment.id, page_number=segment.page_number, page_image_url=f"/pages/{Path(page.image_path).name}" if page else None, page_width=page.width if page else None, page_height=page.height if page else None, bbox=[segment.bbox_x1, segment.bbox_y1, segment.bbox_x2, segment.bbox_y2])


@app.patch("/translations/{translation_id}")
def update_translation(translation_id: int, payload: TranslationUpdate, db: Session = Depends(get_db)):
    tr = db.get(Translation, translation_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Translation not found")
    tr.translated_text = payload.translated_text
    tr.status = payload.status
    tr.updated_at = datetime.utcnow()
    db.commit()
    project = db.get(TranslationProject, tr.project_id)
    if project:
        build_glossary(project, db)
    return {"id": tr.id, "status": tr.status}


@app.post("/translations/{translation_id}/approve")
def approve_translation(translation_id: int, db: Session = Depends(get_db)):
    tr = db.get(Translation, translation_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Translation not found")
    tr.status = "approved"
    tr.approved_at = datetime.utcnow()
    db.commit()
    return {"id": tr.id, "status": tr.status}


@app.post("/projects/{project_id}/segments/{segment_id}/ai-suggestion")
def ai(project_id: int, segment_id: int, db: Session = Depends(get_db)):
    project = db.get(TranslationProject, project_id)
    segment = db.get(Segment, segment_id)
    if not project or not segment:
        raise HTTPException(status_code=404, detail="Project or segment not found")
    return suggest_translation(segment.source_text, project.target_language, glossary=glossary_items(project_id, db))


@app.get("/projects/{project_id}/glossary", response_model=list[GlossaryTermOut])
def glossary(project_id: int, db: Session = Depends(get_db)):
    return db.query(GlossaryTerm).filter_by(project_id=project_id).order_by(GlossaryTerm.source_term.asc()).all()


@app.post("/projects/{project_id}/glossary", response_model=GlossaryTermOut)
def create_glossary(project_id: int, payload: GlossaryTermCreate, db: Session = Depends(get_db)):
    project = db.get(TranslationProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    term = upsert_term(project, payload.source_term, payload.target_term, db)
    db.commit()
    return term


@app.patch("/projects/{project_id}/glossary/{term_id}", response_model=GlossaryTermOut)
def update_glossary(project_id: int, term_id: int, payload: GlossaryTermUpdate, db: Session = Depends(get_db)):
    term = db.get(GlossaryTerm, term_id)
    if not term or term.project_id != project_id:
        raise HTTPException(status_code=404, detail="Term not found")
    if payload.source_term is not None:
        term.source_term = clean_text(payload.source_term).lower()
    if payload.target_term is not None:
        term.target_term = payload.target_term
    if payload.status is not None:
        term.status = payload.status
    db.commit()
    return term


@app.delete("/projects/{project_id}/glossary/{term_id}")
def delete_glossary(project_id: int, term_id: int, db: Session = Depends(get_db)):
    term = db.get(GlossaryTerm, term_id)
    if not term or term.project_id != project_id:
        raise HTTPException(status_code=404, detail="Term not found")
    db.query(GlossaryOccurrence).filter_by(term_id=term.id).delete()
    db.delete(term)
    db.commit()
    return {"deleted": term_id}


@app.post("/projects/{project_id}/glossary/build")
def build_glossary_endpoint(project_id: int, db: Session = Depends(get_db)):
    project = db.get(TranslationProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    before = db.query(GlossaryTerm).filter_by(project_id=project_id).count()
    build_glossary(project, db)
    after = db.query(GlossaryTerm).filter_by(project_id=project_id).count()
    return {"created": max(0, after - before), "total": after}


@app.post("/projects/{project_id}/import-translation")
async def import_translation(project_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    project = db.get(TranslationProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    safe = file.filename.replace("/", "_").replace("\\", "_")
    path = UPLOADS / f"project_{project_id}_{safe}"
    path.write_bytes(await file.read())
    previous_translation = parse_translation_file(path)
    old_map = source_map(SAMPLES / OLD_STANDARD_FILENAME)
    ensure_project_rows(project, db)
    rows = db.query(Segment, Translation).join(Translation, Translation.segment_id == Segment.id).filter(Translation.project_id == project_id).all()
    stats = {"imported": 0, "needs_work": 0, "new_segments": 0, "inconsistent": 0, "previous_units_found": sum(len(v) for v in previous_translation.values())}
    for segment, tr in rows:
        key = segment_key(segment) or ""
        candidates = previous_translation.get(key, [])
        unique = []
        for c in candidates:
            if not any(similar(c, u, 0.98) for u in unique):
                unique.append(c)
        if len(unique) > 1:
            tr.translated_text = unique[0]
            tr.status = "returned"
            stats["inconsistent"] += 1
        elif key in old_map and similar(old_map[key], segment.source_text):
            if unique:
                tr.translated_text = unique[0]
                tr.status = "imported"
                stats["imported"] += 1
        else:
            if unique:
                tr.translated_text = unique[0]
            tr.status = "returned" if unique else "not_started"
            stats["needs_work"] += 1
            if key not in old_map:
                stats["new_segments"] += 1
    db.commit()
    build_glossary(project, db)
    stats["glossary_total"] = db.query(GlossaryTerm).filter_by(project_id=project_id).count()
    return stats


@app.post("/projects/{project_id}/export/html")
def export_html(project_id: int, db: Session = Depends(get_db)):
    project = db.get(TranslationProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    doc = db.get(Document, project.document_id)
    rows = db.query(Segment, Translation).join(Translation, Translation.segment_id == Segment.id).filter(Translation.project_id == project_id).order_by(Segment.reading_order.asc()).all()
    data = [{"paragraph_number": s.paragraph_number, "section_number": s.section_number, "segment_type": s.segment_type, "source_text": s.source_text, "translated_text": t.translated_text} for s, t in rows]
    out = EXPORTS / f"project_{project_id}_{project.target_language}.html"
    export_project_html(doc.title, project.target_language, data, str(out))
    return {"download_url": f"/exports/{out.name}"}


@app.get("/exports/{filename}")
def download_export(filename: str):
    path = EXPORTS / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(path)
