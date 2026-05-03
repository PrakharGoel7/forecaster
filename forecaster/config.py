import math
from dataclasses import dataclass, field
import os


@dataclass
class ForecasterConfig:
    model: str = "openai/gpt-4o"
    api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))

    # Outside view agents (base rate research only)
    num_ov_agents: int = 2
    max_ov_iterations: int = 3

    # Inside view agents (current evidence, updates from base rate)
    num_iv_agents: int = 3
    max_iv_iterations: int = 5

    # K ensemble runs (final probability = geometric mean over K runs)
    num_ensemble_runs: int = 1
    max_tokens_per_agent: int = 4096
    search_max_results: int = 5
    fetch_max_chars: int = 6000

    # Platt scaling coefficient — √3 ≈ 1.732 (from paper, outperforms superforecaster fit)
    platt_coefficient: float = field(default_factory=lambda: math.sqrt(3))

    # Minimum spread (log-odds) to trigger supervisor targeted search
    supervisor_search_threshold: float = 0.15
