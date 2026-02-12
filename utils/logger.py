"""
Transparent Logging System (Visual Edition)
Provides standardized, color-coded logging for Agentic Honey-Pot.
Uses 'colorlog' to create a visual hierarchy of agent actions.
"""

import logging
import sys
import colorlog

# Define distinctive colors for each agent/action type
LOG_COLORS = {
    'DEBUG':    'cyan',
    'INFO':     'white',
    'WARNING':  'yellow',
    'ERROR':    'red',
    'CRITICAL': 'red,bg_white',
    
    # Custom Agent Colors (mapped via logger names or usage)
    'SCAM_ANALYSIS': 'red',     # Critical Alert
    'THOUGHT':       'blue',    # Internal Monologue
    'PLANNER':       'purple',  # Strategy
    'PERSONA':       'cyan',    # Roleplay
    'REPLY':         'green',   # Output to user
    'INTELLIGENCE':  'yellow',  # Data extraction
    'JUDGE':         'bold_red' # Final Verdict
}

class AgentLogger:
    """Helper class for consistent, colored agent logging."""
    
    _configured = False
    
    @classmethod
    def configure(cls):
        """Setup global logger configuration if not already done."""
        if cls._configured: return
        
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s | %(message)s',
            datefmt='%H:%M:%S',
            log_colors=LOG_COLORS,
            secondary_log_colors={},
            style='%'
        ))
        
        logger = colorlog.getLogger()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        # Silence other noisy loggers
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        
        cls._configured = True

    @staticmethod
    def _print_colored(tag: str, color: str, icon: str, title: str, details: str = ""):
        """Internal format for colored log messages using standard logger."""
        RESET = "\033[0m"
        COLORS = {
            'red': "\033[91m", 'green': "\033[92m", 'yellow': "\033[93m",
            'blue': "\033[94m", 'purple': "\033[95m", 'cyan': "\033[96m", 'white': "\033[97m",
            'bold_red': "\033[1;91m", 'magenta': "\033[35m"
        }
        
        c = COLORS.get(color, "\033[97m")
        
        if details:
            msg = f"{c}{icon} [{tag}] {title}: {RESET}{details}"
        else:
            msg = f"{c}{icon} [{tag}] {title}{RESET}"
            
        # Use the root logger to ensure synchronization with other logs
        logging.info(msg)

    @staticmethod
    def scam_detected(probability: float, reason: str):
        outcome = "DETECTED" if probability > 0.6 else "CLEAN"
        color = 'bold_red' if probability > 0.6 else 'green'
        AgentLogger._print_colored("SCAM", color, f"Analysis: {outcome}", f"{probability:.0%}")

    @staticmethod
    def thought_process(agent: str, thought: str):
        AgentLogger._print_colored(f"{agent.upper()}", "blue", "Thinking", thought[:200] + "..." if len(thought) > 200 else thought)
        
    @staticmethod
    def plan_decision(current_turn: int, max_turns: int, decision: str, reasoning: str):
        AgentLogger._print_colored("PLANNER", "purple", f"Strategy: {decision.upper()}", f"Turn {current_turn}/{max_turns}")

    @staticmethod
    def persona_update(name: str, role: str, action: str):
        AgentLogger._print_colored("PERSONA", "cyan", f"Identity", f"{name} ({role})")

    @staticmethod
    def response_generated(response: str):
        preview = response[:80] + "..." if len(response) > 80 else response
        AgentLogger._print_colored("REPLY", "green", "Sent", f'"{preview}"')

    @staticmethod
    def extraction_result(entities: dict):
        found = []
        for k, v in entities.items():
            if k in ["bank_accounts", "upi_ids", "phishing_urls"] and v:
                found.append(f"{k}={len(v)}")
        
        if found:
            AgentLogger._print_colored("INTELLIGENCE", "yellow", "Extracted", ", ".join(found))
        else:
            AgentLogger._print_colored("INTELLIGENCE", "white", "No Entites", "")

    @staticmethod
    def verdict(is_guilty: bool, confidence: float, reasoning: str):
        verdict_str = "GUILTY" if is_guilty else "INNOCENT"
        color = 'bold_red' if is_guilty else 'green'
        AgentLogger._print_colored("JUDGE", color, "⚖️ ", f"Verdict: {verdict_str}", f"{confidence:.0%} | {reasoning}")
