import os
import socket
import subprocess
import sys
import tempfile
import unittest


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CliLifecycleTests(unittest.TestCase):
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
