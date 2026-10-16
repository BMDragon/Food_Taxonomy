# Food Taxonomy
Taxonomy of things I can remember consuming

## Website

`python3 serve.py` starts a local website at `http://localhost:8765/` (it only accepts connections from the same computer). Use `--port` to pick another port. Over VS Code Remote-SSH, the port is forwarded automatically, so the link works in your local browser.

- **Tree**: the whole tree, collapsible and searchable by taxon, food name or meaning; each clade shows what its name means, e.g. "Tetrapoda (four-legged)"; "Major ranks only" hides unranked clades. Each organism has a **Remove** button, which deletes its file from `taxonomy_files/` and rebuilds `taxon_tree.txt` and the cladogram PNGs (with an Undo right after). Without the website, delete the file and run `python3 make_tree.py`.
- **Cladogram**: the drawn tree (needs matplotlib).
- **Stats**: organism and taxon counts, overall and by kingdom, and a coverage sunburst: rings for kingdom, phylum, class and order, each slice sized by how many common foods it holds and shaded by how many of them you've eaten.
- **Relatives**: pick a food to see its closest relatives in your tree, or two foods to see their closest shared ancestor and the path from there to each (e.g. shiitake and human meet at Opisthokonta). Links like `#relatives?a=shiitake&b=human` open a comparison directly.
- **Add organism**: look an organism up on NCBI, check the lineage and file name, then save it; `taxon_tree.txt` and the cladogram PNGs are rebuilt automatically. Commit the new file afterwards.
- **Gaps**: the `gaps.py` report for any taxon, listing groups you haven't eaten from that contain common foods, with examples. Every food not eaten yet has an **Add** button that looks it up on NCBI and adds it in one step. **Suggest foods to try** ranks the common foods you haven't eaten by how many new branches each would add (within the taxon, if one is entered). Links like `#gaps?taxon=Rosaceae&rank=species&suggest=1` run both.

Press Ctrl+C in the terminal to stop the server.

## Command line

Usage: Add a `.txt` file to the "taxonomy_files" folder for each organism, in the format described below, then run `python3 make_tree.py`.

The easiest way to add a file is to fetch it from NCBI Taxonomy:
```
python3 fetch_lineage.py apple="Malus domestica" "Brassica oleracea var. capitata"
```
- `apple="Malus domestica"` writes `taxonomy_files/apple.txt`. Without a file name, the file is named after the common name: the one you typed (`"honey bee"` → `honey_bee.txt`), otherwise NCBI's (`"Brassica oleracea var. capitata"` → `cabbage.txt`). If NCBI has no common name, give a file name.
- Only eukaryotic species, subspecies and varieties are accepted. Common names and synonyms are tried if the scientific name isn't found.
- Clade names already used in other files keep their existing spelling (e.g. NCBI's `eudicotyledons` is written `Eudicotyledons`).
- Existing files, and organisms already in another file, are not overwritten or duplicated unless `--force` is given.
- After writing files it runs `make_tree.py`, which rebuilds `taxon_tree.txt` and the cladogram PNGs; `--no-build` skips that. `--dry-run` prints the files instead of writing them.
- Set the `NCBI_API_KEY` environment variable to use an NCBI API key (optional; raises the request limit from 3 to 10 per second).

Organisms NCBI doesn't list (e.g. `Homo sapiens sapiens`) can still be added by hand.

The meanings shown on the website are in `taxon_meanings.tsv` (one `name<TAB>meaning` line per taxon). Edit it freely. When `fetch_lineage.py` or the website adds an organism, any new taxa without a meaning get NCBI's common name where NCBI has one; existing entries are never overwritten.

Generates a cladogram file (`taxon_tree.txt`) in the Newick format, for upload into https://cladogrammaker.com/, draws the major-ranks cladogram to `cladogram.png`, and draws the full cladogram with every clade to `cladogram_full.png` (both need matplotlib). Both are regenerated whenever organisms are added or removed through the website or `fetch_lineage.py`; after editing or deleting files by hand, run `python3 make_tree.py`.

Major ranks (Kingdom, Phylum, Class, Order, Family, Genus, Species) are lined up at the same depth across the whole tree.

`python3 make_tree.py --stats` also prints how many organisms are in the tree (species, subspecies, varieties), how many distinct taxa there are at each major rank, and a breakdown by kingdom. `--stats-md` writes the same report to `stats.md`.

`python3 make_tree.py --major-only` also writes `taxon_tree_major.txt`, a simpler tree with only the major ranks and the organisms themselves (unranked clades such as `Opisthokonta` are left out).

`python3 make_tree.py --draw tree.svg` draws the tree to an image (`.svg`, `.png` or `.pdf`), with the major ranks lined up in columns. Add `--major-only` to draw the simpler tree. Drawing needs matplotlib (`pip install --user -r requirements.txt`); nothing else does.

`python3 gaps.py Mammalia` lists the groups one rank down (here, orders of mammals) and which of them you haven't eaten yet, using NCBI Taxonomy. Use `--rank` to choose another rank, from kingdom down to genus, or `species` for species and varieties, e.g. `python3 gaps.py Viridiplantae --rank order` or `python3 gaps.py Rosaceae --rank species`. The species level lists the common foods (from `common_foods.tsv`) in the group that you haven't eaten yet; a genus defaults to it. NCBI results are cached in `.ncbi_cache/`; `--refresh` fetches them again.

By default, "not eaten yet" only lists groups that contain at least one commonly eaten species from `common_foods.tsv` (about 580 foods worldwide), each with up to three example foods, e.g. "Rodentia (rodents): e.g. guinea pig, capybara". `--all` (or the website's "Include groups with no common foods" box) lists every group. To extend the food list, add a line `food<TAB>scientific name` to `common_foods.tsv` and run `python3 update_common_foods.py`, which looks up the lineage on NCBI.

`make_tree.py` warns about likely mistakes in the taxonomy files: two files that end at the same organism, and a name that appears under two different parents (usually a skipped or extra line in one file).

`python3 gaps.py --suggest` lists the 20 common foods that would add the most new branches to the tree (a new class ranks above a new genus); `python3 gaps.py Rosaceae --suggest 5` limits it to a group.

`python3 check_ncbi.py` compares every taxonomy file with NCBI's current lineage for its organism (NCBI renames and reclassifies taxa over time) and lists the differences; `--fix` rewrites the files that differ and rebuilds the tree. Organisms NCBI doesn't list, like `Homo sapiens sapiens`, are left as they are.

`python3 export_site.py` writes a static copy of the website to `docs/` (tree, cladograms, stats, coverage and relatives; adding, removing and gaps need the server and are left out). Open `docs/index.html` directly, or publish it with GitHub Pages (Settings → Pages → Deploy from a branch → `main`, folder `/docs`). Run it again after changing the tree to update the copy.

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
