# Food Taxonomy
Taxonomy of things I can remember consuming

Usage: Add a `.txt` file to the "taxonomy_files" folder for each organism, in the format described below, then run `python3 make_tree.py`.

The easiest way to add a file is to fetch it from NCBI Taxonomy:
```
python3 fetch_lineage.py apple="Malus domestica" "Brassica oleracea var. capitata" --build
```
- `apple="Malus domestica"` writes `taxonomy_files/apple.txt`. Without a file name, the file is named after the common name: the one you typed (`"honey bee"` → `honey_bee.txt`), otherwise NCBI's (`"Brassica oleracea var. capitata"` → `cabbage.txt`). If NCBI has no common name, give a file name.
- Only eukaryotic species, subspecies and varieties are accepted. Common names and synonyms are tried if the scientific name isn't found.
- Clade names already used in other files keep their existing spelling (e.g. NCBI's `eudicotyledons` is written `Eudicotyledons`).
- Existing files, and organisms already in another file, are not overwritten or duplicated unless `--force` is given.
- `--dry-run` prints the files instead of writing them; `--build` runs `make_tree.py` afterwards.
- Set the `NCBI_API_KEY` environment variable to use an NCBI API key (optional; raises the request limit from 3 to 10 per second).

Organisms NCBI doesn't list (e.g. `Homo sapiens sapiens`) can still be added by hand.

Generates a cladogram file (`taxon_tree.txt`) in the Newick format, for upload into https://cladogrammaker.com/

Major ranks (Kingdom, Phylum, Class, Order, Family, Genus, Species) are lined up at the same depth across the whole tree.

`python3 make_tree.py --stats` also prints how many organisms are in the tree (species, subspecies, varieties), how many distinct taxa there are at each major rank, and a breakdown by kingdom. `--stats-md` writes the same report to `stats.md`.

`python3 make_tree.py --major-only` also writes `taxon_tree_major.txt`, a simpler tree with only the major ranks and the organisms themselves (unranked clades such as `Opisthokonta` are left out).

`python3 make_tree.py --draw tree.svg` draws the tree to an image (`.svg`, `.png` or `.pdf`), with the major ranks lined up in columns. Add `--major-only` to draw the simpler tree. Drawing needs matplotlib (`pip install --user -r requirements.txt`); nothing else does.

`python3 gaps.py Mammalia` lists the groups one rank down (here, orders of mammals) and which of them you haven't eaten yet, using NCBI Taxonomy. Use `--rank` to choose another rank (kingdom to family), e.g. `python3 gaps.py Viridiplantae --rank order`. NCBI results are cached in `.ncbi_cache/`; `--refresh` fetches them again.

`make_tree.py` warns about likely mistakes in the taxonomy files: two files that end at the same organism, and a name that appears under two different parents (usually a skipped or extra line in one file).

Run the tests with `python3 -m unittest discover tests`.

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
