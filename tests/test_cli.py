import http.client
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def test_seed_is_safe_and_serve_reopens_same_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "demo.sqlite3"
            command = [sys.executable, str(ROOT / "app.py")]
            first = subprocess.run([*command, "seed", "--db", str(path)], capture_output=True, text=True, timeout=10)
            self.assertEqual(0, first.returncode, first.stderr)
            original = path.read_bytes()
            second = subprocess.run([*command, "seed", "--db", str(path)], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(0, second.returncode)
            self.assertIn("already exists", second.stderr)
            self.assertEqual(original, path.read_bytes())
            process = subprocess.Popen([*command, "serve", "--db", str(path), "--port", "0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                # The server prints only after binding and validating the database.
                output = queue.Queue()
                reader = threading.Thread(target=lambda: output.put(process.stdout.readline()), daemon=True)
                reader.start()
                line = output.get(timeout=10)
                self.assertTrue(line.startswith("Fieldwork Scheduler: http://127.0.0.1:"), line)
                port = int(line.rstrip().rsplit(":", 1)[1])
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                connection.request("GET", "/")
                response = connection.getresponse()
                self.assertEqual(200, response.status)
                self.assertIn(b"Fieldwork", response.read())
                connection.close()
            finally:
                process.terminate()
                process.communicate(timeout=5)

    def test_missing_database_does_not_create_an_empty_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "missing.sqlite3"
            result = subprocess.run([sys.executable, str(ROOT / "app.py"), "serve", "--db", str(path)], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Run the seed command first", result.stderr)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
