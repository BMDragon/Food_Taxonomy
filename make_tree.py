# Created by Brandon Weiss on 8/17/2026

import argparse
import os
import sys

class TreeNode:
    def __init__(self, value, code):
        self.value = value
        self.code = code
        self.children = {}
        # True when a taxonomy file ends here. Usually a leaf, but a species can
        # also have an eaten variety below it (onion above shallot).
        self.eaten = False
        # True on the path from the root to LAST_TAXON, which is drawn as the bottom row
        self.leads_to_last = False

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
major_output_path = os.path.join(script_dir, "taxon_tree_major.txt")
stats_path = os.path.join(script_dir, "stats.md")
# Both redrawn on every build: the major-ranks cladogram, and the full one with
# every clade (very wide, so drawn at a lower resolution)
cladogram_path = os.path.join(script_dir, "cladogram.png")
cladogram_full_path = os.path.join(script_dir, "cladogram_full.png")
CLADOGRAM_DPI = 120
CLADOGRAM_FULL_DPI = 100

def parse_line(line, filename, line_num):
    name, sep, code = line.partition(';')
    name, code = name.strip(), code.strip()
    if name == '':
        raise ValueError(f"{filename}:{line_num}: missing taxon name")
    # A line with no ';' is an unranked subspecies
    if sep and code != '' and (len(code) != 1 or code not in RANK_ORDER):
        raise ValueError(f"{filename}:{line_num}: unknown rank code '{code}' (expected one of {', '.join(RANK_ORDER)})")
    return name, code

def build_tree(folder=taxonomy_dir):
    # Returns the root node and a list of warnings about likely mistakes
    root = None
    leaf_files = {}
    for filename in sorted(os.listdir(folder)):
        if not filename.endswith(".txt"):
            continue
        with open(os.path.join(folder, filename), 'r') as file:
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
        if node is not None:
            node.eaten = True
            leaf_files.setdefault(id(node), (node, []))[1].append(filename)
    if root is None:
        raise ValueError(f"no taxonomy files found in {folder}")
    mark_last(root)
    return root, find_warnings(root, leaf_files)

# The cladograms and the Newick file end with this taxon (us)
LAST_TAXON = "Homo sapiens"

def mark_last(node):
    # Marks the nodes leading to LAST_TAXON; returns whether node is one of them
    node.leads_to_last = node.value == LAST_TAXON or any(mark_last(child) for child in node.children.values())
    return node.leads_to_last

def ordered_children(node):
    # Children in file order, except that the branch leading to LAST_TAXON goes last
    return sorted(node.children.values(), key=lambda child: child.leads_to_last)

def find_warnings(root, leaf_files):
    warnings = []
    for node, filenames in leaf_files.values():
        if len(filenames) > 1:
            warnings.append(f"{' and '.join(filenames)} all end at '{node.value}' (duplicate entry?)")
    # Children are keyed by name under their parent, so the same name under two
    # parents makes two nodes: right for true homonyms, but usually a copy-paste slip.
    # Only the point where the parent names differ is reported, not every taxon below it.
    parents = {}
    stack = [root]
    while stack:
        node = stack.pop()
        for child in node.children.values():
            parents.setdefault(child.value, set()).add(node.value)
            stack.append(child)
    for name, parent_names in sorted(parents.items()):
        if len(parent_names) > 1:
            warnings.append(f"'{name}' appears under different parents: {', '.join(sorted(parent_names))}")
    return warnings

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

def newick_name(name):
    # Names with Newick's special characters (e.g. NCBI's "Poeae Chloroplast Group 1
    # (Aveneae type)") are put in single quotes, with any quote inside doubled
    if any(char in name for char in "()[]',:;"):
        return "'" + name.replace("'", "''") + "'"
    return name

def save_tree(node, depths, parent_depth):
    depth = depths[node.code] if node.code != '' else parent_depth + 1
    label = newick_name(node.value) + ':' + str((depth - parent_depth)*base)
    if len(node.children) == 0:
        return label
    return '(' + ','.join(save_tree(child, depths, depth) for child in ordered_children(node)) + ')' + label

def ranked_descendants(node):
    # The nearest ranked nodes (or leaves) below node, skipping unranked clades
    for child in ordered_children(node):
        if child.code != '' or len(child.children) == 0 or child.eaten:
            yield child
        else:
            yield from ranked_descendants(child)

def save_major_tree(node, parent_depth):
    # Like save_tree, but keeps only the root, the major ranks and the leaves.
    # Each rank has a fixed depth, so a skipped rank shows as a longer branch.
    depth = RANK_ORDER.index(node.code) + 1 if node.code != '' else parent_depth + 1
    label = newick_name(node.value) + ':' + str((depth - parent_depth)*base)
    children = list(ranked_descendants(node))
    if len(children) == 0:
        return label
    return '(' + ','.join(save_major_tree(child, depth) for child in children) + ')' + label

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
        if node.eaten or len(node.children) == 0:
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

RANK_NAMES = {"K": "Kingdom", "P": "Phylum", "C": "Class", "O": "Order", "F": "Family", "G": "Genus", "S": "Species"}

def layout_tree(root, depths, major):
    # Returns (node, x, y, children) for every node drawn: x is the node's depth,
    # leaves get y = 0, 1, 2... top to bottom, and a parent sits midway between its children
    placed = []
    next_leaf = [0]
    def place(node, parent_depth):
        if major:
            depth = RANK_ORDER.index(node.code) + 1 if node.code != '' else parent_depth + 1
            children = list(ranked_descendants(node))
        else:
            depth = depths[node.code] if node.code != '' else parent_depth + 1
            children = ordered_children(node)
        child_entries = [place(child, depth) for child in children]
        if child_entries:
            y = (child_entries[0][2] + child_entries[-1][2]) / 2
        else:
            y = next_leaf[0]
            next_leaf[0] += 1
        entry = (node, depth, y, child_entries)
        placed.append(entry)
        return entry
    place(root, -1)
    return placed, next_leaf[0]

def leaf_common_names(folder=taxonomy_dir):
    # Maps each file's last entry to the common name in its file name
    # ("american_clawed_lobster.txt" -> "american clawed lobster")
    names = {}
    for filename in sorted(os.listdir(folder)):
        if not filename.endswith(".txt"):
            continue
        with open(os.path.join(folder, filename), 'r') as file:
            lines = [line for line in file if line.strip()]
        if lines:
            leaf = lines[-1].partition(';')[0].strip()
            names.setdefault(leaf, []).append(filename[:-4].replace("_", " "))
    return {leaf: ", ".join(common) for leaf, common in names.items()}

LABEL_SIZE = 9    # clade names
LEAF_SIZE = 10    # organisms
HEADING_SIZE = 9  # rank column headings
ROW_HEIGHT = 24   # points between organisms
MIN_STEP = 12     # narrowest depth step, in points

def step_widths(max_depth, spans):
    # Width in points of each depth step (step d runs from depth d-1 to d), so that
    # every label fits on its branch: spans are (parent depth, depth, points needed).
    # Steps only get as wide as the labels crossing them need, instead of every
    # step being as wide as the tightest label anywhere.
    widths = [0.0] + [float(MIN_STEP)] * max_depth
    # Short spans first, so longer ones can use the room those already added
    for start, end, need in sorted(spans, key=lambda span: span[1] - span[0]):
        deficit = need - sum(widths[start + 1:end + 1])
        if deficit > 0:
            for step in range(start + 1, end + 1):
                widths[step] += deficit / (end - start)
    return widths

def draw_tree(root, depths, major, path, fmt=None, common_names=None, dpi=None):
    # path is a file name, or a file object with fmt ("svg", "png"...) given.
    # common_names maps organisms to the common name shown after them.
    # matplotlib is only needed for this option
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextToPath

    text_path = TextToPath()
    def text_width(text, size, style="normal"):
        return text_path.get_text_width_height_descent(text, FontProperties(size=size, style=style), ismath=False)[0]

    common_names = common_names or {}
    placed, leaf_count = layout_tree(root, depths, major)
    max_depth = max(x for _, x, _, _ in placed)
    parent_x = {id(child): x for _, x, _, children in placed for child, _, _, _ in children}

    # Every clade is named above the branch leading into it. A species above a
    # subspecies or variety is skipped (the organism's name already contains it),
    # unless the species was eaten itself; then its common name is added.
    labelled = []
    for node, x, y, children in placed:
        if not children or node is root or (node.code == 'S' and not node.eaten):
            continue
        text = node.value
        if node.eaten and common_names.get(node.value):
            text += f" ({common_names[node.value]})"
        labelled.append((node, x, y, text))
    # Depth steps are sized from the labels, and depths become x positions in points
    widths = step_widths(max_depth, [(parent_x[id(node)], x, text_width(text, LABEL_SIZE) + 8)
                                     for node, x, y, text in labelled])
    position = [sum(widths[:depth + 1]) for depth in range(max_depth + 1)]
    leaf_texts = {}
    for node, x, y, children in placed:
        if not children:
            common = common_names.get(node.value)
            leaf_texts[id(node)] = (node.value, f"({common})" if common else "")
    right_points = max(text_width(name, LEAF_SIZE, "italic") + 6 + text_width(common, LEAF_SIZE)
                       for name, common in leaf_texts.values()) + 20
    left_points = text_width(root.value, LABEL_SIZE) + 16
    width = left_points + position[max_depth] + right_points
    height = (leaf_count + 3.5) * ROW_HEIGHT

    fig = plt.figure(figsize=(width / 72, height / 72))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(-left_points, position[max_depth] + right_points)
    ax.set_ylim(leaf_count, -3.0)
    ax.axis("off")

    for node, x, y, children in placed:
        if children:
            ax.plot([position[x]] * 2, [children[0][2], children[-1][2]], color="#555555", linewidth=0.8)
            for _, child_x, child_y, _ in children:
                ax.plot([position[x], position[child_x]], [child_y, child_y], color="#555555", linewidth=0.8)
        else:
            name, common = leaf_texts[id(node)]
            ax.annotate(name, (position[x], y), xytext=(4, 0), textcoords="offset points",
                        ha="left", va="center", fontsize=LEAF_SIZE, style="italic")
            if common:
                ax.annotate(common, (position[x], y), xytext=(10 + text_width(name, LEAF_SIZE, "italic"), 0),
                            textcoords="offset points", ha="left", va="center", fontsize=LEAF_SIZE, color="#555555")
    for node, x, y, text in labelled:
        # Ranked clades in dark text, unranked clades lighter
        ax.annotate(text, (position[x], y), xytext=(-3, 2), textcoords="offset points", ha="right", va="bottom",
                    fontsize=LABEL_SIZE, color="#222222" if node.code or node.eaten else "#888888")
    _, root_x, root_y, _ = placed[-1]
    ax.annotate(root.value, (position[root_x], root_y), xytext=(-4, 0), textcoords="offset points",
                ha="right", va="center", fontsize=LABEL_SIZE, color="#222222")

    # Column headings for the aligned major ranks, angled so close ranks don't overlap
    rank_depths = {code: RANK_ORDER.index(code) + 1 for code in RANK_ORDER} if major else depths
    for code, x in rank_depths.items():
        ax.text(position[x], -1.2, RANK_NAMES[code], ha="left", va="bottom", rotation=35,
                fontsize=HEADING_SIZE, color="#777777")
        ax.axvline(position[x], color="#dddddd", linewidth=0.5, zorder=0)
    fig.savefig(path, format=fmt, dpi=dpi)
    plt.close(fig)

def write_cladogram(root, depths):
    # Redraws cladogram.png and cladogram_full.png; called whenever the tree is rebuilt.
    # Raises ImportError when matplotlib isn't installed.
    common_names = leaf_common_names(taxonomy_dir)
    draw_tree(root, depths, True, cladogram_path, common_names=common_names, dpi=CLADOGRAM_DPI)
    draw_tree(root, depths, False, cladogram_full_path, common_names=common_names, dpi=CLADOGRAM_FULL_DPI)

def main():
    parser = argparse.ArgumentParser(description="Build taxon_tree.txt and cladogram.png from the files in taxonomy_files/.")
    parser.add_argument("--stats", action="store_true", help="print counts of the organisms and taxa in the tree")
    parser.add_argument("--stats-md", action="store_true", help="also write the stats to stats.md")
    parser.add_argument("--major-only", action="store_true",
                        help="also write taxon_tree_major.txt, keeping only the major ranks and the leaves")
    parser.add_argument("--draw", metavar="FILE",
                        help="draw the tree to an image (.svg, .png or .pdf); with --major-only, draws that tree")
    args = parser.parse_args()

    try:
        root, warnings = build_tree()
    except ValueError as e:
        sys.exit(f"Error: {e}")
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    depths = compute_depths(root)

    with open(output_path, 'w') as f:
        f.write(save_tree(root, depths, -1) + ";\n")
    try:
        write_cladogram(root, depths)
    except ImportError:
        print("Warning: cladogram PNGs not updated (needs matplotlib: pip install --user matplotlib)", file=sys.stderr)
    if args.major_only:
        with open(major_output_path, 'w') as f:
            f.write(save_major_tree(root, -1) + ";\n")
    if args.draw:
        try:
            draw_tree(root, depths, args.major_only, args.draw, common_names=leaf_common_names())
        except ImportError:
            sys.exit("Error: --draw needs matplotlib (pip install --user matplotlib)")

    if args.stats or args.stats_md:
        stats = format_stats(*collect_stats(root))
        if args.stats:
            print(stats, end='')
        if args.stats_md:
            with open(stats_path, 'w') as f:
                f.write(stats)

if __name__ == "__main__":
    main()
