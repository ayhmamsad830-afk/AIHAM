from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ============================================================
# Document Upload
# ============================================================

class DocumentUpload(BaseModel):
    filename: str
    session_id: Optional[str] = None


# ============================================================
# Document Response
# ============================================================

class DocumentResponse(BaseModel):
    document_id: str
    message: str


# ============================================================
# Document List
# ============================================================

class DocumentListItem(BaseModel):
    id: str
    filename: str
    status: str
    created_at: str
    chunk_count: int = 0
    total_pages: int = 0
    processed_pages: int = 0


class DocumentList(BaseModel):
    documents: List[DocumentListItem]


# ============================================================
# Dropdown
# ============================================================

class DropdownItem(BaseModel):
    id: str
    filename: str


class DropdownList(BaseModel):
    items: List[DropdownItem]


# ============================================================
# Chat
# ============================================================

class ChatRequest(BaseModel):
    session_id: str
    question: str


# ============================================================
# Document Delete / Edit
# ============================================================

class DocumentDeleteRequest(BaseModel):
    document_id: str


class DocumentEditRequest(BaseModel):
    document_id: str
    filename: Optional[str] = None


# ============================================================
# Document Metadata
# ============================================================

class DocumentMetadata(BaseModel):
    filename: str
    created_at: datetime
    status: str
    chunk_count: int = 0
    error: Optional[str] = None
    total_pages: int = 0
    processed_pages: int = 0


# ============================================================
# Document Status Constants
# ============================================================

class DocumentStatus:
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================
# Session Models
# ============================================================

class SessionCreate(BaseModel):
    session_id: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    message: str


# ============================================================
# Session Document
# ============================================================

class SessionDocument(BaseModel):
    id: str
    filename: str
    status: str
    created_at: str
    chunk_count: int = 0
    total_pages: int = 0
    processed_pages: int = 0
    error: Optional[str] = None


# ============================================================
# Session Status
# ============================================================

class SessionStatus(BaseModel):
    id: str
    created_at: str
    last_active: str
    document_count: int
    documents: List[SessionDocument]


# ============================================================
# Session List
# ============================================================

class SessionList(BaseModel):
    sessions: List[Dict[str, Any]]
