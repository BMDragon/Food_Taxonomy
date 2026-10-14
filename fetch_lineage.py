# Fetches an organism's lineage from NCBI Taxonomy and writes it as a taxonomy file

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
RANK_CODES = {"kingdom": "K", "phylum": "P", "class": "C", "order": "O",
              "family": "F", "genus": "G", "species": "S"}
# Lowest entries we track; anything above species or below variety is refused
LEAF_RANKS = {"species", "subspecies", "varietas"}
ROOT = "Eukaryota"

script_dir = os.path.dirname(os.path.abspath(__file__))
taxonomy_dir = os.path.join(script_dir, "taxonomy_files")

api_key = os.environ.get("NCBI_API_KEY")
# NCBI allows 3 requests per second without an API key, 10 with one
min_interval = 0.11 if api_key else 0.34
last_request = 0.0

class FetchError(Exception):
    pass

def ncbi_get(endpoint, params):
    global last_request
    params = dict(params, db="taxonomy")
    if api_key:
        params["api_key"] = api_key
    url = EUTILS + endpoint + "?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        wait = min_interval - (time.time() - last_request)
        if wait > 0:
            time.sleep(wait)
        last_request = time.time()
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            # Retry when rate limited or when NCBI has a server error
            if e.code not in (429, 500, 502, 503) or attempt == 2:
                raise FetchError(f"NCBI request failed: HTTP {e.code}")
        except urllib.error.URLError as e:
            if attempt == 2:
                raise FetchError(f"could not reach NCBI: {e.reason}")
        time.sleep(1 + attempt)

def search(name, field):
    term = f'"{name}"[{field}]'
    result = json.loads(ncbi_get("esearch.fcgi", {"term": term, "retmode": "json"}))
    return result["esearchresult"]["idlist"]

def fetch_taxa(ids):
    root = ET.fromstring(ncbi_get("efetch.fcgi", {"id": ",".join(ids), "retmode": "xml"}))
    return root.findall("Taxon")

def find_taxid(name):
    ids = search(name, "Scientific Name")
    if len(ids) == 0:
        # Fall back to synonyms and common names
        ids = search(name, "All Names")
    if len(ids) == 0:
        raise FetchError(f"'{name}' was not found in NCBI Taxonomy")
    if len(ids) > 1:
        names = [f"{taxon.findtext('ScientificName')} ({taxon.findtext('Rank')}, taxid {taxon.findtext('TaxId')})"
                 for taxon in fetch_taxa(ids)]
        raise FetchError(f"'{name}' matches {len(ids)} taxa: " + "; ".join(names) + ". Use the exact scientific name.")
    return ids[0]

def fetch_taxon(taxid):
    # Returns the lineage as (name, rank) pairs and the taxon's common names,
    # GenBank's preferred common name first
    taxon = fetch_taxa([taxid])[0]
    lineage = [(t.findtext("ScientificName"), t.findtext("Rank")) for t in taxon.find("LineageEx")]
    lineage.append((taxon.findtext("ScientificName"), taxon.findtext("Rank")))
    lineage = [(name, rank) for name, rank in lineage if name != "cellular organisms"]
    common_names = []
    other_names = taxon.find("OtherNames")
    if other_names is not None:
        for tag in ("GenbankCommonName", "CommonName"):
            common_names += [e.text for e in other_names.findall(tag) if e.text]
    return lineage, common_names

def read_existing():
    # spellings maps lowercased names to how they are already written in the taxonomy
    # files, so NCBI's lowercase clade names (e.g. "eudicotyledons") join the existing
    # nodes. leaves maps each file's last entry to that file, to catch duplicates.
    spellings = {}
    leaves = {}
    for filename in sorted(os.listdir(taxonomy_dir)):
        if not filename.endswith(".txt"):
            continue
        name = ''
        with open(os.path.join(taxonomy_dir, filename), 'r') as file:
            for line in file:
                if line.strip() == '':
                    continue
                name = line.partition(';')[0].strip()
                spellings.setdefault(name.lower(), name)
        if name != '':
            leaves[name.lower()] = filename
    return spellings, leaves

def format_lineage(lineage, spellings):
    lines = []
    for i, (name, rank) in enumerate(lineage):
        name = spellings.get(name.lower(), name[0].upper() + name[1:])
        code = RANK_CODES.get(rank, '')
        if i == len(lineage) - 1 and code == '':
            # An unranked leaf (subspecies, variety) is written without ';'
            lines.append(name)
        else:
            lines.append(name + "; " + code)
    return "\n".join(lines)

def to_filename(common_name):
    # "American lobster" -> "american_lobster.txt"
    return re.sub(r"[^a-z0-9]+", "_", common_name.lower()).strip("_") + ".txt"

def parse_request(arg):
    # "apple=Malus domestica" names the file; a bare name gets its file name from
    # the common name once the organism is looked up
    filename, sep, name = arg.partition('=')
    if not sep:
        return arg.strip(), None
    return name.strip(), filename.strip()

def clean_filename(filename):
    # Lowercase with underscores, and never a path outside taxonomy_files/
    stem = filename[:-4] if filename.lower().endswith(".txt") else filename
    if to_filename(stem) == ".txt":
        raise FetchError(f"'{filename}' is not a usable file name")
    return to_filename(stem)

def choose_filename(name, ncbi_name, common_names):
    # A common name the user typed wins over NCBI's preferred one
    for common_name in common_names:
        if common_name.lower() == name.lower():
            return to_filename(name)
    if len(common_names) == 0:
        raise FetchError(f"NCBI has no common name for '{ncbi_name}'; give a file name, e.g. "
                         f"my_food=\"{ncbi_name}\"")
    return to_filename(common_names[0])

def prepare(name, filename=None, force=False):
    # Looks the organism up and returns what would be written, without writing it:
    # {"filename", "text", "ncbi_name", "taxid", "note"}
    spellings, leaves = read_existing()
    if filename is not None:
        filename = clean_filename(filename)
    taxid = find_taxid(name)
    lineage, common_names = fetch_taxon(taxid)
    ncbi_name, leaf_rank = lineage[-1]
    if lineage[0][0] != ROOT:
        raise FetchError(f"'{ncbi_name}' is not a eukaryote (lineage starts at '{lineage[0][0]}')")
    if leaf_rank not in LEAF_RANKS:
        raise FetchError(f"'{ncbi_name}' has rank '{leaf_rank}'; only species, subspecies and variety are tracked")
    note = f"'{name}' is listed in NCBI as '{ncbi_name}'" if ncbi_name != name else None
    duplicate = leaves.get(ncbi_name.lower())
    if duplicate is not None and duplicate != filename and not force:
        raise FetchError(f"'{ncbi_name}' is already in {duplicate} (use --force to add it anyway)")
    if filename is None:
        filename = choose_filename(name, ncbi_name, common_names)
    return {"filename": filename, "text": format_lineage(lineage, spellings),
            "ncbi_name": ncbi_name, "taxid": taxid, "note": note}

def save(filename, text, force=False):
    filename = clean_filename(filename)
    path = os.path.join(taxonomy_dir, filename)
    if os.path.exists(path) and not force:
        raise FetchError(f"{filename} already exists (use --force to overwrite)")
    with open(path, 'w') as f:
        f.write(text)
    return filename

def process(arg, args):
    name, filename = parse_request(arg)
    result = prepare(name, filename, args.force)
    if result["note"]:
        print("note: " + result["note"])
    if args.dry_run:
        print(f"== {result['filename']} (taxid {result['taxid']})\n{result['text']}")
        return
    save(result["filename"], result["text"], args.force)
    print(f"wrote {result['filename']} ({result['ncbi_name']}, taxid {result['taxid']})")

def main():
    parser = argparse.ArgumentParser(description="Fetch lineages from NCBI Taxonomy into taxonomy_files/.")
    parser.add_argument("names", nargs='+', metavar="[FILE=]NAME",
                        help="scientific or common name, optionally prefixed with a file name, e.g. "
                             "apple=\"Malus domestica\"; otherwise the file is named after the common name")
    parser.add_argument("--force", action="store_true", help="overwrite existing files and allow organisms already in another file")
    parser.add_argument("--dry-run", action="store_true", help="print the files instead of writing them")
    parser.add_argument("--build", action="store_true", help="run make_tree.py afterwards")
    args = parser.parse_args()

    failed = 0
    for arg in args.names:
        try:
            process(arg, args)
        except FetchError as e:
            print(f"Error: {e}", file=sys.stderr)
            failed += 1

    if args.build and not args.dry_run and failed < len(args.names):
        subprocess.run([sys.executable, os.path.join(script_dir, "make_tree.py")], check=True)
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
