# Writes a static copy of the website (tree, cladograms, stats, coverage, relatives) that
# works without serve.py, e.g. for GitHub Pages ("Deploy from a branch", folder /docs).
# Adding, removing and gaps need the server and are hidden in the copy.

import argparse
import json
import os

import gaps
import make_tree
import serve

def embed_json(value):
    # Keeps "</script>" inside the data from ending the script tag
    return json.dumps(value).replace("</", "<\\/")

def main():
    parser = argparse.ArgumentParser(description="Write a static copy of the website.")
    parser.add_argument("--out", default=os.path.join(make_tree.script_dir, "docs"),
                        help="folder to write to (default docs/, which GitHub Pages can serve)")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    root, _ = make_tree.build_tree(make_tree.taxonomy_dir)
    depths = make_tree.compute_depths(root)
    common_names = make_tree.leaf_common_names(make_tree.taxonomy_dir)
    for major, name in ((True, "cladogram_major.svg"), (False, "cladogram_full.svg")):
        make_tree.draw_tree(root, depths, major, os.path.join(args.out, name), common_names=common_names)

    data = {"/api/tree": serve.tree_payload(), "/api/stats": serve.stats_payload(), "/api/coverage": gaps.coverage(root)}
    with open(os.path.join(serve.static_dir, "index.html"), 'r') as f:
        page = f.read()
    with open(os.path.join(serve.static_dir, "style.css"), 'r') as f:
        style = f.read()
    with open(os.path.join(serve.static_dir, "app.js"), 'r') as f:
        script = f.read()
    page = page.replace('<link rel="stylesheet" href="/static/style.css">', f"<style>\n{style}\n</style>")
    page = page.replace('<script src="/static/app.js"></script>',
                        f"<script>window.STATIC_DATA = {embed_json(data)};</script>\n<script>\n{script}\n</script>")
    with open(os.path.join(args.out, "index.html"), 'w') as f:
        f.write(page)
    print(f"Wrote {args.out}/index.html, cladogram_major.svg and cladogram_full.svg")

if __name__ == "__main__":
    main()
