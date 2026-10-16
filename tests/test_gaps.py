# Tests for gaps.py that don't need NCBI. Run from the project folder with:
#   python3 -m unittest discover tests

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import gaps
import make_tree
from test_make_tree import SAMPLE, write_folder

MAMMAL_ORDERS = [{"name": "Artiodactyla", "common": "even-toed ungulates & whales"},
                 {"name": "Carnivora", "common": "carnivores"},
                 {"name": "Primates", "common": "primates"},
                 {"name": "Rodentia", "common": "rodents"}]

class GapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        write_folder(self.tmp.name, SAMPLE)
        self.root, _ = make_tree.build_tree(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_eaten_groups(self):
        self.assertEqual(gaps.eaten_groups(self.root, "Mammalia", "order"), {"Primates"})
        self.assertEqual(gaps.eaten_groups(self.root, "chordata", "class"), {"Mammalia", "Aves"})
        self.assertEqual(gaps.eaten_groups(self.root, "Magnoliopsida", "order"), {"Rosales", "Brassicales"})
        self.assertEqual(gaps.eaten_groups(self.root, "Fungi", "order"), set())

    def test_compare(self):
        have, missing, unknown = gaps.compare({"Primates", "Lagomorpha"}, MAMMAL_ORDERS)
        self.assertEqual([group["name"] for group in have], ["Primates"])
        self.assertEqual([group["name"] for group in missing], ["Artiodactyla", "Carnivora", "Rodentia"])
        # A name NCBI doesn't list at that rank is reported, not silently dropped
        self.assertEqual(unknown, ["Lagomorpha"])

    def test_missing_groups_filtered_to_common_foods(self):
        foods = [{"food": "guinea pig", "species": "Cavia porcellus", "ranks": [],
                  "lineage": ["Eukaryota", "Mammalia", "Rodentia", "Caviidae", "Cavia porcellus"]},
                 {"food": "beef", "species": "Bos taurus", "ranks": [],
                  "lineage": ["Eukaryota", "Mammalia", "Artiodactyla", "Bovidae", "Bos taurus"]}]
        missing = [{"name": "Rodentia", "common": "rodents"}, {"name": "Notoryctemorphia", "common": ""}]
        edible = gaps.foods_by_taxon(foods)
        shown, hidden = gaps.filter_missing(missing, edible, show_all=False)
        self.assertEqual([group["name"] for group in shown], ["Rodentia"])
        self.assertEqual(shown[0]["examples"], [{"food": "guinea pig", "species": "Cavia porcellus"}])
        self.assertEqual(hidden, 1)
        shown, hidden = gaps.filter_missing(missing, edible, show_all=True)
        self.assertEqual([group["name"] for group in shown], ["Rodentia", "Notoryctemorphia"])
        self.assertEqual(hidden, 0)
        self.assertEqual(gaps.describe(shown[0]), "Rodentia (rodents): e.g. guinea pig")

    def test_species_report_lists_common_foods_not_eaten(self):
        saved = gaps.common_foods_path
        gaps.common_foods_path = os.path.join(self.tmp.name, "common_foods.tsv")
        try:
            with open(gaps.common_foods_path, 'w') as f:
                f.write("# comment\n"
                        "apple\tMalus domestica\tEukaryota; Rosales; Malus; Malus domestica\n"
                        "quince\tCydonia oblonga\tEukaryota; Rosales; Cydonia; Cydonia oblonga\n"
                        "kohlrabi\tBrassica oleracea var. gongylodes\tEukaryota; Brassicales; Brassica; "
                        "Brassica oleracea; Brassica oleracea var. gongylodes\n"
                        "wild cabbage\tBrassica oleracea\tEukaryota; Brassicales; Brassica; Brassica oleracea\n")
            report = gaps.species_report(self.root, "Rosales")
            self.assertEqual([entry["common"] for entry in report["have"]], ["apple"])
            self.assertEqual([entry["common"] for entry in report["missing"]], ["quince"])
            # The broccoli sample puts Brassica oleracea in the tree, so the species counts as
            # eaten, but the kohlrabi variety doesn't
            report = gaps.species_report(self.root, "Brassicales")
            self.assertEqual([entry["common"] for entry in report["have"]], ["wild cabbage"])
            self.assertEqual([entry["common"] for entry in report["missing"]], ["kohlrabi"])
        finally:
            gaps.common_foods_path = saved

    def write_common_foods(self, text):
        saved = gaps.common_foods_path
        gaps.common_foods_path = os.path.join(self.tmp.name, "common_foods.tsv")
        self.addCleanup(setattr, gaps, "common_foods_path", saved)
        with open(gaps.common_foods_path, 'w') as f:
            f.write(text)

    def test_suggestions_rank_by_highest_new_branch(self):
        # Sample tree: human, chicken, apple, broccoli
        self.write_common_foods(
            "apple\tMalus domestica\tEukaryota; Metazoa; Malus; Malus domestica\tdomain; kingdom; genus; species\n"
            "sheep\tOvis aries\tEukaryota; Metazoa; Chordata; Mammalia; Artiodactyla; Bovidae; Ovis; Ovis aries\t"
            "domain; kingdom; phylum; class; order; family; genus; species\n"
            "chimp\tPan troglodytes\tEukaryota; Metazoa; Chordata; Mammalia; Primates; Hominidae; Pan; Pan troglodytes\t"
            "domain; kingdom; phylum; class; order; family; genus; species\n"
            "squid\tLoligo vulgaris\tEukaryota; Metazoa; Mollusca; Cephalopoda; Myopsida; Loliginidae; Loligo; Loligo vulgaris\t"
            "domain; kingdom; phylum; class; order; family; genus; species\n")
        results = gaps.suggestions(self.root)
        # Apple is already eaten; squid adds a phylum, sheep an order, chimp only a genus
        self.assertEqual([r["food"] for r in results], ["squid", "sheep", "chimp"])
        self.assertEqual(results[0]["new_major"]["phylum"], "Mollusca")
        self.assertEqual(results[2]["new_major"], {"genus": "Pan", "species": "Pan troglodytes"})
        self.assertEqual([r["food"] for r in gaps.suggestions(self.root, "Mammalia", limit=1)], ["sheep"])

    def test_coverage_counts_common_and_eaten_foods(self):
        self.write_common_foods(
            "apple\tMalus domestica\tEukaryota; Viridiplantae; Streptophyta; Magnoliopsida; Rosales; Malus; "
            "Malus domestica\tdomain; kingdom; phylum; class; order; genus; species\n"
            "pear\tPyrus communis\tEukaryota; Viridiplantae; Streptophyta; Magnoliopsida; Rosales; Pyrus; "
            "Pyrus communis\tdomain; kingdom; phylum; class; order; genus; species\n"
            "hazelnut\tCorylus avellana\tEukaryota; Viridiplantae; Streptophyta; Magnoliopsida; Fagales; Corylus; "
            "Corylus avellana\tdomain; kingdom; phylum; class; order; genus; species\n")
        top = gaps.coverage(self.root)
        # Apple, pear and hazelnut from the list, plus human, chicken and broccoli from the tree
        self.assertEqual((top["eaten"], top["total"]), (4, 6))
        plants = next(child for child in top["children"] if child["name"] == "Viridiplantae")
        flowering = plants["children"][0]["children"][0]
        self.assertEqual((flowering["eaten"], flowering["total"]), (2, 4))
        # Fagales has nothing eaten, so it's left out of the chart, but still counts above
        self.assertEqual([order["name"] for order in flowering["children"]], ["Rosales", "Brassicales"])
        rosales = flowering["children"][0]
        self.assertEqual((rosales["name"], rosales["eaten"], rosales["total"]), ("Rosales", 1, 2))

    def test_describe(self):
        self.assertEqual(gaps.describe(MAMMAL_ORDERS[1]), "Carnivora (carnivores)")
        self.assertEqual(gaps.describe({"name": "Pilosa", "common": ""}), "Pilosa")

if __name__ == "__main__":
    unittest.main()
