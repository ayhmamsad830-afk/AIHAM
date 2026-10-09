from langchain_ollama import OllamaLLM
import logging
import asyncio

from app.config import config

# Set up logging
logger = logging.getLogger(__name__)

class LLMModel:
    def __init__(self):
        self.llm = None
        self.max_tokens = 4096
        self._lock = None  # Initialize the lock when needed
    
    def _get_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def load_model(self):
        """Load the Ollama model with the configured model."""
        logger.info(f"Loading Ollama model: {config.MODEL_NAME}")
        
        try:
            # Create Ollama LangChain model
            # In llm.py:
            self.llm = OllamaLLM(
                model=config.MODEL_NAME,
                temperature=config.TEMPERATURE,
                num_ctx=8192,
                num_predict=self.max_tokens,
                keep_alive="5m",
                base_url=config.OLLAMA_BASE_URL,
                timeout=config.MODEL_TIMEOUT,  # Add timeout parameter
            )
            
            logger.info(f"Successfully loaded Ollama model: {config.MODEL_NAME}")
            return self.llm
            
        except Exception as e:
            logger.error(f"Error loading Ollama model: {str(e)}")
            raise
    
    async def load_model_async(self):
        """Asynchronously load the model."""
        lock = self._get_lock()
        async with lock:
            if self.llm is None:
                # Run model loading in a thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.load_model)
            return self.llm
    
    def get_llm(self):
        """Get the LLM instance, loading it if necessary."""
        if self.llm is None:
            self.load_model()
        return self.llm
    
    def is_loaded(self):
        """Check if the model is loaded."""
        return self.llm is not None