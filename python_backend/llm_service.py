"""
LLM Service for RoboDoc - DeepSeek R1 (Powered by Llama 3.1:8b-instruct-q4_K_M)
"""
import os
import time
import json
import requests
from typing import Dict, List, Any, Optional

# Ollama Configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.3"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))


class LLMService:
    """Service for interacting with Ollama LLM (Llama 3.1)"""
    
    def __init__(self, host: str = OLLAMA_HOST, model: str = OLLAMA_MODEL):
        self.host = host
        self.model = model
        self.temperature = OLLAMA_TEMPERATURE
        self.num_ctx = OLLAMA_NUM_CTX
        
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to Ollama and get model info"""
        try:
            # Test basic connection
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            
            if response.status_code != 200:
                return {
                    "status": "error",
                    "error": f"HTTP {response.status_code}"
                }
            
            data = response.json()
            models = data.get("models", [])
            
            # Check if our model is available
            model_available = any(m.get("name") == self.model for m in models)
            
            if not model_available:
                return {
                    "status": "error",
                    "error": f"Model '{self.model}' not found. Available: {[m.get('name') for m in models]}"
                }
            
            # Get GPU info
            gpu_status = "N/A"
            try:
                show_response = requests.post(
                    f"{self.host}/api/show",
                    json={"name": self.model},
                    timeout=5
                )
                if show_response.status_code == 200:
                    model_info = show_response.json()
                    gpu_status = "GPU (CUDA)" if "cuda" in str(model_info).lower() else "CPU"
            except:
                pass
            
            return {
                "status": "connected",
                "models": [m.get("name") for m in models],
                "current_model": self.model,
                "gpu_status": gpu_status,
                "context_window": self.num_ctx,
                "temperature": self.temperature
            }
            
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "error": "Cannot connect to Ollama. Make sure Ollama is running."
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def chat_with_context(
        self,
        user_message: str,
        chat_history: List[Dict[str, str]] = None,
        inventory_context: Dict = None
    ) -> Dict[str, Any]:
        """
        Send chat message to LLM with context
        Returns JSON action format for inventory operations
        """
        start_time = time.time()
        
        if chat_history is None:
            chat_history = []
        
        # Build system prompt
        system_prompt = self._build_system_prompt(inventory_context)
        
        # Build messages for Ollama
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add chat history
        for msg in chat_history:
            messages.append(msg)
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        try:
            # Call Ollama API
            response = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_ctx": self.num_ctx
                    }
                },
                timeout=30
            )
            
            if response.status_code != 200:
                raise Exception(f"Ollama API error: HTTP {response.status_code}")
            
            result = response.json()
            assistant_message = result.get("message", {}).get("content", "")
            
            elapsed_time = time.time() - start_time
            
            return {
                "response": assistant_message,
                "elapsed_time": elapsed_time,
                "tokens_total": result.get("eval_count", 0) + result.get("prompt_eval_count", 0),
                "model": self.model
            }
            
        except Exception as e:
            print(f"❌ LLM Error: {e}")
            raise
    
    def _build_system_prompt(self, inventory_context: Optional[Dict]) -> str:
        """Build system prompt with inventory context"""
        
        # Base system prompt - DeepSeek R1 style (but using Llama core)
        base_prompt = """You are DeepSeek R1, an advanced AI assistant for RoboDoc warehouse management system.

You help users manage inventory by understanding natural language commands in both English and Vietnamese.

CRITICAL RULES:
1. You MUST respond with ONLY a JSON object, no markdown, no explanation outside JSON
2. JSON format must be EXACTLY:
   {
     "action": "update_inventory" | "none",
     "reply": "your message to user in Vietnamese or English",
     "reasoning": "brief internal reasoning",
     "updates": [{"cell_id": N, "pick": true/false, "done": true/false}, ...]
   }

3. For inventory operations (chọn, xóa, lấy, đánh dấu, clear, pick, done):
   - action = "update_inventory"
   - updates = array of changes (ONLY include pick and done fields, NEVER product or cell_id changes)
   
4. For questions or greetings:
   - action = "none"
   - reply = your answer
   - updates = []

5. When user says "chọn ô 3" or "pick cell 3":
   - updates = [{"cell_id": 3, "pick": true, "done": false}]

6. When user says "xóa ô 3" or "clear cell 3":
   - updates = [{"cell_id": 3, "pick": false, "done": false}]

7. When user says "hoàn thành ô 3" or "done cell 3":
   - updates = [{"cell_id": 3, "done": true}]

REMEMBER: Output ONLY JSON, nothing else!"""

        # Add inventory context if available
        if inventory_context and "items" in inventory_context:
            items_info = []
            for item in inventory_context["items"]:
                cell_id = item.get("cell_id", "?")
                product = item.get("product", "empty")
                pick = item.get("pick", False)
                done = item.get("done", False)
                items_info.append(f"Cell {cell_id}: {product} (pick={pick}, done={done})")
            
            inventory_text = "\n".join(items_info)
            base_prompt += f"\n\nCURRENT INVENTORY STATE:\n{inventory_text}"
        
        return base_prompt


# Export constants for use in app.py
__all__ = ["LLMService", "OLLAMA_TEMPERATURE", "OLLAMA_NUM_CTX"]
