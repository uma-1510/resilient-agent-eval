from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExecutionResult(BaseModel):
    """Outcome of running a generated script inside the sandbox."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    exit_code: Optional[int] = None


class AgentState(BaseModel):
    """Shared state threaded through every node in the orchestrator graph.

    Nodes return partial updates (dicts of the fields they changed) rather than
    mutating an instance directly, so each node can be tested by constructing a
    state and checking the dict it returns.
    """

    problem_id: str
    problem_statement: str
    generated_code: str = ""
    # Full conversation history replayed into repair prompts, seeded with the
    # original problem and appended to after every generation and every failure.
    messages: list[dict] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    last_result: Optional[ExecutionResult] = None
    solved: bool = False
