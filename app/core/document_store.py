import logging
import pickle
import numpy as np
import faiss
import torch
import os
import lzma
import time
import hashlib
import pdfplumber
import asyncio
from pathlib import Path
from functools import lru_cache
from datetime import datetime
from typing import Dict, Optional, List, Tuple, Union, Any, Set
from cachetools import TTLCache
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document as LangchainDocument
from app.models.documents import DocumentStatus, DocumentMetadata
from app.config import config

# Set up logging
logger = logging.getLogger(__name__)

class DocumentStore:
    def __init__(self, base_path: str):
        logger.info(f"Initializing DocumentStore with base path: {base_path}")
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Create cache directory
        self.cache_dir = Path(config.CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # PDF storage paths
        self.pdf_dir = self.base_path / "pdfs"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        
        # FAISS paths
        self.index_path = self.base_path / "faiss_index"
        self.metadata_path = self.base_path / "metadata.pickle"
        
        # Initialize embedding cache
        self.embedding_cache = TTLCache(
            maxsize=config.EMBEDDINGS_CACHE_SIZE,
            ttl=3600  # Cache embeddings for 1 hour
        )
        
        # Initialize embeddings model
        self.embeddings = HuggingFaceEmbeddings(
            model_name=config.EMBEDDINGS_MODEL,
            model_kwargs={'device': "cuda" if torch.cuda.is_available() else "cpu"}
        )
        
        # Initialize or load FAISS index and metadata
        self._initialize_storage()
        
        # Create embedding batch lock
        self.embed_lock = asyncio.Lock()
        
        # New: Dictionary to track session documents
        self.session_documents = {}

    def _initialize_storage(self):
        logger.info("Initializing storage")
        try:
            if self.index_path.exists() and self.metadata_path.exists():
                logger.info("Loading existing index and metadata")
                self.index = faiss.read_index(str(self.index_path))
                with open(self.metadata_path, 'rb') as f:
                    self.metadata = pickle.load(f)
            else:
                logger.info("Creating new index and metadata")
                embedding_dim = len(self.embeddings.embed_query("test"))
                
                # Create FAISS index with quantization if enabled
                if config.FAISS_QUANTIZATION:
                    # Create a quantized index for better memory efficiency
                    quantizer = faiss.IndexFlatL2(embedding_dim)
                    self.index = faiss.IndexIVFPQ(quantizer, embedding_dim, 
                                                 min(128, max(1, self._estimate_pdf_count())), 
                                                 16, 8)
                    # Need to train empty index
                    dummy_vectors = np.random.random((256, embedding_dim)).astype(np.float32)
                    self.index.train(dummy_vectors)
                else:
                    self.index = faiss.IndexFlatL2(embedding_dim)
                
                self.metadata = {
                    'documents': {}, 
                    'id_mapping': {},
                    'dropdown_items': [],
                    'sessions': {},  # New: track chat sessions
                }
                self._save_storage()
        except Exception as e:
            logger.error(f"Error initializing storage: {str(e)}")
            raise
    
    def _estimate_pdf_count(self):
        """Estimate the number of PDFs to be processed for FAISS optimization."""
        return 100  # Default estimate, can be adjusted based on expected load
    
    @lru_cache(maxsize=128)
    def _get_text_hash(self, text: str) -> str:
        """Generate a hash for text to use as a cache key."""
        return hashlib.md5(text.encode()).hexdigest()
    
    def _compress_text(self, text: str) -> bytes:
        """Compress text using LZMA if compression is enabled."""
        if config.TEXT_COMPRESSION:
            return lzma.compress(text.encode('utf-8'))
        return text.encode('utf-8')
    
    def _decompress_text(self, data: Union[bytes, str]) -> str:
        """Decompress text that was compressed with LZMA."""
        if isinstance(data, str):
            return data
            
        try:
            return lzma.decompress(data).decode('utf-8')
        except lzma.LZMAError:
            # If decompression fails, assume it wasn't compressed
            return data.decode('utf-8', errors='replace')
    
    async def _cached_embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Cache embeddings to avoid redundant computation."""
        results = []
        texts_to_embed = []
        indices_to_update = []
        
        # First, check cache for existing embeddings
        for i, text in enumerate(texts):
            text_hash = self._get_text_hash(text)
            if text_hash in self.embedding_cache:
                results.append(self.embedding_cache[text_hash])
            else:
                texts_to_embed.append(text)
                indices_to_update.append(i)
        
        # Generate embeddings for texts not in cache
        if texts_to_embed:
            # Use async lock to prevent multiple embedding processes at once
            async with self.embed_lock:
                start_time = time.time()
                embeddings = self.embeddings.embed_documents(texts_to_embed)
                logger.info(f"Embedded {len(texts_to_embed)} texts in {time.time() - start_time:.2f}s")
                
                # Update cache with new embeddings
                for i, text in enumerate(texts_to_embed):
                    text_hash = self._get_text_hash(text)
                    self.embedding_cache[text_hash] = embeddings[i]
        
            # Insert new embeddings at correct positions
            for cache_idx, result_idx in enumerate(indices_to_update):
                while len(results) <= result_idx:
                    results.append(None)  # Pad if needed
                results[result_idx] = embeddings[cache_idx]
        
        return results
    
    def _extract_text_from_document(self, file_path: str) -> List[LangchainDocument]:
        """Extract text from document based on file type."""
        # Determine file type
        file_ext = os.path.splitext(file_path)[1].lower()
        
        documents = []
        
        if file_ext == '.pdf':
            # For PDFs, convert to images and use OCR
            documents = self._pdf_to_images_and_ocr(file_path)
        elif file_ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif']:
            # For images, use OCR directly
            documents = self._extract_text_from_image(file_path)
        else:
            # For unsupported file types, try as plain text
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                    documents.append(LangchainDocument(
                        page_content=text,
                        metadata={"page": 1, "source": file_path}
                    ))
            except Exception as e:
                logger.error(f"Could not extract text from file: {str(e)}")
                
        return documents
    
    def _extract_text_from_image(self, image_path: str) -> List[LangchainDocument]:
        """Extract text from image using OCR."""
        text = self._perform_ocr(image_path)
        if text:
            return [LangchainDocument(
                page_content=text,
                metadata={"page": 1, "source": image_path}
            )]
        return []
    
    def _get_pdf_page_count(self, pdf_path: str) -> int:
        """Get the number of pages in a PDF document."""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                return len(pdf.pages)
        except Exception as e:
            logger.error(f"Error getting page count: {str(e)}")
            return 0
    
    def _pdf_to_images_and_ocr(self, pdf_path: str) -> List[LangchainDocument]:
        """Convert PDF to images and extract text using OCR without poppler dependency."""
        documents = []
        try:
            # Use PyMuPDF (fitz) instead of pdf2image to avoid Poppler dependency
            import fitz  # PyMuPDF
            
            logger.info(f"Opening PDF with PyMuPDF: {pdf_path}")
            pdf_document = fitz.open(pdf_path)
            
            # Get total pages for progress tracking
            total_pages = len(pdf_document)
            document_id = os.path.basename(pdf_path).split('.')[0]
            
            # Initialize progress in metadata
            if document_id in self.metadata['documents']:
                self.metadata['documents'][document_id]['total_pages'] = total_pages
                self.metadata['documents'][document_id]['processed_pages'] = 0
                self._save_storage()
            
            for page_num in range(total_pages):
                # Get the page
                page = pdf_document[page_num]
                
                # Set a higher resolution for better OCR results
                zoom = 3.0  # zoom factor (higher = better resolution)
                mat = fitz.Matrix(zoom, zoom)
                
                # Get the pixmap (image) of the page
                pix = page.get_pixmap(matrix=mat)
                
                # Save the image temporarily
                img_path = f"{pdf_path}_page_{page_num + 1}.png"
                pix.save(img_path)
                
                logger.info(f"Saved page {page_num + 1} as image, now performing OCR")
                
                # Extract text using OCR
                text = self._perform_ocr(img_path)
                
                if text:
                    documents.append(LangchainDocument(
                        page_content=text,
                        metadata={"page": page_num + 1, "source": pdf_path}
                    ))
                else:
                    logger.warning(f"No text extracted from page {page_num + 1}")
                
                # Clean up
                try:
                    os.remove(img_path)
                except Exception as e:
                    logger.warning(f"Could not remove temporary image: {str(e)}")
                
                # Update progress
                if document_id in self.metadata['documents']:
                    self.metadata['documents'][document_id]['processed_pages'] = page_num + 1
                    self._save_storage()
            
            # Close the PDF document
            pdf_document.close()
                    
        except ImportError:
            logger.error("PyMuPDF (fitz) not installed. Try: pip install pymupdf")
        except Exception as e:
            logger.error(f"Error converting PDF to images: {str(e)}")
            
        return documents
    
    def _perform_ocr(self, image_path: str) -> str:
        """Extract text from image using EasyOCR with GPU if available."""
        try:
            import easyocr
            import numpy as np
            from PIL import Image
            
            # Check for GPU availability
            use_gpu = torch.cuda.is_available()
            reader = easyocr.Reader(['en'], gpu=use_gpu)
            img = Image.open(image_path)
            img_np = np.array(img)
            result = reader.readtext(img_np)
            text = " ".join([item[1] for item in result])
            
            logger.info(f"OCR extracted {len(text)} characters from image")
            return text
        except ImportError:
            logger.error("easyocr not installed")
            return ""
        except Exception as e:
            logger.error(f"Error performing OCR: {str(e)}")
            return ""
    
    async def process_document(self, document_id: str, file_path: str, session_id: Optional[str] = None) -> None:
        """Process a document: extract text, chunk, embed, and index."""
        logger.info(f"Processing document {document_id} for session {session_id}")
        
        try:
            # Check if it's a PDF and get page count for progress tracking
            if file_path.lower().endswith('.pdf'):
                total_pages = self._get_pdf_page_count(file_path)
                self.metadata['documents'][document_id].update({
                    'total_pages': total_pages,
                    'processed_pages': 0
                })
                self._save_storage()
            
            # Extract text from document
            documents = self._extract_text_from_document(file_path)
            
            if not documents:
                logger.warning(f"No content extracted from document {document_id}")
                self.metadata['documents'][document_id].update({
                    'status': DocumentStatus.COMPLETED,
                    'chunks': [],
                    'error': "No text could be extracted from this document"
                })
                
                # If this document belongs to a session, update session metadata
                if session_id:
                    self._add_document_to_session(session_id, document_id)
                
                self._save_storage()
                return
            
            # Split documents into chunks
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=config.SPLIT_CHUNK_SIZE,
                chunk_overlap=config.SPLIT_OVERLAP
            )
            chunks = text_splitter.split_documents(documents)
            logger.info(f"Split document into {len(chunks)} chunks")
            
            if len(chunks) == 0:
                logger.warning(f"No chunks created for document {document_id}")
                self.metadata['documents'][document_id].update({
                    'status': DocumentStatus.COMPLETED,
                    'chunks': [],
                    'error': "Document was processed but no text chunks could be created"
                })
                
                # If this document belongs to a session, update session metadata
                if session_id:
                    self._add_document_to_session(session_id, document_id)
                
                self._save_storage()
                return
            
            # Create embeddings for chunks
            chunk_texts = [chunk.page_content for chunk in chunks]
            embeddings = await self._cached_embed_texts(chunk_texts)
            
            # Add to FAISS index
            logger.info("Adding to FAISS index")
            start_idx = self.index.ntotal
            self.index.add(np.array(embeddings, dtype=np.float32))
            
            # Update metadata
            chunk_metadata = []
            for i, chunk in enumerate(chunks):
                faiss_id = start_idx + i
                self.metadata['id_mapping'][faiss_id] = (document_id, i)
                
                # Compress text if enabled
                compressed_text = self._compress_text(chunk.page_content)
                
                chunk_metadata.append({
                    'text': compressed_text,
                    'page': chunk.metadata.get('page', 0),
                    'compressed': config.TEXT_COMPRESSION
                })
            
            # Update document status
            self.metadata['documents'][document_id].update({
                'status': DocumentStatus.COMPLETED,
                'chunks': chunk_metadata,
                'chunk_count': len(chunks),
                'processed_pages': self.metadata['documents'][document_id].get('total_pages', 0)  # Mark as fully processed
            })
            
            # Make sure document is in dropdown list
            self._update_dropdown_list()
            
            # If this document belongs to a session, update session metadata
            if session_id:
                self._add_document_to_session(session_id, document_id)
            
            # Save changes
            self._save_storage()
            logger.info(f"Successfully processed document {document_id}")
            
        except Exception as e:
            logger.error(f"Error processing document: {str(e)}")
            self.metadata['documents'][document_id]['status'] = DocumentStatus.FAILED
            self.metadata['documents'][document_id]['error'] = str(e)
            self._save_storage()
            raise
    
    def _add_document_to_session(self, session_id: str, document_id: str) -> None:
        """Add a document to a session's document list."""
        if 'sessions' not in self.metadata:
            self.metadata['sessions'] = {}
            
        if session_id not in self.metadata['sessions']:
            self.metadata['sessions'][session_id] = {
                'documents': [],
                'created_at': datetime.utcnow().isoformat(),
                'last_active': datetime.utcnow().isoformat()
            }
        
        # Add document if not already in the session
        if document_id not in self.metadata['sessions'][session_id]['documents']:
            self.metadata['sessions'][session_id]['documents'].append(document_id)
        
        # Update last active time
        self.metadata['sessions'][session_id]['last_active'] = datetime.utcnow().isoformat()

    async def search(self, query: str, k: int = 4, session_id: Optional[str] = None, document_ids: Optional[List[str]] = None) -> List[str]:
        """
        Search for relevant chunks across all documents in a session or specific documents.
        
        Args:
            query: The search query
            k: Number of results to return
            session_id: Optional session ID to restrict search to documents in that session
            document_ids: Optional list of document IDs to restrict search to
            
        Returns:
            List of relevant text chunks
        """
        # Determine which documents to search in
        target_document_ids = set()
        
        if session_id and session_id in self.metadata.get('sessions', {}):
            # Get documents from session
            target_document_ids.update(self.metadata['sessions'][session_id]['documents'])
        
        # If specific document IDs were provided, use those instead
        if document_ids:
            target_document_ids.update(document_ids)
            
        # If no documents specified, return empty results
        if not target_document_ids:
            logger.warning(f"No documents found for search in session {session_id}")
            return []
            
        # Create query embedding
        query_embedding = self.embeddings.embed_query(query)
        
        # Search in FAISS
        D, I = self.index.search(np.array([query_embedding], dtype=np.float32), k * 3)  # Get more results than needed
        
        # Filter results for target documents
        relevant_chunks = []
        used_doc_ids = set()  # Track which documents were actually used
        
        for idx in I[0]:
            if idx != -1:  # Valid FAISS id
                if idx in self.metadata['id_mapping']:
                    doc_id, chunk_id = self.metadata['id_mapping'][int(idx)]
                    
                    # Only include chunks from specified documents
                    if doc_id in target_document_ids:
                        used_doc_ids.add(doc_id)
                        
                        # Ensure chunk_id is within valid range
                        chunks = self.metadata['documents'][doc_id]['chunks']
                        if 0 <= chunk_id < len(chunks):
                            chunk = chunks[chunk_id]
                            # Decompress text if needed
                            text = self._decompress_text(chunk['text'])
                            relevant_chunks.append(text)
                            if len(relevant_chunks) == k:
                                break
                        else:
                            logger.warning(f"Invalid chunk_id {chunk_id} for document {doc_id}")
                else:
                    logger.warning(f"FAISS ID {idx} not found in id_mapping")
        
        # Log which documents were used in the results
        logger.info(f"Search used documents: {list(used_doc_ids)}")
                        
        return relevant_chunks
    
    def get_session_documents(self, session_id: str) -> List[str]:
        """Get the list of document IDs in a session."""
        if session_id in self.metadata.get('sessions', {}):
            return self.metadata['sessions'][session_id]['documents']
        return []
    
    def create_session(self, session_id: str) -> bool:
        """Create a new chat session."""
        if 'sessions' not in self.metadata:
            self.metadata['sessions'] = {}
            
        if session_id in self.metadata['sessions']:
            logger.warning(f"Session {session_id} already exists")
            return False
            
        self.metadata['sessions'][session_id] = {
            'documents': [],
            'created_at': datetime.utcnow().isoformat(),
            'last_active': datetime.utcnow().isoformat()
        }
        
        self._save_storage()
        return True
    
    def get_session_status(self, session_id: str) -> Optional[Dict]:
        """Get status information about a session."""
        if session_id not in self.metadata.get('sessions', {}):
            return None
            
        session_data = self.metadata['sessions'][session_id]
        
        # Get information about each document in the session
        documents = []
        for doc_id in session_data['documents']:
            if doc_id in self.metadata['documents']:
                doc = self.metadata['documents'][doc_id]
                documents.append({
                    'id': doc_id,
                    'filename': doc.get('filename', 'Unknown'),
                    'status': doc.get('status', DocumentStatus.PROCESSING),
                    'created_at': doc.get('created_at', ''),
                    'chunk_count': doc.get('chunk_count', 0),
                    'error': doc.get('error', None),
                    'total_pages': doc.get('total_pages', 0),
                    'processed_pages': doc.get('processed_pages', 0)
                })
        
        return {
            'id': session_id,
            'created_at': session_data['created_at'],
            'last_active': session_data['last_active'],
            'document_count': len(session_data['documents']),
            'documents': documents
        }

    def get_document_status(self, document_id: str) -> Optional[Dict]:
        """Get document processing status, handling binary data correctly."""
        if document_id not in self.metadata['documents']:
            return None
            
        # Get the original document metadata
        doc_data = self.metadata['documents'][document_id]
        
        # Create a safe copy without binary data
        safe_data = {}
        
        # Copy safe values and handle binary data
        for key, value in doc_data.items():
            if key == 'chunks':
                # Skip the chunks array entirely - just store the count
                safe_data['chunk_count'] = len(value) if value else 0
                continue
                
            if isinstance(value, bytes):
                # Skip binary data
                continue
                
            if isinstance(value, (str, int, float, bool, type(None))):
                # Safe primitive types
                safe_data[key] = value
            else:
                # Convert other types to string
                try:
                    safe_data[key] = str(value)
                except:
                    # Skip values that can't be converted
                    continue
        
        return safe_data
        
    def get_all_documents(self) -> List[Dict]:
        """Get all documents for dropdown listing."""
        docs = []
        for doc_id, doc in self.metadata['documents'].items():
            docs.append({
                'id': doc_id,
                'filename': doc.get('filename', 'Unknown'),
                'status': doc.get('status', DocumentStatus.PROCESSING),
                'created_at': doc.get('created_at', datetime.utcnow().isoformat()),
                'chunk_count': doc.get('chunk_count', 0),
                'total_pages': doc.get('total_pages', 0),
                'processed_pages': doc.get('processed_pages', 0)
            })
        return docs
    
    def _update_dropdown_list(self):
        """Update the dropdown list based on current documents."""
        dropdown_items = []
        for doc_id, doc in self.metadata['documents'].items():
            if doc.get('status') == DocumentStatus.COMPLETED:
                dropdown_items.append({
                    'id': doc_id,
                    'filename': doc.get('filename', 'Unknown'),
                })
        
        self.metadata['dropdown_items'] = sorted(
            dropdown_items, 
            key=lambda x: x.get('filename', '')
        )

    def _save_storage(self):
        """Save FAISS index and metadata to disk."""
        logger.info("Saving storage")
        try:
            faiss.write_index(self.index, str(self.index_path))
            with open(self.metadata_path, 'wb') as f:
                pickle.dump(self.metadata, f)
        except Exception as e:
            logger.error(f"Error saving storage: {str(e)}")
            raise

    async def add_document(self, document_id: str, filename: str, session_id: Optional[str] = None) -> str:
        """Register a new document in the store."""
        logger.info(f"Adding document {document_id} with filename {filename} for session {session_id}")
        
        # Create PDF file path
        pdf_path = str(self.pdf_dir / f"{document_id}.pdf")
        
        # Add document to metadata
        self.metadata['documents'][document_id] = {
            'status': DocumentStatus.PROCESSING,
            'filename': filename,
            'created_at': datetime.utcnow().isoformat(),
            'file_path': pdf_path,
            'chunks': [],
            'total_pages': 0,
            'processed_pages': 0
        }
        
        # If session_id is provided, add document to that session
        if session_id:
            self._add_document_to_session(session_id, document_id)
        
        self._save_storage()
        return pdf_path
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its embeddings."""
        logger.info(f"Deleting document {document_id}")
        
        if document_id not in self.metadata['documents']:
            logger.warning(f"Document {document_id} not found for deletion")
            return False
        
        try:
            # Get document info
            doc_info = self.metadata['documents'][document_id]
            
            # Remove file if it exists
            if 'file_path' in doc_info:
                file_path = Path(doc_info['file_path'])
                if file_path.exists():
                    file_path.unlink()
            
            # Get all chunk IDs for this document
            chunk_ids_to_remove = []
            for faiss_id, (doc_id, _) in self.metadata['id_mapping'].items():
                if doc_id == document_id:
                    chunk_ids_to_remove.append(faiss_id)
            
            # If any chunks need to be removed, we need to recreate the index
            if chunk_ids_to_remove:
                # TODO: Implement more efficient removal without rebuilding the entire index
                # For now, rebuild the entire index (slower but safer)
                await self._rebuild_index_without_document(document_id)
            
            # Remove from metadata
            del self.metadata['documents'][document_id]
            
            # Remove from any sessions that include this document
            for session_id, session_data in self.metadata.get('sessions', {}).items():
                if document_id in session_data['documents']:
                    session_data['documents'].remove(document_id)
            
            # Update dropdown list
            self._update_dropdown_list()
            
            # Save changes
            self._save_storage()
            
            return True
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {str(e)}")
            return False
    
    async def _rebuild_index_without_document(self, document_id: str) -> None:
        """Rebuild the FAISS index excluding a specific document."""
        logger.info(f"Rebuilding index without document {document_id}")
        
        # Create a new index with the same parameters
        embedding_dim = self.index.d
        
        if isinstance(self.index, faiss.IndexIVFPQ):
            # For quantized index
            quantizer = faiss.IndexFlatL2(embedding_dim)
            new_index = faiss.IndexIVFPQ(
                quantizer, embedding_dim, 
                self.index.nlist, 
                self.index.pq.M, 
                self.index.pq.nbits
            )
            new_index.train(np.random.random((256, embedding_dim)).astype(np.float32))
        else:
            # For flat index
            new_index = faiss.IndexFlatL2(embedding_dim)
        
        # Create new id mapping
        new_id_mapping = {}
        vectors_to_add = []
        
        # Collect all vectors to keep
        for faiss_id, (doc_id, chunk_id) in self.metadata['id_mapping'].items():
            if doc_id != document_id:
                if faiss_id < self.index.ntotal:
                    vector = np.zeros((1, embedding_dim), dtype=np.float32)
                    self.index.reconstruct(int(faiss_id), vector[0])
                    vectors_to_add.append((vector, doc_id, chunk_id))
        
        # Add vectors to new index
        if vectors_to_add:
            # Combine all vectors
            all_vectors = np.vstack([v[0] for v in vectors_to_add])
            new_index.add(all_vectors)
            
            # Update id mapping
            for i, (_, doc_id, chunk_id) in enumerate(vectors_to_add):
                new_id_mapping[i] = (doc_id, chunk_id)
        
        # Replace old index and mapping
        self.index = new_index
        self.metadata['id_mapping'] = new_id_mapping
    
    def get_dropdown_items(self) -> List[Dict]:
        """Get the list of items to display in dropdown."""
        return self.metadata.get('dropdown_items', [])