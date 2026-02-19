"""
Agentic Honey-Pot API Server
FastAPI application with x-api-key authentication for scam detection and intelligence extraction.
"""

import uuid
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Header, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from models.schemas import AnalyzeRequest, HoneypotResponse, AnalyzeResponse
from graph.workflow import run_honeypot_analysis

settings = get_settings()

# Configure logging
from utils.logger import AgentLogger
AgentLogger.configure(level=settings.log_level)
logger = logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Agentic Honey-Pot API starting up (Gemini Flash Migration)...")
    get_settings().validate_setup()
    logger.info(f"Max engagement turns: {settings.max_engagement_turns}")
    
    # Log Memory status
    memory_status = "enabled" if settings.postgres_enabled and settings.database_url else "disabled"
    logger.info(f"Neon PostgreSQL Memory: {memory_status}")
    
    # Pre-initialize Database Pool to reuse handshake for first request
    if settings.postgres_enabled:
        from memory.postgres_memory import init_db_pool
        logger.info("Pre-warming database connection pool...")
        await init_db_pool()
    
    yield
    logger.info("Agentic Honey-Pot API shutting down...")


app = FastAPI(
    title="Agentic Honey-Pot API",
    description="Multi-agent scam detection and intelligence extraction system with Neon PostgreSQL memory",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Strict CORS is enemy of Hackathons. Allow ALL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_404_headers(request: Request, call_next):
    """Debug middleware to log headers for failed requests."""
    response = await call_next(request)
    if response.status_code == 404 and "ws" in request.url.path:
        logger.error(f"--- 404 DEBUG START ---")
        logger.error(f"Path: {request.url.path}")
        logger.error(f"Scope Type: {request.scope.get('type')}")
        logger.error(f"X-Nginx-Match: {request.headers.get('x-nginx-match')}")
        logger.error(f"X-Debug-Input-Upgrade: {request.headers.get('x-debug-input-upgrade')}")
        logger.error(f"Connection: {request.headers.get('connection')}")
        logger.error(f"Upgrade: {request.headers.get('upgrade')}")
        logger.error(f"All Headers: {dict(request.headers)}")
        logger.error(f"--- 404 DEBUG END ---")
    return response

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors and raw body to debug schema mismatches."""
    try:
        body = await request.body()
        logger.error(f"VALIDATION ERROR: {exc.errors()}")
        logger.error(f"BAD REQUEST BODY: {body.decode()}")
    except Exception as e:
        logger.error(f"Could not read body during validation error: {e}")
    
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": "Invalid Request"}
    )






@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global safety net. Ensures API never crashes and returns valid JSON.
    """
    import traceback
    error_details = traceback.format_exc()
    logger.critical(f"UNHANDLED EXCEPTION: {exc}\n{error_details}")
    
    from utils.safe_response import create_fallback_response
    return create_fallback_response(f"Internal System Error: {str(exc)}")


async def verify_api_key(x_api_key: Optional[str] = Header(None, description="API Key for authentication")):
    """
    Dependency to verify the x-api-key header.
    
    Args:
        x_api_key: API key from request header
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing x-api-key header"
        )
    
    if x_api_key != settings.api_secret_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return x_api_key


def sanitize_message(message: str) -> str:
    """Sanitize input message to prevent issues."""
    # Limit length
    message = message[:settings.max_message_length]
    # Strip whitespace
    message = message.strip()
    return message


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "agentic-honeypot-api",
        "version": "1.1.0",
        "model_used": settings.detection_model,
        "memory_backend": "postgres" if settings.database_url else "disabled"
    }


@app.post(
    "/analyze",
    response_model=HoneypotResponse,
    summary="Analyze message for scam detection",
    description="Analyzes incoming message for scam indicators and extracts intelligence through simulated engagement. Supports multi-turn memory via conversation_id."
)
async def analyze_message(
    request: AnalyzeRequest,
    raw_request: Request,
    background_tasks: BackgroundTasks,  # Fix type hint
    api_key: str = Depends(verify_api_key)
):
    """
    Analyze an incoming message for scam detection and intelligence extraction.
    GUARANTEE: Always returns a valid JSON response.
    """
    # 1. Generate ID safely
    conversation_id = request.conversation_id
    
    # Validation: Ensure conversation_id is a valid UUID
    try:
        if conversation_id:
            uuid.UUID(str(conversation_id))
        else:
            conversation_id = str(uuid.uuid4())
    except ValueError:
        logger.warning(f"Invalid UUID provided: {conversation_id}. Generating new one.")
        conversation_id = str(uuid.uuid4())
        
    request_id = conversation_id[:8]
    
    try:
        # 2. Extract Message Content (Handle Union)
        raw_message = request.message
        message_text = ""
        
        if isinstance(raw_message, str):
            message_text = raw_message
        elif hasattr(raw_message, "text") and raw_message.text:
             message_text = raw_message.text
        elif isinstance(raw_message, dict):
             message_text = raw_message.get("text") or str(raw_message)
        else:
             message_text = str(raw_message) if raw_message else ""
             
        # Sanitize input
        message = sanitize_message(message_text)
        if not message:
            # Soft failure for empty message
            from utils.safe_response import create_fallback_response
            logger.warning(f"[{request_id}] Empty message received")
            return create_fallback_response("Message cannot be empty")
        
        # Log full detailed message now that we have safely parsed it
        logger.info(f"[{request_id}] HEADERS: {raw_request.headers}")
        
        # Use AgentLogger for colored input
        from utils.logger import AgentLogger
        # Passing dummy icon "📥" (ignored by logger) to correctly map title and details
        # Merging message into title to ensure the whole line is colored orange
        AgentLogger._print_colored(f"{request_id}", "orange", "📥", f"ANALYZING MESSAGE BODY: {message}")
        
        # 3. Extract conversation history for multi-turn support (Section 6.2)
        conversation_history = []
        for msg in (request.conversation_history or []):
            conversation_history.append({
                "sender": msg.sender,
                "text": msg.text,
                "timestamp": msg.timestamp
            })
        
        # Extract metadata (Section 6.3)
        metadata = None
        if request.metadata:
            metadata = {
                "channel": request.metadata.channel,
                "language": request.metadata.language,
                "locale": request.metadata.locale
            }
        
        logger.info(f"[{request_id}] Conversation history: {len(conversation_history)} prior messages")
        
        # 4. Execution (Protected)
        # Run workflow with full context
        result = await run_honeypot_analysis(
            message=message,
            max_engagements=settings.max_engagement_turns,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
            metadata=metadata
        )
        
        # 5. Safe Construction — workflow already returns HoneypotResponse.
        # If result is already a HoneypotResponse, use it directly.
        # If it's a plain dict (legacy fallback), wrap it.
        from utils.safe_response import construct_safe_response
        from models.schemas import HoneypotResponse
        if isinstance(result, HoneypotResponse):
            response = result
            # Ensure sessionId is set correctly
            if not response.sessionId:
                response = response.model_copy(update={"sessionId": conversation_id})
        elif isinstance(result, dict):
            response = construct_safe_response(result, conversation_id)
        else:
            response = construct_safe_response({}, conversation_id)
        
        logger.info(f"[{request_id}] Analysis complete. scamDetected={response.scamDetected}")
        return response
        
    except Exception as e:
        # 5. Global Error Boundary
        logger.exception(f"[{request_id}] CRITICAL FAILURE: {str(e)}")
        from utils.safe_response import create_fallback_response
        fb = create_fallback_response("Internal system error during analysis", conversation_id)
        return fb


@app.get("/analyze")
async def analyze_get():
    """Compatibility endpoint for testers checking existence via GET."""
    return {"status": "ready", "message": "Send POST request to analyze"}

@app.post("/analyze/", response_model=HoneypotResponse)
async def analyze_trailing_slash(
    request: AnalyzeRequest,
    raw_request: Request,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """Handle trailing slash to prevent 307 Redirects."""
    return await analyze_message(request, raw_request, background_tasks, api_key)

@app.post("/")
async def root_post(request: Request):
    """Compatibility endpoint for testers posting to root."""
    return {"status": "ready", "message": "Please use /analyze endpoint"}

from dashboard import router as dashboard_router
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
import os

app.include_router(dashboard_router)

# --- WebSocket Fix for Deployment ---
# Sometimes APIRouter prefixes don't play nice with WebSockets behind proxies.
# We explicitly register the route here to guarantee it exists at the correct path.
from fastapi import WebSocket, WebSocketDisconnect
from utils.logger import AgentLogger
import asyncio

@app.websocket("/api/ws/logs")
async def websocket_logs_root(websocket: WebSocket):
    """Stream live logs to dashboard (Root Override)."""
    await websocket.accept()
    queue = asyncio.Queue()
    AgentLogger.register_queue(queue)
    
    try:
        while True:
            # Wait for log entry
            data = await queue.get()
            await websocket.send_json(data)
    except WebSocketDisconnect:
        AgentLogger.remove_queue(queue)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        AgentLogger.remove_queue(queue)

# Serve Frontend (React Build)
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.exists(frontend_dist):
    # Mount assets directory (standard Vite structure)
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # 1. Skip API routes (let them be handled by their routers)
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
             raise HTTPException(status_code=404)
        
        # 2. Check if the exact file exists in dist/ (for vite.svg, favicon.ico, etc.)
        full_file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(full_file_path):
            return FileResponse(full_file_path)
        
        # 3. Fallback to index.html for SPA routing
        return FileResponse(os.path.join(frontend_dist, "index.html"))
else:
    @app.get("/")
    async def root():
        """Root endpoint with API information (Frontend not built)."""
        return {
            "name": "Agentic Honey-Pot API",
            "version": "1.1.0",
            "description": "Multi-agent scam detection and intelligence extraction with Neon PostgreSQL memory",
            "endpoints": {
                "analyze": "POST /analyze - Analyze message for scams",
                "health": "GET /health - Health check",
                "docs": "GET /docs - API documentation"
            }
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        proxy_headers=True, # Trust Nginx headers
        forwarded_allow_ips="*" # Trust all proxies (safe behind Nginx)
    )
