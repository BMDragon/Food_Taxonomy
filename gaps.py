# Lists the groups within a taxon that are not in the tree yet, using NCBI Taxonomy

import argparse
import json
import os
import sys

import fetch_lineage
import make_tree

# Kingdom to genus come from NCBI's lists of groups. "species" (species, subspecies and
# varieties) comes from common_foods.tsv instead: NCBI's species lists are mostly organisms
# nobody eats, many of them unnamed samples.
GAP_RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
RANK_CODES = {"kingdom": "K", "phylum": "P", "class": "C", "order": "O", "family": "F", "genus": "G"}
PLURALS = {"kingdom": "kingdoms", "phylum": "phyla", "class": "classes", "order": "orders", "family": "families",
           "genus": "genera", "species": "common species and varieties"}
BATCH = 200
# Larger NCBI lists (e.g. every plant genus) take too long to download; ask for a smaller group
MAX_GROUPS = 20000

cache_dir = os.path.join(make_tree.script_dir, ".ncbi_cache")
# Commonly eaten species with their NCBI lineages ("food<TAB>species<TAB>lineage; ..."),
# used to show only gaps that contain real foods. Lineages are filled by update_common_foods.py.
common_foods_path = os.path.join(make_tree.script_dir, "common_foods.tsv")
EXAMPLES = 3

def load_common_foods():
    # Returns [{"food", "species", "lineage": [names], "ranks": [NCBI ranks]}] for entries
    # whose lineage is filled in ("ranks" is empty for entries looked up before ranks were stored)
    foods = []
    if os.path.exists(common_foods_path):
        with open(common_foods_path, 'r') as f:
            for line in f:
                if not line.strip() or line.startswith('#'):
                    continue
                parts = line.rstrip('\n').split('\t')
                if len(parts) >= 3 and parts[2].strip():
                    lineage = [name.strip() for name in parts[2].split(';')]
                    ranks = [rank.strip() for rank in parts[3].split(';')] if len(parts) >= 4 else []
                    foods.append({"food": parts[0], "species": parts[1], "lineage": lineage,
                                  "ranks": ranks if len(ranks) == len(lineage) else []})
    return foods

def foods_by_taxon(foods):
    # Maps each lowercased taxon name to the foods inside it, as {"food", "species"}
    found = {}
    for entry in foods:
        for name in entry["lineage"]:
            examples = found.setdefault(name.lower(), [])
            if all(example["food"] != entry["food"] for example in examples):
                examples.append({"food": entry["food"], "species": entry["species"]})
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
    count = int(json.loads(fetch_lineage.ncbi_get("esearch.fcgi", {"term": term, "retmax": 0, "retmode": "json"}))
                ["esearchresult"]["count"])
    if count > MAX_GROUPS:
        raise fetch_lineage.FetchError(f"NCBI lists {count} {PLURALS[rank]} in this group; choose a smaller group "
                                       f"(e.g. an order or family) or a coarser rank")
    ids = []
    for start in range(0, count, 10000):
        result = json.loads(fetch_lineage.ncbi_get("esearch.fcgi", {"term": term, "retstart": start,
                                                                    "retmax": 10000, "retmode": "json"}))
        ids += result["esearchresult"]["idlist"]
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

def tree_names(root):
    names = set()
    stack = [root]
    while stack:
        node = stack.pop()
        names.add(node.value.lower())
        stack.extend(node.children.values())
    return names

def species_report(root, name):
    # The common foods (species, subspecies, varieties) inside the taxon, split into eaten
    # and not. A food counts as eaten when its taxon is in the tree: every node in the tree
    # leads to an organism eaten, so a species above an eaten subspecies counts too.
    foods = load_common_foods()
    if not foods:
        raise fetch_lineage.FetchError("species gaps need common_foods.tsv (run update_common_foods.py)")
    in_tree = tree_names(root)
    have, missing = [], []
    for food in sorted(foods, key=lambda entry: entry["species"]):
        if name.lower() not in (taxon.lower() for taxon in food["lineage"]):
            continue
        entry = {"name": food["species"], "common": food["food"]}
        (have if food["species"].lower() in in_tree else missing).append(entry)
    return {"name": name, "rank": "species", "groups": have + missing, "have": have, "missing": missing,
            "hidden": 0, "filtered": False, "unknown": []}

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
            raise fetch_lineage.FetchError(f"'{name}' is a species; gaps are only listed down to species")
        rank = GAP_RANKS[index]
    elif rank not in GAP_RANKS:
        raise fetch_lineage.FetchError(f"rank must be one of: {', '.join(GAP_RANKS)}")
    elif taxon_rank in GAP_RANKS and GAP_RANKS.index(rank) <= GAP_RANKS.index(taxon_rank):
        raise fetch_lineage.FetchError(f"'{name}' is a {taxon_rank}; choose a rank below it")
    if rank == "species":
        return species_report(root, name)
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
        text += ": e.g. " + ", ".join(example["food"] for example in group["examples"])
    return text

# Ranks in the order they nest, for judging how new a branch is; "species" also covers
# subspecies and varieties
MAJOR_RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

def suggestions(root, taxon=None, limit=None):
    # Common foods not eaten yet, ranked by how much new tree they would add: first by the
    # highest new major rank (a new class beats a new genus), then by how many new major
    # ranks, then by how many new clades in all. Returns
    # [{"food", "species", "new": [{"name", "rank"}], "new_major": {rank: name}}]
    in_tree = tree_names(root)
    results = []
    for food in load_common_foods():
        if food["species"].lower() in in_tree:
            continue
        if taxon and taxon.lower() not in (name.lower() for name in food["lineage"]):
            continue
        ranks = food["ranks"] or ["?"] * len(food["lineage"])
        new = [{"name": name, "rank": rank} for name, rank in zip(food["lineage"], ranks)
               if name.lower() not in in_tree]
        new_major = {}
        for clade in new:
            rank = "species" if clade["rank"] in ("subspecies", "varietas") else clade["rank"]
            if rank in MAJOR_RANKS and rank not in new_major:
                new_major[rank] = clade["name"]
        results.append({"food": food["food"], "species": food["species"], "new": new, "new_major": new_major})
    def key(result):
        highest = min((MAJOR_RANKS.index(rank) for rank in result["new_major"]), default=len(MAJOR_RANKS))
        return (highest, -len(result["new_major"]), -len(result["new"]), result["food"])
    results.sort(key=key)
    return results[:limit] if limit else results

def describe_suggestion(result):
    added = ", ".join(f"+1 {rank} ({name})" for rank, name in result["new_major"].items())
    count = len(result["new"])
    return f"{result['food']} ({result['species']}): {added}; {count} new clade{'' if count == 1 else 's'} in all"

COVERAGE_LEVELS = ["kingdom", "phylum", "class", "order"]
COVERAGE_CODES = {"kingdom": "K", "phylum": "P", "class": "C", "order": "O"}

def coverage(root):
    # How many common foods (plus anything else eaten) each group holds and how many of
    # them are eaten, as nested {"name", "rank", "eaten", "total", "children"} from the
    # kingdom down to the order, for the coverage sunburst
    in_tree = tree_names(root)
    items = {}
    for food in load_common_foods():
        path = {rank: name for name, rank in zip(food["lineage"], food["ranks"]) if rank in COVERAGE_LEVELS}
        items[food["species"].lower()] = (path, food["species"].lower() in in_tree)
    # Organisms eaten that aren't on the list (or are a variety of a listed species)
    stack = [(root, {}, None)]
    while stack:
        node, path, species = stack.pop()
        path = dict(path)
        for rank, code in COVERAGE_CODES.items():
            if node.code == code:
                path[rank] = node.value
        if node.code == 'S':
            species = node.value
        if node.eaten and node.value.lower() not in items and (species or "").lower() not in items:
            items[node.value.lower()] = (path, True)
        for child in node.children.values():
            stack.append((child, path, species))
    top = {"name": root.value, "rank": "", "eaten": 0, "total": 0, "children": {}}
    for path, eaten in items.values():
        group = top
        group["total"] += 1
        group["eaten"] += eaten
        for rank in COVERAGE_LEVELS:
            name = path.get(rank, f"(no {rank})")
            group = group["children"].setdefault(name, {"name": name, "rank": rank, "eaten": 0, "total": 0,
                                                        "children": {}})
            group["total"] += 1
            group["eaten"] += eaten
    def finish(group):
        group["children"] = sorted((finish(child) for child in group["children"].values()),
                                   key=lambda child: (-child["total"], child["name"]))
        return group
    return finish(top)

def main():
    parser = argparse.ArgumentParser(description="List the groups within a taxon that aren't in the tree yet.")
    parser.add_argument("taxon", nargs="?", help="a taxon such as Mammalia, Rosales or Metazoa")
    parser.add_argument("--rank", choices=GAP_RANKS,
                        help="rank of the groups to list (default: the next major rank below the taxon)")
    parser.add_argument("--refresh", action="store_true", help="ignore cached NCBI results")
    parser.add_argument("--all", action="store_true",
                        help="also list groups with no common foods (from common_foods.tsv)")
    parser.add_argument("--suggest", type=int, nargs="?", const=20, metavar="N",
                        help="instead, suggest the N common foods (default 20) that would add the most "
                             "new branches to the tree, within the taxon if one is given")
    args = parser.parse_args()

    if args.suggest is not None:
        root, _ = make_tree.build_tree(make_tree.taxonomy_dir)
        results = suggestions(root, args.taxon, args.suggest)
        where = f" in {args.taxon}" if args.taxon else ""
        print(f"Common foods{where} that would add the most new branches:\n")
        for result in results:
            print("  " + describe_suggestion(result))
        return
    if not args.taxon:
        parser.error("give a taxon, or use --suggest")

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
