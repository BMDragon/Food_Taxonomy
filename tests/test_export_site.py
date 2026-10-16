# Tests for export_site.py. Run from the project folder with:
#   python3 -m unittest discover tests

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

project = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

class ExportTests(unittest.TestCase):
    def test_static_copy_has_data_and_no_server_links(self):
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib is not installed")
        with tempfile.TemporaryDirectory() as out:
            subprocess.run([sys.executable, os.path.join(project, "export_site.py"), "--out", out],
                           check=True, capture_output=True)
            for name in ("index.html", "cladogram_major.svg", "cladogram_full.svg"):
                self.assertTrue(os.path.getsize(os.path.join(out, name)) > 0, name)
            with open(os.path.join(out, "index.html"), 'r') as f:
                page = f.read()
            # Styles and script are inlined, so nothing points at the server
            self.assertNotIn('href="/static/', page)
            self.assertNotIn('src="/static/', page)
            data = json.loads(re.search(r"window\.STATIC_DATA = (.*?);</script>", page).group(1))
            self.assertEqual(set(data), {"/api/tree", "/api/stats", "/api/coverage"})
            self.assertEqual(data["/api/tree"]["tree"]["name"], "Eukaryota")

if __name__ == "__main__":
    unittest.main()
