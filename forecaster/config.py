import math
from dataclasses import dataclass, field
import os


@dataclass
class ForecasterConfig:
    model: str = "anthropic/claude-sonnet-4-6"
    api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))

    # M independent agents per ensemble run
    num_agents: int = 3
    # K ensemble runs (final probability = geometric mean over K runs)
    num_ensemble_runs: int = 1

    max_search_iterations: int = 8   # per agent
    max_tokens_per_agent: int = 4096
    search_max_results: int = 5
    fetch_max_chars: int = 6000

    # Platt scaling coefficient — √3 ≈ 1.732 (from paper, outperforms superforecaster fit)
    platt_coefficient: float = field(default_factory=lambda: math.sqrt(3))

    # Minimum spread (log-odds) to trigger supervisor targeted search
    supervisor_search_threshold: float = 0.15
