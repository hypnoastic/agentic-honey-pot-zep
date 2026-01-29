# Agentic Honey-Pot for Scam Detection & Intelligence Extraction

A multi-agent system built with LangGraph, Google Gemini, and FastAPI that detects scam messages and autonomously engages scammers to extract intelligence (bank accounts, UPI IDs, phishing URLs).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Server (/analyze)                        │
│                        x-api-key Authentication                          │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          LangGraph Workflow                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Shared State (TypedDict)                      │   │
│  │  original_message, scam_detected, conversation_history,         │   │
│  │  extracted_entities, confidence_score, final_response           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                   │                                      │
│  ┌────────────────┐      ┌────────┴────────┐                            │
│  │ Scam Detection │──────▶   Is Scam?      │                            │
│  │    (Gemini)    │      └───┬─────────┬───┘                            │
│  └────────────────┘       Yes│         │No                              │
│                              ▼         ▼                                 │
│  ┌────────────────┐   ┌──────────────────┐                              │
│  │    Persona     │   │  Direct Return   │                              │
│  │  Engagement    │◀──│   (Not Scam)     │                              │
│  │  (Gemini)      │   └──────────────────┘                              │
│  └───────┬────────┘                                                      │
│          │ ◀──── Mock Scammer API                                        │
│          ▼                                                               │
│  ┌────────────────┐                                                      │
│  │  Intelligence  │                                                      │
│  │  Extraction    │                                                      │
│  └───────┬────────┘                                                      │
│          ▼                                                               │
│  ┌────────────────┐                                                      │
│  │  Confidence    │                                                      │
│  │   Scoring      │                                                      │
│  └───────┬────────┘                                                      │
│          ▼                                                               │
│  ┌────────────────┐                                                      │
│  │   Response     │                                                      │
│  │  Formatter     │                                                      │
│  └───────┬────────┘                                                      │
└──────────┼──────────────────────────────────────────────────────────────┘
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Structured JSON Response                            │
│  { is_scam, scam_type, confidence_score, extracted_entities, summary } │
└─────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Setup Environment

```bash
cd "/Users/yashkumar/Hakathon/Agentic Honey-Pot"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your Google Gemini API key
```

### 3. Start the Mock Scammer API (Terminal 1)

```bash
source venv/bin/activate
uvicorn mock_scammer_api:app --port 8001
```

### 4. Start the Main API (Terminal 2)

```bash
source venv/bin/activate
uvicorn main:app --port 8000 --reload
```

### 5. Test the API

```bash
# Test scam detection
curl -X POST "http://localhost:8000/analyze" \
  -H "Content-Type: application/json" \
  -H "x-api-key: test-api-key-123" \
  -d '{"message": "Congratulations! You won Rs 50000! Send Rs 500 to UPI: winner@paytm to claim!"}'
```

## API Endpoints

### POST /analyze

Analyze a message for scam detection.

**Headers:**

- `x-api-key`: Required API key for authentication

**Request Body:**

```json
{
  "message": "Suspicious message text"
}
```

**Response:**

```json
{
  "is_scam": true,
  "scam_type": "LOTTERY_FRAUD",
  "confidence_score": 0.85,
  "extracted_entities": {
    "bank_accounts": [],
    "upi_ids": ["winner@paytm"],
    "phishing_urls": []
  },
  "conversation_summary": "Detected lottery scam requesting UPI payment..."
}
```

### GET /health

Health check endpoint.

### GET /docs

Interactive API documentation (Swagger UI).

## Project Structure

```
Agentic Honey-Pot/
├── main.py                    # FastAPI application
├── config.py                  # Configuration management
├── mock_scammer_api.py        # Mock Scammer API for testing
├── requirements.txt           # Python dependencies
├── .env.example               # Environment template
├── agents/
│   ├── scam_detection.py      # Scam detection using Gemini
│   ├── persona_engagement.py  # Believable persona for engagement
│   ├── intelligence_extraction.py  # Extract bank/UPI/URLs
│   ├── confidence_scoring.py  # Score confidence
│   └── response_formatter.py  # Format final response
├── graph/
│   ├── state.py               # LangGraph state schema
│   └── workflow.py            # LangGraph workflow
├── models/
│   └── schemas.py             # Pydantic models
└── tests/
    └── test_api.py            # API tests
```

## Agents

| Agent                   | Purpose                                            |
| ----------------------- | -------------------------------------------------- |
| Scam Detection          | Analyzes messages for scam indicators using Gemini |
| Persona Engagement      | Creates believable human persona to engage scammer |
| Intelligence Extraction | Extracts bank accounts, UPI IDs, phishing URLs     |
| Confidence Scoring      | Calculates overall confidence score                |
| Response Formatter      | Formats final structured JSON response             |

## Running Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

## Environment Variables

| Variable                 | Description                  | Default          |
| ------------------------ | ---------------------------- | ---------------- |
| GOOGLE_API_KEY           | Google Gemini API key        | Required         |
| API_SECRET_KEY           | API authentication key       | test-api-key-123 |
| MAX_ENGAGEMENT_TURNS     | Max scammer engagement turns | 5                |
| SCAM_DETECTION_THRESHOLD | Minimum confidence for scam  | 0.6              |
| MOCK_SCAMMER_PORT        | Mock Scammer API port        | 8001             |
