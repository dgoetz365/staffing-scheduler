import concurrent.futures
from contextlib import closing
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

import app


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        app.seed(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def state(self):
        return app.state(self.path)

    def change(self, action, **fields):
        return app.mutate(self.path, action, {"version": self.state()["version"], **fields})

    def test_seed_refuses_to_overwrite_persistent_changes(self):
        self.change("assign", shift_id=5, volunteer_id=5)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(app.Problem, "already exists"):
            app.seed(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(5, len(app.state(self.path)["assignments"]))

    def test_role_rejection_is_atomic(self):
        before = self.state()
        with self.assertRaisesRegex(app.Problem, "not eligible"):
            self.change("assign", shift_id=5, volunteer_id=6)
        self.assertEqual(before, self.state())

    def test_availability_covers_the_entire_shift(self):
        self.change("remove", shift_id=4, volunteer_id=4)
        with self.assertRaisesRegex(app.Problem, "unavailable"):
            self.change("assign", shift_id=4, volunteer_id=6)
        self.change("assign", shift_id=4, volunteer_id=1)  # Touching 10:00 boundary is valid.
        self.assertIn({"shift_id": 4, "volunteer_id": 1}, self.state()["assignments"])

    def test_split_windows_cannot_be_combined_across_gap(self):
        with closing(app.connect(self.path)) as db:
            db.execute("UPDATE volunteers SET windows=? WHERE id=5", (json.dumps([[540, 600], [615, 660]]),))
        with self.assertRaisesRegex(app.Problem, "unavailable"):
            self.change("assign", shift_id=5, volunteer_id=5)

    def test_overlap_rejected_even_for_different_roles(self):
        with self.assertRaisesRegex(app.Problem, "overlapping"):
            self.change("assign", shift_id=5, volunteer_id=3)

    def test_capacity_and_duplicate_assignment_rejected(self):
        with self.assertRaisesRegex(app.Problem, "full"):
            self.change("assign", shift_id=1, volunteer_id=6)
        with self.assertRaisesRegex(app.Problem, "already assigned"):
            self.change("assign", shift_id=1, volunteer_id=1)

    def test_publish_requires_every_shift_filled(self):
        before = self.state()
        with self.assertRaisesRegex(app.Problem, "Cannot publish"):
            self.change("publish")
        self.assertEqual(before, self.state())

    def test_publish_revalidates_conflicts_in_store(self):
        with closing(app.connect(self.path)) as db:
            db.execute("INSERT INTO assignments VALUES(5,3)")
        with self.assertRaisesRegex(app.Problem, "overlapping"):
            self.change("publish")
        self.assertEqual([], self.state()["publications"])

    def test_snapshot_survives_draft_edits_and_denormalizes_names(self):
        self.change("assign", shift_id=5, volunteer_id=5)
        self.change("publish")
        original = self.state()["publications"][0]
        self.change("remove", shift_id=1, volunteer_id=1)
        with closing(app.connect(self.path)) as db:
            db.execute("UPDATE volunteers SET name='Changed locally' WHERE id=1")
        saved = self.state()["publications"][0]
        self.assertEqual(original, saved)
        self.assertEqual("Mira Chen", saved["payload"]["volunteers"][0]["name"])
        with closing(app.connect(self.path)) as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                db.execute("UPDATE publications SET payload='{}'")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                db.execute("DELETE FROM publications")

    def test_stale_edit_and_publish_rejected_without_side_effects(self):
        stale = self.state()["version"]
        self.change("assign", shift_id=5, volunteer_id=5)
        before = self.state()
        for action, fields in [("remove", {"shift_id": 1, "volunteer_id": 1}), ("publish", {})]:
            with self.assertRaises(app.Problem) as caught:
                app.mutate(self.path, action, {"version": stale, **fields})
            self.assertEqual(409, caught.exception.status)
            self.assertEqual(before, self.state())

    def test_concurrent_draft_changes_have_exactly_one_winner(self):
        version = self.state()["version"]
        barrier = threading.Barrier(2)

        def attempt(fields):
            barrier.wait()
            try:
                app.mutate(self.path, "remove", {"version": version, **fields})
                return 200
            except app.Problem as error:
                return error.status

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, [{"shift_id": 1, "volunteer_id": 1}, {"shift_id": 2, "volunteer_id": 2}]))
        self.assertEqual([200, 409], sorted(results))
        self.assertEqual(version + 1, self.state()["version"])
        self.assertEqual(3, len(self.state()["assignments"]))

    def request(self):
        self.change("request", shift_id=1, from_id=1, to_id=6, reason="Mira will help with setup.")
        return self.state()["requests"][0]["id"]

    def test_approval_changes_draft_and_preserves_publication(self):
        self.change("assign", shift_id=5, volunteer_id=5)
        self.change("publish")
        publication = self.state()["publications"]
        request_id = self.request()
        self.assertIn({"shift_id": 1, "volunteer_id": 1}, self.state()["assignments"])
        self.change("review", request_id=request_id, decision="approve")
        state = self.state()
        self.assertIn({"shift_id": 1, "volunteer_id": 6}, state["assignments"])
        self.assertNotIn({"shift_id": 1, "volunteer_id": 1}, state["assignments"])
        self.assertEqual("approved", state["requests"][0]["status"])
        self.assertEqual(publication, state["publications"])
        with self.assertRaisesRegex(app.Problem, "already been reviewed"):
            self.change("review", request_id=request_id, decision="decline")
        self.change("publish")
        self.assertEqual(2, len(self.state()["publications"]))

    def test_approval_revalidation_rolls_back_every_write(self):
        request_id = self.request()
        self.change("remove", shift_id=2, volunteer_id=2)
        self.change("assign", shift_id=2, volunteer_id=6)
        before = self.state()
        with self.assertRaisesRegex(app.Problem, "overlapping"):
            self.change("review", request_id=request_id, decision="approve")
        self.assertEqual(before, self.state())
        self.assertEqual("pending", self.state()["requests"][0]["status"])
        self.change("review", request_id=request_id, decision="decline")
        self.assertEqual(before["assignments"], self.state()["assignments"])
        self.assertEqual("declined", self.state()["requests"][0]["status"])

    def test_changed_original_assignment_blocks_approval(self):
        request_id = self.request()
        self.change("remove", shift_id=1, volunteer_id=1)
        with self.assertRaisesRegex(app.Problem, "original assignment changed"):
            self.change("review", request_id=request_id, decision="approve")

    def test_duplicate_request_and_bad_id_validation(self):
        self.request()
        with self.assertRaisesRegex(app.Problem, "already has a pending"):
            self.request()
        for value in (True, 1.5, "1", 2**100, -1):
            with self.subTest(value=value), self.assertRaises(app.Problem):
                self.change("assign", shift_id=value, volunteer_id=5)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / "http.sqlite3"
        app.seed(cls.path)
        cls.server = app.make_server(cls.path, 0)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def request(self, method="GET", path="/api/state", body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        defaults = {"Origin": f"http://127.0.0.1:{self.port}", "Content-Type": "application/json"}
        defaults.update(headers or {})
        conn.request(method, path, body=body, headers=defaults)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def post(self, body, **kwargs):
        return self.request("POST", "/api/publish", body=body, **kwargs)

    def test_assets_and_route_allowlist(self):
        for route in ("/", "/app.js", "/style.css", "/api/state"):
            with self.subTest(route=route):
                status, headers, body = self.request(path=route)
                self.assertEqual(200, status)
                self.assertTrue(body)
                self.assertEqual("nosniff", headers["X-Content-Type-Options"])
                self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        for route in ("/app.py", "/data/schedule.sqlite3", "/../app.py", "/%2e%2e/app.py", "/api/state?x=1"):
            self.assertEqual(404, self.request(path=route)[0])
        self.assertEqual("127.0.0.1", self.server.server_address[0])

    def test_strict_json_and_field_validation(self):
        bad = [b'{"version":1,"version":1}', b'{"version":NaN}', b'{"version":true}', b'[]', b'null', b'"x"', b'{}', b'{"version":1,"extra":0}', b'{"version":"\\ud800"}', b'{"version":"\\udc00"}', b'\xff', b'{' + b'"version":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}']
        for body in bad:
            with self.subTest(body=body[:40]):
                self.assertEqual(400, self.post(body)[0])

    def test_host_origin_and_content_type(self):
        for headers, expected in [({"Host": "example.invalid"}, 403), ({"Origin": "https://example.invalid"}, 403), ({"Origin": "null"}, 403), ({"Content-Type": "text/plain"}, 415), ({"Sec-Fetch-Site": "cross-site"}, 403)]:
            with self.subTest(headers=headers):
                self.assertEqual(expected, self.post(b'{"version":1}', headers=headers)[0])

    def test_body_limit(self):
        self.assertEqual(413, self.post(b" " * (app.MAX_BODY + 1))[0])

    def test_duplicate_headers_and_transfer_encoding(self):
        for duplicate in ("Host", "Origin", "Content-Length", "Content-Type"):
            with self.subTest(duplicate=duplicate):
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
                conn.putrequest("POST", "/api/publish", skip_host=True, skip_accept_encoding=True)
                values = {"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}", "Content-Length": "13", "Content-Type": "application/json"}
                for key, value in values.items():
                    conn.putheader(key, value)
                    if key == duplicate:
                        conn.putheader(key, value)
                conn.endheaders(b'{"version":1}')
                response = conn.getresponse()
                self.assertEqual(400, response.status)
                response.read()
                conn.close()
        self.assertEqual(400, self.post(b'{"version":1}', headers={"Transfer-Encoding": "chunked"})[0])

    def test_live_http_assignment_and_stale_rejection(self):
        original = json.loads(self.request()[2])
        body = json.dumps({"version": original["version"], "shift_id": 5, "volunteer_id": 5})
        self.assertEqual(200, self.request("POST", "/api/assign", body=body)[0])
        self.assertEqual(409, self.request("POST", "/api/assign", body=body)[0])
        current = json.loads(self.request()[2])
        self.assertEqual(original["version"] + 1, current["version"])
        self.assertIn({"shift_id": 5, "volunteer_id": 5}, current["assignments"])
        status, _, body = self.post(json.dumps({"version": current["version"]}))
        self.assertEqual(200, status)
        self.assertIn("Published snapshot", json.loads(body)["message"])


if __name__ == "__main__":
    unittest.main()
