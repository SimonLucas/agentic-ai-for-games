for _ in range(8):
    response = await llm.chat.completions.create(
        model=model, messages=messages, tools=tools, tool_choice="auto"
    )
    message = response.choices[0].message
    messages.append(message.model_dump(exclude_none=True))

    if not message.tool_calls:
        return message.content or "(The model returned no text.)"
