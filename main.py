from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional

from config.settings import get_settings
from src.orchestrator import build_graph
from src.state import AgentState

PROBLEM_SET_PATH = Path(__file__).parent / "tests" / "problem_set.json"
RESULTS_PATH = Path(__file__).parent / "results.json"


def load_problems(problem_id: Optional[str] = None) -> list[dict]:
    problems = json.loads(PROBLEM_SET_PATH.read_text())
    if problem_id is not None:
        problems = [p for p in problems if p["id"] == problem_id]
        if not problems:
            raise SystemExit(f"No problem with id '{problem_id}' in {PROBLEM_SET_PATH}")
    return problems


def run_problem(graph, problem: dict, max_retries: int) -> dict:
    initial = AgentState(
        problem_id=problem["id"],
        problem_statement=problem["statement"],
        max_retries=max_retries,
    )
    start = time.monotonic()
    final = graph.invoke(initial)
    elapsed = time.monotonic() - start

    notes = ""
    last_result = final.get("last_result")
    if not final["solved"] and last_result and last_result.stderr:
        notes = last_result.stderr.strip().splitlines()[-1]

    return {
        "problem_id": problem["id"],
        "solved": final["solved"],
        "retries": final["retry_count"],
        "seconds": round(elapsed, 2),
        "notes": notes,
    }


def print_summary(results: list[dict]) -> None:
    n = len(results)
    solved = sum(1 for r in results if r["solved"])
    avg_retries = sum(r["retries"] for r in results if r["solved"]) / solved if solved else 0.0
    avg_seconds = sum(r["seconds"] for r in results) / n if n else 0.0

    print(f"Problems evaluated:            {n}")
    print(f"Solved within retry budget:    {solved} / {n} ({(solved / n * 100) if n else 0:.0f}%)")
    print(f"Avg. retries to success:       {avg_retries:.1f}")
    print(f"Avg. wall-clock time/problem:  {avg_seconds:.1f}s")
    print()
    print(f"{'problem':<20}{'result':<10}{'retries':<9}notes")
    for r in results:
        result = "SOLVED" if r["solved"] else "FAILED"
        print(f"{r['problem_id']:<20}{result:<10}{r['retries']:<9}{r['notes']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the self-healing code agent benchmark.")
    parser.add_argument("--problem", default=None, help="Run a single problem by id")
    args = parser.parse_args()

    settings = get_settings()
    graph = build_graph()
    problems = load_problems(args.problem)

    results = [run_problem(graph, p, settings.retry_budget) for p in problems]

    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print()
    print_summary(results)


if __name__ == "__main__":
    main()
