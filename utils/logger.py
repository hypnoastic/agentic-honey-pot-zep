"""
Transparent Logging System
Provides standardized, visual logging for Agentic Honey-Pot.
Uses text tags and structured formats to make agent reasoning visible.
"""

import logging
import sys

# Configure standard logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

class AgentLogger:
    """Helper class for consistent, transparent agent logging."""
    
    @staticmethod
    def _print(tag: str, agent: str, title: str, details: str = ""):
        """Internal format for log messages."""
        msg = f"[{tag}] [{agent}] {title}"
        if details:
            msg += f": {details}"
        # We use the root logger to ensure it appears in Uvicorn logs
        logging.getLogger(f"behavior.{agent.lower()}").info(msg)

    @staticmethod
    def scam_detected(probability: float, reason: str):
        outcome = "DETECTED" if probability > 0.6 else "CLEAN"
        AgentLogger._print("SCAM_ANALYSIS", "ScamDetector", f"Analysis Complete ({outcome})", f"Confidence: {probability:.2f} | Reason: {reason}")

    @staticmethod
    def thought_process(agent: str, thought: str):
        AgentLogger._print("THOUGHT", agent, "Thinking", thought)
        
    @staticmethod
    def plan_decision(current_turn: int, max_turns: int, decision: str, reasoning: str):
        AgentLogger._print("STRATEGY", "Planner", f"Decision: {decision.upper()}", f"Turns: {current_turn}/{max_turns} | Reason: {reasoning}")

    @staticmethod
    def persona_update(name: str, role: str, action: str):
        AgentLogger._print("PERSONA", "Persona", f"Identity: {name} ({role})", action)

    @staticmethod
    def response_generated(response: str):
        preview = response[:100] + "..." if len(response) > 100 else response
        AgentLogger._print("RESPONSE", "Persona", "Generated Response", f'"{preview}"')

    @staticmethod
    def extraction_result(entities: dict):
        # Only count items in known list fields
        target_keys = ["bank_accounts", "upi_ids", "phishing_urls"]
        count = 0
        for k in target_keys:
            if k in entities and isinstance(entities[k], list):
                count += len(entities[k])
        
        AgentLogger._print("INTELLIGENCE", "Extractor", f"Extracted ({count} entities)", str(entities))

    @staticmethod
    def verdict(is_guilty: bool, confidence: float, reasoning: str):
        verdict_str = "GUILTY" if is_guilty else "INNOCENT"
        AgentLogger._print("VERDICT", "Judge", f"Final Verdict: {verdict_str}", f"Confidence: {confidence:.2f} | {reasoning}")
