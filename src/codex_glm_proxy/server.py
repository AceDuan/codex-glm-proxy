"""本地 Responses API HTTP 服务。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .request_transform import transform_responses_request
from .response_transform import transform_anthropic_sse


DEFAULT_UPSTREAM_URL = "https://open.bigmodel.cn/api/anthropic/v1/messages"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _extract_api_key(headers: Any) -> str | None:
    authorization = headers.get("authorization")
    if isinstance(authorization, str) and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    api_key = headers.get("x-api-key")
    return api_key.strip() if isinstance(api_key, str) else None


def _map_upstream_error(raw: bytes, status: int) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        parsed = {}
    upstream_error = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(upstream_error, dict):
        message = upstream_error.get("message") or f"上游请求失败：HTTP {status}"
        error_type = upstream_error.get("type") or "upstream_error"
    else:
        message = str(upstream_error or parsed.get("message") or f"上游请求失败：HTTP {status}")
        error_type = "upstream_error"
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": None,
            "code": None,
        }
    }


def _handler(upstream_url: str) -> type[BaseHTTPRequestHandler]:
    class ProxyHandler(BaseHTTPRequestHandler):
        server_version = "codex-glm-proxy/0.1"

        def _write_json(self, status: int, value: Any) -> None:
            body = _json_bytes(value)
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0].rstrip("/")
            if path == "/healthz":
                self._write_json(200, {"status": "ok"})
                return
            if path in {"/models", "/v1/models"}:
                self._write_json(
                    200,
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": "glm-5.2",
                                "object": "model",
                                "created": 0,
                                "owned_by": "zhipu",
                            }
                        ],
                    },
                )
                return
            self._write_json(
                404,
                {"error": {"message": "Not Found", "type": "not_found_error"}},
            )

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0].rstrip("/")
            if path not in {"/responses", "/v1/responses"}:
                self._write_json(
                    404,
                    {"error": {"message": "Not Found", "type": "not_found_error"}},
                )
                return

            api_key = _extract_api_key(self.headers)
            if not api_key:
                self._write_json(
                    401,
                    {
                        "error": {
                            "message": "缺少 Bearer API Key",
                            "type": "authentication_error",
                        }
                    },
                )
                return

            try:
                content_length = int(self.headers.get("content-length", "0"))
                body = json.loads(self.rfile.read(content_length))
                if not isinstance(body, dict):
                    raise ValueError("请求体必须是 JSON 对象")
                upstream_body = transform_responses_request(body)
            except (json.JSONDecodeError, ValueError) as exc:
                self._write_json(
                    400,
                    {"error": {"message": str(exc), "type": "invalid_request_error"}},
                )
                return

            upstream_request = urllib.request.Request(
                upstream_url,
                data=_json_bytes(upstream_body),
                headers={
                    "content-type": "application/json",
                    "x-api-key": api_key,
                    "authorization": f"Bearer {api_key}",
                    "anthropic-version": "2023-06-01",
                    "accept": "text/event-stream",
                },
                method="POST",
            )

            try:
                upstream = urllib.request.urlopen(upstream_request, timeout=600)
            except urllib.error.HTTPError as exc:
                self._write_json(exc.code, _map_upstream_error(exc.read(), exc.code))
                return
            except urllib.error.URLError as exc:
                self._write_json(
                    502,
                    {
                        "error": {
                            "message": f"无法连接智谱 Anthropic API：{exc.reason}",
                            "type": "upstream_connection_error",
                        }
                    },
                )
                return

            self.send_response(200)
            self.send_header("content-type", "text/event-stream; charset=utf-8")
            self.send_header("cache-control", "no-cache")
            self.send_header("x-accel-buffering", "no")
            self.send_header("connection", "close")
            self.end_headers()
            self.close_connection = True

            try:
                for chunk in transform_anthropic_sse(upstream):
                    self.wfile.write(chunk.encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            finally:
                upstream.close()

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ProxyHandler


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    upstream_url: str = DEFAULT_UPSTREAM_URL,
) -> ThreadingHTTPServer:
    """创建可由调用方控制生命周期的代理服务器。"""

    return ThreadingHTTPServer((host, port), _handler(upstream_url))
