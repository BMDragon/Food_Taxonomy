# Created by Brandon Weiss on 8/17/2026

import argparse
import os
import sys

class TreeNode:
    def __init__(self, value, code):
        self.value = value
        self.code = code
        self.children = {}

    def get_or_add_child(self, value, code):
        # Children are keyed by name under their parent, so identically named
        # taxa in different lineages stay separate nodes
        child = self.children.get(value)
        if child is None:
            child = TreeNode(value, code)
            self.children[value] = child
        elif child.code != code:
            raise ValueError(f"'{value}' was given rank '{child.code}' and '{code}' in different files")
        return child

RANK_ORDER = "KPCOFGS"
base = 1

script_dir = os.path.dirname(os.path.abspath(__file__))
taxonomy_dir = os.path.join(script_dir, "taxonomy_files")
output_path = os.path.join(script_dir, "taxon_tree.txt")
stats_path = os.path.join(script_dir, "stats.md")

def parse_line(line, filename, line_num):
    name, sep, code = line.partition(';')
    name, code = name.strip(), code.strip()
    if name == '':
        raise ValueError(f"{filename}:{line_num}: missing taxon name")
    # A line with no ';' is an unranked subspecies
    if sep and code != '' and (len(code) != 1 or code not in RANK_ORDER):
        raise ValueError(f"{filename}:{line_num}: unknown rank code '{code}' (expected one of {', '.join(RANK_ORDER)})")
    return name, code

def build_tree():
    root = None
    for filename in sorted(os.listdir(taxonomy_dir)):
        if not filename.endswith(".txt"):
            continue
        with open(os.path.join(taxonomy_dir, filename), 'r') as file:
            node = None
            last_rank = -1
            for line_num, line in enumerate(file, start=1):
                if line.strip() == '':
                    continue
                name, code = parse_line(line, filename, line_num)
                if code != '':
                    rank = RANK_ORDER.index(code)
                    if rank <= last_rank:
                        raise ValueError(f"{filename}:{line_num}: rank '{code}' is out of order (ranks must follow {RANK_ORDER})")
                    last_rank = rank
                if node is None:
                    if root is None:
                        root = TreeNode(name, code)
                    elif name != root.value:
                        raise ValueError(f"{filename}:{line_num}: lineage starts at '{name}', expected '{root.value}'")
                    node = root
                else:
                    node = node.get_or_add_child(name, code)
    if root is None:
        raise ValueError(f"no taxonomy files found in {taxonomy_dir}")
    return root

def compute_depths(root):
    # Each major rank is drawn at a single depth across the whole tree: the
    # deepest position it needs anywhere. Raising one rank can push later ranks
    # deeper, so repeat until nothing changes. Ranks are validated to be in
    # order within each lineage, so this always settles.
    depths = {}
    changed = True
    while changed:
        changed = False
        stack = [(root, -1)]
        while stack:
            node, parent_depth = stack.pop()
            depth = parent_depth + 1
            if node.code != '':
                if depths.get(node.code, -1) < depth:
                    depths[node.code] = depth
                    changed = True
                depth = depths[node.code]
            for child in node.children.values():
                stack.append((child, depth))
    return depths

def save_tree(node, depths, parent_depth):
    depth = depths[node.code] if node.code != '' else parent_depth + 1
    label = node.value + ':' + str((depth - parent_depth)*base)
    if len(node.children) == 0:
        return label
    return '(' + ','.join(save_tree(child, depths, depth) for child in node.children.values()) + ')' + label

RANK_PLURALS = {"K": "Kingdoms", "P": "Phyla", "C": "Classes", "O": "Orders",
                "F": "Families", "G": "Genera", "S": "Species"}
LEAF_KINDS = [("species", "species"), ("subspecies", "subspecies"), ("variety", "varieties"), ("other", "other")]

def leaf_kind(node, under_species):
    if node.code == 'S':
        return "species"
    if under_species:
        return "variety" if " var. " in node.value else "subspecies"
    return "other"

def collect_stats(root):
    # Per kingdom: the number of taxa at each major rank, and of each kind of leaf
    kingdoms = {}
    stack = [(root, None, False)]
    while stack:
        node, kingdom, under_species = stack.pop()
        if node.code == 'K':
            kingdom = node.value
        counts = kingdoms.setdefault(kingdom or "(no kingdom)", {})
        if node.code != '':
            counts[node.code] = counts.get(node.code, 0) + 1
        if len(node.children) == 0:
            kind = leaf_kind(node, under_species)
            counts[kind] = counts.get(kind, 0) + 1
            counts["organisms"] = counts.get("organisms", 0) + 1
        for child in node.children.values():
            stack.append((child, kingdom, under_species or node.code == 'S'))
    kingdoms = {name: counts for name, counts in kingdoms.items() if counts.get("organisms", 0) > 0}
    totals = {}
    for counts in kingdoms.values():
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value
    return kingdoms, totals

def markdown_table(header, rows):
    widths = [max(len(str(row[i])) for row in [header] + rows) for i in range(len(header))]
    def line(row):
        cells = [str(cell).ljust(width) if i == 0 else str(cell).rjust(width) for i, (cell, width) in enumerate(zip(row, widths))]
        return "| " + " | ".join(cells) + " |"
    separator = "| " + " | ".join(("-" * width if i == 0 else "-" * (width - 1) + ":") for i, width in enumerate(widths)) + " |"
    return [line(header), separator] + [line(row) for row in rows]

def format_stats(kingdoms, totals):
    kinds = [f"{totals[key]} {plural if totals[key] != 1 else key}" for key, plural in LEAF_KINDS if totals.get(key, 0) > 0]
    lines = ["# Food taxonomy stats", "",
             f"{totals.get('organisms', 0)} organisms eaten: " + ", ".join(kinds) + ".", "",
             "## Distinct taxa", ""]
    lines += markdown_table(["Rank", "Count"], [[RANK_PLURALS[code], totals.get(code, 0)] for code in RANK_ORDER])
    lines += ["", "## By kingdom", ""]
    header = ["Kingdom"] + [RANK_PLURALS[code] for code in RANK_ORDER[1:]] + ["Organisms"]
    rows = []
    for name, counts in sorted(kingdoms.items(), key=lambda item: (-item[1]["organisms"], item[0])):
        rows.append([name] + [counts.get(code, 0) for code in RANK_ORDER[1:]] + [counts["organisms"]])
    lines += markdown_table(header, rows)
    return "\n".join(lines) + "\n"

def main():
    parser = argparse.ArgumentParser(description="Build taxon_tree.txt from the files in taxonomy_files/.")
    parser.add_argument("--stats", action="store_true", help="print counts of the organisms and taxa in the tree")
    parser.add_argument("--stats-md", action="store_true", help="also write the stats to stats.md")
    args = parser.parse_args()

    try:
        root = build_tree()
    except ValueError as e:
        sys.exit(f"Error: {e}")
    depths = compute_depths(root)

    with open(output_path, 'w') as f:
        f.write(save_tree(root, depths, -1) + ";\n")

    if args.stats or args.stats_md:
        stats = format_stats(*collect_stats(root))
        if args.stats:
            print(stats, end='')
        if args.stats_md:
            with open(stats_path, 'w') as f:
                f.write(stats)

if __name__ == "__main__":
    main()
