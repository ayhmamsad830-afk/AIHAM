import json
import logging
import asyncio
from typing import Dict, List, Any
from fastapi import WebSocket
from app.config import config
from app.core.document_store import DocumentStore
from app.models.llm import LLMModel
from app.core.websocket_manager import WebSocketManager

# Set up logging
logger = logging.getLogger(__name__)

class SageX3ChatService:
    """
    Service that dynamically selects between Expert and Trainer modes
    based on configuration.
    """
    
    def __init__(self, document_store: DocumentStore, llm_model: LLMModel, websocket_manager: WebSocketManager = None):
        self.document_store = document_store
        self.llm_model = llm_model
        self.websocket_manager = websocket_manager
        self.expert_prompt = self._create_expert_prompt()
        self.trainer_prompt = self._create_trainer_prompt()
        self.model_loaded = False
        self.model_loading_lock = asyncio.Lock()
    
    def get_document_status(self, document_id: str) -> Dict:
        """Get document status."""
        return self.document_store.get_document_status(document_id)
    
    def is_model_loaded(self) -> bool:
        """Check if model is loaded."""
        return self.model_loaded
    
    async def ensure_model_loaded(self) -> None:
        """Ensure model is loaded, with lock to prevent concurrent loads."""
        if self.model_loaded:
            return
            
        async with self.model_loading_lock:
            # Check again in case another task loaded the model while waiting for lock
            if self.model_loaded:
                return
                
            logger.info("Loading language model...")
            try:
                # Load the model
                self.llm_model.load_model()
                self.model_loaded = True
                logger.info("Language model loaded successfully")
            except Exception as e:
                logger.error(f"Error loading language model: {str(e)}")
                raise
    
    def _create_expert_prompt(self) -> str:
        """Create the prompt template for Sage X3 Expert mode."""
        return (
            "You are a Sage X3 system expert with deep technical and functional knowledge. You can analyze complex "
            "Sage X3 scenarios, provide configuration guidance, troubleshoot issues, and offer best-practice recommendations.\n\n"
            
            "ROLE AND RESPONSIBILITIES:\n"
            "- Possess deep technical and functional knowledge of Sage X3 systems\n"
            "- Analyze complex scenarios and provide accurate solutions\n"
            "- Offer configuration guidance based on industry best practices\n"
            "- Troubleshoot issues methodically and effectively\n"
            "- Explain technical concepts clearly to users with varying levels of expertise\n\n"
            
            "APPROACH TO SAGE X3 QUESTIONS:\n"
            "1. Begin by understanding the user's context:\n"
            "   - Which Sage X3 version they're using\n"
            "   - Which specific module(s) are involved\n"
            "   - What business process they are working within\n"
            "   - What steps they've already taken\n"
            "   - Any error messages or specific behaviors they're observing\n\n"
            
            "2. Provide accurate and in-depth information:\n"
            "   - Include relevant details about configuration setup and parameters\n"
            "   - Explain data structures when relevant\n"
            "   - Discuss potential impacts of changes\n"
            "   - Highlight interdependencies between different parts of the system\n\n"
            
            "3. Guide through logical troubleshooting steps:\n"
            "   - Suggest areas to investigate\n"
            "   - Identify potential causes\n"
            "   - Provide methods for diagnosing problems\n\n"
            
            "4. Recommend best practices for:\n"
            "   - System configuration\n"
            "   - Usage patterns\n"
            "   - Maintenance procedures\n"
            "   - Data integrity\n\n"
            
            "5. Consider security and permissions:\n"
            "   - Keep in mind security roles and user permissions\n"
            "   - Highlight relevant security considerations\n\n"
            
            "6. Focus on practical, actionable solutions\n\n"
            
            "If the question is unrelated to Sage X3 systems, politely respond: 'I'm specialized in Sage X3 ERP systems. "
            "Please ask me something related to Sage X3 configuration, usage, or troubleshooting.'\n\n"
            
            "Use the CHAT HISTORY to maintain continuity in the conversation.\n\n"
            
            "Important instructions when responding:\n"
            "- Begin with a concise, professional greeting\n"
            "- If you need more context, ask clarifying questions first\n"
            "- Use technical Sage X3 terminology appropriately\n"
            "- Structure complex answers with clear headings and steps\n"
            "- Focus on providing practical, actionable solutions\n\n"
            
            "CONTEXT FROM DOCUMENTS:\n{context}\n\n"
            "CHAT HISTORY:\n{chat_history}\n\n"
            "User's Question: {input}\n\n"
            "Respond naturally and professionally."
        )
    
    def _create_trainer_prompt(self) -> str:
        """Create the prompt template for Sage X3 Trainer mode."""
        return (
            "You are an experienced Sage X3 system trainer, skilled at explaining complex functionalities in a clear, "
            "concise, and educational manner. You provide step-by-step instructions, offer practical examples, and "
            "tailor your explanations to different learning styles.\n\n"
            
            "ROLE AND RESPONSIBILITIES:\n"
            "- Help users understand how to use Sage X3 effectively\n"
            "- Provide clear explanations and practical examples\n"
            "- Offer step-by-step instructions for various tasks\n"
            "- Share best practices for business processes\n"
            "- Adapt explanations to the user's level of expertise\n\n"
            
            "APPROACH TO SAGE X3 TRAINING:\n"
            "1. Identify the user's learning needs:\n"
            "   - Understand their role and current knowledge level\n"
            "   - Identify specific tasks or areas they want to learn\n\n"
            
            "2. Provide clear and concise explanations:\n"
            "   - Use straightforward language\n"
            "   - Avoid overly technical jargon when possible\n"
            "   - Break complex concepts into simpler parts\n\n"
            
            "3. Offer detailed step-by-step instructions:\n"
            "   - Provide numbered steps that are easy to follow\n"
            "   - Include navigation paths (menus, buttons, screens)\n"
            "   - Highlight required fields and important options\n\n"
            
            "4. Use practical business examples:\n"
            "   - Illustrate concepts with relevant business scenarios\n"
            "   - Connect functionality to practical applications\n"
            "   - Show how features work in real-world situations\n\n"
            
            "5. Highlight key considerations and best practices:\n"
            "   - Point out important aspects to consider\n"
            "   - Share efficiency tips and shortcuts\n"
            "   - Warn about common pitfalls or mistakes\n\n"
            
            "6. Explain the \"why\" behind the \"how\":\n"
            "   - Clarify the purpose of different functions\n"
            "   - Explain benefits of proper configuration\n"
            "   - Connect tasks to business outcomes\n\n"
            
            "If the question is unrelated to Sage X3 systems, politely respond: 'I'm specialized in training for Sage X3 ERP systems. "
            "Please ask me something related to learning how to use Sage X3.'\n\n"
            
            "Use the CHAT HISTORY to maintain continuity in the conversation.\n\n"
            
            "Important instructions when responding:\n"
            "- Begin with a friendly, encouraging greeting\n"
            "- Use clear, simple language that's easy to understand\n"
            "- Provide numbered steps for processes\n"
            "- Include practical examples to illustrate concepts\n"
            "- Encourage the user to ask follow-up questions\n\n"
            
            "CONTEXT FROM DOCUMENTS:\n{context}\n\n"
            "CHAT HISTORY:\n{chat_history}\n\n"
            "User's Question: {input}\n\n"
            "Respond in a friendly, educational manner."
        )
    
    async def process_chat_message(
        self, 
        session_id: str,
        client_id: str, 
        question: str, 
        websocket: WebSocket, 
        chat_history: List[Dict[str, str]]
    ) -> None:
        """Process a chat message and send the response using the configured mode."""
        from langchain.prompts import ChatPromptTemplate
        from langchain.chains.combine_documents import create_stuff_documents_chain
        from langchain.chains import create_retrieval_chain
        from langchain_core.documents import Document
        from langchain.callbacks.base import BaseCallbackHandler
        from app.utils.helpers import Timer
        
        logger.info(f"Processing message from client {client_id} for session {session_id}")
        
        # WebSocket callback handler with improved error handling
        class WebSocketCallbackHandler(BaseCallbackHandler):
            def __init__(self, websocket):
                self.websocket = websocket
                self.collected_tokens = ""
                self.connection_closed = False
                
            async def on_llm_new_token(self, token: str, **kwargs):
                # Skip if connection is already closed
                if self.connection_closed:
                    return
                    
                # Send each token as it comes
                self.collected_tokens += token
                try:
                    await self.websocket.send_text(json.dumps({
                        "status": "streaming",
                        "token": token
                    }))
                except Exception as e:
                    logger.error(f"Error sending token: {str(e)}")
                    self.connection_closed = True
        
        # Ensure model is loaded
        await self.ensure_model_loaded()
        
        with Timer() as timer:
            # Retrieve context chunks from all documents in the session
            try:
                # Get the document IDs in this session
                document_ids = self.document_store.get_session_documents(session_id)
                
                if not document_ids:
                    await websocket.send_text(json.dumps({
                        "status": "error",
                        "error": "No documents found in this session. Please upload at least one document."
                    }))
                    return
                
                # Search across all documents in the session
                context_chunks = await self.document_store.search(
                    query=question,
                    k=config.SIMILAR_DOCS_COUNT,
                    session_id=session_id
                )
                
                documents = [Document(page_content=chunk) for chunk in context_chunks]
                retriever = self._get_static_retriever(documents)
                
                # Create callback manager with our handler
                callback_handler = WebSocketCallbackHandler(websocket)
                
                # First, send acknowledgment that processing has started
                try:
                    await websocket.send_text(json.dumps({
                        "status": "processing",
                        "message": "Processing your question..."
                    }))
                except Exception as e:
                    logger.error(f"Error sending processing message: {str(e)}")
                    # If we can't send this message, the connection is likely closed
                    return
                
                # Format chat history based on the selected mode
                bot_name = "Sage X3 Expert" if config.SAGE_X3_MODE == "expert" else "Sage X3 Trainer"
                
                formatted_chat_history = ""
                for entry in chat_history:
                    formatted_chat_history += f"User: {entry['question']}\n{bot_name}: {entry['answer']}\n\n"
                
                # Select the appropriate prompt based on configuration
                base_prompt = self.expert_prompt if config.SAGE_X3_MODE == "expert" else self.trainer_prompt

                # Create prompt template
                prompt_template = ChatPromptTemplate.from_messages([
                    ("system", base_prompt),
                    ("human", "{input}")
                ])
                
                # Create retrieval-based QA chain with streaming
                try:
                    # Get LLM with callback handler for streaming
                    llm_with_callback = self.llm_model.get_llm().with_config(
                        {"callbacks": [callback_handler]}
                    )
                    
                    # Create the chain
                    document_chain = create_stuff_documents_chain(
                        llm_with_callback,
                        prompt_template
                    )
                    
                    qa_chain = create_retrieval_chain(
                        retriever,
                        document_chain
                    )

                    # Generate combined response based on document context
                    # Set a timeout for the model response
                    result = await asyncio.wait_for(
                        qa_chain.ainvoke({
                            "input": question,
                            "chat_history": formatted_chat_history,
                            "context": "\n\n".join(context_chunks) if context_chunks else "(No relevant document context found)"
                        }),
                        timeout=config.MODEL_TIMEOUT
                    )
                    
                    final_response = result.get("answer", "").strip()
                    
                    if not final_response:
                        final_response = "I apologize, but I couldn't generate a proper response. This might be due to limitations in the model or the context provided."
                
                except asyncio.TimeoutError:
                    logger.error(f"Model response timed out after {config.MODEL_TIMEOUT} seconds")
                    final_response = "I apologize, but the response is taking longer than expected. Please try asking a more focused question or break your question into smaller parts."
                except Exception as e:
                    logger.error(f"Error generating response: {str(e)}")
                    final_response = f"I apologize, but there was an error generating a response. Please try again or contact support if the issue persists."
                    
                # Add the current Q&A to chat history
                chat_history.append({
                    "question": question,
                    "answer": final_response
                })
                
                # Keep chat history to a reasonable size (last 10 exchanges)
                if len(chat_history) > 10:
                    chat_history = chat_history[-10:]

                # Send final complete response if connection is still open
                if not callback_handler.connection_closed:
                    try:
                        await websocket.send_text(json.dumps({
                            "status": "complete",
                            "answer": final_response,
                            "time": timer.interval
                        }))
                    except Exception as e:
                        logger.error(f"Error sending complete response: {str(e)}")
                
            except Exception as e:
                logger.error(f"Error in process_chat_message for client {client_id}: {str(e)}")
                try:
                    await websocket.send_text(json.dumps({
                        "status": "error",
                        "error": str(e)
                    }))
                except Exception as websocket_error:
                    logger.error(f"Could not send error message - WebSocket closed: {str(websocket_error)}")
    
    def _get_static_retriever(self, documents):
        """Create a static retriever for a set of documents."""
        from langchain_core.retrievers import BaseRetriever
        
        class StaticRetriever(BaseRetriever):
            def _get_relevant_documents(self, query: str):
                return documents

            async def _aget_relevant_documents(self, query: str):
                return documents

        return StaticRetriever()