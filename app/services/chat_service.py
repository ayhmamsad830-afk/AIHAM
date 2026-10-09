# import json
# import logging
# from typing import List, Dict, Any
# from fastapi import WebSocket
# from langchain.prompts import ChatPromptTemplate
# from langchain.chains.combine_documents import create_stuff_documents_chain
# from langchain.chains import create_retrieval_chain
# from langchain_core.documents import Document
# from langchain.callbacks.base import BaseCallbackHandler
# from app.core.document_store import DocumentStore
# from app.models.llm import LLMModel
# from app.utils.helpers import Timer
# from app.config import config

# # Set up logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

# class ChatService:
#     def __init__(self, document_store: DocumentStore, llm_model: LLMModel):
#         self.document_store = document_store
#         self.llm_model = llm_model
    
#     def get_document_status(self, document_id: str) -> Dict:
#         """Get document status."""
#         return self.document_store.get_document_status(document_id)
    
#     async def process_chat_message(
#         self, 
#         document_id: str, 
#         client_id: str, 
#         question: str, 
#         websocket: WebSocket, 
#         chat_history: List[Dict[str, str]]
#     ) -> None:
#         """Process a chat message and send the response."""
#         with Timer() as timer:
#             # Retrieve context chunks from document
#             try:
#                 context_chunks = await self.document_store.search(
#                     document_id,
#                     question,
#                     k=config.SIMILAR_DOCS_COUNT
#                 )
                
#                 documents = [Document(page_content=chunk) for chunk in context_chunks]
#                 retriever = self._get_static_retriever(documents)
                
#                 # Create streaming callback handler
#                 class WebSocketCallbackHandler(BaseCallbackHandler):
#                     def __init__(self, websocket):
#                         self.websocket = websocket
#                         self.collected_tokens = ""
                        
#                     async def on_llm_new_token(self, token: str, **kwargs):
#                         # Send each token as it comes for streaming response
#                         self.collected_tokens += token
#                         try:
#                             await websocket.send_text(json.dumps({
#                                 "status": "streaming",
#                                 "token": token
#                             }))
#                         except Exception as e:
#                             logger.error(f"Error sending token: {str(e)}")
                        
#                 # Create callback manager with our handler
#                 callback_handler = WebSocketCallbackHandler(websocket)
                
#                 # Format chat history for inclusion in the prompt
#                 formatted_chat_history = ""
#                 for entry in chat_history:
#                     formatted_chat_history += f"User: {entry['question']}\nAssistant: {entry['answer']}\n\n"
                
#                 # Generic RAG prompt without Sage X3 specific instructions
#                 base_prompt = (
#                     "You are a helpful AI assistant that answers questions based on the content of provided documents. "
#                     "Your goal is to provide accurate, relevant, and helpful responses derived from the document text.\n\n"
                    
#                     "INSTRUCTIONS:\n"
#                     "1. Answer questions based ONLY on the context provided in the document\n"
#                     "2. If the answer cannot be found in the document context, honestly state that you don't have that information\n"
#                     "3. Keep answers concise, clear, and directly relevant to the question\n"
#                     "4. If the context contains multiple perspectives or options, present them fairly\n"
#                     "5. For questions about processes or steps, provide clear numbered lists\n"
#                     "6. Maintain a helpful, professional tone\n"
#                     "7. Do not make up information not contained in the context\n\n"
                    
#                     "DOCUMENT CONTEXT:\n{context}\n\n"
#                     "CHAT HISTORY:\n{chat_history}\n\n"
#                     "User's Question: {input}\n\n"
#                     "Please respond with the most accurate and helpful answer based on the document context."
#                 )

#                 # Create prompt template
#                 prompt_template = ChatPromptTemplate.from_messages([
#                     ("system", base_prompt),
#                     ("human", "{input}")
#                 ])
                
#                 # Create retrieval-based QA chain with streaming
#                 try:
#                     # Get LLM with callback handler for streaming
#                     llm_with_callback = self.llm_model.get_llm().with_config(
#                         {"callbacks": [callback_handler]}
#                     )
                    
#                     # Create the chain
#                     document_chain = create_stuff_documents_chain(
#                         llm_with_callback,
#                         prompt_template
#                     )
                    
#                     qa_chain = create_retrieval_chain(
#                         retriever,
#                         document_chain
#                     )

#                     # Generate combined response based on document context
#                     result = await qa_chain.ainvoke({
#                         "input": question,
#                         "chat_history": formatted_chat_history,
#                         "context": "\n\n".join(context_chunks) if context_chunks else "(No relevant document context found)"
#                     })
                    
#                     final_response = result.get("answer", "").strip()
                    
#                     if not final_response:
#                         final_response = "I apologize, but I couldn't generate a proper response. This might be due to limitations in the model or the context provided."
                
#                 except Exception as e:
#                     logger.error(f"Error generating response: {str(e)}")
#                     final_response = f"I apologize, but there was an error generating a response. Please try again or contact support if the issue persists."
                    
#                 # Add the current Q&A to chat history
#                 chat_history.append({
#                     "question": question,
#                     "answer": final_response
#                 })
                
#                 # Keep chat history to a reasonable size (last 10 exchanges)
#                 if len(chat_history) > 10:
#                     chat_history = chat_history[-10:]

#                 # Send final complete response
#                 await websocket.send_text(json.dumps({
#                     "status": "complete",
#                     "answer": final_response,
#                     "time": timer.interval
#                 }))
                
#             except Exception as e:
#                 logger.error(f"Error in process_chat_message: {str(e)}")
#                 await websocket.send_text(json.dumps({
#                     "status": "error",
#                     "error": str(e)
#                 }))
    
#     def _get_static_retriever(self, documents):
#         """Create a static retriever for a set of documents."""
#         from langchain_core.retrievers import BaseRetriever
        
#         class StaticRetriever(BaseRetriever):
#             def _get_relevant_documents(self, query: str):
#                 return documents

#             async def _aget_relevant_documents(self, query: str):
#                 return documents

#         return StaticRetriever()