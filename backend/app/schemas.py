from pydantic import BaseModel

class DocumentOut(BaseModel):
    id: int
    title: str
    source_language: str
    page_count: int
    class Config:
        from_attributes = True

class ProjectCreate(BaseModel):
    document_id: int
    target_language: str

class ProjectOut(BaseModel):
    id: int
    document_id: int
    target_language: str
    status: str
    class Config:
        from_attributes = True

class SegmentOut(BaseModel):
    id: int
    page_number: int
    section_number: str | None
    paragraph_number: str | None
    segment_type: str
    source_text: str
    reading_order: int
    translated_text: str | None = None
    translation_status: str | None = None
    translation_id: int | None = None
    class Config:
        from_attributes = True

class SegmentLocationOut(BaseModel):
    segment_id: int
    page_number: int
    page_image_url: str | None
    page_width: float | None
    page_height: float | None
    bbox: list[float | None]

class TranslationUpdate(BaseModel):
    translated_text: str
    status: str = "translated"

class AiSuggestionOut(BaseModel):
    suggested_translation: str
    confidence: float
    notes: list[str]

class CommentCreate(BaseModel):
    comment_text: str

class LanguageOut(BaseModel):
    code: str
    name: str

class GlossaryTermCreate(BaseModel):
    source_term: str
    target_term: str | None = None
    status: str = "suggested"

class GlossaryTermUpdate(BaseModel):
    source_term: str | None = None
    target_term: str | None = None
    status: str | None = None

class GlossaryTermOut(BaseModel):
    id: int
    project_id: int
    source_term: str
    target_term: str | None
    source_language: str
    target_language: str
    status: str
    class Config:
        from_attributes = True
