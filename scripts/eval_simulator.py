#!/usr/bin/env python3
"""
Full Evaluation Simulator for Agentic Honey-Pot
================================================
Mirrors the exact scoring rubric to project final hackathon score.

Features:
  - Multi-turn scammer simulation (injects all 8 fake data types)
  - Uses x-api-key authentication
  - Calculates score per category using exact rubric math
  - Identifies point loss and root cause
  - Prints full scoring report + suggestions

Usage:
  # Ensure server is running first:
  #   uvicorn main:app --host 0.0.0.0 --port 8000
  python scripts/eval_simulator.py
"""

import asyncio
import json
import os
import sys
import re
import uuid
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Allow running from project root or scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE = os.getenv("HONEYPOT_BASE_URL", "http://localhost:8000")
API_KEY  = os.getenv("HONEYPOT_API_KEY", "langfastgeminihoneypot1234")
TIMEOUT  = 120.0

# ── Test Scenario — injects all 8 fake data types ────────────────────────────
SCENARIO_FAKE_DATA = {
    "phoneNumber":   "9876543210",
    "bankAccount":   "1234567890123456",
    "upiId":         "scammer.fraud@fakebank",
    "phishingLink":  "http://fake-sbi-verify.ml/kyc",
    "emailAddress":  "fraud.agent@fakedomain.in",
    "caseId":        "CASE-SBI-20240203",
    "policyNumber":  "LIC1234567890",
    "orderNumber":   "OD123456789012",
}

# 10-turn scammer script that naturally delivers all 8 fake data types
SCAMMER_TURNS = [
    # Turn 1 — opening hook
    "URGENT: Your SBI bank account has been compromised. Your account will be blocked in 24 hours. "
    "Please verify your KYC immediately to avoid account suspension. Call us NOW.",

    # Turn 2 — create urgency + phishing link
    f"This is SBI Security Department. Click here to update KYC: {SCENARIO_FAKE_DATA['phishingLink']} "
    "You must complete this in 1 hour or your account will be permanently blocked.",

    # Turn 3 — introduce case ID
    f"Your complaint has been registered. Case ID: {SCENARIO_FAKE_DATA['caseId']}. "
    "Our officer will assist you. Please confirm your phone number for OTP verification.",

    # Turn 4 — push for phone number
    f"To proceed, I need to send OTP. Our call-back number is {SCENARIO_FAKE_DATA['phoneNumber']}. "
    "Can you confirm your registered mobile number with us?",

    # Turn 5 — introduce bank account
    f"For refund processing, please verify: Bank Account {SCENARIO_FAKE_DATA['bankAccount']}. "
    "Is this your account? We need you to confirm so we can release your funds.",

    # Turn 6 — UPI ID
    f"Please send Re. 1 to verify your account. Our UPI: {SCENARIO_FAKE_DATA['upiId']}. "
    "This is a standard verification step used by all banks.",

    # Turn 7 — email
    f"I will send you the official confirmation to your email. Our secure email is "
    f"{SCENARIO_FAKE_DATA['emailAddress']}. Can you also share your email for records?",

    # Turn 8 — policy / insurance angle
    f"This also affects your insurance policy {SCENARIO_FAKE_DATA['policyNumber']}. "
    "Your policy benefits will be cancelled if KYC is not updated. Please confirm.",

    # Turn 9 — order number angle
    f"Our reference order number is {SCENARIO_FAKE_DATA['orderNumber']}. "
    "This is linked to your pending refund. Please cooperate to receive Rs. 50,000.",

    # Turn 10 — pressure close
    "Why are you not cooperating? This is your last chance. The account block goes live in 10 minutes. "
    "Are you sure you want to lose all your money?",
]


# =============================================================================
# SCORING ENGINE — mirrors exact rubric math
# =============================================================================

def score_scam_detection(response: Dict) -> Dict:
    """Category 1: Scam Detection — 20 pts"""
    detected = (
        response.get("scamDetected") 
        if response.get("scamDetected") is not None 
        else response.get("scam_detected", False)
    )
    points = 20 if detected else 0
    return {
        "points": points,
        "max": 20,
        "detail": f"scamDetected={detected}"
    }


def score_intelligence_extraction(response: Dict, fake_data: Dict) -> Dict:
    """Category 2: Intelligence Extraction — 30 pts"""
    intel = (
        response.get("extractedIntelligence") 
        or response.get("extracted_entities") 
        or {}
    )

    # Flatten all extracted values into a single set
    all_extracted = set()
    for vals in intel.values():
        if isinstance(vals, list):
            for v in vals:
                all_extracted.add(str(v).strip().lower())

    # Map fake data values
    fake_values = [str(v).strip().lower() for v in fake_data.values()]
    total_fake = len(fake_values)

    matched = []
    missed = []
    for fv in fake_values:
        # Substring match (rubric allows substring)
        found = any(fv in ex or ex in fv for ex in all_extracted)
        if found:
            matched.append(fv)
        else:
            missed.append(fv)

    points_per_item = 30.0 / total_fake if total_fake > 0 else 0
    points = round(len(matched) * points_per_item, 2)

    return {
        "points": points,
        "max": 30,
        "matched": matched,
        "missed": missed,
        "detail": f"{len(matched)}/{total_fake} fake values extracted"
    }


def score_conversation_quality(responses: List[Dict], session_history: List[Dict]) -> Dict:
    """Category 3: Conversation Quality — 30 pts"""

    total_turns = len(session_history) // 2  # each round trip = 1 turn
    all_honeypot_text = " ".join(
        m.get("text", "") for m in session_history if m.get("sender") == "honeypot"
    )

    # Sub-score 1: Turn count (8 pts)
    if total_turns >= 8:
        turn_pts = 8
    elif total_turns >= 6:
        turn_pts = 6
    elif total_turns >= 4:
        turn_pts = 3
    else:
        turn_pts = 0

    # Sub-score 2: Questions asked (4 pts)
    q_count = all_honeypot_text.count("?")
    if q_count >= 5:
        q_pts = 4
    elif q_count >= 3:
        q_pts = 2
    elif q_count >= 1:
        q_pts = 1
    else:
        q_pts = 0

    # Sub-score 3: Relevant investigative questions (3 pts)
    investigative_patterns = [
        r"official.*website|website.*official",
        r"reference.*number|case.*number|case.*id|ticket.*number",
        r"supervisor|manager|officer.*name",
        r"branch.*name|branch.*code",
        r"why.*urgent|why.*so.*urgent",
        r"employee.*id|staff.*id",
        r"how.*does.*this.*work|explain.*process",
    ]
    inv_count = sum(
        1 for p in investigative_patterns
        if re.search(p, all_honeypot_text, re.IGNORECASE)
    )
    if inv_count >= 3:
        inv_pts = 3
    elif inv_count >= 2:
        inv_pts = 2
    elif inv_count >= 1:
        inv_pts = 1
    else:
        inv_pts = 0

    # Sub-score 4: Red Flags (8 pts)
    red_flag_patterns = [
        r"suspicious|suspici",
        r"red flag",
        r"unusual|uncommon",
        r"legitimate.*bank.*not|bank.*not.*usually",
        r"official.*channels|go.*through.*official",
        r"verify.*independently|check.*yourself",
        r"share.*otp.*suspicious|otp.*share.*unusual",
        r"link.*unofficial|unofficial.*link",
    ]
    rf_count = sum(
        1 for p in red_flag_patterns
        if re.search(p, all_honeypot_text, re.IGNORECASE)
    )
    if rf_count >= 5:
        rf_pts = 8
    elif rf_count >= 3:
        rf_pts = 5
    elif rf_count >= 1:
        rf_pts = 2
    else:
        rf_pts = 0

    # Sub-score 5: Information Elicitation (7 pts)
    # 1.5 pts per successful elicitation attempt (max 7)
    elicitation_patterns = [
        r"phone.*number|number.*phone",
        r"email.*address|send.*email",
        r"case.*id|reference.*number|ticket",
        r"supervisor|speak.*to.*manager",
        r"website|official.*link|link.*official",
        r"branch|which.*branch",
        r"policy.*number|policy.*no",
        r"upi.*id|upi.*number",
        r"bank.*account|account.*number",
        r"order.*number|order.*id",
    ]
    elix_count = sum(
        1 for p in elicitation_patterns
        if re.search(p, all_honeypot_text, re.IGNORECASE)
    )
    elix_pts = min(7.0, elix_count * 1.5)
    elix_pts = round(elix_pts, 1)

    total = turn_pts + q_pts + inv_pts + rf_pts + elix_pts
    total = round(min(30, total), 1)

    return {
        "points": total,
        "max": 30,
        "breakdown": {
            "turn_count": {"turns": total_turns, "points": turn_pts, "max": 8},
            "questions_asked": {"count": q_count, "points": q_pts, "max": 4},
            "investigative_questions": {"count": inv_count, "points": inv_pts, "max": 3},
            "red_flags": {"count": rf_count, "points": rf_pts, "max": 8},
            "elicitation": {"count": elix_count, "points": elix_pts, "max": 7},
        }
    }


def score_engagement_quality(response: Dict) -> Dict:
    """Category 4: Engagement Quality — 10 pts"""
    duration = response.get("engagementDurationSeconds", 0)
    messages = response.get("totalMessagesExchanged", 0)

    pts = 0
    breakdown = {}

    # Duration scoring
    if duration > 0:
        pts += 1
    if duration > 60:
        pts += 2
    if duration > 180:
        pts += 1
    breakdown["duration"] = {"seconds": duration, "pts_earned": min(4, (duration > 0) + 2*(duration > 60) + (duration > 180))}

    # Message scoring
    if messages > 0:
        pts += 2
    if messages >= 5:
        pts += 3
    if messages >= 10:
        pts += 1
    breakdown["messages"] = {"count": messages, "pts_earned": min(6, 2*(messages > 0) + 3*(messages >= 5) + (messages >= 10))}

    return {
        "points": pts,
        "max": 10,
        "breakdown": breakdown,
        "detail": f"duration={duration}s, messages={messages}"
    }


def score_response_structure(response: Dict) -> Dict:
    """Category 5: Response Structure — 10 pts"""
    required_fields = ["sessionId", "scamDetected", "extractedIntelligence"]
    optional_fields = [
        ("engagementDurationSeconds", ("engagementDurationSeconds" in response)),
        ("totalMessagesExchanged", ("totalMessagesExchanged" in response)),
        ("agentNotes", bool(response.get("agentNotes"))),
        ("scamType", bool(response.get("scamType"))),
        ("confidenceLevel", response.get("confidenceLevel") is not None),
    ]

    pts = 0
    penalties = []
    detail_lines = []

    # Required (2 pts each)
    for field in required_fields:
        if field in response and response[field] is not None:
            pts += 2
            detail_lines.append(f"  ✅ {field} (2 pts)")
        else:
            pts -= 1  # penalty
            penalties.append(field)
            detail_lines.append(f"  ❌ {field} MISSING (-1 pt)")

    # Optional (1 pt each)
    for label, present in optional_fields:
        if present:
            pts += 1
            detail_lines.append(f"  ✅ {label} (1 pt)")
        else:
            detail_lines.append(f"  ○  {label} missing (0 pts)")

    pts = max(0, pts)
    return {
        "points": pts,
        "max": 10,
        "penalties": penalties,
        "detail": "\n".join(detail_lines)
    }


def calculate_final_score(scores: Dict) -> float:
    """Final weighted score (assuming 1 scenario, weight=100)."""
    scenario_score = sum(s["points"] for s in scores.values())
    # With 1 scenario at weight 100: Scenario Score = scenario_score * 100/100
    # Final = (Scenario Score * 0.9) + Code Quality (10% assumed = 8/10)
    code_quality_pts = 8.0  # Typically 8/10 for clean code
    final = (scenario_score * 0.9) + code_quality_pts
    return round(min(100, final), 2)


# =============================================================================
# WEAKNESS ANALYZER
# =============================================================================

def analyze_weaknesses(scores: Dict, responses: List[Dict], session_history: List[Dict]) -> List[str]:
    """Returns list of human-readable weakness descriptions."""
    issues = []

    # Scam Detection
    if scores["scam_detection"]["points"] < 20:
        issues.append("❌ SCAM DETECTION (−20): scamDetected is False or missing. "
                       "Ensure the LLM always sets scam_detected=True for scam messages.")

    # Intelligence Extraction
    ext = scores["intelligence_extraction"]
    if ext["missed"]:
        issues.append(f"❌ EXTRACTION (lost {30 - ext['points']:.0f} pts): Missed values: {ext['missed']}")
        issues.append(
            "   FIX: Ensure scammer messages containing fake data are fully indexed. "
            "Check prefilter.py regex patterns for caseIds, policyNumbers, orderNumbers."
        )

    # Conversation Quality sub-checks
    cq = scores["conversation_quality"]["breakdown"]

    if cq["turn_count"]["turns"] < 8:
        issues.append(f"❌ TURNS (−{8 - cq['turn_count']['points']} pts): Only {cq['turn_count']['turns']} turn(s). "
                       "Planner must hold to ≥8 turns. Check planner.py minimum turn guard.")

    if cq["questions_asked"]["count"] < 5:
        issues.append(f"❌ QUESTIONS (−{4 - cq['questions_asked']['points']} pts): Only {cq['questions_asked']['count']} '?' found. "
                       "Persona must end every message with a question mark.")

    if cq["red_flags"]["count"] < 5:
        issues.append(f"❌ RED FLAGS (−{8 - cq['red_flags']['points']} pts): Only {cq['red_flags']['count']} red flag phrases. "
                       "Persona must explicitly name suspicious behavior every other turn.")

    if cq["elicitation"]["count"] < 5:
        issues.append(f"❌ ELICITATION (−{7 - cq['elicitation']['points']:.0f} pts): Only {cq['elicitation']['count']} attempts. "
                       "Strategy hints must explicitly request specific data types each turn.")

    # Engagement Metrics
    eq = scores["engagement_quality"]
    if eq["points"] < 8:
        resp = responses[-1] if responses else {}
        dur = resp.get("engagementDurationSeconds", 0)
        msg = resp.get("totalMessagesExchanged", 0)
        if dur == 0:
            issues.append("❌ DURATION (−3 pts): engagementDurationSeconds=0. "
                           "Ensure engagement_start_time is set in state.py create_initial_state().")
        if msg < 10:
            issues.append(f"❌ MESSAGES (−1 pt): Only {msg} messages counted. "
                           "Ensure totalMessagesExchanged counts both sides of conversation.")

    # Response Structure
    rs = scores["response_structure"]
    if rs["penalties"]:
        issues.append(f"❌ STRUCTURE: Missing required fields: {rs['penalties']}. "
                       "Check HoneypotResponse in schemas.py and construct_safe_response() in safe_response.py.")

    return issues


# =============================================================================
# MAIN SIMULATION RUNNER
# =============================================================================

async def run_simulation():
    session_id = str(uuid.uuid4())
    print(f"\n{'='*70}")
    print(f"  🍯 HONEYPOT EVALUATION SIMULATOR")
    print(f"  Session: {session_id}")
    print(f"  API:     {API_BASE}")
    print(f"  Turns:   {len(SCAMMER_TURNS)}")
    print(f"{'='*70}\n")

    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json"
    }

    conversation_history: List[Dict] = []
    all_responses: List[Dict] = []
    simulation_start = time.time()

    async with httpx.AsyncClient(base_url=API_BASE, timeout=TIMEOUT) as client:

        # ── Health check ───────────────────────────────────────────────────
        try:
            health = await client.get("/health")
            if health.status_code != 200:
                print(f"❌ Server not healthy: {health.status_code}")
                print("   Start server first: uvicorn main:app --host 0.0.0.0 --port 8000")
                return
            print(f"✅ Server healthy: {health.json().get('service', 'unknown')}\n")
        except Exception as e:
            print(f"❌ Cannot reach server at {API_BASE}: {e}")
            print("   Start server first: uvicorn main:app --host 0.0.0.0 --port 8000")
            return

        # ── Multi-turn simulation ─────────────────────────────────────────
        for turn_num, scammer_msg in enumerate(SCAMMER_TURNS, 1):
            print(f"{'─'*60}")
            print(f"Turn {turn_num}/{len(SCAMMER_TURNS)}")
            print(f"🦹 SCAMMER: {scammer_msg[:120]}{'...' if len(scammer_msg) > 120 else ''}")

            payload = {
                "sessionId": session_id,
                "message": {
                    "sender": "scammer",
                    "text": scammer_msg,
                    "timestamp": int(datetime.now(timezone.utc).timestamp()),
                },
                "conversationHistory": conversation_history,
                "metadata": {
                    "channel": "SMS",
                    "language": "English",
                    "locale": "IN"
                }
            }

            try:
                resp = await client.post("/analyze", json=payload, headers=headers)
            except Exception as e:
                print(f"   ❌ Request failed: {e}")
                break

            if resp.status_code == 401:
                print(f"   ❌ 401 Unauthorized — check API key (current: '{API_KEY}')")
                print(f"      Set HONEYPOT_API_KEY env var if different from default.")
                break
            elif resp.status_code != 200:
                print(f"   ❌ HTTP {resp.status_code}: {resp.text[:200]}")
                break

            data = resp.json()
            all_responses.append(data)

            reply = data.get("reply") or "(no reply)"
            print(f"🍯 HONEYPOT: {reply[:200]}{'...' if len(reply) > 200 else ''}")
            print(f"   scamDetected={data.get('scamDetected')} | "
                  f"confidence={data.get('confidenceLevel', 'N/A')} | "
                  f"scamType={data.get('scamType', 'N/A')}")

            intel = data.get("extractedIntelligence", {})
            non_empty = {k: v for k, v in intel.items() if v}
            if non_empty:
                print(f"   📦 Extracted: {json.dumps(non_empty)}")

            # Update conversation history for next turn
            conversation_history.append({
                "sender": "scammer",
                "text": scammer_msg,
                "timestamp": int(datetime.now(timezone.utc).timestamp())
            })
            if reply and reply != "(no reply)":
                conversation_history.append({
                    "sender": "honeypot",
                    "text": reply,
                    "timestamp": int(datetime.now(timezone.utc).timestamp())
                })
            print()

    # ── Use final response for structure + engagement scoring ─────────────
    final_response = all_responses[-1] if all_responses else {}
    # Inject real duration into final response so scorer sees it
    final_response["engagementDurationSeconds"] = round(time.time() - simulation_start, 1)
    final_response["totalMessagesExchanged"] = len(conversation_history)

    # Print final payload
    print(f"\n{'='*70}")
    print("📤 FINAL RESPONSE STRUCTURE:")
    # Print key fields only
    display = {
        k: v for k, v in final_response.items()
        if k not in ("reply", "status")
    }
    print(json.dumps(display, indent=2, default=str))

    # ── RUN SCORING ───────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("📊 SCORING REPORT\n")

    scores = {}

    scores["scam_detection"] = score_scam_detection(final_response)
    scores["intelligence_extraction"] = score_intelligence_extraction(
        final_response, SCENARIO_FAKE_DATA
    )
    scores["conversation_quality"] = score_conversation_quality(
        all_responses, conversation_history
    )
    scores["engagement_quality"] = score_engagement_quality(final_response)
    scores["response_structure"] = score_response_structure(final_response)

    print(f"  {'Category':<30} {'Score':>6} / {'Max':>3}")
    print(f"  {'─'*45}")
    for name, s in scores.items():
        label = name.replace("_", " ").title()
        print(f"  {label:<30} {s['points']:>6.1f} / {s['max']:<3}")

    scenario_raw = sum(s["points"] for s in scores.values())
    final_score  = calculate_final_score(scores)

    print(f"  {'─'*45}")
    print(f"  {'Scenario Raw':30} {scenario_raw:>6.1f} / 100")
    print(f"  {'Code Quality (assumed 8/10)':30} {'8.0':>6} /  10")
    print(f"  {'─'*45}")
    print(f"  {'FINAL PROJECTED SCORE':30} {final_score:>6.1f} / 100")
    print()

    # ── DETAILED BREAKDOWN ─────────────────────────────────────────────────
    print(f"{'─'*60}")
    print("🔍 DETAILED BREAKDOWN:")
    cq = scores["conversation_quality"]["breakdown"]
    for sub_name, sub in cq.items():
        label = sub_name.replace("_", " ").title()
        print(f"   {label:<28} {sub.get('points', sub.get('pts_earned', 0)):>5.1f} / {sub.get('max', '?')}")

    # ── WEAKNESS REPORT ────────────────────────────────────────────────────
    issues = analyze_weaknesses(scores, all_responses, conversation_history)
    if issues:
        print(f"\n⚠️  WEAKNESSES FOUND ({len(issues)}):")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("\n🎯 NO WEAKNESSES FOUND — Perfect score profile!")

    print(f"\n{'='*70}")
    if final_score >= 95:
        print(f"🏆 TARGET REACHED: {final_score}/100 ≥ 95 — Hackathon ready!")
    elif final_score >= 85:
        print(f"⚠️  CLOSE: {final_score}/100 — Fix the weaknesses above to reach 95+")
    else:
        print(f"🔴 NEEDS WORK: {final_score}/100 — Multiple areas need improvement")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(run_simulation())
