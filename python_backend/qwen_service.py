"""
Qwen Service Module
Handles communication with Ollama/Qwen LLM
"""
import os
import json
import urllib.request
import urllib.error
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b-instruct")
OLLAMA_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.3"))
OLLAMA_TOP_P = float(os.environ.get("OLLAMA_TOP_P", "0.9"))
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))


class QwenService:
    """Service for interacting with Qwen via Ollama"""
    
    def __init__(self):
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL
        # Initialize system message - JSON-only responses
        self.system_message = {
            "role": "system",
            "content": (
                "Bạn là trợ lý điều khiển inventory cho robot.\n"
                "Luôn trả về ĐÚNG 1 JSON object (KHÔNG markdown, KHÔNG code fence, KHÔNG giải thích thêm).\n\n"
                
                "INPUT: bạn sẽ được cung cấp INVENTORY_JSON gồm danh sách items: cell_id, product, pick, done.\n"
                "NHIỆM VỤ: dựa theo yêu cầu người dùng, tạo JSON theo schema:\n"
                "{\n"
                "  \"action\": \"update_inventory\" | \"none\",\n"
                "  \"reply\": \"câu trả lời bằng tiếng Việt\",\n"
                "  \"updates\": [\n"
                "    {\"cell_id\": 1, \"pick\": true},\n"
                "    {\"cell_id\": 3, \"done\": true}\n"
                "  ]\n"
                "}\n\n"
                
                "QUY TẮC BẮT BUỘC:\n"
                "- KHÔNG BAO GIỜ được thay đổi cell_id.\n"
                "- KHÔNG được thêm hoặc sửa product name (chỉ backend/user mới được thêm sản phẩm).\n"
                "- CHỈ được thay đổi pick và done fields.\n"
                "- Nếu user yêu cầu thay đổi inventory (chọn lấy, bỏ chọn, đánh dấu đã lấy) "
                "→ action PHẢI là \"update_inventory\".\n"
                "- Với action=\"update_inventory\" thì updates PHẢI có ít nhất 1 phần tử.\n"
                "- Chỉ dùng cell_id tồn tại trong INVENTORY_JSON.\n"
                "- KHÔNG được tự bịa sản phẩm mới; chỉ chọn sản phẩm đang có trong INVENTORY_JSON.\n\n"
                
                "MAPPING CỤ THỂ:\n"
                "- 'chọn/lấy ô N' → {\"cell_id\": N, \"pick\": true}\n"
                "- 'chọn/lấy X' (X là tên sản phẩm) → tìm item có product=X, set {\"cell_id\": ..., \"pick\": true}\n"
                "- 'bỏ chọn ô N' → {\"cell_id\": N, \"pick\": false}\n"
                "- 'đã lấy xong ô N' → {\"cell_id\": N, \"done\": true}\n\n"
                
                "VÍ DỤ:\n"
                "User: 'Chọn ô 1'\n"
                "Response: {\"action\": \"update_inventory\", \"reply\": \"Đã chọn ô 1\", \"updates\": [{\"cell_id\": 1, \"pick\": true}]}\n\n"
                
                "User: 'Bỏ chọn ô 2'\n"
                "Response: {\"action\": \"update_inventory\", \"reply\": \"Đã bỏ chọn ô 2\", \"updates\": [{\"cell_id\": 2, \"pick\": false}]}\n\n"
                
                "User: 'Đánh dấu ô 3 đã lấy xong'\n"
                "Response: {\"action\": \"update_inventory\", \"reply\": \"Đã đánh dấu ô 3 hoàn thành\", \"updates\": [{\"cell_id\": 3, \"done\": true}]}\n\n"
                
                "User: 'Tổng số hàng là bao nhiêu?'\n"
                "Response: {\"action\": \"none\", \"reply\": \"Hiện có X sản phẩm trong kho\", \"updates\": []}"
            )
        }
    
    def chat_stream(self, messages: List[Dict[str, str]], system_override: Optional[Dict[str, str]] = None) -> str:
        """
        Stream chat response from Ollama /api/chat
        Returns full assistant content
        
        Args:
            messages: List of chat messages
            system_override: Optional system message to override default (for normalization)
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
            "stream": False,  # Non-streaming for HTTP response
            "options": {
                "temperature": OLLAMA_TEMPERATURE,
                "top_p": OLLAMA_TOP_P,
                "num_ctx": OLLAMA_NUM_CTX,
            },
        }
        
        req = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                
                if result.get("error"):
                    raise RuntimeError(result["error"])
                
                message = result.get("message", {})
                content = message.get("content", "")
                return content.strip()
                
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
    ) -> str:
        """
        Chat with Qwen including inventory context
        
        Args:
            user_message: The user's message
            chat_history: Previous chat messages (optional)
            inventory_context: Current inventory data (optional)
        
        Returns:
            Qwen's response (JSON string)
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
        
        # Get response from Qwen (should be JSON-only)
        response = self.chat_stream(messages)
        return response
    
    def test_connection(self) -> Dict[str, any]:
        """Test connection to Ollama"""
        try:
            url = f"{self.host}/api/tags"
            req = urllib.request.Request(url, method="GET")
            
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", [])]
                
                return {
                    "status": "connected",
                    "host": self.host,
                    "models": models,
                    "current_model": self.model,
                    "model_available": self.model in models
                }
        except Exception as e:
            return {
                "status": "error",
                "host": self.host,
                "error": str(e),
                "current_model": self.model
            }

