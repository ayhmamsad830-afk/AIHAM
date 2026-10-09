import logging
import os
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from app.models.documents import (
    DocumentDeleteRequest,
    DocumentEditRequest,
    DocumentList,
    DocumentResponse,
    DocumentStatus,
    DropdownList,
    SessionStatus,
)
from app.services.document_service import DocumentService
from app.utils.helpers import generate_id


# Set up logging
logger = logging.getLogger(__name__)


class DocumentRouter:
    def __init__(self, document_service: DocumentService):
        self.router = APIRouter(tags=["documents"])
        self.document_service = document_service

        # Register route handlers
        self._register_routes()

    def _register_routes(self):

        # ============================================================
        # Upload document
        # ============================================================
        @self.router.post(
            "/api/documents/upload",
            response_model=DocumentResponse
        )
        async def upload_document(
            background_tasks: BackgroundTasks,
            file: UploadFile = File(...),
            filename: str = Form(None),
            session_id: str = Form(...)
        ):
            """Upload a document and start background processing."""

            supported_extensions = [
                ".pdf",
                ".png",
                ".jpg",
                ".jpeg",
                ".tiff",
                ".bmp",
                ".gif",
            ]

            if not file.filename:
                raise HTTPException(
                    status_code=400,
                    detail="No filename provided"
                )

            file_ext = os.path.splitext(file.filename.lower())[1]

            if file_ext not in supported_extensions:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Unsupported file type. Supported types: "
                        + ", ".join(supported_extensions)
                    ),
                )

            # Generate document ID
            document_id = generate_id()

            # Use original filename if no custom filename was provided
            if not filename:
                filename = file.filename

            try:
                # Register document and get destination path
                pdf_path = await self.document_service.add_document(
                    document_id,
                    filename,
                    session_id
                )

                # Save uploaded file
                success = await self.document_service.save_uploaded_file(
                    file,
                    pdf_path
                )

                if not success:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to save uploaded file"
                    )

                # Process document in background
                background_tasks.add_task(
                    self.document_service.process_document_task,
                    document_id=document_id,
                    pdf_path=pdf_path,
                    session_id=session_id
                )

                return DocumentResponse(
                    document_id=document_id,
                    message=(
                        "Document uploaded successfully "
                        "and is being processed"
                    )
                )

            except HTTPException:
                raise

            except Exception as e:
                logger.exception(
                    f"Error uploading document: {e}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Error uploading document: {str(e)}"
                )

        # ============================================================
        # Get all documents
        # ============================================================
        @self.router.get(
            "/api/documents",
            response_model=DocumentList
        )
        async def get_documents():
            """Get all documents."""
            try:
                documents = await self.document_service.get_all_documents()

                return DocumentList(
                    documents=documents
                )

            except Exception as e:
                logger.exception(
                    f"Error getting documents: {e}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Error getting documents: {str(e)}"
                )

        # ============================================================
        # Get dropdown items
        # ============================================================
        @self.router.get(
            "/api/documents/dropdown",
            response_model=DropdownList
        )
        async def get_dropdown_items():
            """Get document items for dropdown."""
            try:
                items = self.document_service.get_dropdown_items()

                return DropdownList(
                    items=items
                )

            except Exception as e:
                logger.exception(
                    f"Error getting dropdown items: {e}"
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Error getting dropdown items: {str(e)}"
                )

        # ============================================================
        # Get document status
        # ============================================================
        @self.router.get(
            "/api/documents/{document_id}/status"
        )
        async def get_document_status(document_id: str):
            """Get document processing status."""

            try:
                status = self.document_service.get_document_status(
                    document_id
                )

                if not status:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Document {document_id} not found"
                    )

                # Ensure a safe serializable dictionary
                safe_status = {}

                for key, value in status.items():

                    if isinstance(
                        value,
                        (
                            str,
                            int,
                            float,
                            bool,
                            type(None),
                            list,
                            dict,
                        )
                    ):
                        safe_status[key] = value
                    else:
                        safe_status[key] = str(value)

                return safe_status

            except HTTPException:
                raise

            except Exception as e:
                logger.exception(
                    f"Error retrieving document status: {e}"
                )

                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Error retrieving document status: "
                        "The document metadata may be corrupted"
                    )
                )

        # ============================================================
        # Delete document
        # ============================================================
        @self.router.delete(
            "/api/documents/{document_id}"
        )
        async def delete_document(document_id: str):
            """Delete a document and its embeddings."""

            try:
                success = await self.document_service.delete_document(
                    document_id
                )

                if not success:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            f"Document {document_id} not found "
                            "or couldn't be deleted"
                        )
                    )

                return {
                    "message": (
                        f"Document {document_id} "
                        "deleted successfully"
                    )
                }

            except HTTPException:
                raise

            except Exception as e:
                logger.exception(
                    f"Error deleting document: {e}"
                )

                raise HTTPException(
                    status_code=500,
                    detail=f"Error deleting document: {str(e)}"
                )

        # ============================================================
        # Create session
        # ============================================================
        @self.router.post(
            "/api/sessions/create"
        )
        async def create_session():
            """Create a new chat session."""

            try:
                session_id = self.document_service.create_session()

                return {
                    "session_id": session_id,
                    "message": "Session created successfully"
                }

            except Exception as e:
                logger.exception(
                    f"Error creating session: {e}"
                )

                raise HTTPException(
                    status_code=500,
                    detail=f"Error creating session: {str(e)}"
                )

        # ============================================================
        # Get session information
        # ============================================================
        @self.router.get(
            "/api/sessions/{session_id}"
        )
        async def get_session(session_id: str):
            """Get session information."""

            try:
                session_status = (
                    self.document_service.get_session_status(
                        session_id
                    )
                )

                if not session_status:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Session {session_id} not found"
                    )

                return session_status

            except HTTPException:
                raise

            except Exception as e:
                logger.exception(
                    f"Error getting session {session_id}: {e}"
                )

                raise HTTPException(
                    status_code=500,
                    detail=f"Error getting session: {str(e)}"
                )

        # ============================================================
        # Get documents for a specific session
        # ============================================================
        @self.router.get(
            "/api/sessions/{session_id}/documents"
        )
        async def get_session_documents(session_id: str):
            """Get documents for a specific session."""

            try:
                session_status = (
                    self.document_service.get_session_status(
                        session_id
                    )
                )

                if not session_status:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Session {session_id} not found"
                    )

                return {
                    "documents": session_status.get(
                        "documents",
                        []
                    )
                }

            except HTTPException:
                raise

            except Exception as e:
                logger.exception(
                    f"Error getting session documents "
                    f"for {session_id}: {e}"
                )

                raise HTTPException(
                    status_code=500,
                    detail="Error getting session documents"
                )