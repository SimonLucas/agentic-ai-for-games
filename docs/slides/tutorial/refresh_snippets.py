"""Extract exact, dedented code fragments from this repository."""
from pathlib import Path
import textwrap
import json
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXCERPTS = {
    'function': ('src/simple_examples/operations.py', 'def multiply(', '\n\ndef count_letters'),
    'server': ('src/simple_examples/server.py', '@mcp.tool()\ndef multiply', '\n\n@mcp.tool()\ndef count_letters'),
    'discovery': ('src/simple_examples/mcp_client.py', '    async with stdio_client(server)', '\n            letters ='),
    'schema': ('src/simple_examples/model_client.py', '    return [', '\n\n\ndef tool_result_text'),
    'request': ('src/simple_examples/model_client.py', '            for _ in range(8):', '\n                for call in message.tool_calls:'),
    'execute': ('src/simple_examples/model_client.py', '                for call in message.tool_calls:', '\n\n    raise RuntimeError'),
    'search': ('src/game_agent/griddle/search_server.py', '    @server.tool()\n    def mcs_advice', '\n    @server.tool()\n    def rollout'),
}
manifest = {}
for name, (file, start, end) in EXCERPTS.items():
    source = (ROOT / file).read_text()
    a = source.index(start)
    b = source.index(end, a)
    snippet = textwrap.dedent(source[a:b]).rstrip() + '\n'
    (HERE / 'snippets' / (name + '.py')).write_text(snippet)
    manifest[name] = {'source': file, 'first_line': source[:a].count('\n') + 1,
                      'last_line': source[:b].count('\n')}
(HERE / 'snippets' / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
