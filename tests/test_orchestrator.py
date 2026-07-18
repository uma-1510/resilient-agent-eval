from __future__ import annotations

from src.orchestrator import build_graph, execute_code, generate_code, route_after_execution
from src.state import AgentState, ExecutionResult


# --- route_after_execution ---------------------------------------------------

def test_route_ends_when_solved():
    state = AgentState(problem_id="p", problem_statement="x", solved=True)
    assert route_after_execution(state) == "__end__"


def test_route_loops_when_retries_remain():
    state = AgentState(
        problem_id="p", problem_statement="x", solved=False, retry_count=1, max_retries=3
    )
    assert route_after_execution(state) == "generate_code"


def test_route_loops_on_final_allowed_repair():
    # retry_count == max_retries means the budget isn't exhausted yet: one
    # more (the max_retries-th) repair attempt is still allowed.
    state = AgentState(
        problem_id="p", problem_statement="x", solved=False, retry_count=3, max_retries=3
    )
    assert route_after_execution(state) == "generate_code"


def test_route_ends_when_budget_exhausted():
    state = AgentState(
        problem_id="p", problem_statement="x", solved=False, retry_count=4, max_retries=3
    )
    assert route_after_execution(state) == "__end__"


# --- generate_code node -------------------------------------------------------

def test_generate_code_uses_generate_prompt_on_first_attempt(mocker):
    llm = mocker.Mock()
    llm.generate.return_value = "print('hi')"
    state = AgentState(problem_id="p", problem_statement="say hi", retry_count=0)

    update = generate_code(state, llm)

    sent_prompt = llm.generate.call_args.args[0][-1]["content"]
    assert "say hi" in sent_prompt
    assert "That script failed" not in sent_prompt
    assert update["generated_code"] == "print('hi')"
    assert update["messages"][-1] == {"role": "model", "content": "print('hi')"}


def test_generate_code_uses_repair_prompt_on_retry(mocker):
    llm = mocker.Mock()
    llm.generate.return_value = "print('fixed')"
    state = AgentState(
        problem_id="p",
        problem_statement="say hi",
        generated_code="print(1/0)",
        retry_count=1,
        last_result=ExecutionResult(success=False, stderr="ZeroDivisionError"),
    )

    update = generate_code(state, llm)

    sent_prompt = llm.generate.call_args.args[0][-1]["content"]
    assert "That script failed" in sent_prompt
    assert "ZeroDivisionError" in sent_prompt
    assert update["generated_code"] == "print('fixed')"


# --- execute_code node ---------------------------------------------------------

def test_execute_code_marks_solved_on_success(mocker):
    sandbox = mocker.Mock()
    sandbox.run.return_value = ExecutionResult(success=True, stdout="OK", exit_code=0)
    state = AgentState(problem_id="p", problem_statement="x", generated_code="print('OK')")

    update = execute_code(state, sandbox)

    assert update["solved"] is True
    assert "retry_count" not in update


def test_execute_code_bumps_retry_count_on_failure(mocker):
    sandbox = mocker.Mock()
    sandbox.run.return_value = ExecutionResult(success=False, stderr="boom", exit_code=1)
    state = AgentState(
        problem_id="p", problem_statement="x", generated_code="raise ValueError", retry_count=1
    )

    update = execute_code(state, sandbox)

    assert "solved" not in update
    assert update["retry_count"] == 2


# --- full graph, mocked llm/sandbox --------------------------------------------

def test_graph_solves_after_one_repair(mocker):
    llm = mocker.Mock()
    llm.generate.side_effect = ["print(1/0)", "print(1)"]

    sandbox = mocker.Mock()
    sandbox.run.side_effect = [
        ExecutionResult(success=False, stderr="ZeroDivisionError", exit_code=1),
        ExecutionResult(success=True, stdout="1", exit_code=0),
    ]

    graph = build_graph(llm=llm, sandbox=sandbox)
    final = graph.invoke(AgentState(problem_id="p1", problem_statement="print 1", max_retries=3))

    assert final["solved"] is True
    assert final["retry_count"] == 1
    assert llm.generate.call_count == 2
    assert sandbox.run.call_count == 2


def test_graph_fails_after_exhausting_retry_budget(mocker):
    llm = mocker.Mock()
    llm.generate.return_value = "raise ValueError('nope')"

    sandbox = mocker.Mock()
    sandbox.run.return_value = ExecutionResult(success=False, stderr="ValueError: nope", exit_code=1)

    graph = build_graph(llm=llm, sandbox=sandbox)
    final = graph.invoke(AgentState(problem_id="p1", problem_statement="x", max_retries=2))

    assert final["solved"] is False
    assert final["retry_count"] == 3  # 1 initial failure + 2 repair failures
    assert llm.generate.call_count == 3  # initial attempt + 2 repairs
    assert sandbox.run.call_count == 3
