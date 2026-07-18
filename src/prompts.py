from __future__ import annotations

from src.state import AgentState

GENERATE_INSTRUCTIONS = """You are an expert Python engineer. Given a problem statement, \
write a single, complete, self-contained Python script that solves it.

Rules:
- Standard library only, no third-party imports.
- The script must be directly executable top-to-bottom with `python script.py` — no CLI \
args, no stdin.
- Include your own correctness checks in the script itself (e.g. `assert` statements \
exercising the solution) so a bug surfaces as a script failure, not silent wrong output.
- Print nothing except what's needed to demonstrate the checks passed (e.g. "OK" on success).
- Return ONLY the code, inside a single ```python fenced block. No prose before or after.
"""

REPAIR_INSTRUCTIONS = """Diagnose the root cause of this failure and return a corrected, \
complete, self-contained script fixing this specific problem. Do not repeat an approach you \
already tried earlier in this conversation if it already failed. Return ONLY the code, \
inside a single ```python fenced block. No prose before or after."""


def build_generate_prompt(problem_statement: str) -> str:
    return f"{GENERATE_INSTRUCTIONS}\n\nProblem:\n{problem_statement}"


def build_repair_prompt(state: AgentState) -> str:
    result = state.last_result
    stderr = result.stderr.strip() if result and result.stderr else "(no stderr captured)"
    if result and result.timed_out:
        stderr = f"(script timed out — did not finish){stderr and chr(10) + stderr or ''}"
    return (
        "That script failed. Here is exactly what happened:\n\n"
        f"--- code that was run ---\n{state.generated_code}\n\n"
        f"--- stderr ---\n{stderr}\n\n"
        f"{REPAIR_INSTRUCTIONS}"
    )
