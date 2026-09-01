# Config for Models 
# Contains configuration settings for the models used in the application
# Example settings might include model paths, API keys, or other relevant parameters.

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = Path(os.getenv("CORPUS_DIR", ROOT / "data" / "corpus"))
FIXTURES_DIR = Path(os.getenv("FIXTURES_DIR", ROOT / "data" / "fixtures"))


# Model 
# Option to switch between a Fake / OpenAI as choice of model 
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "fake") # "fake" or "openai"
if(LLM_PROVIDER == "openai"):
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
else:
    LLM_MODEL = os.getenv("LLM_MODEL", "fake-model")

# Retrieval / budgets
RETRIEVE_K = int(os.getenv("RETRIEVE_K", "8"))
MAX_STEPS = int(os.getenv("MAX_STEPS", "12"))
TOOL_TIMEOUT_MS = int(os.getenv("TOOL_TIMEOUT_MS", "3000"))
TOOL_MAX_ATTEMPTS = int(os.getenv("TOOL_MAX_ATTEMPTS", "3"))

# Persistence
DB_PATH = os.getenv("DB_PATH", str(ROOT / "run_state.sqlite"))

# Authority Matrix to understand the approvals and gating mechanism
AUTH_MATRIX = [
    ("Cost Centre Manager", 10_000),
    ("Department Director", 50_000),
    ("Executive Director", 250_000),
    ("Chief Financial Officer", 1_000_000),
]
