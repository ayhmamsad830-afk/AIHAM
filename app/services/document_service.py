import os
import logging
import shutil
from typing import Optional, Dict, List
from fastapi import UploadFile
from app.core.document_store import DocumentStore
from app.models.documents import DocumentStatus, DropdownItem
from app.utils.helpers import generate_id

# Set up logging
logger = logging.getLogger(__name__)

class DocumentService:
    def __init__(self, document_store: DocumentStore):
        self.document_store = document_store
    
    async def add_document(self, document_id: str, filename: str, session_id: Optional[str] = None) -> str:
        """Register a new document in the store and return the file path where it should be saved."""
        return await self.document_store.add_document(document_id, filename, session_id)
    
    async def save_uploaded_file(self, file: UploadFile, file_path: str) -> bool:
        """Save an uploaded PDF file to the specified path."""
        logger.info(f"Saving uploaded file to {file_path}")
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save file
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
                
            return True
        except Exception as e:
            logger.error(f"Error saving uploaded file: {str(e)}")
            return False
    
    async def process_document_task(self, document_id: str, pdf_path: str, session_id: Optional[str] = None) -> None:
        """Process a document for RAG."""
        logger.info(f"Starting processing for document {document_id} in session {session_id}")
        try:
            # Process the uploaded document
            await self.document_store.process_document(document_id, pdf_path, session_id)
            logger.info(f"Successfully processed document {document_id}")
                
        except Exception as e:
            logger.error(f"Error during document processing: {str(e)}")
            # Update document status to failed
            doc_status = self.document_store.get_document_status(document_id)
            if doc_status:
                doc_status['status'] = DocumentStatus.FAILED
                doc_status['error'] = str(e)
                self.document_store._save_storage()
    
    def get_document_status(self, document_id: str) -> Optional[Dict]:
        """Get document processing status safely."""
        status = self.document_store.get_document_status(document_id)
        
        # Ensure we return a valid dict even if the status is corrupted
        if status is None:
            return None
        
        # Ensure we have the minimum required fields
        if 'status' not in status:
            status['status'] = 'unknown'
        
        # Make sure we have a filename
        if 'filename' not in status:
            status['filename'] = f"Document-{document_id[:8]}"
        
        return status
    
    async def get_all_documents(self) -> List[Dict]:
        """Get all documents for listing."""
        return self.document_store.get_all_documents()
    
    async def search_document(self, query: str, k: int = 4, session_id: Optional[str] = None, document_ids: Optional[List[str]] = None) -> List[str]:
        """Search for relevant chunks in documents."""
        return await self.document_store.search(query, k, session_id, document_ids)
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its embeddings."""
        return await self.document_store.delete_document(document_id)
    
    def get_dropdown_items(self) -> List[Dict]:
        """Get all documents for dropdown menu."""
        return self.document_store.get_dropdown_items()
    
    # Session-related methods
    def create_session(self, session_id: Optional[str] = None) -> str:
        """Create a new chat session."""
        if not session_id:
            session_id = generate_id()
            
        # Create the session in document store
        self.document_store.create_session(session_id)
        
        return session_id
    
    def get_session_status(self, session_id: str) -> Optional[Dict]:
        """Get status information about a session."""
        return self.document_store.get_session_status(session_id)
    
    def get_session_documents(self, session_id: str) -> List[str]:
        """Get the list of document IDs in a session."""
        return self.document_store.get_session_documents(session_id)