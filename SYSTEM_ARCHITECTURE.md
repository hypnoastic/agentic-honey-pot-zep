# How It Works: End-to-End System Explanation

This document explains exactly what happens when a scammer sends a message to our system, how the **Zep Knowledge Graph** is built, and how each agent works together.

---

## 🚀 The Flow: From Message to Intelligence

Imagine a scammer sends this message:

> _"Congratulation! You won Rs 1 Lakh. Pay Rs 500 registration fee to UPI: winner@paytm"_

Here is the step-by-step journey of that message:

### Step 1: The "Wake Up" (API & Memory Load)

**What happens:** The API receives the message. If a `conversation_id` was provided, it immediately calls **Zep**.
**Why:** To check if we've met this scammer before.
**Zep Action:**

- **Fetches History:** Pulls the last 10 messages from this conversation.
- **Fetches Facts:** "Hey, last time this guy mentioned he was from 'Head Office'."
- **Fetches Intelligence:** "We previously extracted the phone number 98765..."

### Step 2: The Assembly Line (LangGraph Workflow)

The message + the memory from Zep are packaged into a "State" (a shared folder of info) and sent to the agents.

#### 🕵️ Agent 1: The Guard (Scam Detection)

- **Role:** The Bouncer.
- **Input:** The scammer's message + Zep Memory.
- **Job:** Decides "Is this a scam?"
- **How it uses Context:** If the message is vague like "Hello", but Zep memory shows the previous message was a phishing link, the Guard knows it's still a scam.
- **Output:** `scam_detected: True`

#### 🎭 Agent 2: The Actor (Persona Engagement)

- **Role:** The Bait.
- **Input:** The message + "Persona: Naive Elderly Man".
- **Job:** Write a reply that sounds like a distinct victim to keep the scammer hooked.
- **How it uses Context:** It reads the chat history to ensure it doesn't repeat questions ("I already asked for your name").
- **Action:** Generates a reply like: _"Oh my god really? I have never won anything. How do I pay?"_

#### 🔍 Agent 3: The Detective (Intelligence Extraction)

- **Role:** The Sieve.
- **Input:** The entire conversation so far.
- **Job:** Looks for specific pieces of valuable data (The "Loot").
- **Targets:**
  - 🏦 Bank Account Numbers
  - 💸 UPI IDs (e.g., `winner@paytm`)
  - 🔗 Phishing Links
  - 📞 Phone Numbers
- **Action:** Extracts `winner@paytm` and adds it to the State.

#### ⚖️ Agent 4: The Judge (Confidence Scoring)

- **Role:** The Validator.
- **Input:** How many scam indicators were found? Did we get any intelligence?
- **Job:** Assigns a score (0.0 to 1.0).
- **Action:** "We found a UPI ID and urgency keywords. Score: 0.9 (High Confidence)."

### Step 3: Saving the Evidence (Zep Persistence)

Once the agents finish, we save everything back to **Zep**. This is where the **Knowledge Graph** gets built.

---

## 🧠 The Zep Knowledge Graph: What Are We Building?

We are not just saving text logs. We are building a structured web of connections.

### 1. The Users (Nodes)

- **Honeypot System:** The central node representing our AI agent.
- **Scammer:** A node representing the attacker.

### 2. The Threads (Edges)

- **Conversation Threads:** Links the Scammer to the Honeypot.
- **Storage:** Contains the actual text messages time-stamped in order.

### 3. The Intelligence (Structured Facts)

This is the most powerful part. We inject **JSON Data** directly into the graph linked to the User.

**What gets stored in the Graph:**

```json
{
  "event_type": "scam_detected",
  "scam_type": "LOTTERY_FRAUD",
  "upi_ids": ["winner@paytm"],
  "bank_accounts": [],
  "confidence_score": 0.9,
  "timestamp": "2026-01-29T15:30:00Z"
}
```

### Why is this Graph useful?

If the same scammer messages again in a new thread, or if we search the graph later:

1. **Zep Vector Search:** We can search "Who asked for payments to winner@paytm?" and find this exact conversation.
2. **Pattern Matching:** We can query "Show all users who used 'LOTTERY_FRAUD' tactics."

---

## 🤖 How This Helps the LLM

Memory is the key to intelligence. Without Zep, the LLM is like a person with amnesia—it forgets everything after each sentence.

| Feature        | Without Zep (Amnesia)                                                                           | With Zep (Memory)                                                                                             |
| :------------- | :---------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------ |
| **Continuity** | Scammer: "Send money"<br>AI: "How?"<br>Scammer: "UPI"<br>AI: "What do you want?" (Forgot topic) | Scammer: "Send money"<br>AI: "How?"<br>Scammer: "UPI"<br>AI: "Which UPI ID should I use?" (Remembers context) |
| **Strategy**   | Reacts only to the last sentence.                                                               | "He asked for money 3 times, he is getting desperate. I will stall him."                                      |
| **Facts**      | Forgets extracted info instantly.                                                               | "You mentioned account HDFC ending in 8899, is that correct?"                                                 |

---

## Simple Summary

1. **Scammer speaks.**
2. **Zep remembers** what happened before.
3. **Guard** checks for danger.
4. **Actor** plays along to get info.
5. **Detective** steals their bank details.
6. **Zep saves** the evidence into a searchable web of facts.

This loop turns a simple chatbot into a **Trap** that learns and remembers.
