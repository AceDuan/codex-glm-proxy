"""将 OpenAI Responses 请求转换为 Anthropic Messages 请求。"""

from __future__ import annotations

import json
from typing import Any


JsonObject = dict[str, Any]


def _text_blocks(content: Any) -> list[JsonObject]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return []

    blocks: list[JsonObject] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type in {"input_text", "output_text", "text"}:
            text = part.get("text")
            if isinstance(text, str):
                blocks.append({"type": "text", "text": text})
        elif part_type == "input_image":
            image_url = part.get("image_url")
            if isinstance(image_url, str) and image_url.startswith("data:"):
                header, _, data = image_url.partition(",")
                media_type = header.removeprefix("data:").split(";", 1)[0]
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type or "image/png",
                            "data": data,
                        },
                    }
                )
    return blocks


def _parse_arguments(raw: Any) -> JsonObject:
    if isinstance(raw, dict):
        return raw
    if raw in {None, ""}:
        return {}
    if not isinstance(raw, str):
        raise ValueError("函数参数不是有效 JSON 对象")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("函数参数不是有效 JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("函数参数不是有效 JSON 对象")
    return parsed


def _transform_tools(tools: Any) -> tuple[list[JsonObject], dict[str, str]]:
    if not isinstance(tools, list):
        return [], {}

    result: list[JsonObject] = []
    name_map: dict[str, str] = {}

    def add_function(tool: JsonObject, namespace: str | None = None) -> None:
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            return
        routed_name = f"{namespace}__{name}" if namespace else name
        name_map[name] = routed_name
        name_map[routed_name] = routed_name
        if namespace:
            name_map[f"{namespace}.{name}"] = routed_name
        result.append(
            {
                "name": routed_name,
                "description": tool.get("description") or "",
                "input_schema": tool.get("parameters")
                if isinstance(tool.get("parameters"), dict)
                else {"type": "object", "properties": {}},
            }
        )

    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_type = tool.get("type")
        if tool_type == "function":
            add_function(tool)
        elif tool_type == "namespace":
            namespace = tool.get("name")
            nested_tools = tool.get("tools")
            if isinstance(namespace, str) and isinstance(nested_tools, list):
                for nested in nested_tools:
                    if isinstance(nested, dict) and nested.get("type") == "function":
                        add_function(nested, namespace)
        # web_search、image_generation 等 Responses 内置工具没有等价的
        # Anthropic 客户端工具，首版明确过滤。

    return result, name_map


def _map_tool_choice(value: Any, name_map: dict[str, str]) -> JsonObject | None:
    if value is None or value == "auto":
        return {"type": "auto"}
    if value == "required":
        return {"type": "any"}
    if value == "none":
        return None
    if isinstance(value, dict) and value.get("type") == "function":
        name = value.get("name")
        if isinstance(name, str):
            return {"type": "tool", "name": name_map.get(name, name)}
    return {"type": "auto"}


def transform_responses_request(body: JsonObject) -> JsonObject:
    """转换单个 Responses API 请求。"""

    model = body.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("缺少 model")

    tools, name_map = _transform_tools(body.get("tools"))
    messages: list[JsonObject] = []
    system_parts: list[str] = []

    instructions = body.get("instructions")
    if isinstance(instructions, str) and instructions:
        system_parts.append(instructions)

    input_items = body.get("input")
    if isinstance(input_items, str):
        messages.append(
            {"role": "user", "content": [{"type": "text", "text": input_items}]}
        )
    elif isinstance(input_items, list):
        for item in input_items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type", "message")
            if item_type == "message":
                role = item.get("role", "user")
                blocks = _text_blocks(item.get("content"))
                if not blocks:
                    continue
                if role in {"developer", "system"}:
                    system_parts.extend(
                        block["text"]
                        for block in blocks
                        if block.get("type") == "text"
                    )
                else:
                    messages.append(
                        {
                            "role": "assistant" if role == "assistant" else "user",
                            "content": blocks,
                        }
                    )
            elif item_type == "function_call":
                name = item.get("name")
                call_id = item.get("call_id") or item.get("id")
                if not isinstance(name, str) or not isinstance(call_id, str):
                    continue
                messages.append(
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": call_id,
                                "name": name_map.get(name, name),
                                "input": _parse_arguments(item.get("arguments")),
                            }
                        ],
                    }
                )
            elif item_type == "function_call_output":
                call_id = item.get("call_id")
                if not isinstance(call_id, str):
                    continue
                output = item.get("output", "")
                if not isinstance(output, str):
                    output = json.dumps(output, ensure_ascii=False)
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": call_id,
                                "content": output,
                            }
                        ],
                    }
                )

    result: JsonObject = {
        "model": model,
        "max_tokens": body.get("max_output_tokens", 32768),
        "messages": messages,
        "stream": bool(body.get("stream", True)),
    }
    if system_parts:
        result["system"] = "\n\n".join(system_parts)
    if tools:
        result["tools"] = tools
        tool_choice = _map_tool_choice(body.get("tool_choice"), name_map)
        if tool_choice is not None:
            result["tool_choice"] = tool_choice

    for source, target in (
        ("temperature", "temperature"),
        ("top_p", "top_p"),
        ("stop", "stop_sequences"),
    ):
        if source in body:
            result[target] = body[source]

    return result
