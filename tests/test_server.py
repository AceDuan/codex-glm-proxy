import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from codex_glm_proxy.server import create_server


ANTHROPIC_STREAM = (
    'event: message_start\n'
    'data: {"type":"message_start","message":{"id":"msg_test","model":"glm-5.2",'
    '"usage":{"input_tokens":4,"output_tokens":0,"cache_read_input_tokens":6,'
    '"cache_creation_input_tokens":3}}}\n\n'
    'event: content_block_start\n'
    'data: {"type":"content_block_start","index":0,'
    '"content_block":{"type":"text","text":""}}\n\n'
    'event: content_block_delta\n'
    'data: {"type":"content_block_delta","index":0,'
    '"delta":{"type":"text_delta","text":"OK"}}\n\n'
    'event: content_block_stop\n'
    'data: {"type":"content_block_stop","index":0}\n\n'
    'event: message_delta\n'
    'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},'
    '"usage":{"output_tokens":2}}\n\n'
    'event: message_stop\n'
    'data: {"type":"message_stop"}\n\n'
)


class FakeAnthropicHandler(BaseHTTPRequestHandler):
    request_body = None
    request_headers = None
    response_status = 200

    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        type(self).request_body = json.loads(self.rfile.read(length))
        type(self).request_headers = dict(self.headers.items())
        self.send_response(type(self).response_status)
        if type(self).response_status == 200:
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            self.wfile.write(ANTHROPIC_STREAM.encode())
        else:
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(
                b'{"type":"error","error":{"type":"authentication_error",'
                b'"message":"invalid key"}}'
            )

    def log_message(self, format, *args):
        return


def start(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


class ServerTests(unittest.TestCase):
    def setUp(self):
        FakeAnthropicHandler.response_status = 200
        FakeAnthropicHandler.request_body = None
        FakeAnthropicHandler.request_headers = None
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeAnthropicHandler)
        start(self.upstream)
        upstream_url = (
            f"http://127.0.0.1:{self.upstream.server_port}/v1/messages"
        )
        self.proxy = create_server("127.0.0.1", 0, upstream_url)
        start(self.proxy)
        self.base_url = f"http://127.0.0.1:{self.proxy.server_port}"

    def tearDown(self):
        self.proxy.shutdown()
        self.proxy.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()

    def test_health_and_models(self):
        with urllib.request.urlopen(f"{self.base_url}/healthz") as response:
            health = json.load(response)
        with urllib.request.urlopen(f"{self.base_url}/v1/models") as response:
            models = json.load(response)

        self.assertEqual(health, {"status": "ok"})
        self.assertEqual(models["data"][0]["id"], "glm-5.2")

    def test_forwards_request_and_streams_responses_events(self):
        body = {
            "model": "glm-5.2",
            "instructions": "简短回答",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "只回复 OK"}],
                }
            ],
            "tools": [],
            "tool_choice": "auto",
            "stream": True,
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/responses",
            data=json.dumps(body).encode(),
            headers={
                "content-type": "application/json",
                "authorization": "Bearer secret-key",
            },
            method="POST",
        )

        with urllib.request.urlopen(request) as response:
            result = response.read().decode()

        self.assertIn("event: response.created", result)
        self.assertIn("event: response.output_text.delta", result)
        self.assertIn("event: response.completed", result)
        completed_line = next(
            line
            for line in result.splitlines()
            if line.startswith("data:")
            and '"type":"response.completed"' in line
        )
        completed = json.loads(completed_line.removeprefix("data:").strip())
        self.assertEqual(
            completed["response"]["usage"],
            {
                "input_tokens": 13,
                "input_tokens_details": {"cached_tokens": 6},
                "output_tokens": 2,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 15,
            },
        )
        self.assertEqual(
            FakeAnthropicHandler.request_headers["X-Api-Key"],
            "secret-key",
        )
        self.assertEqual(
            FakeAnthropicHandler.request_body["system"],
            "简短回答",
        )
        self.assertEqual(
            FakeAnthropicHandler.request_body["messages"][0]["content"][0]["text"],
            "只回复 OK",
        )

    def test_maps_upstream_http_error(self):
        FakeAnthropicHandler.response_status = 401
        request = urllib.request.Request(
            f"{self.base_url}/v1/responses",
            data=json.dumps(
                {"model": "glm-5.2", "input": [], "stream": True}
            ).encode(),
            headers={
                "content-type": "application/json",
                "authorization": "Bearer bad-key",
            },
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request)

        self.assertEqual(context.exception.code, 401)
        error = json.loads(context.exception.read())
        self.assertEqual(error["error"]["type"], "authentication_error")
        self.assertEqual(error["error"]["message"], "invalid key")


if __name__ == "__main__":
    unittest.main()
