"""
Flask API Server for RoboDoc with Qwen Integration + STT
"""
import os
import json
import asyncio
import time
from pathlib import Path
from threading import Lock
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from llm_service import LLMService, OLLAMA_TEMPERATURE, OLLAMA_NUM_CTX
from stt_deepgram import DeepgramSTTController, normalize_with_qwen

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Initialize Socket.IO with CORS
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize LLM service
llm_service = LLMService()

# Store chat history per session
chat_sessions = {}

# ============================================================================
# Inventory Management Helpers (Atomic + Lock)
# ============================================================================

inventory_lock = Lock()

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INVENTORY_PATH = (BASE_DIR / "data/inventory.json").resolve()
INVENTORY_PATH = Path(os.environ.get("INVENTORY_JSON_PATH", str(DEFAULT_INVENTORY_PATH)))

def load_inventory():
    """Load inventory from file with lock"""
    with inventory_lock:
        if not INVENTORY_PATH.exists():
            # Create default if missing
            data = {"items": [{"cell_id": i, "product": "", "pick": False, "done": False} for i in range(1, 10)]}
            save_inventory(data)
            return data
        with INVENTORY_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)

def save_inventory(data: dict):
    """Save inventory to file atomically with lock"""
    with inventory_lock:
        INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = INVENTORY_PATH.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        tmp_path.replace(INVENTORY_PATH)
        print(f"💾 Inventory saved to: {INVENTORY_PATH}")

def apply_updates(current: dict, updates: list) -> dict:
    """Apply updates to inventory items - ONLY allow pick and done changes"""
    items = current.get("items", [])
    id_map = {int(it.get("cell_id")): it for it in items if "cell_id" in it}
    
    for upd in updates:
        if not isinstance(upd, dict):
            continue
        if "cell_id" not in upd:
            continue
        try:
            cid = int(upd["cell_id"])
        except:
            continue
        if cid not in id_map:
            continue
        
        item = id_map[cid]
        print(f"🔄 Updating cell {cid}: {upd}")
        
        # ONLY allow pick and done changes
        # Ignore cell_id and product changes from updates
        if "pick" in upd:
            item["pick"] = bool(upd["pick"])
            # If picking, reset done unless explicitly set
            if item["pick"] is True and "done" not in upd:
                item["done"] = False
        if "done" in upd:
            item["done"] = bool(upd["done"])
        
        print(f"✅ Updated item: {item}")
    
    # Sort for stability
    current["items"] = sorted(items, key=lambda x: int(x.get("cell_id", 0)))
    return current

def parse_llm_json(text: str):
    """Parse JSON from LLM response (expects JSON-only, no markdown)"""
    if not text:
        return None
    s = text.strip()
    # Standard case: JSON-only
    if s.startswith("{") and s.endswith("}"):
        try:
            return json.loads(s)
        except Exception as e:
            print(f"⚠️ JSON parse error: {e}")
            print(f"Text was: {s[:200]}")
            return None
    return None


# Store STT controllers per session
stt_controllers = {}


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "RoboDoc Python Backend with STT"
    })


@app.route('/api/ollama/status', methods=['GET'])
def ollama_status():
    """Check Ollama connection status and GPU info"""
    status = llm_service.test_connection()
    return jsonify(status)




def looks_like_inventory_intent(text: str) -> bool:
    """Detect if user message is likely an inventory operation"""
    t = (text or "").lower()
    keywords = ["xóa", "xoá", "ô ", "o ", "cell", "pick", "done", "bỏ chọn", "chọn", "lấy", "thêm", "cho vào", "clear"]
    return any(k in t for k in keywords)


@app.route('/api/chat', methods=['POST'])
def chat():
    """Chat endpoint with Qwen - JSON action based with guardrails"""
    try:
        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({"error": "Missing 'message' in request body"}), 400
        
        user_message = data['message']
        session_id = data.get('session_id', 'default')
        chat_history = data.get('chat_history', [])
        inventory_context = data.get('inventory_context')
        
        # ALWAYS load inventory from file to ensure LLM sees current state
        if not inventory_context:
            inventory_context = load_inventory()
        
        print(f"\n{'='*50}")
        print(f"📩 User message: {user_message}")
        print(f"📦 Inventory context: {len(inventory_context.get('items', []))} items")
        
        # ============================================================
        # DETERMINISTIC FALLBACK: Handle "xóa ô N" directly
        # ============================================================
        import re
        m = re.search(r"(?:ô|o)\s*(\d+)", user_message.lower())
        if ("xóa" in user_message.lower() or "xoá" in user_message.lower() or "clear" in user_message.lower()) and m:
            cid = int(m.group(1))
            print(f"🎯 Deterministic fallback: Xóa ô {cid}")
            
            current = load_inventory()
            current = apply_updates(current, [{"cell_id": cid, "product": "", "pick": False, "done": False}])
            save_inventory(current)
            
            assistant_text = f"✅ Đã xóa hàng ở ô {cid}"
            
            # Store in session history
            if session_id not in chat_sessions:
                chat_sessions[session_id] = []
            chat_sessions[session_id].append({"role": "user", "content": user_message})
            chat_sessions[session_id].append({"role": "assistant", "content": assistant_text})
            
            return jsonify({
                "response": assistant_text,
                "session_id": session_id,
                "inventory_updated": True,
                "updated_inventory": current
            })
        
        # ============================================================
        # Get response from LLM (should be JSON-only)
        # ============================================================
        response_data = llm_service.chat_with_context(
            user_message=user_message,
            chat_history=chat_history,
            inventory_context=inventory_context
        )
        
        response_raw = response_data.get("response", "")
        print(f"🤖 Raw LLM response: {response_raw[:300]}")
        
        # Parse JSON action from response
        action = parse_llm_json(response_raw)
        
        # ============================================================
        # GUARDRAIL: Retry if LLM returned wrong action for inventory intent
        # ============================================================
        if looks_like_inventory_intent(user_message):
            if not isinstance(action, dict) or action.get("action") != "update_inventory" or not action.get("updates"):
                print(f"⚠️ LLM trả sai schema cho inventory intent, đang retry...")
                
                retry_msg = (
                    "Bạn đã trả sai schema. Đây là yêu cầu thao tác inventory.\n"
                    "Hãy trả về ĐÚNG 1 JSON object với action=\"update_inventory\" và updates KHÔNG RỖNG.\n"
                    f"User request: {user_message}"
                )
                response_data_2 = llm_service.chat_with_context(
                    user_message=retry_msg,
                    chat_history=chat_history,
                    inventory_context=load_inventory()
                )
                response_raw_2 = response_data_2.get("response", "")
                print(f"🔄 Retry response: {response_raw_2[:300]}")
                action = parse_llm_json(response_raw_2)
        
        # ============================================================
        # Process action
        # ============================================================
        inventory_updated = False
        updated_inventory = None
        assistant_text = response_raw  # fallback
        
        if isinstance(action, dict):
            act = action.get("action")
            assistant_text = action.get("reply", "") or ""
            reasoning = action.get("reasoning", "")
            
            print(f"✅ Parsed action: {act}")
            print(f"💬 Reply text: {assistant_text}")
            print(f"🧠 Reasoning: {reasoning}")
            print(f"⏱️  LLM Response Time: {response_data.get('elapsed_time', 0):.2f}s")
            print(f"🎯 Tokens: {response_data.get('tokens_total', 0)} total")
            
            if act == "update_inventory":
                updates = action.get("updates", [])
                print(f"🔄 {len(updates)} update(s) to apply")
                
                # Load current inventory and apply updates
                current = load_inventory()
                current = apply_updates(current, updates)
                save_inventory(current)
                
                inventory_updated = True
                updated_inventory = current
                
                if not assistant_text:
                    assistant_text = "✅ Đã cập nhật inventory."
            
            elif act == "none":
                # No update, just reply
                if not assistant_text:
                    assistant_text = "OK."
                print(f"ℹ️ No inventory update needed")
        else:
            print(f"⚠️ Could not parse JSON from response")
            # Fallback: use raw response as text
            assistant_text = response_raw
        
        # Store in session history (use assistant_text, not raw JSON)
        if session_id not in chat_sessions:
            chat_sessions[session_id] = []
        
        chat_sessions[session_id].append({"role": "user", "content": user_message})
        chat_sessions[session_id].append({"role": "assistant", "content": assistant_text})
        
        result = {
            "response": assistant_text,
            "session_id": session_id
        }
        
        if inventory_updated:
            result["inventory_updated"] = True
            result["updated_inventory"] = updated_inventory
            # Include raw action for debugging
            result["action"] = action
        
        print(f"{'='*50}\n")
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Chat error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500





@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    """Get current inventory state"""
    try:
        data = load_inventory()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/inventory/update', methods=['POST'])
def update_inventory():
    """Update inventory.json file"""
    try:
        data = request.get_json()
        
        if not data or 'items' not in data:
            return jsonify({"error": "Missing 'items' in request body"}), 400
        
        save_inventory(data)
        return jsonify({"status": "success", "message": "Inventory updated successfully"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/inventory/reset', methods=['POST'])
def reset_inventory_endpoint():
    """Reset inventory.json to default state"""
    try:
        default_data = {
            "items": [
                {"cell_id": i, "product": "", "pick": False, "done": False}
                for i in range(1, 10)
            ]
        }
        save_inventory(default_data)
        return jsonify({"status": "success", "message": "Inventory reset successfully", "data": default_data})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/settings/reset', methods=['POST'])
def reset_settings():
    """Reset settings.json to default state"""
    try:
        import json
        settings_path = os.path.join(os.path.dirname(__file__), '../frontend/public/data/settings.json')
        
        # Default settings data
        default_data = {
            "robot_settings": {
                "home_position": {"x": 0, "y": 0, "z": 0},
                "delta_adjustments": {"delta_x": 10.0, "delta_y": 10.0, "delta_z": 5.0},
                "grid_positions": {
                    f"cell_{i}": {
                        "x": 50 + ((i-1) % 3) * 100,
                        "y": 50 + ((i-1) // 3) * 100,
                        "z": 10
                    }
                    for i in range(1, 10)
                },
                "speed": 100,
                "acceleration": 50
            },
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        
        # Write to file
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, ensure_ascii=False, indent=4)
        
        return jsonify({"status": "success", "message": "Settings reset successfully", "data": default_data})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/robot/command', methods=['POST'])
def robot_command():
    """Execute robot commands (start, stop, reset)"""
    try:
        data = request.get_json()
        
        if not data or 'command' not in data:
            return jsonify({"error": "Missing 'command' in request body"}), 400
        
        command = data['command'].lower()
        
        if command == 'start':
            # Logic to start robot picking
            return jsonify({
                "status": "success",
                "message": "Robot started picking items",
                "command": "start"
            })
        
        elif command == 'stop':
            # Logic to stop robot
            return jsonify({
                "status": "success",
                "message": "Robot stopped",
                "command": "stop"
            })
        
        elif command == 'reset':
            # Reset inventory only, not settings
            import json
            inventory_path = os.path.join(os.path.dirname(__file__), '../frontend/public/data/inventory.json')
            
            default_data = {
                "items": [
                    {"cell_id": i, "product": "", "pick": False, "done": False}
                    for i in range(1, 10)
                ]
            }
            
            with open(inventory_path, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=4)
            
            return jsonify({
                "status": "success",
                "message": "Robot reset - inventory cleared",
                "command": "reset",
                "data": default_data
            })
        
        else:
            return jsonify({"error": f"Unknown command: {command}"}), 400
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# Socket.IO Events for STT
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f"Client connected: {request.sid}")
    emit('connected', {'session_id': request.sid})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print(f"Client disconnected: {request.sid}")
    # Cleanup STT controller
    if request.sid in stt_controllers:
        del stt_controllers[request.sid]


@socketio.on('start_stt')
def handle_start_stt(data):
    """Start STT session"""
    print(f"Starting STT for {request.sid}")
    
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Create STT controller
        controller = DeepgramSTTController(loop)
        stt_controllers[request.sid] = {'controller': controller, 'loop': loop}
        
        # Start streaming (run in event loop)
        loop.run_until_complete(controller.start_streaming())
        
        emit('stt_started', {'message': 'STT started successfully'})
        print(f"STT started for {request.sid}")
        
    except Exception as e:
        print(f"Error starting STT: {e}")
        emit('error', {'message': str(e)})


@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    """Receive audio chunk from frontend"""
    if request.sid not in stt_controllers:
        emit('error', {'message': 'STT not started'})
        return
    
    try:
        stt_data = stt_controllers[request.sid]
        controller = stt_data['controller']
        loop = stt_data['loop']
        
        # Feed audio to controller
        audio_base64 = data.get('audio')
        if audio_base64:
            # Run async feed_audio in the loop
            asyncio.run_coroutine_threadsafe(
                controller.feed_audio(audio_base64),
                loop
            )
    
    except Exception as e:
        print(f"Error processing audio chunk: {e}")


@socketio.on('stop_stt')
def handle_stop_stt(data):
    """Stop STT and get transcript"""
    print(f"Stopping STT for {request.sid}")
    
    if request.sid not in stt_controllers:
        emit('error', {'message': 'STT not started'})
        return
    
    try:
        stt_data = stt_controllers[request.sid]
        controller = stt_data['controller']
        loop = stt_data['loop']
        
        # Stop streaming and collect results
        result = loop.run_until_complete(controller.stop_streaming_and_collect())
        
        raw_full = result.get('raw_full', '').strip()
        last_interim = result.get('last_interim', '').strip()
        
        print(f"Raw transcript: {raw_full}")
        print(f"Last interim: {last_interim}")
        
        # Normalize with Qwen if we have transcript
        normalized = raw_full or last_interim
        
        if result.get('spoken_trace', '').strip():
            payload = {
                'spoken_trace': result.get('spoken_trace', ''),
                'stream_log_tail': result.get('stream_log_tail', []),
                'final_segments': result.get('final_segments', []),
                'raw_full': raw_full,
                'last_interim': last_interim,
            }
            
            try:
                # Run normalization
                normalized = loop.run_until_complete(normalize_with_qwen(loop, payload))
                print(f"Normalized: {normalized}")
            except Exception as e:
                print(f"Qwen normalization error: {e}")
                normalized = raw_full or last_interim
        
        # Send result back to frontend
        emit('stt_stopped', {
            'raw_full': raw_full,
            'last_interim': last_interim,
            'normalized': normalized,
            'final_segments': result.get('final_segments', []),
            'spoken_trace': result.get('spoken_trace', ''),
            'stream_log_tail': result.get('stream_log_tail', [])
        })
        
        # Cleanup
        loop.close()
        del stt_controllers[request.sid]
        
        print(f"STT stopped for {request.sid}")
        
    except Exception as e:
        print(f"Error stopping STT: {e}")
        emit('error', {'message': str(e)})


if __name__ == '__main__':
    port = int(os.environ.get('FLASK_PORT', 5000))
    
    print(f"\n{'='*80}")
    print(f"🚀 Starting RoboDoc Python Backend on port {port}")
    print(f"{'='*80}")
    print(f"🤖 LLM Model: {llm_service.model}")
    print(f"🔗 Ollama Host: {llm_service.host}")
    print(f"🎤 STT: Deepgram + LLM normalization enabled")
    print(f"⚙️  Config: temp={OLLAMA_TEMPERATURE}, ctx={OLLAMA_NUM_CTX}")
    print(f"📡 Testing Ollama connection...")
    
    status = llm_service.test_connection()
    if status['status'] == 'connected':
        print(f"✅ Ollama connected!")
        print(f"   📦 Available models: {len(status.get('models', []))} total")
        print(f"   🎯 Current model: {status.get('current_model')}")
        print(f"   🎮 GPU Status: {status.get('gpu_status', 'Unknown')}")
        print(f"   📏 Context Window: {status.get('context_window', 'N/A')} tokens")
    else:
        print(f"⚠️  Ollama connection failed: {status.get('error')}")
    
    print(f"{'='*80}\n")
    
    # Run with Socket.IO
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
