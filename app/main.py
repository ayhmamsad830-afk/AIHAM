from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from app.api.routes.chat_routes import ChatRouter
from app.api.routes.document_routes import DocumentRouter
from app.config import config
from app.core.document_store import DocumentStore
from app.core.sage_x3_mode_selector import SageX3ChatService
from app.core.websocket_manager import WebSocketManager
from app.services.document_service import DocumentService
from app.models.llm import LLMModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging

# Set up logging
logger = logging.getLogger(__name__)

def create_app():
    app = FastAPI(
        title="Sage X3 RAG Expert System",
        description="Retrieval-Augmented Generation system for Sage X3 documentation",
        version="1.0.0"
    )
    
    # Initialize components
    document_store = DocumentStore(config.DATA_DIR)
    websocket_manager = WebSocketManager()
    llm_model = LLMModel()
    
    # Initialize services
    document_service = DocumentService(document_store)
    chat_service = SageX3ChatService(document_store, llm_model, websocket_manager)
    
    # Initialize routers
    document_router = DocumentRouter(document_service)
    chat_router = ChatRouter(websocket_manager, chat_service)
    
    # Register routers
    app.include_router(document_router.router)
    app.include_router(chat_router.router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Serve static files
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

    @app.get("/")
    async def get_main_page():
        return FileResponse("static/index.html")
    
    # Startup events
    @app.on_event("startup")
    async def startup_event():
        # Start WebSocket heartbeat
        await websocket_manager.start_heartbeat()
        
        # Preload model if configured
        if config.PRELOAD_MODEL:
            logger.info("Preloading language model at startup...")
            try:
                await chat_service.ensure_model_loaded()
                logger.info("Model preloaded successfully")
            except Exception as e:
                logger.error(f"Error preloading model: {str(e)}")
    
    return app