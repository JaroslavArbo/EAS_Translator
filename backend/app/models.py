from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    edition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_language: Mapped[str] = mapped_column(String(10), default="en")
    uploaded_file_path: Mapped[str] = mapped_column(String(500))
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    pages = relationship("DocumentPage", cascade="all, delete-orphan")
    segments = relationship("Segment", cascade="all, delete-orphan")

class DocumentPage(Base):
    __tablename__ = "document_pages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    page_number: Mapped[int] = mapped_column(Integer)
    image_path: Mapped[str] = mapped_column(String(500))
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)

class Segment(Base):
    __tablename__ = "segments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    page_number: Mapped[int] = mapped_column(Integer)
    section_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    paragraph_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    segment_type: Mapped[str] = mapped_column(String(50), default="numbered_paragraph")
    source_text: Mapped[str] = mapped_column(Text)
    bbox_x1: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y1: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_x2: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y2: Mapped[float | None] = mapped_column(Float, nullable=True)
    reading_order: Mapped[int] = mapped_column(Integer)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)

class TranslationProject(Base):
    __tablename__ = "translation_projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    target_language: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("document_id", "target_language"),)

class Translation(Base):
    __tablename__ = "translations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("translation_projects.id"))
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"))
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="not_started")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    segment = relationship("Segment")
    __table_args__ = (UniqueConstraint("project_id", "segment_id"),)

class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    translation_id: Mapped[int] = mapped_column(ForeignKey("translations.id"))
    comment_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("translation_projects.id"))
    source_term: Mapped[str] = mapped_column(String(255))
    target_term: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_language: Mapped[str] = mapped_column(String(10), default="en")
    target_language: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(50), default="suggested")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("project_id", "source_term", "target_language"),)

class GlossaryOccurrence(Base):
    __tablename__ = "glossary_occurrences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("glossary_terms.id"))
    segment_id: Mapped[int] = mapped_column(ForeignKey("segments.id"))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
