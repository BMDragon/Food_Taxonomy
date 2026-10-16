# Checks every taxonomy file against NCBI's current lineage for its organism, since NCBI
# renames and reclassifies taxa over time. Reports the differences; --fix rewrites the files.

import argparse
import os
import subprocess
import sys

import fetch_lineage
import make_tree

def read_lines(path):
    with open(path, 'r') as f:
        return [line.rstrip() for line in f if line.strip()]

def parse(lines):
    # [(name, rank code)] for a file's lines
    return [(line.partition(';')[0].strip(), line.partition(';')[2].strip()) for line in lines]

def differences(current, expected):
    # Short descriptions of how two parsed lineages differ
    notes = []
    current_names = [name for name, _ in current]
    expected_names = [name for name, _ in expected]
    if current_names[-1] != expected_names[-1]:
        notes.append(f"organism renamed: {current_names[-1]} -> {expected_names[-1]}")
    removed = [name for name in current_names if name not in expected_names]
    added = [name for name in expected_names if name not in current_names]
    if removed:
        notes.append("no longer in NCBI's lineage: " + ", ".join(removed))
    if added:
        notes.append("new in NCBI's lineage: " + ", ".join(added))
    current_codes = dict(current)
    for name, code in expected:
        if name in current_codes and current_codes[name] != code:
            notes.append(f"rank of {name}: {current_codes[name] or 'unranked'} -> {code or 'unranked'}")
    if not notes:
        notes.append("same names and ranks, different order or spacing")
    return notes

def check_file(filename, spellings):
    # Returns (status, expected text, notes); status is "ok", "differs", "not found" or
    # "not checked" (NCBI couldn't be reached)
    lines = read_lines(os.path.join(make_tree.taxonomy_dir, filename))
    organism = lines[-1].partition(';')[0].strip()
    try:
        lineage, _ = fetch_lineage.fetch_taxon(fetch_lineage.find_taxid(organism))
    except fetch_lineage.NcbiUnavailable as e:
        return "not checked", None, [str(e)]
    except fetch_lineage.FetchError as e:
        return "not found", None, [str(e)]
    expected = fetch_lineage.format_lineage(lineage, spellings)
    if expected.splitlines() == [line for line in lines] or \
            [l.rstrip() for l in expected.splitlines()] == lines:
        return "ok", expected, []
    return "differs", expected, differences(parse(lines), parse(expected.splitlines()))

def main():
    parser = argparse.ArgumentParser(description="Check every taxonomy file against NCBI's current lineage.")
    parser.add_argument("files", nargs="*", help="only check these files (e.g. apple.txt)")
    parser.add_argument("--fix", action="store_true",
                        help="rewrite files that differ to NCBI's lineage, then rebuild the tree")
    args = parser.parse_args()

    spellings, _ = fetch_lineage.read_existing()
    filenames = args.files or sorted(name for name in os.listdir(make_tree.taxonomy_dir) if name.endswith(".txt"))
    counts = {"ok": 0, "differs": 0, "not found": 0, "not checked": 0}
    fixed = 0
    for filename in filenames:
        status, expected, notes = check_file(filename, spellings)
        counts[status] += 1
        if status == "ok":
            continue
        print(f"{filename}: {status}")
        for note in notes:
            print("  " + note)
        if status == "differs" and args.fix:
            with open(os.path.join(make_tree.taxonomy_dir, filename), 'w') as f:
                f.write(expected)
            fixed += 1
            print("  fixed")
            # New clades get NCBI's common name as their meaning, as when adding
            try:
                fetch_lineage.fill_meanings(expected)
            except fetch_lineage.FetchError:
                pass
    print(f"\n{counts['ok']} match NCBI, {counts['differs']} differ, {counts['not found']} not found in NCBI")
    if counts["not checked"]:
        print(f"{counts['not checked']} couldn't be checked because NCBI was unavailable; run again to check them")
    if fixed:
        subprocess.run([sys.executable, os.path.join(make_tree.script_dir, "make_tree.py")], check=True)
        print(f"{fixed} files fixed and the tree rebuilt")
    elif counts["differs"] and not args.fix:
        print("Run with --fix to rewrite the files that differ.")

if __name__ == "__main__":
    main()
