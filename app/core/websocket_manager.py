import asyncio
import json
import logging
from typing import Dict
from fastapi import WebSocket

# Set up logging
logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        # Format: {session_id: {client_id: websocket}}
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        self.heartbeat_task = None
    
    def register_connection(self, session_id: str, client_id: str, websocket: WebSocket) -> None:
        """Register a new WebSocket connection."""
        if session_id not in self.active_connections:
            self.active_connections[session_id] = {}
            
        self.active_connections[session_id][client_id] = websocket
        logger.info(f"Registered connection for session {session_id}, client {client_id}")
    
    def unregister_connection(self, session_id: str, client_id: str) -> None:
        """Unregister a WebSocket connection."""
        if (session_id in self.active_connections and 
            client_id in self.active_connections[session_id]):
            
            del self.active_connections[session_id][client_id]
            logger.info(f"Unregistered connection for session {session_id}, client {client_id}")
            
            # Clean up empty dictionaries
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
                logger.info(f"Removed empty session entry {session_id}")
    
    async def start_heartbeat(self) -> None:
        """Start the heartbeat task."""
        self.heartbeat_task = asyncio.create_task(self.websocket_heartbeat())
    
    async def websocket_heartbeat(self) -> None:
        """Send periodic heartbeats to keep WebSocket connections alive."""
        while True:
            await asyncio.sleep(15)  # Send heartbeat every 15 seconds instead of 30
            
            # Copy the dictionary keys to avoid modification during iteration
            session_ids = list(self.active_connections.keys())
            
            for session_id in session_ids:
                if session_id in self.active_connections:
                    client_ids = list(self.active_connections[session_id].keys())
                    
                    for client_id in client_ids:
                        try:
                            if client_id in self.active_connections.get(session_id, {}):
                                websocket = self.active_connections[session_id][client_id]
                                await websocket.send_text(json.dumps({
                                    "status": "heartbeat"
                                }))
                        except Exception as e:
                            logger.error(f"Error sending heartbeat: {str(e)}")
                            # Remove failed connection
                            self.unregister_connection(session_id, client_id)
    
    async def broadcast_to_session(self, session_id: str, message: Dict) -> None:
        """Broadcast a message to all clients in a session."""
        if session_id not in self.active_connections:
            return
            
        for client_id, websocket in self.active_connections[session_id].items():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error broadcasting to client {client_id}: {str(e)}")
                # Don't unregister here, let the heartbeat do the cleanup
                
    async def safe_send(self, session_id: str, client_id: str, message: str) -> bool:
        """Safely send a message to a websocket, handling errors."""
        try:
            if (session_id in self.active_connections and 
                client_id in self.active_connections[session_id]):
                
                websocket = self.active_connections[session_id][client_id]
                await websocket.send_text(message)
                return True
            return False
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False