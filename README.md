# Food Taxonomy
Taxonomy of things I can remember consuming

Usage: Obtain taxonomic information from NCBI, then copy it into a `.txt` file in the "taxonomy_files" folder with the format described below. Then run `python3 make_tree.py`.

Generates a cladogram file (`taxon_tree.txt`) in the Newick format, for upload into https://cladogrammaker.com/

Major ranks (Kingdom, Phylum, Class, Order, Family, Genus, Species) are lined up at the same depth across the whole tree.

Text file input format:
- One taxon per line, from the root (`Eukaryota`) down to the organism.
- Each line is `Name; R`, where `R` is the rank code: `K`, `P`, `C`, `O`, `F`, `G` or `S`.
- Leave the rank code empty (`Name;`) for unranked clades.
- A final line with no `;` (e.g. a subspecies) is treated as unranked.
- Ranked lines must appear in the order K, P, C, O, F, G, S, and every file must start with the same root.

Example:
```
Eukaryota;
Opisthokonta;
Fungi; K
Dikarya;
Basidiomycota; P
...
Agaricus; G
Agaricus bisporus; S
```
