# Running the MCP model demo

This runbook records the complete, tested path for the beginner MCP example in
`src/simple_examples/`. Start with [the tutorial](tutorial.md) for the conceptual tutorial; use this
file when you want to run and compare the backends.

The model outputs below are historical results from the original tutorial;
outputs can vary by model and version.

## What the demo proves

The same local MCP server can be used with different language-model backends:

```text
OpenAI gpt-5-mini ----\
                       > model_client.py <-- MCP/stdio --> server.py
Ollama + Qwen --------/                              |
                                                     +--> operations.py
```

The model does not execute the arithmetic or string functions. It chooses a
tool and supplies arguments. `model_client.py` sends that request to the MCP
server, receives the result, and returns it to the model for a final answer.

## 1. Install the tutorial dependencies

From the repository root:

```bash
uv sync --extra dev
```

This creates a `.venv` at the repository root.

## 2. Verify the code without a model

Run the plain Python and direct MCP examples:

```bash
./src/simple_examples/scripts/run_basics.sh
```

Expected essential output:

```text
12 + 30 = 42
6 × 7 = 42
'a' in 'Banana' = 3

Discovered tools: add, multiply, count_letters
multiply(6, 7): 42.0
count_letters(...): 6
```

This step cleanly separates MCP from model behavior. The second half performs
the MCP initialization handshake, discovers the tools, and calls them without
using any LLM API.

Run the unit tests too:

```bash
uv run --extra dev pytest -q
```

The verified result is:

```text
3 passed
```

## 3. Run with OpenAI `gpt-5-mini`

Create a local environment file:

```bash
cp .env.example .env
```

Edit `.env` and replace `replace-me` with an OpenAI API key:

```dotenv
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-5-mini
```

`.env` is ignored by Git. Never commit an API key.

Run the default compound example:

```bash
./src/simple_examples/scripts/run_openai.sh
```

This is equivalent to:

```bash
./src/simple_examples/scripts/run_openai.sh \
  "What is 23 multiplied by 19, and how many times does e occur in Tennessee?"
```

The tested run produced:

```text
MCP call -> multiply({'a': 23, 'b': 19})
MCP call -> count_letters({'text': 'Tennessee', 'letter': 'e'})
23 × 19 = 437.

The letter "e" appears 4 times in "Tennessee".
```

Try other requests by passing one quoted prompt:

```bash
./src/simple_examples/scripts/run_openai.sh "Add 17 and 25."
./src/simple_examples/scripts/run_openai.sh "Count the letter a in abracadabra."
```

To select another OpenAI model for one run:

```bash
OPENAI_MODEL=gpt-5-mini ./src/simple_examples/scripts/run_openai.sh "Multiply 9 by 11."
```

## Run with OpenRouter

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

## 4. Run with local Qwen through Ollama

First install Ollama if necessary, then start its server in a separate terminal:

```bash
ollama serve
```

In another terminal, pull the tutorial's default Qwen model once:

```bash
ollama pull qwen2.5:3b
```

Check what is installed:

```bash
ollama list
```

Run the same default prompt:

```bash
./src/simple_examples/scripts/run_qwen.sh
```

Or provide a different prompt:

```bash
./src/simple_examples/scripts/run_qwen.sh "Use the count_letters tool to count the letter s in Mississippi."
```

The script uses Ollama's OpenAI-compatible endpoint at
`http://localhost:11434/v1`. Its `ollama` API-key value is only a placeholder
required by the OpenAI client library; local Ollama does not authenticate it.

### Use a Qwen model already installed

The machine used to verify this tutorial had `qwen2.5:3b`, so it was selected
without downloading another model:

```bash
QWEN_MODEL=qwen2.5:3b ./src/simple_examples/scripts/run_qwen.sh \
  "Use the multiply tool to multiply 23 by 19."
```

Verified result:

```text
MCP call -> multiply({'a': 23, 'b': 19})
The result of multiplying 23 by 19 is 437.0.
```

The string tool was also verified independently:

```bash
QWEN_MODEL=qwen2.5:3b ./src/simple_examples/scripts/run_qwen.sh \
  "Use the count_letters tool to count how many times e occurs in Tennessee."
```

Verified result:

```text
MCP call -> count_letters({'text': 'Tennessee', 'letter': 'e'})
The letter 'e' occurs 4 times in the string "Tennessee".
```

### Local verification on 14 September 2026

The installed `qwen2.5:3b` model was checked with the relocated tutorial.
After starting `ollama serve`, the Qwen script successfully called
`count_letters` for `Tennessee` and returned 4. No model download was needed.

## An instructive small-model failure

The installed 3-billion-parameter Qwen model was also tested with the compound
prompt asking for both multiplication and letter counting. It emitted:

```text
MCP call -> multiply({'a': 23, 'b': 19})
MCP call -> multiply({'letter': 'e', 'text': 'Tennessee'})
```

The second request supplied the right arguments for `count_letters` but the
wrong tool name. The MCP server rejected it because `multiply` requires `a`
and `b`.

This demonstrates two useful lessons:

1. Backend compatibility does not imply equal tool-selection quality. A small
   local model may struggle more with multiple calls in one turn.
2. MCP tool schemas provide a validation boundary. The incorrect model output
   was rejected rather than silently producing a misleading result.

Focused, explicit prompts worked with this small model. A larger or newer
tool-capable Qwen model should generally handle compound requests more reliably.

## Changing backends directly

All backend wrapper scripts call the same `model_client.py`. The effective settings
are:

| Backend | Model | Base URL | API key |
|---|---|---|---|
| OpenAI | `gpt-5-mini` | OpenAI default | `OPENAI_API_KEY` |
| OpenRouter | `openai/gpt-4o-mini` by default | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| Ollama | `qwen2.5:3b` by default | `http://localhost:11434/v1` | placeholder `ollama` |

You can invoke the client directly:

```bash
MODEL=gpt-5-mini \
OPENAI_API_KEY=your-key-here \
uv run python src/simple_examples/model_client.py "Add 10 and 32."
```

For Ollama:

```bash
MODEL=qwen2.5:3b \
BASE_URL=http://localhost:11434/v1 \
API_KEY=ollama \
uv run python src/simple_examples/model_client.py "Multiply 6 by 7."
```

Prefer `.env` over putting a real key directly in shell history.

## Reading the output

MCP SDK messages such as `ListToolsRequest` and `CallToolRequest` show protocol
activity. Lines beginning with `MCP call ->` are printed by `model_client.py`
and reveal the model-selected tool name and arguments. The final lines are the
model's natural-language response after it receives the tool result.

## A/B comparison: LLM only versus LLM + MCP

The comparison scripts send the same prompt to the same model twice:

```bash
./src/simple_examples/scripts/compare_openai.sh \
  "What is 23 multiplied by 19, and how many times does e occur in Tennessee?"

./src/simple_examples/scripts/compare_qwen.sh \
  "What is 23 multiplied by 19, and how many times does e occur in Tennessee?"
```

Arm A calls the model API without starting the MCP server and without including
any tool definitions. Arm B uses the full MCP loop. `MCP call ->` output is
therefore direct evidence that only arm B invoked a tool.

You can also run only the tool-free arm:

```bash
MODEL=gpt-5-mini uv run python src/simple_examples/model_client.py --no-tools \
  "Count the letter s in Mississippi."
```

For a meaningful experiment, repeat prompts several times and record exact
correctness, latency, and token usage. Model outputs can vary between calls, so
a single side-by-side result is illustrative rather than statistically useful.

## Troubleshooting

### OpenAI reports a missing key

Confirm the repository-root `.env` exists and contains `OPENAI_API_KEY`. Run commands
from the repository root so the expected `.env` is loaded.

### Ollama says all connection attempts failed

The server is not listening. Start it in another terminal:

```bash
ollama serve
```

`run_qwen.sh` performs this check before launching the MCP client and prints the
same instruction when it cannot reach Ollama.

### Ollama says the model is missing

Either pull the default:

```bash
ollama pull qwen2.5:3b
```

or select one shown by `ollama list`:

```bash
QWEN_MODEL=your-model-name ./src/simple_examples/scripts/run_qwen.sh
```

For example, `QWEN_MODEL=qwen3:8b` only selects that model; it does not download
it. Install it once before the first run:

```bash
ollama pull qwen3:8b
QWEN_MODEL=qwen3:8b ./src/simple_examples/scripts/run_qwen.sh \
  "Count the letter s in Mississippi."
```

### Qwen chooses the wrong tool

Try a focused prompt naming the desired tool, then consider a larger or newer
tool-capable model. The validation error is useful evidence that MCP is
enforcing the tool's declared input contract.

### The MCP server appears to hang when run directly

That is expected for a stdio server: it is waiting for MCP messages on stdin.
Run one of the clients instead; the client starts and manages the server.
