"""
LLM Service Module - Generic LLM Integration
Supports Ollama models (Llama, Qwen, etc.) with GPU acceleration
"""
import os
import json
import time
import urllib.request
import urllib.error
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")
OLLAMA_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.2"))
OLLAMA_TOP_P = float(os.environ.get("OLLAMA_TOP_P", "0.9"))
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))


class LLMService:
    """Service for interacting with LLM via Ollama with GPU support"""
    
    def __init__(self):
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL
        
        # Enhanced system message with better logic and structure
        self.system_message = {
            "role": "system",
            "content": (
                "You are RoboDoc AI Assistant - an intelligent inventory management system for robotic picking.\n\n"
                
                "## YOUR ROLE\n"
                "Help users manage inventory through natural language (Vietnamese/English). "
                "You can read current inventory state and execute safe update actions.\n\n"
                
                "## RESPONSE FORMAT (CRITICAL)\n"
                "You MUST respond with EXACTLY ONE valid JSON object. "
                "NO markdown formatting, NO code blocks (```), NO explanations outside JSON.\n\n"
                
                "Required JSON Schema:\n"
                "{\n"
                '  "action": "update_inventory" | "none",\n'
                '  "reply": "your helpful response in Vietnamese",\n'
                '  "reasoning": "brief explanation of your decision (1 sentence)",\n'
                '  "updates": [\n'
                '    {"cell_id": 1, "pick": true},\n'
                '    {"cell_id": 2, "done": true}\n'
                '  ]\n'
                "}\n\n"
                
                "## STRICT SAFETY RULES\n"
                "1. NEVER modify 'cell_id' or 'product' fields - these are immutable\n"
                "2. ONLY change 'pick' (boolean) and 'done' (boolean) fields\n"
                "3. Use ONLY cell_id values that exist in the provided INVENTORY_JSON\n"
                "4. Do NOT create, add, or invent new products - only backend/user can add products\n"
                "5. If user requests inventory changes → action MUST be 'update_inventory'\n"
                "6. If action='update_inventory' → 'updates' array MUST have at least 1 item\n"
                "7. If no changes needed (info query) → action='none' and updates=[]\n\n"
                
                "## ACTION MAPPING RULES\n"
                "Vietnamese commands:\n"
                "- 'chọn ô N' / 'lấy ô N' → {\"cell_id\": N, \"pick\": true}\n"
                "- 'chọn [tên sản phẩm]' → find item with matching product, set pick=true\n"
                "- 'bỏ chọn ô N' / 'huỷ ô N' → {\"cell_id\": N, \"pick\": false}\n"
                "- 'đã lấy xong ô N' / 'hoàn thành ô N' → {\"cell_id\": N, \"done\": true}\n"
                "- 'xóa ô N' / 'clear ô N' → {\"cell_id\": N, \"pick\": false, \"done\": false}\n"
                "- 'chọn tất cả' → set all cells to pick=true\n"
                "- 'bỏ chọn tất cả' → set all cells to pick=false\n\n"
                
                "English commands:\n"
                "- 'pick cell N' / 'select N' → {\"cell_id\": N, \"pick\": true}\n"
                "- 'unpick cell N' → {\"cell_id\": N, \"pick\": false}\n"
                "- 'done cell N' / 'complete N' → {\"cell_id\": N, \"done\": true}\n"
                "- 'clear cell N' → {\"cell_id\": N, \"pick\": false, \"done\": false}\n\n"
                
                "## CONTEXT UNDERSTANDING\n"
                "You will receive INVENTORY_JSON containing current inventory state with fields:\n"
                "- cell_id: unique identifier (1-9 typically)\n"
                "- product: product name (empty string if no product)\n"
                "- pick: true if selected for picking, false otherwise\n"
                "- done: true if already picked/completed, false otherwise\n\n"
                
                "## LOGIC RULES\n"
                "- When pick=true is set, automatically set done=false (unless explicitly requested)\n"
                "- done=true should only be set for items that are pick=true or were previously picked\n"
                "- Empty cells (product='') can still be picked if user explicitly requests\n"
                "- When counting items, only count cells with non-empty product names\n\n"
                
                "## EXAMPLES\n\n"
                
                "Example 1 - Pick a cell:\n"
                'User: "Chọn ô 1"\n'
                'Response: {"action": "update_inventory", "reply": "Đã chọn ô 1 để lấy hàng", '
                '"reasoning": "User explicitly requested to pick cell 1", '
                '"updates": [{"cell_id": 1, "pick": true}]}\n\n'
                
                "Example 2 - Mark as done:\n"
                'User: "Đã lấy xong ô 3"\n'
                'Response: {"action": "update_inventory", "reply": "Đã đánh dấu ô 3 hoàn thành", '
                '"reasoning": "User confirmed cell 3 pickup is complete", '
                '"updates": [{"cell_id": 3, "done": true}]}\n\n'
                
                "Example 3 - Information query:\n"
                'User: "Có bao nhiêu sản phẩm?"\n'
                'Response: {"action": "none", "reply": "Hiện có X sản phẩm trong kho, trong đó Y đã chọn và Z đã hoàn thành", '
                '"reasoning": "Information query, no inventory changes needed", '
                '"updates": []}\n\n'
                
                "Example 4 - Multiple updates:\n"
                'User: "Chọn ô 1, 2 và 3"\n'
                'Response: {"action": "update_inventory", "reply": "Đã chọn 3 ô: 1, 2, 3", '
                '"reasoning": "User requested multiple cells to be picked", '
                '"updates": [{"cell_id": 1, "pick": true}, {"cell_id": 2, "pick": true}, {"cell_id": 3, "pick": true}]}\n\n'
                
                "Example 5 - Clear a cell:\n"
                'User: "Xóa ô 5"\n'
                'Response: {"action": "update_inventory", "reply": "Đã xóa trạng thái của ô 5", '
                '"reasoning": "User wants to reset cell 5 status", '
                '"updates": [{"cell_id": 5, "pick": false, "done": false}]}\n\n'
                
                "REMEMBER: Always output valid JSON only. No other text."
            )
        }
    
    def chat_stream(self, messages: List[Dict[str, str]], system_override: Optional[Dict[str, str]] = None) -> Dict:
        """
        Stream chat response from Ollama /api/chat
        Returns dict with response and metadata
        
        Args:
            messages: List of chat messages
            system_override: Optional system message to override default (for normalization)
        
        Returns:
            Dict with 'response', 'elapsed_time', 'model', 'tokens_estimate'
        """
        url = f"{self.host}/api/chat"
        
        # Use override system message if provided, otherwise use default
        system_msg = system_override if system_override is not None else self.system_message
        
        # Ensure system message is first
        full_messages = [system_msg] + [
            msg for msg in messages if msg.get("role") != "system"
        ]
        
        payload = {
            "model": self.model,
            "messages": full_messages,
            "stream": False,  # Non-streaming for simpler HTTP response
            "options": {
                "temperature": OLLAMA_TEMPERATURE,
                "top_p": OLLAMA_TOP_P,
                "num_ctx": OLLAMA_NUM_CTX,
                "num_gpu": int(os.environ.get("OLLAMA_NUM_GPU", "1")),
            },
        }
        
        req = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        start_time = time.time()
        
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                elapsed = time.time() - start_time
                
                if result.get("error"):
                    raise RuntimeError(result["error"])
                
                message = result.get("message", {})
                content = message.get("content", "")
                
                # Extract tokens info if available
                eval_count = result.get("eval_count", 0)
                prompt_eval_count = result.get("prompt_eval_count", 0)
                
                return {
                    "response": content.strip(),
                    "elapsed_time": elapsed,
                    "model": self.model,
                    "tokens_generated": eval_count,
                    "tokens_prompt": prompt_eval_count,
                    "tokens_total": eval_count + prompt_eval_count
                }
                
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.host}. "
                f"Is Ollama running? Error: {e}"
            )
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON response from Ollama: {e}")
    
    def chat_with_context(
        self, 
        user_message: str, 
        chat_history: Optional[List[Dict[str, str]]] = None,
        inventory_context: Optional[Dict] = None
    ) -> Dict:
        """
        Chat with LLM including inventory context
        
        Args:
            user_message: The user's message
            chat_history: Previous chat messages (optional)
            inventory_context: Current inventory data (optional)
        
        Returns:
            Dict with response, metadata, and parsing info
        """
        messages = []
        
        # Add chat history if provided
        if chat_history:
            messages.extend(chat_history)
        
        # Build context-enriched user message with FULL inventory JSON
        context_msg = user_message
        if inventory_context and inventory_context.get("items"):
            inv_json = json.dumps(inventory_context, ensure_ascii=False, indent=2)
            context_msg = (
                user_message
                + "\n\nINVENTORY_JSON:\n"
                + inv_json
            )
        
        messages.append({"role": "user", "content": context_msg})
        
        # Enhanced logging - BEFORE LLM call
        print(f"\n{'='*80}")
        print(f"🧠 LLM Model: {self.model}")
        print(f"📥 User Message: {user_message}")
        if inventory_context:
            items = inventory_context.get("items", [])
            total = len(items)
            picked = sum(1 for it in items if it.get("pick"))
            done = sum(1 for it in items if it.get("done"))
            print(f"📊 Inventory: {total} items (picked: {picked}, done: {done})")
        if chat_history:
            print(f"📝 Chat History: {len(chat_history)} messages")
        print(f"🔧 Config: temp={OLLAMA_TEMPERATURE}, top_p={OLLAMA_TOP_P}, ctx={OLLAMA_NUM_CTX}")
        print(f"⏳ Calling LLM...")
        
        # Get response from LLM (with timing)
        result = self.chat_stream(messages)
        
        # Enhanced logging - AFTER LLM call
        print(f"✅ Response received in {result['elapsed_time']:.2f}s")
        print(f"📤 Response ({len(result['response'])} chars):")
        print(f"   {result['response'][:150]}{'...' if len(result['response']) > 150 else ''}")
        print(f"🎯 Tokens: {result.get('tokens_generated', 0)} generated, "
              f"{result.get('tokens_prompt', 0)} prompt, "
              f"{result.get('tokens_total', 0)} total")
        print(f"💨 Speed: {result.get('tokens_generated', 0) / max(result['elapsed_time'], 0.01):.1f} tokens/s")
        print(f"{'='*80}\n")
        
        return result
    
    def test_connection(self) -> Dict[str, any]:
        """Test connection to Ollama and check GPU status"""
        try:
            url = f"{self.host}/api/tags"
            req = urllib.request.Request(url, method="GET")
            
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", [])]
                
                # Test a simple query to check GPU
                test_result = None
                gpu_info = "Unknown"
                try:
                    test_result = self.chat_stream([
                        {"role": "user", "content": "Hi"}
                    ])
                    # If we got a response, GPU is likely working
                    gpu_info = "Available (CUDA detected)" if os.environ.get("OLLAMA_NUM_GPU", "1") != "0" else "CPU only"
                except:
                    gpu_info = "Not detected"
                
                return {
                    "status": "connected",
                    "host": self.host,
                    "models": models,
                    "current_model": self.model,
                    "model_available": self.model in models,
                    "gpu_status": gpu_info,
                    "context_window": OLLAMA_NUM_CTX,
                    "temperature": OLLAMA_TEMPERATURE
                }
        except Exception as e:
            return {
                "status": "error",
                "host": self.host,
                "error": str(e),
                "current_model": self.model,
                "gpu_status": "Unknown"
            }
