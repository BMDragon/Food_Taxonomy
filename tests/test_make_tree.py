# Tests for make_tree.py. Run from the project folder with:
#   python3 -m unittest discover tests

import itertools
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import make_tree

# Small lineages with different numbers of unranked clades between the major
# ranks, which is what made rank alignment depend on file order before
HUMAN = ["Eukaryota; ", "Opisthokonta; ", "Metazoa; K", "Chordata; P", "Craniata; ", "Vertebrata; ",
         "Mammalia; C", "Theria; ", "Primates; O", "Haplorrhini; ", "Hominidae; F", "Homo; G",
         "Homo sapiens; S", "Homo sapiens sapiens"]
CHICKEN = ["Eukaryota; ", "Opisthokonta; ", "Metazoa; K", "Chordata; P", "Craniata; ", "Vertebrata; ",
           "Tetrapoda; ", "Amniota; ", "Sauropsida; ", "Dinosauria; ", "Theropoda; ", "Aves; C",
           "Galliformes; O", "Phasianidae; F", "Gallus; G", "Gallus gallus; S"]
APPLE = ["Eukaryota; ", "Viridiplantae; K", "Streptophyta; P", "Embryophyta; ", "Magnoliopsida; C",
         "Rosids; ", "Fabids; ", "Rosales; O", "Rosaceae; F", "Amygdaloideae; ", "Maleae; ", "Malus; G",
         "Malus domestica; S"]
BROCCOLI = ["Eukaryota; ", "Viridiplantae; K", "Streptophyta; P", "Embryophyta; ", "Magnoliopsida; C",
            "Rosids; ", "Malvids; ", "Brassicales; O", "Brassicaceae; F", "Brassica; G",
            "Brassica oleracea; S", "Brassica oleracea var. italica"]
SAMPLE = {"human.txt": HUMAN, "chicken.txt": CHICKEN, "apple.txt": APPLE, "broccoli.txt": BROCCOLI}

def write_folder(folder, files):
    for filename, lines in files.items():
        with open(os.path.join(folder, filename), 'w') as f:
            f.write("\n".join(lines))

def parse_newick(text):
    # Returns (name, branch length, children) for the root of a Newick string
    def parse(i):
        children = []
        if text[i] == '(':
            i += 1
            while True:
                child, i = parse(i)
                children.append(child)
                if text[i] == ',':
                    i += 1
                    continue
                i += 1
                break
        if text[i] == "'":
            # A quoted name, with '' standing for a quote inside it
            j = i + 1
            while not (text[j] == "'" and text[j + 1] != "'"):
                j += 2 if text[j] == "'" else 1
            name = text[i + 1:j].replace("''", "'")
            i = j + 1
        else:
            name = None
        j = i
        while text[j] not in ',);':
            j += 1
        unquoted, length = text[i:j].rsplit(':', 1)
        return (unquoted if name is None else name, int(length), children), j
    text = text.strip()
    return parse(0)[0]

def walk(node, distance=0, parent=None):
    # Yields (name, branch length, distance from the top, parent name) for every node
    name, length, children = node
    distance += length
    yield name, length, distance, parent
    for child in children:
        yield from walk(child, distance, name)

def rank_codes(root):
    codes = {}
    stack = [root]
    while stack:
        node = stack.pop()
        codes[node.value] = node.code
        stack.extend(node.children.values())
    return codes

def build(folder):
    root, warnings = make_tree.build_tree(folder)
    full = make_tree.save_tree(root, make_tree.compute_depths(root), -1) + ";"
    major = make_tree.save_major_tree(root, -1) + ";"
    return root, warnings, full, major

class TreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def folders(self):
        # The sample lineages, plus the real taxonomy files
        write_folder(self.folder, SAMPLE)
        return [self.folder, make_tree.taxonomy_dir]

    def test_branch_lengths_positive(self):
        for folder in self.folders():
            _, _, full, major = build(folder)
            for tree in (full, major):
                for name, length, _, _ in walk(parse_newick(tree)):
                    self.assertGreater(length, 0, f"{name} in {folder}")

    def test_ranks_aligned(self):
        for folder in self.folders():
            root, _, full, major = build(folder)
            codes = rank_codes(root)
            for tree in (full, major):
                distances = {}
                for name, _, distance, _ in walk(parse_newick(tree)):
                    if codes.get(name, '') != '':
                        distances.setdefault(codes[name], set()).add(distance)
                for code, found in distances.items():
                    self.assertEqual(len(found), 1, f"rank {code} at distances {found} in {folder}")
                self.assertEqual(set(distances), set(make_tree.RANK_ORDER))

    def test_output_independent_of_file_order(self):
        # Prefixes change the sorted order the files are read in
        results = set()
        for order in itertools.permutations(SAMPLE.items()):
            with tempfile.TemporaryDirectory() as folder:
                write_folder(folder, {f"{i}_{name}": lines for i, (name, lines) in enumerate(order)})
                _, _, full, major = build(folder)
                results.add(tuple(sorted(walk(parse_newick(full)))) + tuple(sorted(walk(parse_newick(major)))))
        self.assertEqual(len(results), 1)

    def test_major_only_drops_unranked_clades(self):
        write_folder(self.folder, SAMPLE)
        root, _, _, major = build(self.folder)
        codes = rank_codes(root)
        names = {name for name, _, _, _ in walk(parse_newick(major))}
        for name in ("Opisthokonta", "Craniata", "Rosids", "Haplorrhini", "Maleae"):
            self.assertNotIn(name, names)
        # Leaves are kept even when unranked
        self.assertIn("Homo sapiens sapiens", names)
        self.assertIn("Brassica oleracea var. italica", names)
        for name in names - {"Eukaryota", "Homo sapiens sapiens", "Brassica oleracea var. italica"}:
            self.assertNotEqual(codes[name], '', name)

    def test_draw_writes_an_image_with_every_organism(self):
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib is not installed")
        write_folder(self.folder, SAMPLE)
        root, _ = make_tree.build_tree(self.folder)
        depths = make_tree.compute_depths(root)
        for major in (False, True):
            path = os.path.join(self.folder, f"tree_{major}.svg")
            make_tree.draw_tree(root, depths, major, path)
            with open(path, 'r') as f:
                svg = f.read()
            # matplotlib writes text as paths, so check the layout instead of the svg text
            self.assertTrue(svg.startswith("<?xml"))
            placed, leaf_count = make_tree.layout_tree(root, depths, major)
            leaves = [node.value for node, _, _, children in placed if not children]
            self.assertEqual(sorted(leaves), sorted(lines[-1].partition(';')[0].strip() for lines in SAMPLE.values()))
            self.assertEqual(leaf_count, len(SAMPLE))

    def test_species_eaten_above_its_subspecies_counts_as_an_organism(self):
        # Like red onion (Allium cepa) above shallot (Allium cepa var. aggregatum)
        write_folder(self.folder, {"human.txt": HUMAN, "homo_sapiens.txt": HUMAN[:-1], "apple.txt": APPLE})
        root, warnings, _, major = build(self.folder)
        self.assertEqual(warnings, [])
        kingdoms, totals = make_tree.collect_stats(root)
        self.assertEqual(totals["organisms"], 3)
        self.assertEqual(totals["species"], 2)
        self.assertEqual(totals["subspecies"], 1)
        self.assertIn("Homo sapiens", {name for name, _, _, _ in walk(parse_newick(major))})

    def test_names_with_newick_characters_are_quoted(self):
        oat = APPLE[:5] + ["Poeae Chloroplast Group 1 (Aveneae type); ", "Pooideae; O", "Poaceae; F",
                           "Avena; G", "Avena sativa; S"]
        oat = [line.replace("Rosids", "x") for line in oat]
        write_folder(self.folder, {"oat.txt": oat, "apple.txt": APPLE, "o'brien.txt": APPLE[:5] + ["Fo'o; ", "Bar; O", "Baz; F", "Qux; G", "Qux quux; S"]})
        _, _, full, major = build(self.folder)
        self.assertIn("'Poeae Chloroplast Group 1 (Aveneae type)':", full)
        self.assertIn("'Fo''o':", full)
        names = {name for name, _, _, _ in walk(parse_newick(full))}
        self.assertIn("Poeae Chloroplast Group 1 (Aveneae type)", names)
        self.assertIn("Fo'o", names)
        self.assertIn("Avena sativa", {name for name, _, _, _ in walk(parse_newick(major))})

    def test_human_is_the_last_row(self):
        # HUMAN is written to the folder first (so read first), yet must come out last
        write_folder(self.folder, {"a_human.txt": HUMAN, "b_chicken.txt": CHICKEN, "c_apple.txt": APPLE,
                                   "d_broccoli.txt": BROCCOLI})
        root, _, full, major = build(self.folder)
        for tree in (full, major):
            leaves = [name for name, _, _, _ in walk(parse_newick(tree))
                      if name in ("Homo sapiens sapiens", "Gallus gallus", "Malus domestica",
                                  "Brassica oleracea var. italica")]
            self.assertEqual(leaves[-1], "Homo sapiens sapiens")
        for major in (False, True):
            placed, leaf_count = make_tree.layout_tree(root, make_tree.compute_depths(root), major)
            bottom = max(placed, key=lambda entry: entry[2])
            self.assertEqual(bottom[0].value, "Homo sapiens sapiens")

    def test_step_widths_fit_every_label_without_widening_other_steps(self):
        spans = [(0, 1, 50.0), (1, 3, 100.0), (3, 4, 5.0), (0, 4, 40.0)]
        widths = make_tree.step_widths(5, spans)
        for start, end, need in spans:
            self.assertGreaterEqual(sum(widths[start + 1:end + 1]) + 1e-9, need)
        # Steps no label needs stay at the minimum
        self.assertEqual(widths[4], make_tree.MIN_STEP)
        self.assertEqual(widths[5], make_tree.MIN_STEP)
        # The two-step label is shared across both of its steps
        self.assertAlmostEqual(widths[2], widths[3])

    def test_leaf_common_names_come_from_file_names(self):
        write_folder(self.folder, {"american_clawed_lobster.txt": HUMAN, "apple.txt": APPLE, "apple_2.txt": APPLE})
        self.assertEqual(make_tree.leaf_common_names(self.folder),
                         {"Homo sapiens sapiens": "american clawed lobster", "Malus domestica": "apple, apple 2"})

    def assertBuildError(self, files, message):
        write_folder(self.folder, files)
        with self.assertRaises(ValueError) as context:
            make_tree.build_tree(self.folder)
        self.assertIn(message, str(context.exception))

    def test_unknown_rank_code(self):
        self.assertBuildError({"a.txt": APPLE[:7] + ["Rosales; X"]}, "unknown rank code 'X'")

    def test_ranks_out_of_order(self):
        self.assertBuildError({"a.txt": APPLE[:7] + ["Rosales; P"]}, "out of order")

    def test_wrong_root(self):
        self.assertBuildError({"a.txt": APPLE, "b.txt": ["Bacteria; "] + HUMAN[1:]}, "expected 'Eukaryota'")

    def test_no_warnings_for_clean_files(self):
        for folder in self.folders():
            _, warnings, _, _ = build(folder)
            self.assertEqual(warnings, [], folder)

    def test_warns_about_duplicate_entries(self):
        write_folder(self.folder, {"apple.txt": APPLE, "apple2.txt": APPLE, "human.txt": HUMAN})
        _, warnings, _, _ = build(self.folder)
        self.assertEqual(len(warnings), 1)
        self.assertIn("apple.txt and apple2.txt", warnings[0])

    def test_species_above_a_subspecies_is_not_a_duplicate(self):
        write_folder(self.folder, {"human.txt": HUMAN, "human_species.txt": HUMAN[:-1]})
        _, warnings, _, _ = build(self.folder)
        self.assertEqual(warnings, [])

    def test_warns_about_name_under_two_parents(self):
        # "Fabids" skipped in one file puts Rosales under two different parents
        slipped = [line for line in APPLE if line != "Fabids; "]
        write_folder(self.folder, {"apple.txt": APPLE, "pear.txt": slipped[:-2] + ["Pyrus; G", "Pyrus communis; S"]})
        _, warnings, _, _ = build(self.folder)
        # Only where the lineages split, not again for every taxon below it
        self.assertEqual(warnings, ["'Rosales' appears under different parents: Fabids, Rosids"])

if __name__ == "__main__":
    unittest.main()
