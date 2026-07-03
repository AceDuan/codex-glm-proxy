import os
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from codex_glm_proxy import cli


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CliLifecycleTests(unittest.TestCase):
    def test_detach_kwargs_on_posix(self):
        with mock.patch.object(cli.sys, "platform", "linux"):
            self.assertEqual(cli._detach_kwargs(), {"start_new_session": True})

    def test_terminate_pid_on_posix(self):
        with (
            mock.patch.object(cli.sys, "platform", "linux"),
            mock.patch.object(cli.os, "kill") as kill,
        ):
            cli._terminate_pid(123)
        kill.assert_called_once_with(123, cli.signal.SIGTERM)

    @unittest.skipUnless(sys.platform == "win32", "Windows-specific Popen flags")
    def test_detach_kwargs_on_windows(self):
        self.assertEqual(
            cli._detach_kwargs(),
            {
                "creationflags": (
                    subprocess.CREATE_NO_WINDOW
                    | subprocess.CREATE_NEW_PROCESS_GROUP
                )
            },
        )

    @unittest.skipUnless(sys.platform == "win32", "Windows-specific taskkill")
    def test_terminate_pid_on_windows(self):
        with mock.patch.object(cli.subprocess, "run") as run:
            cli._terminate_pid(123)
        run.assert_called_once_with(
            ["taskkill", "/PID", "123", "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def test_start_status_and_stop(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as runtime_dir:
            base = [
                sys.executable,
                "-m",
                "codex_glm_proxy",
            ]
            start = subprocess.run(
                [
                    *base,
                    "start",
                    "--port",
                    str(port),
                    "--runtime-dir",
                    runtime_dir,
                ],
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(start.returncode, 0, start.stderr)
            self.assertTrue(os.path.isfile(os.path.join(runtime_dir, "proxy.pid")))
            self.assertTrue(os.path.isfile(os.path.join(runtime_dir, "proxy.log")))

            status = subprocess.run(
                [
                    *base,
                    "status",
                    "--port",
                    str(port),
                    "--runtime-dir",
                    runtime_dir,
                ],
                text=True,
                capture_output=True,
                timeout=5,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("running", status.stdout)

            stop = subprocess.run(
                [
                    *base,
                    "stop",
                    "--runtime-dir",
                    runtime_dir,
                ],
                text=True,
                capture_output=True,
                timeout=5,
            )
            self.assertEqual(stop.returncode, 0, stop.stderr)
            self.assertFalse(os.path.exists(os.path.join(runtime_dir, "proxy.pid")))


if __name__ == "__main__":
    unittest.main()
