import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

from app import SERVER_PASSWORD, FileBrowserServer, parse_byte_range, resolve_shared_path


class SharedPathTests(unittest.TestCase):
    def test_resolves_path_inside_share(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.assertEqual(resolve_shared_path(root, "movies/film.mp4"), root / "movies" / "film.mp4")

    def test_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                resolve_shared_path(Path(directory).resolve(), "../private.txt")

    def test_rejects_windows_separators(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                resolve_shared_path(Path(directory).resolve(), r"..\private.txt")


class ByteRangeTests(unittest.TestCase):
    def test_no_range(self):
        self.assertIsNone(parse_byte_range(None, 10))

    def test_explicit_range(self):
        self.assertEqual(parse_byte_range("bytes=2-5", 10), (2, 5))

    def test_open_ended_range(self):
        self.assertEqual(parse_byte_range("bytes=7-", 10), (7, 9))

    def test_suffix_range(self):
        self.assertEqual(parse_byte_range("bytes=-3", 10), (7, 9))

    def test_rejects_out_of_bounds_range(self):
        with self.assertRaises(ValueError):
            parse_byte_range("bytes=10-12", 10)


class HttpServerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.other_temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()
        self.other_root = Path(self.other_temp_dir.name).resolve()
        (self.root / "clip.mp4").write_bytes(b"0123456789")
        (self.root / ".hidden-note").write_text("visible", encoding="utf-8")
        (self.other_root / "second-drive.txt").write_text("second drive", encoding="utf-8")
        self.server = FileBrowserServer(
            ("127.0.0.1", 0),
            {"test-root": ("Test drive", self.root), "second-root": ("Second drive", self.other_root)},
            SERVER_PASSWORD,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp_dir.cleanup()
        self.other_temp_dir.cleanup()

    def sign_in(self):
        body = json.dumps({"password": SERVER_PASSWORD})
        self.connection.request(
            "POST",
            "/api/login",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["authenticated"])
        return response.getheader("Set-Cookie").split(";", 1)[0]

    def test_login_rejects_incorrect_password(self):
        body = json.dumps({"password": "incorrect"})
        self.connection.request(
            "POST",
            "/api/login",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 401)
        response.read()

    def test_api_requires_login(self):
        self.connection.request("GET", "/api/list")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 401)
        response.read()

    def test_static_file_icons_are_available_without_login(self):
        self.connection.request("GET", "/static/icons/video.svg")
        response = self.connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "image/svg+xml; charset=utf-8")
        self.assertIn(b"<svg", response.read())

    def test_login_listing_and_media_range(self):
        cookie = self.sign_in()
        self.connection.request("GET", "/api/list?root=test-root", headers={"Cookie": cookie})
        listing = self.connection.getresponse()
        self.assertEqual(listing.status, 200)
        names = {entry["name"] for entry in json.loads(listing.read())["entries"]}
        self.assertEqual(names, {"clip.mp4", ".hidden-note"})

        path = "/api/file?" + urlencode({"root": "test-root", "path": "clip.mp4", "inline": "1"})
        self.connection.request(
            "GET",
            path,
            headers={"Cookie": cookie, "Range": "bytes=2-5"},
        )
        media = self.connection.getresponse()
        self.assertEqual(media.status, 206)
        self.assertEqual(media.getheader("Content-Range"), "bytes 2-5/10")
        self.assertEqual(media.getheader("Content-Disposition").split(";", 1)[0], "inline")
        self.assertEqual(media.read(), b"2345")

    def test_drive_home_and_second_root(self):
        cookie = self.sign_in()
        self.connection.request("GET", "/api/list", headers={"Cookie": cookie})
        home = self.connection.getresponse()
        roots = json.loads(home.read())
        self.assertEqual(roots["rootName"], "Computer")
        self.assertEqual({entry["root"] for entry in roots["entries"]}, {"test-root", "second-root"})

        self.connection.request("GET", "/api/list?root=second-root", headers={"Cookie": cookie})
        second_drive = self.connection.getresponse()
        self.assertEqual(second_drive.status, 200)
        self.assertEqual(json.loads(second_drive.read())["entries"][0]["name"], "second-drive.txt")

        path = "/api/file?" + urlencode({"root": "second-root", "path": "second-drive.txt"})
        self.connection.request("GET", path, headers={"Cookie": cookie})
        download = self.connection.getresponse()
        self.assertEqual(download.status, 200)
        self.assertEqual(download.read(), b"second drive")

    def test_api_rejects_path_escape(self):
        cookie = self.sign_in()
        path = "/api/list?" + urlencode({"root": "test-root", "path": "../outside"})
        self.connection.request("GET", path, headers={"Cookie": cookie})
        response = self.connection.getresponse()
        self.assertEqual(response.status, 404)
        response.read()


if __name__ == "__main__":
    unittest.main()