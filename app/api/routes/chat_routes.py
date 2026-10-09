import asyncio
import logging
from typing import Dict, List
from app.config import config
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from app.core.sage_x3_mode_selector import SageX3ChatService
from app.core.websocket_manager import WebSocketManager

# Set up logging
logger = logging.getLogger(__name__)

class ChatRouter:
    def __init__(self, websocket_manager: WebSocketManager, chat_service: SageX3ChatService):
        self.router = APIRouter(tags=["chat"])
        self.websocket_manager = websocket_manager
        self.chat_service = chat_service
        
        # Register route handlers
        self._register_routes()
        
        # Chat history storage
        # Format: {session_id: {client_id: [chat history]}}
        self.chat_histories: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
    
    def _register_routes(self):
        @self.router.websocket("/api/chat/{session_id}")
        async def chat_websocket(websocket: WebSocket, session_id: str):
            # Accept the websocket connection
            await websocket.accept()
            
            client_id = None
            
            try:
                # Receive initial connection message with client_id
                first_message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30  # 30 second timeout for initial connection
                )
                
                # Parse connection message
                import json
                try:
                    data = json.loads(first_message)
                    
                    # Extract client_id, reject if not provided
                    client_id = data.get("client_id")
                    if not client_id:
                        await websocket.send_text(json.dumps({
                            "status": "error", 
                            "error": "Client ID is required for connection"
                        }))
                        await websocket.close()
                        return
                        
                    # Register the connection
                    self.websocket_manager.register_connection(session_id, client_id, websocket)
                    
                    # Check if model is loaded before proceeding
                    if not self.chat_service.is_model_loaded():
                        # Send model loading message
                        await websocket.send_text(json.dumps({
                            "status": "loading",
                            "message": "Loading language model. Please wait..."
                        }))
                        
                        # Load the model with a timeout
                        try:
                            await asyncio.wait_for(
                                self.chat_service.ensure_model_loaded(),
                                timeout=60  # 60 second timeout for model loading
                            )
                        except asyncio.TimeoutError:
                            await websocket.send_text(json.dumps({
                                "status": "error", 
                                "error": "Model loading timed out. Please try again later."
                            }))
                            await websocket.close()
                            return
                    
                    # Initialize chat history if not exists
                    if session_id not in self.chat_histories:
                        self.chat_histories[session_id] = {}
                        
                    if client_id not in self.chat_histories[session_id]:
                        self.chat_histories[session_id][client_id] = []
                    
                    # Send initial confirmation
                    await websocket.send_text(json.dumps({
                        "status": "connected",
                        "client_id": client_id,
                        "session_id": session_id
                    }))
                    
                    # Process messages
                    while True:
                        # Receive message with a timeout
                        message = await asyncio.wait_for(
                            websocket.receive_text(),
                            timeout=config.WEBSOCKET_TIMEOUT  # Configurable timeout
                        )
                        
                        # Parse message (assumes JSON format)
                        try:
                            data = json.loads(message)
                            if 'question' in data:
                                question = data['question']
                                
                                # Get chat history for this session
                                chat_history = self.chat_histories[session_id][client_id]
                                
                                # Set up task for processing message with timeout
                                processing_task = asyncio.create_task(
                                    self.chat_service.process_chat_message(
                                        session_id=session_id,
                                        client_id=client_id,
                                        question=question,
                                        websocket=websocket,
                                        chat_history=chat_history
                                    )
                                )
                                
                                # Wait for the processing to complete with a long timeout
                                try:
                                    await asyncio.wait_for(
                                        processing_task,
                                        timeout=config.MODEL_TIMEOUT * 2  # Double the model timeout
                                    )
                                except asyncio.TimeoutError:
                                    logger.error(f"Message processing timed out for client {client_id}")
                                    # Don't try to send a timeout message - the connection might be closed
                                    # Just continue to receive the next message
                                    
                            else:
                                await websocket.send_text(json.dumps({
                                    "status": "error", 
                                    "error": "Invalid message format"
                                }))
                        except json.JSONDecodeError:
                            await websocket.send_text(json.dumps({
                                "status": "error", 
                                "error": "Invalid JSON"
                            }))
                        except Exception as e:
                            logger.error(f"Error processing message: {str(e)}")
                            try:
                                await websocket.send_text(json.dumps({
                                    "status": "error", 
                                    "error": str(e)
                                }))
                            except:
                                # Connection might be closed, just continue
                                pass
                                
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({
                        "status": "error", 
                        "error": "Invalid initial connection format"
                    }))
                    await websocket.close()
                    return
                    
            except asyncio.TimeoutError:
                logger.error("WebSocket timed out waiting for initial message")
                try:
                    await websocket.send_text(json.dumps({
                        "status": "error",
                        "error": "Connection timed out waiting for initial message"
                    }))
                    await websocket.close()
                except:
                    pass
                    
            except WebSocketDisconnect:
                # Handle disconnect - only log if we have client info
                if client_id:
                    logger.info(f"WebSocket disconnected for client {client_id}")
                    self.websocket_manager.unregister_connection(session_id, client_id)
                else:
                    logger.info(f"WebSocket disconnected before establishing client session")
                
            except Exception as e:
                logger.error(f"Error in WebSocket: {str(e)}")
                try:
                    await websocket.send_text(json.dumps({
                        "status": "error", 
                        "error": str(e)
                    }))
                    await websocket.close()
                except:
                    pass
                
                # Only unregister if we have client info
                if client_id:
                    self.websocket_manager.unregister_connection(session_id, client_id)
                    
            finally:
                # Ensure connection is unregistered
                if client_id:
                    self.websocket_manager.unregister_connection(session_id, client_id)

        @self.router.post("/api/preload-model")
        async def preload_model():
            """Endpoint to preload the LLM model to reduce latency on first chat."""
            try:
                # Ensure model is loaded
                await self.chat_service.ensure_model_loaded()
                return {"status": "success", "message": "Model loaded successfully"}
            except Exception as e:
                logger.error(f"Error preloading model: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error preloading model: {str(e)}")
                
        @self.router.post("/api/sessions/create")
        async def create_session():
            """Create a new chat session"""
            from app.utils.helpers import generate_id
            
            try:
                # Generate a session ID
                session_id = generate_id()
                
                # Initialize chat history for this session
                self.chat_histories[session_id] = {}
                
                return {
                    "status": "success", 
                    "session_id": session_id,
                    "message": "Chat session created successfully"
                }
            except Exception as e:
                logger.error(f"Error creating session: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error creating session: {str(e)}")
                
        @self.router.get("/api/sessions/{session_id}/status")
        async def get_session_status(session_id: str):
            """Get session status including documents"""
            try:
                # Check if the session exists in chat history
                if session_id not in self.chat_histories:
                    # Try to initialize it
                    self.chat_histories[session_id] = {}
                
                # Get session status from document service
                session_status = self.chat_service.document_store.get_session_status(session_id)
                
                if not session_status:
                    # Create a new session if it doesn't exist
                    self.chat_service.document_store.create_session(session_id)
                    session_status = self.chat_service.document_store.get_session_status(session_id)
                    
                if not session_status:
                    raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
                    
                return session_status
                
            except Exception as e:
                logger.error(f"Error getting session status: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error getting session status: {str(e)}")