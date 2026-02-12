"""
Transparent Logging System (Visual Edition)
Provides standardized, color-coded logging for Agentic Honey-Pot.
Uses 'colorlog' to create a visual hierarchy of agent actions.
"""

import logging
import sys
import colorlog
import asyncio
import re
from datetime import datetime

# Define distinctive colors for each agent/action type
LOG_COLORS = {
    'DEBUG':    'cyan',
    'INFO':     'white',
    'WARNING':  'yellow',
    'ERROR':    'red',
    'CRITICAL': 'red,bg_white',
    
    # Custom Agent Colors
    'SCAM_ANALYSIS': 'red',
    'THOUGHT':       'blue',
    'PLANNER':       'purple',
    'PERSONA':       'cyan',
    'REPLY':         'green',
    'INTELLIGENCE':  'yellow',
    'JUDGE':         'bold_red'
}

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

class AgentLogger:
    """Helper class for consistent, colored agent logging."""
    
    _configured = False
    _log_queues = []
    
    @classmethod
    def configure(cls, level=logging.INFO):
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
        logger.addHandler(BroadcastHandler())
        logger.setLevel(level)
        
        # Silence other noisy loggers
        silence_list = [
            "httpx", "httpcore", "google_genai", "google.auth",
            "multipart.multipart", "apscheduler", "tzlocal",
            "urllib3", "asyncio"
        ]
        
        for lib in silence_list:
            logging.getLogger(lib).setLevel(logging.WARNING)
        
        cls._configured = True
    
    @classmethod
    def register_queue(cls, queue):
        """Register a queue to receive log records."""
        cls._log_queues.append(queue)
        
    @classmethod
    def remove_queue(cls, queue):
        """Remove a queue."""
        if queue in cls._log_queues:
            cls._log_queues.remove(queue)
            
    @classmethod
    def broadcast_log(cls, record):
        """Broadcast log record to all registered queues."""
        raw_msg = record.getMessage()
        msg = ANSI_ESCAPE.sub('', raw_msg) # Clean for web
        
        timestamp = record.asctime if hasattr(record, 'asctime') else datetime.now().strftime('%H:%M:%S')
        
        # Determine semantic type (for frontend to style)
        log_type = "default" # Default white
        
        ui_color = getattr(record, 'ui_color', None)
        if ui_color:
            # Map ui_color names to semantic types
            color_map = {
                'red': 'error',
                'bold_red': 'critical',
                'green': 'success',
                'yellow': 'warning',
                'blue': 'thought',
                'purple': 'planner',
                'cyan': 'persona',
                'orange': 'system'
            }
            log_type = color_map.get(ui_color, "default")
        else:
            # Fallback for standard log records by level/content
            if record.levelno >= logging.ERROR:
                log_type = "error"
            elif record.levelno >= logging.WARNING:
                log_type = "warning"
            elif "[SCAM]" in msg:
                log_type = "critical"
            elif "[PLANNER]" in msg:
                log_type = "planner"
            elif "[REPLY]" in msg:
                log_type = "success"
            elif "[THOUGHT]" in msg:
                log_type = "thought"
            elif "[PERSONA]" in msg:
                log_type = "persona"
            elif "[INTELLIGENCE]" in msg:
                log_type = "warning"
            elif "[WORKFLOW]" in msg or "[LOCK]" in msg:
                log_type = "system"
            
        log_entry = {
            "timestamp": timestamp,
            "message": msg,
            "type": log_type
        }
        
        for q in cls._log_queues:
            try:
                q.put_nowait(log_entry)
            except asyncio.QueueFull:
                pass

    @staticmethod
    def _print_colored(tag: str, color: str, icon: str, title: str, details: str = ""):
        """Internal format for colored log messages."""
        RESET = "\033[0m"
        COLORS = {
            'red': "\033[91m", 'green': "\033[92m", 'yellow': "\033[93m",
            'blue': "\033[94m", 'purple': "\033[95m", 'cyan': "\033[96m", 'white': "\033[97m",
            'bold_red': "\033[1;91m", 'magenta': "\033[35m", 'orange': "\033[38;5;208m"
        }
        
        c = COLORS.get(color, "\033[97m")
        tag_width = 14
        formatted_tag = f"[{tag}]".ljust(tag_width)
        
        if details:
            msg = f"{c}{formatted_tag} {title}: {RESET}{details}"
        else:
            msg = f"{c}{formatted_tag} {title}{RESET}"
            
        logging.getLogger().info(msg, extra={"ui_color": color})

    @staticmethod
    def scam_detected(probability: float, reason: str):
        outcome = "DETECTED" if probability > 0.6 else "CLEAN"
        color = 'bold_red' if probability > 0.6 else 'green'
        AgentLogger._print_colored("SCAM", color, "", f"Analysis: {outcome}", f"{probability:.0%}")

    @staticmethod
    def thought_process(agent: str, thought: str):
        AgentLogger._print_colored(f"{agent.upper()}", "blue", "", "Thinking", thought[:200] + "..." if len(thought) > 200 else thought)
        
    @staticmethod
    def plan_decision(current_turn: int, max_turns: int, decision: str, reasoning: str):
        AgentLogger._print_colored("PLANNER", "purple", "", f"Strategy: {decision.upper()}", f"Turn {current_turn}/{max_turns}")

    @staticmethod
    def persona_update(name: str, role: str, action: str):
        AgentLogger._print_colored("PERSONA", "cyan", "", "Identity", f"{name} ({role})")

    @staticmethod
    def response_generated(response: str):
        preview = response[:80] + "..." if len(response) > 80 else response
        AgentLogger._print_colored("REPLY", "green", "", "Sent", f'"{preview}"')

    @staticmethod
    def extraction_result(entities: dict):
        found = []
        for k, v in entities.items():
            if k in ["bank_accounts", "upi_ids", "phishing_urls"] and v:
                found.append(f"{k}={len(v)}")
        
        if found:
            AgentLogger._print_colored("INTELLIGENCE", "yellow", "", "Extracted", ", ".join(found))
        else:
            AgentLogger._print_colored("INTELLIGENCE", "white", "", "No Entities", "")

    @staticmethod
    def verdict(is_guilty: bool, confidence: float, reasoning: str):
        verdict_str = "GUILTY" if is_guilty else "INNOCENT"
        color = 'bold_red' if is_guilty else 'green'
        AgentLogger._print_colored("JUDGE", color, "", f"Verdict: {verdict_str}", f"{confidence:.0%} | {reasoning}")

class BroadcastHandler(logging.Handler):
    """Handler to broadcast logs to WebSockets."""
    def emit(self, record):
        try:
            self.format(record) # Ensure asctime is present
            AgentLogger.broadcast_log(record)
        except Exception:
            self.handleError(record)
