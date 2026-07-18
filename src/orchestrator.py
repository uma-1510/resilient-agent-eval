from __future__ import annotations

from typing import Literal, Optional

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.llm_client import GeminiClient
from src.prompts import build_generate_prompt, build_repair_prompt
from src.sandbox import DockerSandbox
from src.state import AgentState


def generate_code(state: AgentState, llm: GeminiClient) -> dict:
    prompt = (
        build_generate_prompt(state.problem_statement)
        if state.retry_count == 0
        else build_repair_prompt(state)
    )
    messages = state.messages + [{"role": "user", "content": prompt}]
    code = llm.generate(messages)
    messages = messages + [{"role": "model", "content": code}]
    return {"generated_code": code, "messages": messages}


def execute_code(state: AgentState, sandbox: DockerSandbox) -> dict:
    result = sandbox.run(state.generated_code)
    if result.success:
        return {"last_result": result, "solved": True}
    return {"last_result": result, "retry_count": state.retry_count + 1}


def route_after_execution(state: AgentState) -> Literal["generate_code", "__end__"]:
    """Standalone routing function, independent of graph internals, so it can
    be unit-tested by constructing an AgentState directly."""
    if state.solved:
        return END
    # retry_count is the number of failed attempts so far. max_retries repair
    # attempts means max_retries + 1 total attempts (1 initial + N repairs),
    # so we keep looping until retry_count exceeds max_retries.
    if state.retry_count > state.max_retries:
        return END
    return "generate_code"


def build_graph(
    llm: Optional[GeminiClient] = None,
    sandbox: Optional[DockerSandbox] = None,
) -> CompiledStateGraph:
    llm = llm or GeminiClient()
    sandbox = sandbox or DockerSandbox()

    graph = StateGraph(AgentState)
    graph.add_node("generate_code", lambda state: generate_code(state, llm))
    graph.add_node("execute_code", lambda state: execute_code(state, sandbox))
    graph.set_entry_point("generate_code")
    graph.add_edge("generate_code", "execute_code")
    graph.add_conditional_edges("execute_code", route_after_execution)
    return graph.compile()
