# Tests for serve.py that don't need NCBI. They run the server on a temporary
# copy of sample lineages, never the real taxonomy_files/. Run from the project folder with:
#   python3 -m unittest discover tests

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import fetch_lineage
import make_tree
import serve
from test_make_tree import APPLE, SAMPLE, write_folder

TOKEN = "test-token"

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = os.path.join(self.tmp.name, "taxonomy_files")
        os.mkdir(self.folder)
        write_folder(self.folder, SAMPLE)
        self.saved = (make_tree.taxonomy_dir, make_tree.output_path, fetch_lineage.taxonomy_dir)
        make_tree.taxonomy_dir = fetch_lineage.taxonomy_dir = self.folder
        make_tree.output_path = os.path.join(self.tmp.name, "taxon_tree.txt")
        serve.Handler.token = TOKEN
        self.server = serve.ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        make_tree.taxonomy_dir, make_tree.output_path, fetch_lineage.taxonomy_dir = self.saved
        self.tmp.cleanup()

    def request(self, path, body=None, token=TOKEN):
        headers = {"X-Token": token} if token else {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base + path, data, headers)) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_token_required(self):
        self.assertEqual(self.request("/", token=None)[0], 403)
        self.assertEqual(self.request("/api/tree", token="wrong")[0], 403)
        self.assertEqual(self.request("/api/save", {"filename": "x", "text": "y"}, token=None)[0], 403)
        self.assertEqual(self.request("/?token=" + TOKEN, token=None)[0], 200)

    def test_static_files_stay_in_web_folder(self):
        self.assertEqual(self.request("/static/app.js", token=None)[0], 200)
        self.assertEqual(self.request("/static/../serve.py", token=None)[0], 404)
        self.assertEqual(self.request("/static/%2e%2e/serve.py", token=None)[0], 404)

    def test_tree_and_stats(self):
        status, body = self.request("/api/tree")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["tree"]["name"], "Eukaryota")
        self.assertEqual(data["warnings"], [])
        self.assertEqual(sorted(name for files in data["files"].values() for name in files), sorted(SAMPLE))
        self.assertTrue(os.path.exists(make_tree.output_path))
        stats = json.loads(self.request("/api/stats")[1])
        self.assertEqual(stats["totals"]["organisms"], len(SAMPLE))

    def test_save_cleans_the_file_name(self):
        pear = APPLE[:-2] + ["Pyrus; G", "Pyrus communis; S"]
        status, body = self.request("/api/save", {"filename": "../Pear Tree", "text": "\n".join(pear)})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["filename"], "pear_tree.txt")
        self.assertTrue(os.path.exists(os.path.join(self.folder, "pear_tree.txt")))
        # Saving again without force is refused
        self.assertEqual(self.request("/api/save", {"filename": "pear_tree", "text": "\n".join(pear)})[0], 400)

    def test_save_removes_a_lineage_that_breaks_the_tree(self):
        status, body = self.request("/api/save", {"filename": "broken", "text": "Bacteria; \nEscherichia coli; S"})
        self.assertEqual(status, 400)
        self.assertIn("not saved", json.loads(body)["error"])
        self.assertFalse(os.path.exists(os.path.join(self.folder, "broken.txt")))

    def test_bad_requests(self):
        self.assertEqual(self.request("/api/nope")[0], 404)
        self.assertEqual(self.request("/api/lookup", {"name": ""})[0], 400)
        self.assertEqual(self.request("/api/gaps?taxon=")[0], 400)

if __name__ == "__main__":
    unittest.main()
