# Setup & Troubleshooting Guide

This guide covers environment configuration, common errors, and deployment tips for the Neepot AI Agentic Honey-Pot.

## 🛠️ Environment Setup

### 1. Prerequisites

- **Python 3.10+**
- **PostgreSQL** (Optional, but recommended for memory persistence)
- **API Keys**:
  - Google Gemini API (`GEMINI_API_KEY`)
  - Serper Dev API (`SERPER_API_KEY`) - _Optional for Fact Checker_

### 2. Configuration (`.env`)

Create a `.env` file in the root directory.

```bash
# --- AI Configuration ---
GEMINI_API_KEY=AIzaSy...           # REQUIRED
PLANNER_MODEL=gemini-2.5-flash     # Recommended
PERSONA_MODEL=gemini-2.5-flash
SCAM_DETECTION_THRESHOLD=0.6       # 0.0 to 1.0 (Lower = more sensitive)

# --- Security ---
API_SECRET_KEY=my-secret-key-123   # MUST match x-api-key header in requests

# --- Database (Neon/Postgres) ---
POSTGRES_ENABLED=true
DATABASE_URL=postgres://user:pass@host:5432/dbname?sslmode=require

# --- Operational ---
MAX_ENGAGEMENT_TURNS=12            # Max turns before forced exit
LOG_LEVEL=INFO                     # DEBUG, INFO, WARNING, ERROR
```

## 🚀 Running the Server

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run server with hot-reload
uvicorn main:app --reload
```

Server runs at: `http://127.0.0.1:8000`

### Production Deployment

```bash
# Run with 4 worker processes
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000
```

## ❓ Common Issues & Troubleshooting

### 1. `401 Unauthorized` / `Missing x-api-key header`

- **Cause**: The request is missing the `x-api-key` header or it doesn't match `API_SECRET_KEY`.
- **Fix**: Ensure your request includes:
  ```bash
  curl -H "x-api-key: my-secret-key-123" ...
  ```

### 2. `ConnectionError: Can't connect to MySQL server` (or Postgres)

- **Cause**: Database is unreachable or `DATABASE_URL` is incorrect.
- **Fix**:
  - Check internet connection.
  - Verify `DATABASE_URL` format.
  - Set `POSTGRES_ENABLED=false` to run in **Stateless Mode** (No memory).

### 3. "Scam Not Detected" on obvious scams

- **Cause**: `SCAM_DETECTION_THRESHOLD` might be too high (default 0.8).
- **Fix**: Lower it to `0.6` in `.env`.
- **Check**: Ensure `scam_detection.py` blacklist hasn't been modified to exclude the topic.

### 4. "ImportError: No module named 'agents'"

- **Cause**: Python path issue when running scripts from subdirectories.
- **Fix**: Run from root directory:
  ```bash
  export PYTHONPATH=$PYTHONPATH:.
  python scripts/test_model_connection.py
  ```

### 5. "ResourceExhausted" (Gemini API)

- **Cause**: Quota limit reached on free tier.
- **Fix**:
  - Wait 60 seconds.
  - Upgrade to paid tier.
  - Switch to a smaller model if applicable.

## 🧪 Testing

### Run Robustness Test

We include a script to verify API stability:

```bash
python scripts/test_api_robustness.py
```

### Verify Extraction Logic

Check if phone numbers are being correctly normalized:

```bash
python scripts/test_extraction_fix.py
```
