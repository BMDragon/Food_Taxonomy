# Tests for check_ncbi.py that don't need NCBI. Run from the project folder with:
#   python3 -m unittest discover tests

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_ncbi

class DifferenceTests(unittest.TestCase):
    def test_new_clade_rank_change_and_rename(self):
        current = [("Eukaryota", ""), ("Brassica", "G"), ("Brassica rapa", "S"), ("Brassica rapa var. ruvo", "")]
        expected = [("Eukaryota", ""), ("Brassica", "G"), ("Brassica rapa", "S"),
                    ("Brassica rapa subsp. oleifera", ""), ("Brassica rapa var. ruvo", "")]
        self.assertEqual(check_ncbi.differences(current, expected),
                         ["new in NCBI's lineage: Brassica rapa subsp. oleifera"])
        renamed = [("Eukaryota", ""), ("Pisum", "G"), ("Pisum sativum", "S")]
        now = [("Eukaryota", ""), ("Lathyrus", "G"), ("Lathyrus oleraceus", "S")]
        notes = check_ncbi.differences(renamed, now)
        self.assertIn("organism renamed: Pisum sativum -> Lathyrus oleraceus", notes)
        self.assertIn("no longer in NCBI's lineage: Pisum, Pisum sativum", notes)
        self.assertIn("rank of Brassica: G -> unranked",
                      check_ncbi.differences([("Brassica", "G"), ("x", "S")], [("Brassica", ""), ("x", "S")]))

if __name__ == "__main__":
    unittest.main()
