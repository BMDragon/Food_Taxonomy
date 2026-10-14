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

    def test_describe(self):
        self.assertEqual(gaps.describe(MAMMAL_ORDERS[1]), "Carnivora (carnivores)")
        self.assertEqual(gaps.describe({"name": "Pilosa", "common": ""}), "Pilosa")

if __name__ == "__main__":
    unittest.main()
