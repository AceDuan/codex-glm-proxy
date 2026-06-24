import unittest

from codex_glm_proxy.request_transform import transform_responses_request


class RequestTransformTests(unittest.TestCase):
    def test_transforms_messages_tools_and_tool_results(self):
        request = {
            "model": "glm-5.2",
            "instructions": "你是编码助手",
            "input": [
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "遵守项目规范"}],
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "读取文件"}],
                },
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "read_file",
                    "arguments": '{"path":"README.md"}',
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "文件内容",
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "name": "read_file",
                    "description": "读取文件",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                    "strict": False,
                },
                {
                    "type": "namespace",
                    "name": "tools",
                    "description": "工具集合",
                    "tools": [
                        {
                            "type": "function",
                            "name": "write_file",
                            "description": "写入文件",
                            "parameters": {"type": "object", "properties": {}},
                        }
                    ],
                },
                {"type": "web_search", "external_web_access": True},
                {"type": "image_generation", "output_format": "png"},
            ],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "stream": True,
        }

        result = transform_responses_request(request)

        self.assertEqual(result["model"], "glm-5.2")
        self.assertEqual(
            result["system"],
            "你是编码助手\n\n遵守项目规范",
        )
        self.assertTrue(result["stream"])
        self.assertEqual(result["tool_choice"], {"type": "auto"})
        self.assertEqual(
            [tool["name"] for tool in result["tools"]],
            ["read_file", "tools__write_file"],
        )
        self.assertEqual(
            result["messages"],
            [
                {"role": "user", "content": [{"type": "text", "text": "读取文件"}]},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "read_file",
                            "input": {"path": "README.md"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_1",
                            "content": "文件内容",
                        }
                    ],
                },
            ],
        )

    def test_maps_required_and_specific_tool_choices(self):
        base = {
            "model": "glm-5.2",
            "input": [],
            "tools": [
                {
                    "type": "function",
                    "name": "read_file",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
        }

        required = transform_responses_request({**base, "tool_choice": "required"})
        specific = transform_responses_request(
            {
                **base,
                "tool_choice": {"type": "function", "name": "read_file"},
            }
        )

        self.assertEqual(required["tool_choice"], {"type": "any"})
        self.assertEqual(
            specific["tool_choice"],
            {"type": "tool", "name": "read_file"},
        )

    def test_rejects_invalid_function_arguments(self):
        request = {
            "model": "glm-5.2",
            "input": [
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "read_file",
                    "arguments": "{invalid",
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "函数参数不是有效 JSON"):
            transform_responses_request(request)


if __name__ == "__main__":
    unittest.main()
