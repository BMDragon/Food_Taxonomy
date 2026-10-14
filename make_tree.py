# Created by Brandon Weiss on 8/17/2026

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

try:
    root = build_tree()
except ValueError as e:
    sys.exit(f"Error: {e}")
depths = compute_depths(root)

with open(output_path, 'w') as f:
    f.write(save_tree(root, depths, -1) + ";\n")
