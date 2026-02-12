import asyncio
import logging
from typing import List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from pydantic import BaseModel
from config import get_settings
from utils.logger import AgentLogger
import memory.postgres_memory as pg_memory

router = APIRouter(prefix="/api", tags=["dashboard"])
settings = get_settings()
logger = logging.getLogger(__name__)

# --- Models ---
class LoginRequest(BaseModel):
    password: str

# --- Auth ---
@router.post("/auth/login")
async def login(request: LoginRequest):
    """Simple password check."""
    if request.password == settings.dashboard_password:
        return {"status": "success"}
    
    logger.warning(f"Login failed. Attempted: '{request.password}' vs Configured: '{settings.dashboard_password}'")
    raise HTTPException(status_code=401, detail="Invalid password")

# --- Stats ---
@router.get("/stats")
async def get_stats():
    """Get aggregated top-level stats."""
    return await pg_memory.get_dashboard_stats()

# --- Detections ---
@router.get("/detections")
async def get_detections(limit: int = 20, offset: int = 0):
    """Get list of past detections for infinite scroll."""
    return await pg_memory.get_recent_detections(limit, offset)

@router.get("/detections/{session_id}")
async def get_detection_detail(session_id: str):
    """Get full details for a specific detection."""
    details = await pg_memory.get_detection_details(session_id)
    if not details:
        raise HTTPException(status_code=404, detail="Detection not found")
    return details

# --- Live Logs (WebSocket) ---
# NOTE: This is overridden in main.py for better proxy compatibility (root registration)
# @router.websocket("/ws/logs")
# async def websocket_logs(websocket: WebSocket):
#     """Stream live logs to dashboard."""
#     await websocket.accept()
#     queue = asyncio.Queue()
#     AgentLogger.register_queue(queue)
#     
#     try:
#         while True:
#             # Wait for log entry
#             data = await queue.get()
#             await websocket.send_json(data)
#     except WebSocketDisconnect:
#         AgentLogger.remove_queue(queue)
#     except Exception as e:
#         logger.error(f"WebSocket error: {e}")
#         AgentLogger.remove_queue(queue)
