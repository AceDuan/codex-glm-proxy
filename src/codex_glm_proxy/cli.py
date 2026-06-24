"""命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .server import DEFAULT_UPSTREAM_URL, create_server


def _add_network_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex GLM Responses 转换代理")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="启动代理服务")
    _add_network_arguments(serve)
    serve.add_argument("--upstream", default=DEFAULT_UPSTREAM_URL)

    health = subparsers.add_parser("health", help="检查代理健康状态")
    health.add_argument("--url", default="http://127.0.0.1:8765/healthz")
    health.add_argument("--timeout", type=float, default=2.0)

    start = subparsers.add_parser("start", help="在后台启动代理")
    _add_network_arguments(start)
    start.add_argument("--upstream", default=DEFAULT_UPSTREAM_URL)
    start.add_argument(
        "--runtime-dir",
        default="~/.codex-glm/proxy",
        help="保存 proxy.pid 和 proxy.log 的目录",
    )
    start.add_argument("--startup-timeout", type=float, default=5.0)

    status = subparsers.add_parser("status", help="检查后台代理状态")
    _add_network_arguments(status)
    status.add_argument("--runtime-dir", default="~/.codex-glm/proxy")

    stop = subparsers.add_parser("stop", help="停止后台代理")
    stop.add_argument("--runtime-dir", default="~/.codex-glm/proxy")

    return parser


def _health(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.load(response) == {"status": "ok"}
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return False


def _runtime_paths(raw: str) -> tuple[Path, Path, Path]:
    runtime_dir = Path(raw).expanduser()
    return runtime_dir, runtime_dir / "proxy.pid", runtime_dir / "proxy.log"


def _start(args: argparse.Namespace) -> int:
    health_url = f"http://{args.host}:{args.port}/healthz"
    if _health(health_url):
        print("already running")
        return 0

    runtime_dir, pid_file, log_file = _runtime_paths(args.runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "codex_glm_proxy",
        "serve",
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--upstream",
        args.upstream,
    ]
    with log_file.open("ab", buffering=0) as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    pid_file.write_text(f"{process.pid}\n", encoding="utf-8")

    deadline = time.monotonic() + args.startup_timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pid_file.unlink(missing_ok=True)
            print(f"代理启动失败，请查看日志：{log_file}", file=sys.stderr)
            return 1
        if _health(health_url):
            print(f"started pid={process.pid} log={log_file}")
            return 0
        time.sleep(0.1)

    process.terminate()
    pid_file.unlink(missing_ok=True)
    print(f"代理启动超时，请查看日志：{log_file}", file=sys.stderr)
    return 1


def _status(args: argparse.Namespace) -> int:
    health_url = f"http://{args.host}:{args.port}/healthz"
    _, pid_file, _ = _runtime_paths(args.runtime_dir)
    if _health(health_url):
        pid = pid_file.read_text(encoding="utf-8").strip() if pid_file.exists() else "unknown"
        print(f"running pid={pid}")
        return 0
    print("stopped")
    return 1


def _stop(args: argparse.Namespace) -> int:
    _, pid_file, _ = _runtime_paths(args.runtime_dir)
    if not pid_file.exists():
        print("not running")
        return 0
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        print(f"PID 文件格式错误：{pid_file}", file=sys.stderr)
        return 1

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError as exc:
        print(f"无法停止代理：{exc}", file=sys.stderr)
        return 1
    finally:
        pid_file.unlink(missing_ok=True)
    print(f"stopped pid={pid}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "health":
        if not _health(args.url, args.timeout):
            print("代理不可用", file=sys.stderr)
            return 1
        print("ok")
        return 0
    if args.command == "start":
        return _start(args)
    if args.command == "status":
        return _status(args)
    if args.command == "stop":
        return _stop(args)

    server = create_server(args.host, args.port, args.upstream)
    print(
        f"codex-glm-proxy 监听 http://{args.host}:{server.server_port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
