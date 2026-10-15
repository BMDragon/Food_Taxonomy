# Lists the groups within a taxon that are not in the tree yet, using NCBI Taxonomy

import argparse
import json
import os
import sys

import fetch_lineage
import make_tree

# Coarse ranks only: NCBI doesn't know what's edible, so finer gaps are mostly noise
GAP_RANKS = ["kingdom", "phylum", "class", "order", "family"]
RANK_CODES = {"kingdom": "K", "phylum": "P", "class": "C", "order": "O", "family": "F"}
PLURALS = {"kingdom": "kingdoms", "phylum": "phyla", "class": "classes", "order": "orders", "family": "families"}
BATCH = 200

cache_dir = os.path.join(make_tree.script_dir, ".ncbi_cache")
# Commonly eaten species with their NCBI lineages ("food<TAB>species<TAB>lineage; ..."),
# used to show only gaps that contain real foods. Lineages are filled by update_common_foods.py.
common_foods_path = os.path.join(make_tree.script_dir, "common_foods.tsv")
EXAMPLES = 3

def load_common_foods():
    # Returns [(food, species, [lineage names])] for entries whose lineage is filled in
    foods = []
    if os.path.exists(common_foods_path):
        with open(common_foods_path, 'r') as f:
            for line in f:
                if not line.strip() or line.startswith('#'):
                    continue
                parts = line.rstrip('\n').split('\t')
                if len(parts) >= 3 and parts[2].strip():
                    foods.append((parts[0], parts[1], [name.strip() for name in parts[2].split(';')]))
    return foods

def foods_by_taxon(foods):
    # Maps each lowercased taxon name to the foods inside it
    found = {}
    for food, species, lineage in foods:
        for name in lineage:
            found.setdefault(name.lower(), [])
            if food not in found[name.lower()]:
                found[name.lower()].append(food)
    return found

def ncbi_summaries(ids):
    summaries = []
    for start in range(0, len(ids), BATCH):
        params = {"id": ",".join(ids[start:start + BATCH]), "retmode": "json"}
        result = json.loads(fetch_lineage.ncbi_get("esummary.fcgi", params))["result"]
        summaries += [result[uid] for uid in result["uids"]]
    return summaries

def ncbi_taxon(name, refresh):
    # Returns (taxid, scientific name, rank), cached on disk
    cache_path = os.path.join(cache_dir, "taxa.json")
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            cache = json.load(f)
    if refresh or name.lower() not in cache:
        taxid = fetch_lineage.find_taxid(name)
        summary = ncbi_summaries([taxid])[0]
        cache[name.lower()] = [taxid, summary["scientificname"], summary["rank"]]
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, 'w') as f:
            json.dump(cache, f, indent=1)
    return tuple(cache[name.lower()])

def ncbi_groups(taxid, rank, refresh):
    # All taxa of the given rank inside taxid, as {"name", "common"} dicts, cached on disk
    cache_path = os.path.join(cache_dir, f"{taxid}_{rank}.json")
    if not refresh and os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            return json.load(f)
    term = f"txid{taxid}[Subtree] AND {rank}[Rank]"
    result = json.loads(fetch_lineage.ncbi_get("esearch.fcgi", {"term": term, "retmax": 10000, "retmode": "json"}))
    ids = result["esearchresult"]["idlist"]
    groups = [{"name": s["scientificname"], "common": s.get("commonname", "")}
              for s in ncbi_summaries(ids) if s.get("rank") == rank]
    groups.sort(key=lambda group: group["name"])
    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_path, 'w') as f:
        json.dump(groups, f, indent=1)
    return groups

def eaten_groups(root, taxon, rank):
    # Names of the nodes of the given rank under every node named taxon
    code = RANK_CODES[rank]
    found = set()
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(node.children.values())
        if node.value.lower() == taxon.lower():
            below = list(node.children.values())
            while below:
                child = below.pop()
                if child.code == code:
                    found.add(child.value)
                below.extend(child.children.values())
    return found

def compare(eaten, groups):
    # Returns (eaten groups, groups not eaten yet, eaten names NCBI doesn't list at this rank)
    ncbi_names = {group["name"].lower() for group in groups}
    eaten_lower = {name.lower() for name in eaten}
    have = [group for group in groups if group["name"].lower() in eaten_lower]
    missing = [group for group in groups if group["name"].lower() not in eaten_lower]
    unknown = sorted(name for name in eaten if name.lower() not in ncbi_names)
    return have, missing, unknown

def filter_missing(missing, edible, show_all):
    # Adds example foods to each group not eaten yet, and (unless show_all) drops the
    # groups with no common foods. Returns (groups to show, number hidden).
    shown = []
    for group in missing:
        examples = edible.get(group["name"].lower(), [])
        if examples or show_all:
            shown.append(dict(group, examples=examples[:EXAMPLES]))
    return shown, len(missing) - len(shown)

def gap_report(root, taxon, rank=None, refresh=False, show_all=False):
    # Returns {"name", "rank", "groups", "have", "missing", "hidden", "filtered", "unknown"}
    # for taxon; rank defaults to the next major rank below the taxon's. "missing" only
    # lists groups containing common foods unless show_all (or no food list exists).
    taxid, name, taxon_rank = ncbi_taxon(taxon, refresh)
    if rank is None:
        if taxon_rank not in GAP_RANKS:
            raise fetch_lineage.FetchError(f"'{name}' has rank '{taxon_rank}'; choose a rank")
        index = GAP_RANKS.index(taxon_rank) + 1
        if index == len(GAP_RANKS):
            raise fetch_lineage.FetchError(f"'{name}' is a family; gaps are only listed down to families")
        rank = GAP_RANKS[index]
    elif rank not in GAP_RANKS:
        raise fetch_lineage.FetchError(f"rank must be one of: {', '.join(GAP_RANKS)}")
    elif taxon_rank in GAP_RANKS and GAP_RANKS.index(rank) <= GAP_RANKS.index(taxon_rank):
        raise fetch_lineage.FetchError(f"'{name}' is a {taxon_rank}; choose a rank below it")
    groups = ncbi_groups(taxid, rank, refresh)
    have, missing, unknown = compare(eaten_groups(root, name, rank), groups)
    foods = load_common_foods()
    filtered = bool(foods) and not show_all
    missing, hidden = filter_missing(missing, foods_by_taxon(foods), not filtered)
    return {"name": name, "rank": rank, "groups": groups, "have": have, "missing": missing,
            "hidden": hidden, "filtered": filtered, "unknown": unknown}

def describe(group):
    text = group["name"] + (f" ({group['common']})" if group["common"] else "")
    if group.get("examples"):
        text += ": e.g. " + ", ".join(group["examples"])
    return text

def main():
    parser = argparse.ArgumentParser(description="List the groups within a taxon that aren't in the tree yet.")
    parser.add_argument("taxon", help="a taxon such as Mammalia, Rosales or Metazoa")
    parser.add_argument("--rank", choices=GAP_RANKS,
                        help="rank of the groups to list (default: the next major rank below the taxon)")
    parser.add_argument("--refresh", action="store_true", help="ignore cached NCBI results")
    parser.add_argument("--all", action="store_true",
                        help="also list groups with no common foods (from common_foods.tsv)")
    args = parser.parse_args()

    try:
        root, _ = make_tree.build_tree(make_tree.taxonomy_dir)
        report = gap_report(root, args.taxon, args.rank, args.refresh, args.all)
    except (ValueError, fetch_lineage.FetchError) as e:
        sys.exit(f"Error: {e}")

    name, rank, groups = report["name"], report["rank"], report["groups"]
    have, missing, unknown = report["have"], report["missing"], report["unknown"]
    print(f"{name}: {len(have)} of {len(groups)} {PLURALS[rank]} eaten\n")
    print(f"Eaten ({len(have)}):")
    for group in have:
        print("  " + describe(group))
    label = " with common foods" if report["filtered"] else ""
    print(f"\nNot eaten yet{label} ({len(missing)}):")
    for group in missing:
        print("  " + describe(group))
    if report["hidden"]:
        print(f"\n{report['hidden']} more {PLURALS[rank]} with no common foods not shown (use --all to list them)")
    if unknown:
        print(f"\nIn the tree but not listed by NCBI as {PLURALS[rank]} of {name}: " + ", ".join(unknown))

if __name__ == "__main__":
    main()
