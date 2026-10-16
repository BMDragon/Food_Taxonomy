# Fills in NCBI lineages for common_foods.tsv, the list of commonly eaten species that
# gaps.py uses to show only gaps containing real foods.
# Add a line "food<TAB>scientific name" to common_foods.tsv, then run this script.

import argparse
import sys

import fetch_lineage
import gaps

def main():
    parser = argparse.ArgumentParser(description="Look up NCBI lineages for entries in common_foods.tsv.")
    parser.add_argument("--refresh", action="store_true", help="look up every entry again, not just new ones")
    args = parser.parse_args()

    with open(gaps.common_foods_path, 'r') as f:
        lines = [line.rstrip('\n') for line in f]
    updated, failed = 0, []
    for i, line in enumerate(lines):
        if not line.strip() or line.startswith('#'):
            continue
        parts = line.split('\t')
        food, species = parts[0].strip(), parts[1].strip() if len(parts) > 1 else ''
        if not species:
            failed.append(f"{food}: no scientific name")
            continue
        # Columns 3 and 4 are the lineage names and their NCBI ranks
        if len(parts) >= 4 and parts[2].strip() and parts[3].strip() and not args.refresh:
            continue
        try:
            lineage, _ = fetch_lineage.fetch_taxon(fetch_lineage.find_taxid(species))
        except fetch_lineage.FetchError as e:
            failed.append(f"{food} ({species}): {e}")
            continue
        if lineage[0][0] != fetch_lineage.ROOT:
            failed.append(f"{food} ({species}): not a eukaryote")
            continue
        if lineage[-1][0] != species:
            print(f"note: {species} is listed in NCBI as {lineage[-1][0]}")
        lines[i] = (f"{food}\t{lineage[-1][0]}\t" + "; ".join(name for name, _ in lineage)
                    + "\t" + "; ".join(rank for _, rank in lineage))
        updated += 1
        print(f"looked up {food} ({lineage[-1][0]})")
    with open(gaps.common_foods_path, 'w') as f:
        f.write("\n".join(lines) + "\n")
    print(f"{updated} entries updated")
    for message in failed:
        print("Error: " + message, file=sys.stderr)
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
