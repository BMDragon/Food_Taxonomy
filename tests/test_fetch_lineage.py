# Tests for fetch_lineage.py that don't need NCBI. Run from the project folder with:
#   python3 -m unittest discover tests

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import fetch_lineage

class FormatTests(unittest.TestCase):
    def test_ranks_codes_and_unranked_leaf(self):
        lineage = [("Eukaryota", "domain"), ("Metazoa", "kingdom"), ("Bos", "genus"),
                   ("Bos taurus", "species"), ("Bos taurus taurus", "subspecies")]
        self.assertEqual(fetch_lineage.format_lineage(lineage, {}),
                         "Eukaryota; \nMetazoa; K\nBos; G\nBos taurus; S\nBos taurus taurus")

    def test_existing_spelling_is_reused(self):
        lineage = [("Eukaryota", "domain"), ("eudicotyledons", "clade"), ("asterids", "clade")]
        text = fetch_lineage.format_lineage(lineage, {"eudicotyledons": "Eudicotyledons"})
        # The last line is unranked here, so it's written without ';'
        self.assertEqual(text, "Eukaryota; \nEudicotyledons; \nAsterids")

    def test_taxon_named_like_its_parent_gets_its_rank(self):
        # NCBI's escargot lineage: genus Cornu, then subgenus Cornu
        lineage = [("Eukaryota", "domain"), ("Helicidae", "family"), ("Cornu", "genus"),
                   ("Cornu", "subgenus"), ("Cornu aspersum", "species")]
        self.assertEqual(fetch_lineage.format_lineage(lineage, {}),
                         "Eukaryota; \nHelicidae; F\nCornu; G\nCornu (subgenus); \nCornu aspersum; S")

    def test_fill_meanings_adds_ncbi_common_names_for_new_taxa_only(self):
        import tempfile
        import xml.etree.ElementTree as ET
        import make_tree
        saved = (make_tree.meanings_path, fetch_lineage.search, fetch_lineage.fetch_taxa)
        taxids = {"Mammalia": "40674", "Theria": "32525", "Primates": "9443"}
        common = {"40674": "mammals", "32525": "", "9443": "primates"}
        def fake_taxa(ids):
            return [ET.fromstring(f"<Taxon><TaxId>{i}</TaxId><OtherNames>"
                                  + (f"<GenbankCommonName>{common[i]}</GenbankCommonName>" if common[i] else "")
                                  + "</OtherNames></Taxon>") for i in ids]
        with tempfile.TemporaryDirectory() as folder:
            make_tree.meanings_path = os.path.join(folder, "taxon_meanings.tsv")
            with open(make_tree.meanings_path, 'w') as f:
                f.write("Primates\tprimate order\n")
            fetch_lineage.search = lambda name, field: [taxids[name]] if name in taxids else []
            fetch_lineage.fetch_taxa = fake_taxa
            try:
                added = fetch_lineage.fill_meanings("Mammalia; C\nTheria; \nPrimates; O\nHomo sapiens; S")
                self.assertEqual(added, {"Mammalia": "mammals"})
                self.assertEqual(make_tree.load_meanings(), {"Primates": "primate order", "Mammalia": "mammals"})
            finally:
                make_tree.meanings_path, fetch_lineage.search, fetch_lineage.fetch_taxa = saved

    def test_clean_filename(self):
        self.assertEqual(fetch_lineage.clean_filename("../Pear Tree.txt"), "pear_tree.txt")
        with self.assertRaises(fetch_lineage.FetchError):
            fetch_lineage.clean_filename("...")

if __name__ == "__main__":
    unittest.main()
