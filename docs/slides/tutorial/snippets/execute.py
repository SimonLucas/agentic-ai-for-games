for call in message.tool_calls:
    arguments = json.loads(call.function.arguments)
    print(f"MCP call -> {call.function.name}({arguments})")
    result = await mcp_session.call_tool(call.function.name, arguments)
    if result.isError:
        raise RuntimeError(tool_result_text(result))
    messages.append(
        {
            "role": "tool",
            "tool_call_id": call.id,
            "content": tool_result_text(result),
        }
    )
