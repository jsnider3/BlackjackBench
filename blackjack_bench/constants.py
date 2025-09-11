"""Constants and configuration values for BlackjackBench."""

from __future__ import annotations

# CLI Error Handling
MAX_CONSECUTIVE_ERRORS = 10
RETRY_BACKOFF_BASE = 0.5

# Heartbeat and Timing
DEFAULT_HEARTBEAT_SECONDS = 60
DEFAULT_TIMEOUT_SECONDS = 120

# LLM Configuration  
DEFAULT_MAX_OUTPUT_TOKENS = 8
DEFAULT_TEMPERATURE = 0.0
DEFAULT_RETRIES = 2
DEFAULT_RETRY_BACKOFF = 1.5

# OpenAI Specific
OPENAI_MAX_TOKENS = 8000

# Model defaults
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"
DEFAULT_OLLAMA_MODEL = "llama3.1"
DEFAULT_OPENROUTER_MODEL = "openrouter/sonoma-sky-alpha"

# Prompt modes
VALID_PROMPT_MODES = {"minimal", "rules_lite", "verbose"}
DEFAULT_PROMPT_MODE = "rules_lite"

# Reasoning levels
VALID_REASONING_LEVELS = {"none", "low", "medium", "high"}
DEFAULT_REASONING_LEVEL = "low"

# Grid configuration
POLICY_GRID_CELLS = 550
POLICY_GRID_PLAYER_CATEGORIES = 55
POLICY_GRID_DEALER_UPCARDS = 10

# File extensions
JSONL_EXTENSION = ".jsonl"
REPORT_EXTENSION = ".json"

# Agents
AVAILABLE_AGENTS = {
    "basic", "random", "bad", "worst", "llm", "claude-sonnet", 
    "gpt5", "gemini-flash", "sonoma-sky", "gemma", "qwen-cli"
}

# Tracks  
AVAILABLE_TRACKS = {"policy", "policy-grid"}
DEFAULT_TRACK = "policy"

# Default run parameters
DEFAULT_HANDS = 10000
DEFAULT_SEED = 42
DEFAULT_REPS = 1
DEFAULT_PARALLEL = 1