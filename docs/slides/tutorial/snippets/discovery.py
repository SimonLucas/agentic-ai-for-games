async with stdio_client(server) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()

        tools = await session.list_tools()
        print("Discovered tools:", ", ".join(tool.name for tool in tools.tools))

        arithmetic = await session.call_tool("multiply", {"a": 6, "b": 7})
