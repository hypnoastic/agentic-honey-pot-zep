# System Architecture

## Agent Graph (LangGraph)

```
Inbound Message
      │
      ▼
┌─────────────────┐
│  Scam Detection │  ← Prefilter (regex) + LLM classification
└────────┬────────┘
         │ scamDetected = True
         ▼
┌─────────────────┐
│  Intelligence   │  ← Regex corpus scan + LLM verification + recovery merge
│  Extraction     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     Planner     │  ← Decides: ENGAGE | END | JUDGE
└────────┬────────┘
         │ ENGAGE
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Persona Agent  │────▶│  Fact Checker   │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └──────────┬────────────┘
                    │
                    ▼
          ┌──────────────────┐
          │ Response Format  │  ← Assembles final API response
          └────────┬─────────┘
                   │
                   ▼
          ┌──────────────────┐
          │  GUVI Callback   │  ← Fired on session end
          └──────────────────┘
```

## Key Components

| Component      | File                                | Role                                                |
| -------------- | ----------------------------------- | --------------------------------------------------- |
| Main API       | `main.py`                           | FastAPI server, request routing, session locking    |
| State Schema   | `graph/state.py`                    | LangGraph `TypedDict` shared state + entity reducer |
| Workflow       | `graph/workflow.py`                 | LangGraph graph definition and edge routing         |
| Scam Detection | `agents/scam_detection.py`          | Prefilter + LLM scam classification                 |
| Planner        | `agents/planner.py`                 | Turn-by-turn strategy (engage/end/judge)            |
| Persona        | `agents/persona_engagement.py`      | Adaptive victim persona response generation         |
| Fact Checker   | `agents/fact_checker.py`            | Claim consistency guard                             |
| Intelligence   | `agents/intelligence_extraction.py` | Dual-layer entity extraction pipeline               |
| Entity Utils   | `agents/entity_utils.py`            | Normalization, deduplication, noise filtering       |
| Prefilter      | `utils/prefilter.py`                | Regex patterns for detection + extraction           |
| Memory         | `memory/postgres_memory.py`         | Neon PostgreSQL session persistence                 |
| Config         | `config.py`                         | Pydantic settings loaded from `.env`                |

## Data Flow per Request

1. `POST /analyze` received with `{message, conversation_id}`
2. Session lock acquired (prevents concurrent writes for same conversation)
3. Prior history loaded from Postgres
4. **Scam Detection** → sets `scam_detected`, `scam_type`, `confidence`
5. **Intelligence Extraction** → updates `extracted_entities` in state via reducer
6. **Planner** → sets `planner_action` (engage / end)
7. **Persona** → generates human-like stalling/probing reply
8. **Fact Checker** → validates reply consistency
9. **Response Formatter** → builds final response JSON
10. If `engagement_complete` → fires GUVI callback with full intelligence payload
11. Messages persisted to Postgres
12. Session lock released
13. API response returned

## Entity Types Extracted

| Type             | Examples                        |
| ---------------- | ------------------------------- |
| `upiIds`         | `scammer@fakebank`              |
| `phoneNumbers`   | `9876543210`                    |
| `bankAccounts`   | `1234567890123456`              |
| `phishingLinks`  | `http://fake-sbi-verify.ml/kyc` |
| `emailAddresses` | `fraud.agent@fakedomain.in`     |
| `caseIds`        | `SBI-20240203`                  |
| `policyNumbers`  | `LIC1234567890`                 |
| `orderNumbers`   | `OD123456789012`                |
