"""将 Anthropic Messages SSE 转换为 OpenAI Responses SSE。"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable, Iterator
from typing import Any


JsonObject = dict[str, Any]


def _parse_sse(chunks: Iterable[str | bytes]) -> Iterator[tuple[str, JsonObject]]:
    buffer = ""
    for chunk in chunks:
        buffer += chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            event_name = ""
            data_lines: list[str] = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if not data_lines:
                continue
            raw = "\n".join(data_lines)
            if raw == "[DONE]":
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                yield event_name or str(data.get("type", "")), data


def _usage(input_tokens: int, output_tokens: int, cached_tokens: int) -> JsonObject:
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {"cached_tokens": cached_tokens},
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": input_tokens + output_tokens,
    }


class _ResponsesState:
    def __init__(self) -> None:
        self.sequence = 0
        self.response_id = ""
        self.model = ""
        self.created_at = int(time.time())
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        self.blocks: dict[int, JsonObject] = {}
        self.output: list[JsonObject] = []

    def emit(self, event_type: str, **payload: Any) -> str:
        event = {
            "type": event_type,
            "sequence_number": self.sequence,
            **payload,
        }
        self.sequence += 1
        return (
            f"event: {event_type}\n"
            f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"
        )

    def response(self, status: str, usage: JsonObject | None) -> JsonObject:
        return {
            "id": self.response_id,
            "object": "response",
            "created_at": self.created_at,
            "status": status,
            "error": None,
            "incomplete_details": None,
            "model": self.model,
            "output": self.output if status == "completed" else [],
            "parallel_tool_calls": False,
            "store": False,
            "usage": usage,
        }


def transform_anthropic_sse(chunks: Iterable[str | bytes]) -> Iterator[str]:
    """把任意分块的 Anthropic SSE 流转换为 Responses SSE 流。"""

    state = _ResponsesState()

    for event_name, data in _parse_sse(chunks):
        if event_name == "ping":
            continue

        if event_name == "message_start":
            message = data.get("message", {})
            state.response_id = str(message.get("id") or f"resp_{int(time.time() * 1000)}")
            state.model = str(message.get("model") or "")
            usage = message.get("usage") or {}
            state.input_tokens = int(usage.get("input_tokens") or 0)
            state.cached_tokens = int(usage.get("cache_read_input_tokens") or 0)
            yield state.emit(
                "response.created",
                response=state.response("in_progress", None),
            )
            yield state.emit(
                "response.in_progress",
                response=state.response("in_progress", None),
            )
            continue

        if event_name == "content_block_start":
            index = int(data.get("index") or 0)
            block = data.get("content_block") or {}
            block_type = block.get("type")
            if block_type == "text":
                item_id = f"msg_{state.response_id}"
                item = {
                    "type": "message",
                    "id": item_id,
                    "status": "in_progress",
                    "role": "assistant",
                    "content": [],
                }
                part = {"type": "output_text", "text": "", "annotations": []}
                state.blocks[index] = {
                    "kind": "text",
                    "item": item,
                    "item_id": item_id,
                    "text": "",
                }
                yield state.emit(
                    "response.output_item.added",
                    output_index=len(state.output),
                    item=item,
                )
                yield state.emit(
                    "response.content_part.added",
                    item_id=item_id,
                    output_index=len(state.output),
                    content_index=0,
                    part=part,
                )
            elif block_type == "tool_use":
                call_id = str(block.get("id") or f"tool_{index}")
                name = str(block.get("name") or "")
                item = {
                    "type": "function_call",
                    "id": f"fc_{call_id}",
                    "call_id": call_id,
                    "name": name,
                    "arguments": "",
                    "status": "in_progress",
                }
                state.blocks[index] = {
                    "kind": "tool",
                    "item": item,
                    "arguments": "",
                }
                yield state.emit(
                    "response.output_item.added",
                    output_index=len(state.output),
                    item=item,
                )
            continue

        if event_name == "content_block_delta":
            index = int(data.get("index") or 0)
            tracked = state.blocks.get(index)
            if tracked is None:
                continue
            delta = data.get("delta") or {}
            if tracked["kind"] == "text" and delta.get("type") == "text_delta":
                text = str(delta.get("text") or "")
                tracked["text"] += text
                yield state.emit(
                    "response.output_text.delta",
                    item_id=tracked["item_id"],
                    output_index=len(state.output),
                    content_index=0,
                    delta=text,
                )
            elif (
                tracked["kind"] == "tool"
                and delta.get("type") == "input_json_delta"
            ):
                partial = str(delta.get("partial_json") or "")
                tracked["arguments"] += partial
                yield state.emit(
                    "response.function_call_arguments.delta",
                    item_id=tracked["item"]["id"],
                    output_index=len(state.output),
                    delta=partial,
                )
            continue

        if event_name == "content_block_stop":
            index = int(data.get("index") or 0)
            tracked = state.blocks.get(index)
            if tracked is None:
                continue
            output_index = len(state.output)
            if tracked["kind"] == "text":
                text = tracked["text"]
                item = tracked["item"]
                part = {"type": "output_text", "text": text, "annotations": []}
                item = {**item, "status": "completed", "content": [part]}
                yield state.emit(
                    "response.output_text.done",
                    item_id=tracked["item_id"],
                    output_index=output_index,
                    content_index=0,
                    text=text,
                )
                yield state.emit(
                    "response.content_part.done",
                    item_id=tracked["item_id"],
                    output_index=output_index,
                    content_index=0,
                    part=part,
                )
            else:
                arguments = tracked["arguments"]
                item = {
                    **tracked["item"],
                    "arguments": arguments,
                    "status": "completed",
                }
                yield state.emit(
                    "response.function_call_arguments.done",
                    item_id=item["id"],
                    output_index=output_index,
                    arguments=arguments,
                )
            state.output.append(item)
            yield state.emit(
                "response.output_item.done",
                output_index=output_index,
                item=item,
            )
            continue

        if event_name == "message_delta":
            usage = data.get("usage") or {}
            state.input_tokens = int(
                usage.get("input_tokens") or state.input_tokens
            )
            state.output_tokens = int(
                usage.get("output_tokens") or state.output_tokens
            )
            state.cached_tokens = int(
                usage.get("cache_read_input_tokens") or state.cached_tokens
            )
            continue

        if event_name == "message_stop":
            final_usage = _usage(
                state.input_tokens,
                state.output_tokens,
                state.cached_tokens,
            )
            yield state.emit(
                "response.completed",
                response=state.response("completed", final_usage),
            )
