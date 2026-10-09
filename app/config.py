import os
from typing import Optional

class Config:
    # Server configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8900"))
    WORKERS: int = int(os.getenv("WORKERS", "2"))
    
    # Storage paths
    DATA_DIR: str = os.getenv("DATA_DIR", "./data")
    CACHE_DIR: str = os.getenv("CACHE_DIR", "./cache")
    
    # Document processing
    SPLIT_CHUNK_SIZE: int = int(os.getenv("SPLIT_CHUNK_SIZE", "1000"))
    SPLIT_OVERLAP: int = int(os.getenv("SPLIT_OVERLAP", "200"))
    
    # LLM configuration
    MODEL_NAME: str = os.getenv("MODEL_NAME", "gemma3:12b")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.1"))
    PRELOAD_MODEL: bool = os.getenv("PRELOAD_MODEL", "true").lower() == "true"
    
    # Embeddings configuration
    EMBEDDINGS_MODEL: str = os.getenv("EMBEDDINGS_MODEL", "hkunlp/instructor-xl")
    EMBEDDINGS_CACHE_SIZE: int = int(os.getenv("EMBEDDINGS_CACHE_SIZE", "10000"))
    
    # RAG configuration
    SIMILAR_DOCS_COUNT: int = int(os.getenv("SIMILAR_DOCS_COUNT", "4"))
    
    # FAISS optimization
    FAISS_QUANTIZATION: bool = os.getenv("FAISS_QUANTIZATION", "true").lower() == "true"
    
    # Document compression
    TEXT_COMPRESSION: bool = os.getenv("TEXT_COMPRESSION", "true").lower() == "true"
    
    # Sage X3 configuration
    SAGE_X3_MODE: str = os.getenv("SAGE_X3_MODE", "expert")
    
    # Client session configuration
    CLIENT_SESSION_TIMEOUT: int = int(os.getenv("CLIENT_SESSION_TIMEOUT", "360000"))  

    WEBSOCKET_TIMEOUT: int = int(os.getenv("WEBSOCKET_TIMEOUT", "1200"))  
    MODEL_TIMEOUT: int = int(os.getenv("MODEL_TIMEOUT", "1200"))
    
config = Config()