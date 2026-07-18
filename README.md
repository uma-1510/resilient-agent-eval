# Kintsugi — A Self-Healing Code Generation Agent
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An agent that writes Python code from a problem statement, runs it in an isolated Docker
sandbox, and — when it crashes — reads its own traceback and repairs itself, up to a bounded
retry budget. Evaluated as a benchmark harness across a set of problems, not a single demo run.

> Named after *kintsugi*, the Japanese art of repairing broken pottery with visible gold
> seams — the repair is the point, not something to hide. This agent's value isn't that it
> writes perfect code on the first try; it's that it can diagnose and fix its own failures.

## Results

*(From a real `python main.py` run against `tests/problem_set.json` — model: `gemini-flash-latest`, Docker sandbox, 2026-07-18.)*

| Metric | Value |
|---|---|
| Problems evaluated | 6 |
| Solved within retry budget | 6 / 6 (100%) |
| Avg. retries to success | 0.0 |
| Avg. wall-clock time per problem | 4.6s |
| Retry budget | 3 |

<details>
<summary>Full per-problem breakdown</summary>

| Problem | Result | Retries | Notes |
|---|---|---|---|
| fizzbuzz_variant | ✅ Solved | 0 | |
| binary_search | ✅ Solved | 0 | |
| reverse_words | ✅ Solved | 0 | |
| matrix_transpose | ✅ Solved | 0 | |
| balanced_parentheses | ✅ Solved | 0 | |
| flatten_repeat_calls | ✅ Solved | 0 | Designed to trip the classic Python mutable-default-argument bug across repeated calls — solved cleanly on the first attempt anyway. |

</details>

**Honest caveat:** every problem in this run was solved on the first attempt, including two
(`balanced_parentheses`'s edge cases and `flatten_repeat_calls`, the latter specifically
engineered to bait a known Python gotcha) chosen to be more likely to trip up a one-shot
generation. `gemini-flash-latest` handled all of them cleanly, so this particular run doesn't
exercise the repair loop — the repair path (retry routing, repair-prompt construction, and the
full-history replay) is instead verified by the mocked test suite in
`tests/test_orchestrator.py`, which explicitly drives a fail-then-repair-then-succeed scenario
and a fail-until-budget-exhausted scenario. A harder or more adversarial problem set would be
needed to observe a live repair in `results.json`.

## How it works

The core loop is a LangGraph state graph with two nodes:

```
 entry ──▶ generate_code ──▶ execute_code ──┬─▶ success or retries exhausted → END
                  ▲                          │
                  └──────────────────────────┘
                     failure, retries remain
```

1. **`generate_code`** — calls Gemini to produce a complete, self-contained Python script.
   The first attempt uses a "write from scratch" prompt; every retry after that switches to a
   repair prompt built from the **full conversation history** (every prior attempt and its
   traceback, not just the latest one), so the model can reason about what it already tried
   instead of repeating a fix that didn't work.
2. **`execute_code`** — runs the script inside a locked-down Docker container: no network
   access, capped memory and CPU, read-only filesystem, hard timeout. The container is
   destroyed after every run regardless of outcome.
3. **Routing** — success ends the graph. Failure with retry budget remaining loops back to
   `generate_code`. Retry budget exhausted ends the graph and the problem is reported as
   failed.

All state (message history, current code, retry count) lives in a single shared `AgentState`
object every node reads from and writes back to — nodes return partial updates rather than
mutating state directly, which keeps each node independently testable.

## Project structure

```
.
├── main.py                  # Entry point — runs the full problem set and reports aggregate results
├── config/
│   └── settings.py          # Loads config from environment via .env (see .env.example)
├── src/
│   ├── orchestrator.py      # LangGraph nodes, routing logic, graph assembly
│   ├── sandbox.py           # Isolated Docker execution
│   ├── state.py             # Shared state schema
│   ├── prompts.py           # Generation and repair prompts
│   └── llm_client.py        # Gemini SDK wrapper
├── tests/
│   ├── problem_set.json     # Benchmark problems
│   └── test_orchestrator.py # Unit tests for routing logic (mocked, no live API/Docker needed)
├── requirements.txt
├── .env.example
└── LICENSE
```

## Setup

```bash
git clone https://github.com/uma-1510/resilient-agent-eval.git
cd resilient-agent-eval
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your Gemini API key
```

Requires Docker Desktop (or the Docker daemon) running locally — the sandbox connects via
`docker.from_env()` and will raise a clear error at startup if it can't reach the daemon.

**Gemini free-tier quota note:** some Google Cloud projects report `limit: 0` free-tier quota
on specific model IDs (e.g. `gemini-2.0-flash`) even with a valid key, and older model IDs like
`gemini-1.5-flash` may 404 as fully retired. If you hit a `429 RESOURCE_EXHAUSTED` with
`limit: 0` or a `404` on the model in `.env`, list the models your key can actually reach and
try one of the `-latest` aliases:

```bash
python -c "
from google import genai
from config.settings import get_settings
for m in genai.Client(api_key=get_settings().gemini_api_key).models.list():
    if 'generateContent' in (m.supported_actions or []):
        print(m.name)
"
```

This project's results below were generated with `MODEL_NAME=gemini-flash-latest`.

## Usage

```bash
python main.py                  # run the full benchmark set, print aggregate results, write results.json
python main.py --problem [id]   # run a single problem
```

## Sandbox security

Generated code never runs on the host. Every attempt executes inside a disposable container
with:

- `network_mode="none"` — no outbound network access
- `mem_limit="128m"` / `nano_cpus=1_000_000_000` — capped memory and CPU
- `read_only=True` — container filesystem is read-only
- A hard timeout — a hung script is killed and treated as a failed attempt, not left running

Containers are removed after every run, successful or not.

## Testing

```bash
pytest tests/
```

Unit tests cover the parts of the system that don't require a live LLM key or a running
Docker daemon: the retry/routing logic and sandbox result parsing (mocked container). The LLM
call and live sandbox execution are exercised by actually running `main.py` end to end, not
by the unit test suite.

## Known limitations

- Repair prompts replay the full conversation history, so token cost per retry grows with the
  retry budget; there's no cap or summarization if that budget is raised significantly.
- Only tested against single-file, standard-library-only problems — no support yet for
  problems requiring external packages inside the sandbox.
- Retry budget of 3 is fixed via a config value, not adaptive to problem difficulty.

## Possible extensions

- Parallel evaluation across the problem set instead of sequential
- Multi-language support beyond Python
- A small vector store of past failures used as few-shot context for repair
- Per-run cost/token tracking and a budget cap
- Swappable LLM backend (currently Gemini) — `llm_client.py` already isolates the SDK calls
  from the orchestrator to make this a contained change

## License

MIT — see [LICENSE](LICENSE).
