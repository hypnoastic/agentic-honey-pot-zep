# Zep Context AI Integration

## Overview

This document explains how the Agentic Honey-Pot system uses **Zep Context AI** as a temporal knowledge graph to enhance scam detection and intelligence extraction capabilities.

## What is Zep?

Zep is a context engineering platform that provides:

- **Persistent Memory**: Long-term storage of conversation history
- **Temporal Knowledge Graph**: Structured relationships between scammers, tactics, and extracted intelligence
- **Context Assembly**: Retrieves relevant context for each interaction in sub-200ms
- **User Profiling**: Builds behavioral patterns from interactions

## Our Knowledge Graph Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                     ZEP KNOWLEDGE GRAPH                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐          ┌─────────────────────────────┐  │
│  │  HONEYPOT USER  │          │      SCAM INTELLIGENCE      │  │
│  │  honeypot-system│◄────────►│  • Detected scam types      │  │
│  └────────┬────────┘          │  • Extracted bank accounts  │  │
│           │                   │  • Extracted UPI IDs        │  │
│           │ owns              │  • Phishing URLs discovered │  │
│           ▼                   │  • Scam indicators/patterns │  │
│  ┌─────────────────┐          │  • Confidence scores        │  │
│  │    THREADS      │          └─────────────────────────────┘  │
│  │ (Conversations) │                                           │
│  ├─────────────────┤                                           │
│  │ • Thread ID     │                                           │
│  │ • User context  │                                           │
│  │ • Messages      │                                           │
│  └────────┬────────┘                                           │
│           │                                                     │
│           │ contains                                            │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────────┐           │
│  │              MESSAGES                           │           │
│  ├─────────────────────────────────────────────────┤           │
│  │ Role: user (Scammer) / assistant (Honeypot)    │           │
│  │ Content: Actual message text                    │           │
│  │ Name: "Scammer" / "Honeypot Agent"             │           │
│  │ Timestamp: When message was sent                │           │
│  └─────────────────────────────────────────────────┘           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. On New Request

```
User Request ──► Load Zep Context ──► Inject into LangGraph State
                      │
                      ├── Prior conversation history
                      ├── Previously extracted entities
                      ├── Known scam patterns
                      └── User context summary
```

### 2. During Analysis

```
LangGraph Workflow
     │
     ├── Scam Detection (uses Zep context for pattern matching)
     │
     ├── Persona Engagement (uses prior context for realistic replies)
     │
     ├── Intelligence Extraction (merges with prior entities)
     │
     └── Confidence Scoring (considers historical patterns)
```

### 3. After Analysis

```
Final State ──► Persist to Zep
                     │
                     ├── Thread: Store conversation messages
                     │
                     └── Graph: Store extracted intelligence
                              • Scam type detected
                              • Bank accounts extracted
                              • UPI IDs discovered
                              • Phishing URLs found
                              • Confidence score
```

## Why We're Building This Graph

### 1. **Multi-Turn Memory**

Without Zep, each API call is stateless. With Zep:

- Scammers don't have to repeat themselves
- Honeypot can reference prior conversation turns
- Engagement appears more realistic to scammers

### 2. **Pattern Recognition**

The knowledge graph accumulates intelligence over time:

- Identifies repeat scammers using same UPI IDs
- Detects common phishing domains
- Recognizes scam tactics across conversations

### 3. **Entity Deduplication**

Prior entities are merged with new extractions:

```python
# Automatic deduplication
prior_upis = ["scam@paytm"]
new_upis = ["fraud@ybl", "scam@paytm"]
final_upis = ["scam@paytm", "fraud@ybl"]  # No duplicates
```

### 4. **Improved Confidence Scoring**

Historical context informs current analysis:

- If a phone number appeared in previous scams → higher confidence
- If UPI ID matches known fraud patterns → boost score

## How LLM Uses Zep Context

### Context Injection in Scam Detection

```python
# Before calling Gemini for scam detection
prompt = f"""
Analyze this message for scam indicators.

PRIOR CONTEXT FROM ZEP:
{state.get('zep_context', '')}

PREVIOUSLY DETECTED SCAM TYPES:
{state.get('prior_scam_types', [])}

CURRENT MESSAGE:
{message}
"""
```

### Context Injection in Persona Engagement

```python
# The honeypot uses prior messages to maintain consistency
prior_messages = state.get('prior_messages', [])

prompt = f"""
You are playing the persona of {persona_name}.

CONVERSATION HISTORY:
{format_prior_messages(prior_messages)}

Generate a believable response to continue extracting intelligence.
"""
```

### Benefits for LLM

| Without Zep                | With Zep                            |
| -------------------------- | ----------------------------------- |
| Stateless, no memory       | Remembers prior turns               |
| Each call is isolated      | Builds on previous context          |
| Generic responses          | Personalized, consistent replies    |
| Misses repeat patterns     | Recognizes known scam tactics       |
| Fresh extraction each time | Merges with historical intelligence |

## API Usage

### Request with Conversation ID (Multi-Turn)

```bash
# First message
curl -X POST /analyze \
  -d '{"message": "You won lottery!", "conversation_id": "scam-001"}'

# Follow-up (Zep loads prior context)
curl -X POST /analyze \
  -d '{"message": "Pay Rs 500 to claim", "conversation_id": "scam-001"}'
```

### Response Includes Conversation ID

```json
{
  "is_scam": true,
  "scam_type": "LOTTERY_FRAUD",
  "confidence_score": 0.85,
  "conversation_id": "scam-001",
  "extracted_entities": {
    "upi_ids": ["winner@paytm"]
  }
}
```

## Zep Dashboard

View your data at **https://app.getzep.com**:

| Section     | What You'll See                               |
| ----------- | --------------------------------------------- |
| **Users**   | `honeypot-system` user profile                |
| **Threads** | All conversation threads with messages        |
| **Graph**   | Visual knowledge graph with scam intelligence |
| **Facts**   | Extracted entities and relationships          |

## Files Involved

| File                   | Purpose                                   |
| ---------------------- | ----------------------------------------- |
| `memory/zep_memory.py` | Core Zep integration module               |
| `memory/__init__.py`   | Module exports                            |
| `graph/workflow.py`    | Loads/persists Zep memory around workflow |
| `graph/state.py`       | State fields for Zep context              |
| `config.py`            | Zep API key and enabled flag              |

## Environment Variables

```env
# Zep Configuration
ZEP_API_KEY=your_zep_api_key
ZEP_ENABLED=true
```

## Summary

Zep transforms our honeypot from a **stateless scam detector** into an **intelligent system** that:

1. **Remembers** past scammer interactions
2. **Learns** patterns across conversations
3. **Builds** a knowledge graph of scam intelligence
4. **Provides** contextual memory to LLMs for better responses
5. **Enables** multi-turn engagement for deeper intelligence extraction

The temporal knowledge graph acts as the system's "long-term memory," making the honeypot more effective at realistic engagement and comprehensive intelligence gathering.
