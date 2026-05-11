"""
Run a single forecast and print every LLM message exchange.
Usage:
    python debug_run.py "Will the Fed cut rates in June 2025?"
"""
import sys
import json
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# Monkey-patch LLMClient.complete to print every exchange
from forecaster.agents import base as _base

_orig_complete = _base.LLMClient.complete

def _verbose_complete(self, system, messages, tools, force_tool=False):
    agent_label = f"[{getattr(self, '_debug_label', 'Agent')}]"
    print(f"\n{'='*70}")
    print(f"{agent_label} LLM CALL  (force_tool={force_tool})")
    print(f"{'='*70}")
    print(f"SYSTEM:\n{system}\n")
    for i, m in enumerate(messages):
        role = m["role"].upper()
        content = m.get("content") or ""
        tool_calls = m.get("tool_calls", [])
        print(f"--- msg[{i}] {role} ---")
        if content:
            print(content[:2000])
        for tc in tool_calls:
            fn = tc.get("function", {})
            args = fn.get("arguments", "{}")
            try:
                args_pretty = json.dumps(json.loads(args), indent=2)
            except Exception:
                args_pretty = args
            print(f"  TOOL_CALL {fn.get('name')}: {args_pretty[:800]}")
    print()

    response = _orig_complete(self, system, messages, tools, force_tool)

    print(f"{agent_label} RESPONSE:")
    for tb in response.tool_blocks:
        print(f"  → {tb.name}({json.dumps(tb.input, indent=2)[:1200]})")
    if not response.tool_blocks:
        print("  (no tool calls — model produced text only)")
    print()
    return response

_base.LLMClient.complete = _verbose_complete

# Now run the forecast
from forecaster.forecaster_system import ForecasterSystem
from forecaster.config import ForecasterConfig

question = sys.argv[1] if len(sys.argv) > 1 else "Will the Fed cut rates in June 2025?"

print(f"\nQuestion: {question}\n")

def on_step(name, stage, data=None):
    print(f"  [step] {name} → {stage}")

config = ForecasterConfig()
memo = ForecasterSystem(config).forecast(question, on_step=on_step)

print(f"\n{'='*70}")
print(f"FINAL PROBABILITY: {memo.final_probability:.1%}")
print(f"RAW:               {memo.raw_probability:.1%}")
print(f"OV BASE RATE:      {memo.ov_forecasts[0].base_rate:.1%} (agent 0)" if memo.ov_forecasts else "")
print(f"SUPERVISOR:        {memo.supervisor_reconciliation.reconciled_probability:.1%}")
print(f"\nSYNTHESIS:\n{memo.supervisor_reconciliation.reconciliation_reasoning}")
