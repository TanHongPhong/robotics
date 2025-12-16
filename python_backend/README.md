# RoboDoc Python Backend

Flask backend server with Qwen LLM integration via Ollama.

## Setup

1. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

2. **Configure environment variables:**
Edit `.env` file with your Ollama configuration.

3. **Make sure Ollama is running:**
```bash
ollama serve
```

4. **Pull Qwen model (if not already):**
```bash
ollama pull qwen2.5:1.5b-instruct
```

## Running the Server

```bash
python app.py
```

Server will start on `http://localhost:5000`

## API Endpoints

### Health Check
```
GET /health
```

### Check Ollama Status
```
GET /api/ollama/status
```

### Chat with Qwen
```
POST /api/chat
Content-Type: application/json

{
  "message": "Hello, how are you?",
  "session_id": "user123",
  "inventory_context": {
    "items": [...]
  }
}
```

### Get Chat History
```
GET /api/chat/history/<session_id>
```

### Clear Chat History
```
DELETE /api/chat/history/<session_id>
```

### List Sessions
```
GET /api/chat/sessions
```

## Integration with Frontend

The Python backend runs on port 5000 (default) and provides REST API endpoints that the React frontend can call to interact with Qwen LLM.

CORS is enabled for frontend communication.
