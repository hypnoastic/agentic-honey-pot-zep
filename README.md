# Honeypot API

## Description

An autonomous scambaiting system that detects inbound scam messages, deploys an adaptive victim persona to stall and engage the scammer, and extracts actionable intelligence (UPI IDs, bank accounts, phishing URLs, case IDs, etc.) across multi-turn conversations. The system uses a LangGraph agentic graph with specialized agents for detection, persona generation, intelligent planning, fact-checking, and entity extraction.

## Tech Stack

- **Language / Framework:** Python 3.11, FastAPI, LangGraph
- **Key Libraries:** LangChain, Pydantic v2, asyncpg, httpx, uvicorn
- **LLM / AI Models:** Google Gemini 2.5 Flash (planner, persona, extraction, detection)
- **Memory:** Neon PostgreSQL (pgvector) for cross-session entity persistence
- **Extraction:** Dual-layer pipeline — deterministic regex prefilter + LLM verification

## Setup Instructions

1. **Clone the repository**

   ```bash
   git clone <repo-url>
   cd agentic-honey-pot
   ```

2. **Install dependencies**

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Set environment variables** — copy `.env.example` to `.env` and fill in:

   ```bash
   cp .env.example .env
   # Edit .env with your keys:
   # GEMINI_API_KEY, DATABASE_URL, API_SECRET_KEY
   ```

4. **Initialize the database** (first run only)

   ```bash
   python scripts/db_init.py
   ```

5. **Run the application**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

## API Endpoint

- **URL:** `http://<your-server>/analyze`
- **Method:** `POST`
- **Authentication:** `x-api-key` header

**Request:**

```json
{
  "message": "Urgent! Your SBI account is blocked. Verify KYC immediately.",
  "conversation_id": "session-abc123"
}
```

**Response:**

```json
{
  "sessionId": "session-abc123",
  "scamDetected": true,
  "scamType": "BANK_IMPERSONATION",
  "confidenceLevel": 0.95,
  "extractedIntelligence": {
    "phoneNumbers": ["9876543210"],
    "upiIds": ["scammer@fakebank"],
    "phishingLinks": ["http://fake-sbi-verify.ml/kyc"],
    "bankAccounts": [],
    "emailAddresses": [],
    "caseIds": [],
    "policyNumbers": [],
    "orderNumbers": []
  },
  "engagementDurationSeconds": 120,
  "totalMessagesExchanged": 8,
  "agentNotes": "Scammer impersonating SBI security department..."
}
```

## Approach

### Scam Detection

- A deterministic prefilter (`utils/prefilter.py`) scans every inbound message with pattern-matched rules covering UPI fraud, bank impersonation, phishing, lottery scams, and investment fraud — with weighted confidence scores.
- If the prefilter score crosses the threshold, the Scam Detection Agent runs a full LLM analysis for nuanced classification.

### Intelligence Extraction

- **Layer 1 (Regex):** A comprehensive set of named-capture regexes extracts UPI IDs, phone numbers, bank accounts, phishing URLs, emails, case IDs, policy numbers, and order numbers from the full conversation corpus.
- **Layer 2 (LLM Verification):** The Gemini model verifies regex candidates against conversational context and recovers obfuscated entities.
- **Recovery Merge:** All regex-found entities are merged with LLM results to ensure nothing is dropped.
- Normalization and deduplication clean up the final entity set per type.

### Engagement Maintenance

- The **Planner Agent** decides per-turn whether to stall, extract deeper, or conclude — enforcing a minimum engagement window before ending.
- The **Persona Agent** dynamically generates a culturally-grounded victim persona (elderly, retired, regional accent) and maintains it consistently across turns via Postgres memory.
- A **Fact Checker** guards against persona inconsistencies, ensuring the honeypot response stays believable.
- The system fires a final callback to the GUVI endpoint once engagement is complete with all extracted intelligence.
