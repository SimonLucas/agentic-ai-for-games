# Understanding the decorators in this repository

`@mcp.tool()` and `@server.tool()` do the same job. `mcp` and `server` are
ordinary variable names for instances of `FastMCP`; neither name is a special
Python keyword or a different kind of decorator.

## What the `@` means

A decorator is a callable applied to a function or class when its definition
executes. For example:

```python
@mcp.tool()
def multiply(a: float, b: float) -> float:
    return a * b
```

is equivalent to defining the function and then writing:

```python
multiply = mcp.tool()(multiply)
```

Here `mcp.tool()` produces the decorator; the parentheses matter. In the
installed SDK it registers the function with that server and returns the
function itself. Registration does not execute the multiplication, start the
server, or call the LLM. The function still works as an ordinary Python callable.

## Why the names differ in our examples

| File | Server object | Decorator | Reason for the structure |
|---|---|---|---|
| `src/simple_examples/server.py` | `mcp = FastMCP(...)` at module level | `@mcp.tool()` | One small, straightforward server |
| `src/game_agent/griddle/search_server.py` | `server = FastMCP(...)` inside `create_server()` | `@server.tool()` | Each factory call creates a fresh server and `SearchContext` |

In Griddle, the nested tool functions close over that factory's `context`.
This keeps each server's game state separate and makes tests easier. The
variable name itself changes nothing: use the object you want to register on.
A top-level decorator runs when its module is imported; Griddle's nested
registrations happen when `create_server()` executes.

## Which MCP decorator should I use?

This project pins the official Python SDK to **v1 (`mcp<2`)** and imports
`FastMCP` from `mcp.server.fastmcp`. Examples for other SDK versions or the
separate `fastmcp` package may differ.

| Decorator | Use when | Example | Used here? |
|---|---|---|---|
| `@mcp.tool()` | Exposing an operation the host may let a model request | Arithmetic, MCS advice, rollout | Yes |
| `@mcp.resource("rules://griddle")` | Exposing addressable context for the application to read | Game rules or a level description | No; illustrative extension |
| `@mcp.prompt()` | Exposing a reusable prompt template for a user to select | A game-analysis prompt assembled from parameters | No; illustrative extension |
| `@mcp.completion()` | Suggesting values for prompt/resource-template arguments | Known level names while entering a parameter | No |

Tools can be read-only: search advice is a tool even though it does not mutate
the real game. A prompt decorator registers a template; it does not itself
send a request to a model. Our versioned prompt text files are loaded locally,
not registered as MCP prompts. Completion here means argument suggestions,
not an LLM chat completion.

The host still controls what reaches the model. `configure` and `set_position`
are MCP tools in Griddle, but the host omits them from model-facing tool schemas.
They are not intrinsically private because of their decorators: another MCP
client connected to that server can discover them. The host's selected-tool
checks enforce the boundary for our LLM agent.

See the [official v1 SDK documentation](https://py.sdk.modelcontextprotocol.io/v1/)
for tool, resource and prompt examples.

## Other decorators in our Python code

These have no role in registering MCP capabilities.

| Decorator | Purpose | Example in this repo |
|---|---|---|
| `@dataclass(frozen=True, ...)` from `pydantic.dataclasses` | Construct and validate typed data objects; prevent field reassignment | `GriddleState`, `CardDeck`, `FlatLetterGrid`, `WordMatch` |
| `@model_validator(mode="after")` | Check relationships between already validated fields | Reject duplicate tool names or benchmark agent labels |
| `@asynccontextmanager` from `contextlib` | Turn an async generator into an `async with` resource scope | `LLMAgent.game_session`: acquire clients before `yield`, clean up in `finally` |
| `@classmethod` | Receive the class as `cls`; useful for alternate constructors | `ForwardModelGriddle.new_game(...)` |
| `@staticmethod` | Keep a helper on a class without implicit `self` or `cls` | `MCSAgent._rollout(...)` |
| `@property` | Read a computed value using attribute syntax | `match.score`, rather than `match.score()` |

`frozen=True` prevents assigning fields; it is not a general guarantee that
all nested objects are immutable. Validators run as part of validation, not on
every ordinary method call. An async context manager controls lifetime; it does
not make the code inside its scope execute concurrently.

Use plain functions unless registration, validation, resource management or
class access semantics require a decorator. If decorators are stacked, Python
applies the one nearest the function first.
