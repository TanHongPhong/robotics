# RoboDoc Integration Guide: Qwen LLM

## Overview

This guide explains how to set up and run the complete RoboDoc system with Qwen LLM integration.

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────┐
│  React Frontend │ ───▶ │  Python Backend  │ ───▶ │   Ollama    │
│  (Port 5173)    │      │  (Port 5000)     │      │ (Port 11434)│
│                 │      │                  │      │             │
│  - ChatPage     │      │  - Flask API     │      │  - Qwen 2.5 │
│  - Inventory    │      │  - Qwen Service  │      │             │
└─────────────────┘      └──────────────────┘      └─────────────┘
```

## Prerequisites

1. **Python 3.8+** installed
2. **Node.js 18+** installed
3. **Ollama** installed and running
4. **Qwen model** pulled in Ollama

## Setup Steps

### 1. Install Ollama and Qwen

```bash
# Install Ollama (if not installed)
# Visit: https://ollama.ai/download

# Pull Qwen model
ollama pull qwen2.5:1.5b-instruct

# Start Ollama server (if not running)
ollama serve
```

### 2. Setup Python Backend

```bash
cd D:\A UEH_UNIVERSITY\UEH_Subjects\robotics\python_backend

# Create virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate   # On Windows

# Install dependencies
pip install -r requirements.txt

# Configure .env file (already created, verify settings)
# Make sure OLLAMA_HOST and OLLAMA_MODEL are correct
```

### 3. Setup React Frontend

```bash
cd D:\A UEH_UNIVERSITY\UEH_Subjects\robotics\frontend

# Install dependencies (if not done)
npm install

# Configure .env file (already created)
# Verify VITE_PYTHON_API_URL=http://localhost:5000
```

## Running the System

### Option 1: Run Manually

**Terminal 1 - Python Backend:**
```bash
cd D:\A UEH_UNIVERSITY\UEH_Subjects\robotics\python_backend
python app.py
```

**Terminal 2 - React Frontend:**
```bash
cd D:\A UEH_UNIVERSITY\UEH_Subjects\robotics\frontend
npm run dev
```

### Option 2: Run with PowerShell Script (Create this)

Create `start_all.ps1` in robotics folder:
```powershell
# Start Ollama (if not running)
Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden

# Start Python Backend
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd python_backend; python app.py"

# Wait 3 seconds
Start-Sleep -Seconds 3

# Start React Frontend
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm run dev"

Write-Host "✅ All services started!"
```

Then run:
```bash
.\start_all.ps1
```

## Testing the Integration

1. **Open Browser:** http://localhost:5173

2. **Navigate to Chat Page** (click robot icon in sidebar)

3. **Check Connection Status:**
   - Should see "● Connected" if Ollama is running
   - Should see "⚠️ Warning" if Ollama is not connected

4. **Test Chat:**
   ```
   User: "How many items are picked?"
   Qwen: [AI response with real inventory data]
   
   User: "What is the inventory status?"
   Qwen: [AI response with current stats]
   ```

5. **Test Inventory Context:**
   - Go to Inventory page
   - Pick/unpick some items
   - Return to Chat page
   - Ask about inventory
   - Qwen should respond with current data!

## API Endpoints

### Python Backend (Port 5000)

- `GET /health` - Health check
- `GET /api/ollama/status` - Check Ollama connection
- `POST /api/chat` - Send message to Qwen
- `GET /api/chat/history/<session_id>` - Get chat history
- `DELETE /api/chat/history/<session_id>` - Clear chat history
- `GET /api/chat/sessions` - List active sessions

## Troubleshooting

### Qwen not responding

1. **Check Ollama is running:**
   ```bash
   curl http://localhost:11434/api/tags
   ```

2. **Check Python backend is running:**
   ```bash
   curl http://localhost:5000/health
   ```

3. **Check model is loaded:**
   ```bash
   ollama list
   # Should see qwen2.5:1.5b-instruct
   ```

### CORS errors

- Make sure Python backend has `flask-cors` installed
- Check Python backend console for errors

### Frontend can't connect

- Verify `.env` file in frontend has correct `VITE_PYTHON_API_URL`
- Restart Vite dev server after changing `.env`

## Features

✅ **Real-time Chat** with Qwen LLM
✅ **Inventory Context** - Qwen knows current inventory state
✅ **Chat History** - Maintains conversation context
✅ **Session Management** - Multiple chat sessions
✅ **Connection Status** - Shows Ollama connection state
✅ **Fallback Responses** - Works even if Ollama is offline
✅ **Export Chat** - Download chat history as JSON

## Environment Variables

### Python Backend (.env)
```
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:1.5b-instruct
OLLAMA_TEMPERATURE=0.3
OLLAMA_TOP_P=0.9
OLLAMA_NUM_CTX=4096
FLASK_PORT=5000
FLASK_DEBUG=True
```

### React Frontend (.env)
```
VITE_PYTHON_API_URL=http://localhost:5000
```

## Next Steps

- Add voice input integration (using existing Deepgram code)
- Add text-to-speech for AI responses
- Implement real-time inventory updates via WebSocket
- Add user authentication
- Deploy to production server
