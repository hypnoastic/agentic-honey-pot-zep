"""
Agentic Honey-Pot API Server
FastAPI application with x-api-key authentication for scam detection and intelligence extraction.
Includes Zep Context AI memory integration for persistent conversational context.
"""

import uuid
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from models.schemas import AnalyzeRequest, AnalyzeResponse, ExtractedEntities
from graph.workflow import run_honeypot_analysis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Agentic Honey-Pot API starting up (OpenAI Edition)...")
    logger.info(f"OpenAI Model: {settings.openai_model}")
    logger.info(f"Max engagement turns: {settings.max_engagement_turns}")
    
    # Log Zep status
    zep_status = "enabled" if settings.zep_api_key and settings.zep_enabled else "disabled"
    logger.info(f"Zep Context AI Memory: {zep_status}")
    
    yield
    logger.info("Agentic Honey-Pot API shutting down...")


app = FastAPI(
    title="Agentic Honey-Pot API",
    description="Multi-agent scam detection and intelligence extraction system with Zep memory",
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
    """Health check endpoint."""
    # Check Zep availability
    zep_available = False
    try:
        from memory.zep_memory import is_zep_available
        zep_available = is_zep_available()
    except ImportError:
        pass
    
    return {
        "status": "healthy",
        "service": "agentic-honeypot-api",
        "version": "1.1.0",
        "openai_model": settings.openai_model,
        "zep_memory": "enabled" if zep_available else "disabled"
    }


@app.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Analyze message for scam detection",
    description="Analyzes incoming message for scam indicators and extracts intelligence through simulated engagement. Supports multi-turn memory via conversation_id."
)
async def analyze_message(
    request: AnalyzeRequest,
    raw_request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Analyze an incoming message for scam detection and intelligence extraction.
    GUARANTEE: Always returns a valid JSON response.
    """
    # 1. Generate ID safely
    conversation_id = request.conversation_id or str(uuid.uuid4())
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
            return create_fallback_response(conversation_id, "Message cannot be empty")
        
        # Log full detailed message now that we have safely parsed it
        logger.info(f"[{request_id}] HEADERS: {raw_request.headers}")
        logger.info(f"[{request_id}] ANALYZING MESSAGE BODY: {message}")
        
        # 3. Execution (Protected)
        # Run workflow
        result = await run_honeypot_analysis(
            message=message,
            max_engagements=settings.max_engagement_turns,
            conversation_id=conversation_id
        )
        
        # 4. Safe Construction
        from utils.safe_response import construct_safe_response
        response = construct_safe_response(result, conversation_id)
        
        logger.info(f"[{request_id}] Analysis complete. Is scam: {response.is_scam}")
        return response
        
    except Exception as e:
        # 5. Global Error Boundary
        logger.exception(f"[{request_id}] CRITICAL FAILURE: {str(e)}")
        from utils.safe_response import create_fallback_response
        return create_fallback_response(conversation_id, "Internal system error during analysis")


@app.get("/analyze")
async def analyze_get():
    """Compatibility endpoint for testers checking existence via GET."""
    return {"status": "ready", "message": "Send POST request to analyze"}

@app.post("/analyze/")
async def analyze_trailing_slash(
    request: AnalyzeRequest,
    api_key: str = Depends(verify_api_key)
):
    """Handle trailing slash to prevent 307 Redirects."""
    return await analyze_message(request, api_key)

@app.post("/")
async def root_post(request: Request):
    """Compatibility endpoint for testers posting to root."""
    return {"status": "ready", "message": "Please use /analyze endpoint"}

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Agentic Honey-Pot API",
        "version": "1.1.0",
        "description": "Multi-agent scam detection and intelligence extraction with Zep memory",
        "model_provider": "OpenAI",
        "features": {
            "zep_memory": "Persistent conversational memory for multi-turn context",
            "multi_agent": "LangGraph-orchestrated agent pipeline",
            "scam_detection": "Advanced LLM-based scam analysis"
        },
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
        reload=settings.debug
    )
