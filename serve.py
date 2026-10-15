# Serves a local website for browsing the tree, its stats and gaps, and adding organisms.
# Run: python3 serve.py   then open the printed http://localhost:... link

import argparse
import hmac
import io
import json
import mimetypes
import os
import secrets
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fetch_lineage
import gaps
import make_tree

static_dir = os.path.join(make_tree.script_dir, "web")
# NCBI requests are rate limited per process, so run them one at a time
ncbi_lock = threading.Lock()
# Building and writing the tree touches taxonomy_files/ and taxon_tree.txt
files_lock = threading.Lock()

def node_json(node):
    return {"name": node.value, "code": node.code, "eaten": node.eaten,
            "children": [node_json(child) for child in node.children.values()]}

def leaf_files():
    # Maps each file's last entry to its file name, so the page can show both
    files = {}
    for filename in sorted(os.listdir(make_tree.taxonomy_dir)):
        if filename.endswith(".txt"):
            with open(os.path.join(make_tree.taxonomy_dir, filename), 'r') as file:
                lines = [line for line in file if line.strip()]
            if lines:
                files.setdefault(lines[-1].partition(';')[0].strip(), []).append(filename)
    return files

def rebuild():
    # Rebuilds taxon_tree.txt from the files and returns (root, warnings, depths)
    root, warnings = make_tree.build_tree(make_tree.taxonomy_dir)
    depths = make_tree.compute_depths(root)
    with open(make_tree.output_path, 'w') as f:
        f.write(make_tree.save_tree(root, depths, -1) + ";\n")
    return root, warnings, depths

class ApiError(Exception):
    pass

class Handler(BaseHTTPRequestHandler):
    token = None

    def log_message(self, format, *args):
        # Keep the terminal quiet apart from errors
        pass

    def send(self, status, body, content_type):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, value, status=200):
        self.send(status, json.dumps(value), "application/json")

    def authorized(self, query):
        given = self.headers.get("X-Token") or query.get("token", [""])[0]
        return hmac.compare_digest(given, self.token)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        if url.path.startswith("/static/"):
            return self.serve_static(url.path[len("/static/"):])
        if not self.authorized(query):
            return self.send(403, "Open the link printed by serve.py (it includes the access token).\n",
                             "text/plain; charset=utf-8")
        if url.path == "/":
            return self.serve_static("index.html")
        self.handle_api(url.path, query, None)

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        if not self.authorized(query):
            return self.send_json({"error": "missing or wrong access token"}, 403)
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self.send_json({"error": "request body must be JSON"}, 400)
        self.handle_api(url.path, query, body)

    def serve_static(self, name):
        path = os.path.realpath(os.path.join(static_dir, name))
        if not path.startswith(os.path.realpath(static_dir) + os.sep) or not os.path.isfile(path):
            return self.send(404, "Not found\n", "text/plain; charset=utf-8")
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type.endswith("javascript"):
            content_type += "; charset=utf-8"
        with open(path, 'rb') as f:
            self.send(200, f.read(), content_type)

    def handle_api(self, path, query, body):
        routes = {
            ("GET", "/api/tree"): self.api_tree,
            ("GET", "/api/stats"): self.api_stats,
            ("GET", "/api/cladogram.svg"): self.api_cladogram,
            ("GET", "/api/gaps"): self.api_gaps,
            ("POST", "/api/lookup"): self.api_lookup,
            ("POST", "/api/save"): self.api_save,
            ("POST", "/api/remove"): self.api_remove,
        }
        route = routes.get(("GET" if body is None else "POST", path))
        if route is None:
            return self.send_json({"error": "not found"}, 404)
        try:
            route(query, body)
        except (ApiError, ValueError, fetch_lineage.FetchError) as e:
            self.send_json({"error": str(e)}, 400)

    def api_tree(self, query, body):
        with files_lock:
            root, warnings, depths = rebuild()
            files = leaf_files()
        self.send_json({"tree": node_json(root), "warnings": warnings, "files": files,
                        "ranks": list(make_tree.RANK_ORDER), "rankNames": make_tree.RANK_NAMES})

    def api_stats(self, query, body):
        with files_lock:
            root, _ = make_tree.build_tree(make_tree.taxonomy_dir)
        kingdoms, totals = make_tree.collect_stats(root)
        self.send_json({"kingdoms": kingdoms, "totals": totals,
                        "ranks": list(make_tree.RANK_ORDER), "rankPlurals": make_tree.RANK_PLURALS})

    def api_cladogram(self, query, body):
        major = query.get("major", ["0"])[0] == "1"
        with files_lock:
            root, _ = make_tree.build_tree(make_tree.taxonomy_dir)
        buffer = io.BytesIO()
        try:
            make_tree.draw_tree(root, make_tree.compute_depths(root), major, buffer, "svg",
                                common_names=make_tree.leaf_common_names(make_tree.taxonomy_dir))
        except ImportError:
            raise ApiError("drawing needs matplotlib (pip install --user matplotlib)")
        self.send(200, buffer.getvalue(), "image/svg+xml")

    def api_gaps(self, query, body):
        taxon = query.get("taxon", [""])[0].strip()
        if not taxon:
            raise ApiError("enter a taxon, e.g. Mammalia")
        rank = query.get("rank", [""])[0] or None
        refresh = query.get("refresh", ["0"])[0] == "1"
        with files_lock:
            root, _ = make_tree.build_tree(make_tree.taxonomy_dir)
        with ncbi_lock:
            report = gaps.gap_report(root, taxon, rank, refresh)
        del report["groups"]
        report["total"] = len(report["have"]) + len(report["missing"])
        report["plural"] = gaps.PLURALS[report["rank"]]
        self.send_json(report)

    def api_lookup(self, query, body):
        name = str(body.get("name", "")).strip()
        if not name:
            raise ApiError("enter a scientific or common name")
        filename = str(body.get("filename", "")).strip() or None
        with ncbi_lock:
            result = fetch_lineage.prepare(name, filename, bool(body.get("force")))
        self.send_json(result)

    def api_save(self, query, body):
        filename = str(body.get("filename", "")).strip()
        text = str(body.get("text", ""))
        if not filename or not text.strip():
            raise ApiError("nothing to save; look the organism up first")
        with files_lock:
            filename = fetch_lineage.save(filename, text, bool(body.get("force")))
            # Keep the files valid: a lineage that breaks the tree is removed again
            try:
                _, warnings, _ = rebuild()
            except ValueError as e:
                os.remove(os.path.join(make_tree.taxonomy_dir, filename))
                rebuild()
                raise ApiError(f"{filename} was not saved: {e}")
        self.send_json({"filename": filename, "warnings": warnings})

    def api_remove(self, query, body):
        # Deletes one taxonomy file and rebuilds the tree. The file's text is sent
        # back so the page can offer to undo (by saving it again).
        filename = fetch_lineage.clean_filename(str(body.get("filename", "")).strip())
        with files_lock:
            path = os.path.join(make_tree.taxonomy_dir, filename)
            if not os.path.isfile(path):
                raise ApiError(f"{filename} doesn't exist")
            remaining = [name for name in os.listdir(make_tree.taxonomy_dir) if name.endswith(".txt")]
            if len(remaining) == 1:
                raise ApiError("can't remove the last organism; the tree needs at least one")
            with open(path, 'r') as f:
                text = f.read()
            os.remove(path)
            _, warnings, _ = rebuild()
        self.send_json({"filename": filename, "text": text, "warnings": warnings})

def main():
    parser = argparse.ArgumentParser(description="Serve the Food Taxonomy website on localhost.")
    parser.add_argument("--port", type=int, default=8765, help="port to listen on (default 8765)")
    args = parser.parse_args()

    Handler.token = secrets.token_urlsafe(16)
    try:
        # Only reachable from this machine; the token keeps other users of a shared machine out
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as e:
        sys.exit(f"Error: can't use port {args.port} ({e.strerror}); try --port with another number")
    print(f"Food Taxonomy is running at http://localhost:{args.port}/?token={Handler.token}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
