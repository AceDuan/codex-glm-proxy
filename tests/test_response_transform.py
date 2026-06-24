import json
import unittest

from codex_glm_proxy.response_transform import transform_anthropic_sse


def event(name, data):
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def parse_output(chunks):
    result = []
    for chunk in chunks:
        lines = chunk.strip().splitlines()
        result.append((lines[0].removeprefix("event: "), json.loads(lines[1][6:])))
    return result


class ResponseTransformTests(unittest.TestCase):
    def test_transforms_text_stream_and_usage(self):
        source = [
            event(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_1",
                        "type": "message",
                        "role": "assistant",
                        "model": "glm-5.2",
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    },
                },
            ),
            event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "O"},
                },
            ),
            event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "K"},
                },
            ),
            event(
                "content_block_stop",
                {"type": "content_block_stop", "index": 0},
            ),
            event(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 2,
                        "cache_read_input_tokens": 3,
                    },
                },
            ),
            event("message_stop", {"type": "message_stop"}),
        ]

        output = parse_output(transform_anthropic_sse(source))
        event_names = [name for name, _ in output]

        self.assertEqual(event_names[0], "response.created")
        self.assertIn("response.output_item.added", event_names)
        self.assertEqual(
            [
                payload["delta"]
                for name, payload in output
                if name == "response.output_text.delta"
            ],
            ["O", "K"],
        )
        completed = output[-1][1]["response"]
        self.assertEqual(output[-1][0], "response.completed")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["output"][0]["content"][0]["text"], "OK")
        self.assertEqual(
            completed["usage"],
            {
                "input_tokens": 12,
                "input_tokens_details": {"cached_tokens": 3},
                "output_tokens": 2,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 14,
            },
        )

    def test_transforms_tool_use_stream(self):
        source = [
            event(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_2",
                        "model": "glm-5.2",
                        "usage": {"input_tokens": 20, "output_tokens": 0},
                    },
                },
            ),
            event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "tool_1",
                        "name": "read_file",
                        "input": {},
                    },
                },
            ),
            event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": '{"path":',
                    },
                },
            ),
            event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": '"README.md"}',
                    },
                },
            ),
            event(
                "content_block_stop",
                {"type": "content_block_stop", "index": 0},
            ),
            event(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use"},
                    "usage": {"output_tokens": 10},
                },
            ),
            event("message_stop", {"type": "message_stop"}),
        ]

        output = parse_output(transform_anthropic_sse(source))
        deltas = [
            payload["delta"]
            for name, payload in output
            if name == "response.function_call_arguments.delta"
        ]
        self.assertEqual(deltas, ['{"path":', '"README.md"}'])

        completed = output[-1][1]["response"]
        self.assertEqual(
            completed["output"][0],
            {
                "type": "function_call",
                "id": "fc_tool_1",
                "call_id": "tool_1",
                "name": "read_file",
                "arguments": '{"path":"README.md"}',
                "status": "completed",
            },
        )


if __name__ == "__main__":
    unittest.main()
