# MCP from zero: arithmetic and strings

This is a deliberately small, standalone tutorial. You will expose three ordinary Python functions
as MCP tools, call them through the protocol, and finally let an OpenAI, OpenRouter-hosted,
or local Qwen model decide which tools to call.

For a command-focused guide containing the actual verified OpenAI and Qwen run
results, see [demo runbook](running_the_demo.md).

All Python files referenced below live in `src/simple_examples/`.
Run the commands from the repository root.

## The mental model

MCP is a standard conversation between a **client** and a **server**. The server
advertises capabilities (here, tools); the client discovers and invokes them.
A language model is optional.

```text
Without a model:  mcp_client.py <--- MCP over stdio ---> server.py ---> operations.py

With a model:     model_client.py ---> model API
                        |                 |
                        |<-- tool choice--|
                        |
                        +--- MCP over stdio ---> server.py ---> operations.py
```

`stdio` means the client starts the server as a subprocess and exchanges MCP
messages through its standard input/output streams. Nothing listens on a port.

## Prerequisites and setup

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/)
- For OpenAI: an API key
- For local Qwen: [Ollama](https://ollama.com/) and a Qwen model

From the repository root:

```bash
uv sync --extra dev
```

`uv` creates an isolated `.venv` for this tutorial.

## Lesson 1: there is no MCP yet

Read `operations.py`, then run:

```bash
uv run python src/simple_examples/direct_python.py
```

These are plain function calls. This baseline matters: MCP does not implement
arithmetic or counting—it standardizes how another process discovers and calls
the functions.

## Lesson 2: turn functions into MCP tools

Read `server.py`. `FastMCP` creates a server and `@mcp.tool()` publishes each
decorated function. Python type hints and docstrings become the JSON input
schema and description seen by clients.

You normally do not run a stdio server by itself because it waits for protocol
messages on stdin. The next client starts it for you.

## Lesson 3: call MCP without a language model

```bash
uv run python src/simple_examples/mcp_client.py
```

Follow `mcp_client.py` in this order:

1. Build the server process parameters.
2. Open the stdio transport.
3. Perform the MCP initialization handshake.
4. Ask the server to list its tools.
5. Call tools by name with JSON-like arguments.

Or run lessons 1 and 3 together:

```bash
./src/simple_examples/scripts/run_basics.sh
```

## Lesson 4: add a model

`model_client.py` is a small bridge. It discovers MCP tools, converts their
schemas to the OpenAI-compatible function-tool shape, sends those schemas to a
model, executes requested calls through MCP, and returns results to the model.

This example uses the OpenAI-compatible Chat Completions interface because OpenAI, OpenRouter, and Ollama support it. That keeps the MCP code identical while swapping
the model backend.

### OpenAI (`gpt-5-mini`)

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY.
./src/simple_examples/scripts/run_openai.sh
```

Supply a different question as one quoted argument:

```bash
./src/simple_examples/scripts/run_openai.sh "Add 17 and 26, then count the letter a in abracada."
```

Override the model if desired:

```bash
OPENAI_MODEL=gpt-5-mini ./src/simple_examples/scripts/run_openai.sh "Multiply 9 by 11."
```

### OpenRouter

OpenRouter uses the same model client and MCP server through its
[OpenAI-compatible API](https://openrouter.ai/docs/quickstart).
Set these values in your repository-root `.env` (create it from `.env.example`
if needed):

```dotenv
OPENROUTER_API_KEY=replace-me
OPENROUTER_MODEL=openai/gpt-4o-mini
```

Replace the key placeholder with your OpenRouter key. The OpenAI key is not
used by these scripts. Run from the repository root:

```bash
./src/simple_examples/scripts/run_openrouter.sh "Add 17 and 25."
./src/simple_examples/scripts/compare_openrouter.sh \
  "What is 23 multiplied by 19, and how many times does e occur in Tennessee?"
```

The comparison runs the same prompt without tools, then with MCP tools.
To select another model, change `OPENROUTER_MODEL` in `.env` to a tool-capable
model ID from OpenRouter's catalog. These are hosted API calls billed through
your OpenRouter account. The endpoint is `https://openrouter.ai/api/v1`.

### Local Qwen through Ollama

The model name is **Qwen** (not Gwen). Install/start Ollama, then pull the small
default model once:

```bash
ollama pull qwen2.5:3b
./src/simple_examples/scripts/run_qwen.sh
```

You can select any installed tool-capable Qwen model:

```bash
QWEN_MODEL=qwen3:8b ./src/simple_examples/scripts/run_qwen.sh "Count the letter s in Mississippi."
```

The script points the same OpenAI Python client at Ollama's local
`http://localhost:11434/v1` endpoint. The placeholder API key is required by
the client library but is not used by local Ollama.

## What to observe

The model does not execute Python functions directly. A complete tool turn is:

1. The MCP client discovers tool names and schemas from the MCP server.
2. The client sends those schemas and your prompt to the model API.
3. The model responds with a tool name and JSON arguments.
4. The client validates/routes that request through MCP.
5. The MCP server runs the Python function and returns content.
6. The client sends that content to the model for its final natural-language answer.

Try a prompt unrelated to the tools, such as `Explain what a prime number is.`
The model may answer without an MCP call. Tool availability is not the same as
forcing tool use.

## Tests

```bash
uv run --extra dev pytest
```

The unit tests target the underlying deterministic functions. Model behavior
is probabilistic and requires an external service, so it is intentionally not a
unit test.

## A/B test: model alone versus model with MCP tools

Run the identical prompt twice against the same backend. In arm A, the client
does not start the MCP server and sends no tool schemas. In arm B, the model can
discover and call the MCP tools:

```bash
./src/simple_examples/scripts/compare_openai.sh \
  "What is 23 multiplied by 19, and how many times does e occur in Tennessee?"

./src/simple_examples/scripts/compare_qwen.sh \
  "What is 23 multiplied by 19, and how many times does e occur in Tennessee?"
```

For just the LLM-only arm, invoke the client directly:

```bash
MODEL=gpt-5-mini uv run python src/simple_examples/model_client.py --no-tools \
  "Count the letter s in Mississippi."
```

Look for `MCP call ->` lines. They can only appear in the tool-enabled arm.
Compare answer correctness, latency, token usage, and consistency over repeated
runs. One run is a demonstration, not a reliable benchmark.

## Experiments to deepen the lesson

1. Add a `subtract` function to `operations.py`, expose it in `server.py`, and
   verify it appears automatically in the client's discovered list.
2. Make `count_letters` case-sensitive by adding a Boolean argument. Watch how
   that changes the discovered JSON schema.
3. Temporarily remove the call to `session.initialize()` and inspect the error.
4. Print each discovered `inputSchema` in `mcp_client.py`.
5. Add logging to **stderr** in the server. Never print diagnostics to stdout
   when using stdio transport, because stdout carries protocol messages.

## Troubleshooting

- `OPENAI_API_KEY` error: copy the root `.env.example` to `.env` and replace the value.
- Ollama connection error: run `ollama serve` and confirm `ollama list` shows
  the configured Qwen model.
- The local model never calls a tool: use a tool-capable Qwen release, make the
  request explicit, or try a larger model.
- Dependency confusion: run commands from the repository root.

## Further reading

- [Model Context Protocol documentation](https://modelcontextprotocol.io/)
- [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI tools and remote MCP](https://developers.openai.com/api/docs/guides/tools)
