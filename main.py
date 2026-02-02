"""
Agentic Honey-Pot API Server
FastAPI application with x-api-key authentication for scam detection and intelligence extraction.
Includes Zep Context AI memory integration for persistent conversational context.
"""

import uuid
import logging
from contextlib import asynccontextmanager
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

# Parse CORS origins from config
cors_origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]

# Add CORS middleware with configurable origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify_api_key(x_api_key: str = Header(..., description="API Key for authentication")):
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
    api_key: str = Depends(verify_api_key)
):
    """
    Analyze an incoming message for scam detection and intelligence extraction.
    
    The system will:
    1. Load prior context from Zep memory (if conversation_id provided)
    2. Detect if the message is a scam attempt
    3. If scam detected, engage using a believable persona
    4. Extract bank accounts, UPI IDs, and phishing URLs
    5. Persist conversation to Zep memory for future context
    6. Return structured intelligence report
    
    Args:
        request: AnalyzeRequest with the message to analyze
        api_key: Valid API key (via dependency)
        
    Returns:
        AnalyzeResponse with scam detection results and extracted entities
    """
    # Generate or use provided conversation ID
    conversation_id = request.conversation_id or str(uuid.uuid4())
    request_id = conversation_id[:8]
    
    # Sanitize input
    message = sanitize_message(request.message)
    
    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )
    
    logger.info(f"[{request_id}] Analyzing message: {message[:100]}...")
    
    try:
        # Run the honeypot workflow (Zep memory is handled inside)
        result = await run_honeypot_analysis(
            message=message,
            max_engagements=settings.max_engagement_turns,
            conversation_id=conversation_id,
            execution_mode=request.mode
        )
        
        # Construct response
        response = AnalyzeResponse(
            is_scam=result.get("is_scam", False),
            scam_type=result.get("scam_type"),
            confidence_score=result.get("confidence_score", 0.0),
            extracted_entities=ExtractedEntities(
                bank_accounts=result.get("extracted_entities", {}).get("bank_accounts", []),
                upi_ids=result.get("extracted_entities", {}).get("upi_ids", []),
                phishing_urls=result.get("extracted_entities", {}).get("phishing_urls", [])
            ),
            conversation_summary=result.get("conversation_summary", ""),
            agent_reply=result.get("final_response", {}).get("agent_response") if request.mode == "live" else None,
            conversation_id=conversation_id
        )
        
        logger.info(f"[{request_id}] Analysis complete. Is scam: {response.is_scam}, Type: {response.scam_type}")
        return response
        
    except Exception as e:
        logger.error(f"[{request_id}] Analysis error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


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
