// Food Taxonomy website. Everything is built with the DOM API (no innerHTML), so
// names from NCBI or the taxonomy files can't inject markup.

const KINGDOM_COLORS = { Metazoa: "--k-metazoa", Fungi: "--k-fungi", Viridiplantae: "--k-viridiplantae" };

let treeData = null;

// ---------- helpers ----------

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "style") node.setAttribute("style", value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

async function api(path, body) {
  // The static copy made by export_site.py has its data built in and no server
  if (window.STATIC_DATA) {
    const data = window.STATIC_DATA[path.split("?")[0]];
    if (!data) throw new Error("not available in this static copy of the site");
    return data;
  }
  const options = { headers: {} };
  if (body !== undefined) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function banner(kind, ...content) {
  return el("div", { class: `banner ${kind}`, role: kind === "error" ? "alert" : "status" }, ...content);
}

function kingdomVar(name) {
  return `var(${KINGDOM_COLORS[name] || "--k-other"})`;
}

function foodName(filename) {
  return filename.replace(/\.txt$/, "").replace(/_/g, " ");
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

// Text with every case-insensitive match of query wrapped in <mark>
function highlight(text, query) {
  if (!query) return [text];
  const parts = [];
  const lower = text.toLowerCase();
  let start = 0;
  for (let i = lower.indexOf(query); i !== -1; i = lower.indexOf(query, start)) {
    parts.push(text.slice(start, i), el("mark", {}, text.slice(i, i + query.length)));
    start = i + query.length;
  }
  parts.push(text.slice(start));
  return parts;
}

// ---------- tabs ----------

function showTab(name) {
  for (const button of document.querySelectorAll(".tabs button")) {
    const selected = button.dataset.tab === name;
    button.setAttribute("aria-selected", selected);
    document.getElementById(`tab-${button.dataset.tab}`).hidden = !selected;
  }
  if (name === "stats") { loadStats(); loadCoverage(); }
  if (name === "cladogram") loadCladogram();
  if (name === "relatives" && treeData) fillRelativesOptions();
}

for (const button of document.querySelectorAll(".tabs button")) {
  button.addEventListener("click", () => {
    history.replaceState(null, "", `${location.search}#${button.dataset.tab}`);
    showTab(button.dataset.tab);
  });
}

// ---------- tree ----------

// Organisms below each node, and which kingdom it belongs to
function annotate(node, kingdom) {
  if (node.code === "K") kingdom = node.name;
  node.kingdom = kingdom;
  node.leaves = node.eaten || node.children.length === 0 ? 1 : 0;
  for (const child of node.children) node.leaves += annotate(child, kingdom);
  return node.leaves;
}

// The tree with unranked clades removed (leaves stay, even if unranked)
function majorOnly(node) {
  const children = [];
  const collect = (parent) => {
    for (const child of parent.children) {
      if (child.code || child.children.length === 0 || child.eaten) children.push(majorOnly(child));
      else collect(child);
    }
  };
  collect(node);
  return { ...node, children };
}

// Does the node or anything below it match the search?
function matches(node, query, files) {
  if (!query) return true;
  return selfMatches(node, query, files) || node.children.some((child) => matches(child, query, files));
}

// Matches the scientific name, its meaning ("four-legged") or a food name
function selfMatches(node, query, files) {
  const own = [node.name, node.meaning || "", ...(files[node.name] || []).map(foodName)];
  return own.some((text) => text.toLowerCase().includes(query));
}

// The food names and Remove buttons for an eaten node (one per taxonomy file)
function foodParts(node, query, files) {
  const nodeFiles = files[node.name] || [];
  const foods = nodeFiles.map(foodName).join(", ");
  return [
    foods ? el("span", { class: "food" }, highlight(foods, query)) : null,
    nodeFiles.map((filename) => el("button", {
      type: "button", class: "remove",
      title: `Remove ${filename}`, "aria-label": `Remove ${foodName(filename)} (${node.name})`,
      onclick: (event) => { event.preventDefault(); removeFile(filename, node.name); },
    }, nodeFiles.length > 1 ? `Remove ${foodName(filename)}` : "Remove")),
  ];
}

function renderNode(node, query, files, showAll) {
  const style = node.kingdom ? `--kingdom: ${kingdomVar(node.kingdom)}` : null;
  if (node.children.length === 0) {
    return el("li", { class: "leaf", style },
      el("span", { class: "sci" }, highlight(node.name, query)),
      foodParts(node, query, files));
  }
  const showChildren = showAll || (query && selfMatches(node, query, files));
  const children = node.children.filter((child) => showChildren || matches(child, query, files));
  const rankName = node.code ? treeData.rankNames[node.code] : null;
  return el("li", { style },
    el("details", { open: true },
      el("summary", {},
        node.code === "K" ? el("span", { class: "kdot", "aria-hidden": "true" }) : null,
        el("span", { class: node.code ? "name" : "" }, highlight(node.name, query)),
        node.meaning ? el("span", { class: "meaning" }, "(", highlight(node.meaning, query), ")") : null,
        rankName ? el("span", { class: "rank" }, rankName) : null,
        // A species eaten itself, with a variety or subspecies below it (onion above shallot)
        node.eaten ? foodParts(node, query, files) : null,
        el("span", { class: "count" }, plural(node.leaves, "organism", "organisms"))),
      el("ul", {}, children.map((child) => renderNode(child, query, files, showChildren)))));
}

function renderTree() {
  if (!treeData) return;
  const query = document.getElementById("tree-search").value.trim().toLowerCase();
  const major = document.getElementById("tree-major").checked;
  const root = major ? majorOnly(treeData.tree) : treeData.tree;
  annotate(root, null);
  const container = document.getElementById("tree");
  // Every clade gets a row, so the full tree is much deeper; it uses a narrower indent
  container.classList.toggle("full", !major);
  if (query && !matches(root, query, treeData.files)) {
    container.replaceChildren(el("p", { class: "muted" }, `Nothing matches “${query}”.`));
    return;
  }
  container.replaceChildren(el("ul", {}, renderNode(root, query, treeData.files, !query)));
}

async function loadTree() {
  try {
    treeData = await api("/api/tree");
  } catch (error) {
    document.getElementById("tree").replaceChildren(banner("error", `Couldn't load the tree: ${error.message}`));
    return;
  }
  annotate(treeData.tree, null);
  const kingdoms = new Set();
  const walk = (node) => { if (node.code === "K") kingdoms.add(node.name); node.children.forEach(walk); };
  walk(treeData.tree);
  document.getElementById("tree-summary").textContent =
    `${plural(treeData.tree.leaves, "organism", "organisms")} across ${plural(kingdoms.size, "kingdom", "kingdoms")}. ` +
    "Dot colors mark each kingdom.";

  const warnings = document.getElementById("warnings");
  warnings.hidden = treeData.warnings.length === 0;
  warnings.replaceChildren("Possible mistakes in the taxonomy files:",
    el("ul", {}, treeData.warnings.map((warning) => el("li", {}, warning))));

  // Ranked names (kingdom to order) as suggestions for the gaps form
  const options = [];
  const collect = (node) => {
    if ("KPCOFG".includes(node.code) && node.code) options.push(node.name);
    node.children.forEach(collect);
  };
  collect(treeData.tree);
  document.getElementById("gaps-taxa").replaceChildren(...options.sort().map((name) => el("option", { value: name })));
  renderTree();
  fillRelativesOptions();
}

const treeStatus = document.getElementById("tree-status");

async function removeFile(filename, name) {
  if (!confirm(`Remove ${foodName(filename)} (${name})?\n\nThis deletes taxonomy_files/${filename}. You can undo it right after.`)) return;
  try {
    const removed = await api("/api/remove", { filename });
    const undo = el("button", { type: "button", class: "secondary" }, "Undo");
    undo.addEventListener("click", async () => {
      undo.disabled = true;
      try {
        await api("/api/save", { filename: removed.filename, text: removed.text });
        treeStatus.replaceChildren(banner("ok", `Restored taxonomy_files/${removed.filename}.`));
        cladogramKey = null;
        await loadTree();
      } catch (error) {
        treeStatus.replaceChildren(banner("error", `Couldn't restore ${removed.filename}: ${error.message}`));
      }
    });
    treeStatus.replaceChildren(banner("ok",
      `Removed taxonomy_files/${removed.filename} and rebuilt taxon_tree.txt. Commit the change from VS Code when you're ready. `,
      undo));
    cladogramKey = null;
    await loadTree();
  } catch (error) {
    treeStatus.replaceChildren(banner("error", error.message));
  }
}

document.getElementById("tree-search").addEventListener("input", renderTree);
document.getElementById("tree-major").addEventListener("change", renderTree);
document.getElementById("tree-expand").addEventListener("click", () => {
  document.querySelectorAll("#tree details").forEach((details) => { details.open = true; });
});
document.getElementById("tree-collapse").addEventListener("click", () => {
  document.querySelectorAll("#tree details").forEach((details, i) => { details.open = i === 0; });
});

// ---------- cladogram ----------

let cladogramKey = null;

function loadCladogram() {
  const major = document.getElementById("clado-major").checked ? 1 : 0;
  const key = `${major}:${treeData ? treeData.tree.leaves : ""}`;
  if (key === cladogramKey) return;
  cladogramKey = key;
  const src = window.STATIC_DATA ? (major ? "cladogram_major.svg" : "cladogram_full.svg")
    : `/api/cladogram.svg?major=${major}&v=${Date.now()}`;
  const img = document.getElementById("clado-img");
  img.parentElement.classList.toggle("natural", !major);
  const status = document.getElementById("clado-status");
  status.hidden = false;
  status.textContent = "Drawing…";
  img.onload = () => { status.hidden = true; };
  img.onerror = () => { status.textContent = "Couldn't draw the cladogram (is matplotlib installed?)."; };
  img.src = src;
  document.getElementById("clado-open").href = src;
}

document.getElementById("clado-major").addEventListener("change", loadCladogram);

// ---------- stats ----------

async function loadStats() {
  let stats;
  try {
    stats = await api("/api/stats");
  } catch (error) {
    document.getElementById("stats-tiles").replaceChildren(banner("error", `Couldn't load stats: ${error.message}`));
    return;
  }
  const totals = stats.totals;
  const tiles = [["Organisms", totals.organisms || 0], ["Species", totals.species || 0]];
  if (totals.subspecies) tiles.push(["Subspecies", totals.subspecies]);
  if (totals.variety) tiles.push([totals.variety === 1 ? "Variety" : "Varieties", totals.variety]);
  tiles.push(["Families", totals.F || 0], ["Orders", totals.O || 0]);
  document.getElementById("stats-tiles").replaceChildren(...tiles.map(([label, value]) =>
    el("div", { class: "tile" }, el("div", { class: "value" }, value), el("div", { class: "label" }, label))));

  document.getElementById("stats-ranks").replaceChildren(
    el("thead", {}, el("tr", {}, el("th", {}, "Rank"), el("th", { class: "num" }, "Count"))),
    el("tbody", {}, stats.ranks.map((code) =>
      el("tr", {}, el("td", {}, stats.rankPlurals[code]), el("td", { class: "num" }, totals[code] || 0)))));

  const ranks = stats.ranks.slice(1);
  const kingdoms = Object.entries(stats.kingdoms).sort((a, b) => b[1].organisms - a[1].organisms || a[0].localeCompare(b[0]));
  document.getElementById("stats-kingdoms").replaceChildren(
    el("thead", {}, el("tr", {}, el("th", {}, "Kingdom"),
      ranks.map((code) => el("th", { class: "num" }, stats.rankPlurals[code])), el("th", { class: "num" }, "Organisms"))),
    el("tbody", {}, kingdoms.map(([name, counts]) =>
      el("tr", {},
        el("td", {}, el("span", { class: "dot", style: `--kingdom: ${kingdomVar(name)}` }), name),
        ranks.map((code) => el("td", { class: "num" }, counts[code] || 0)),
        el("td", { class: "num" }, counts.organisms)))));
}

// ---------- add organism ----------

const addResult = document.getElementById("add-result");

document.getElementById("add-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter || event.target.querySelector("button");
  const force = document.getElementById("add-force").checked;
  button.disabled = true;
  addResult.replaceChildren(el("p", { class: "muted" }, "Asking NCBI…"));
  try {
    const result = await api("/api/lookup", {
      name: document.getElementById("add-name").value,
      filename: document.getElementById("add-file").value,
      force,
    });
    showPreview(result, force);
  } catch (error) {
    addResult.replaceChildren(banner("error", error.message));
  } finally {
    button.disabled = false;
  }
});

function showPreview(result, force) {
  const fileInput = el("input", { value: result.filename.replace(/\.txt$/, ""), "aria-label": "File name" });
  const ncbiLink = `https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=${encodeURIComponent(result.taxid)}`;
  const save = el("button", { type: "button" }, "Save");
  const cancel = el("button", { type: "button", class: "secondary", onclick: () => addResult.replaceChildren() }, "Cancel");
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      const saved = await api("/api/save", { filename: fileInput.value, text: result.text, force });
      const done = [banner("ok", `Saved taxonomy_files/${saved.filename} and rebuilt taxon_tree.txt. Commit it from VS Code when you're ready.`)];
      if (saved.warnings.length) done.push(banner("warn", "Possible mistakes:", el("ul", {}, saved.warnings.map((w) => el("li", {}, w)))));
      addResult.replaceChildren(...done);
      document.getElementById("add-form").reset();
      cladogramKey = null;
      await loadTree();
    } catch (error) {
      addResult.append(banner("error", error.message));
      save.disabled = false;
    }
  });
  addResult.replaceChildren(el("div", { class: "card" },
    el("p", {}, el("strong", {}, el("i", {}, result.ncbi_name)), " · ",
      el("a", { href: ncbiLink, target: "_blank", rel: "noopener" }, `NCBI taxid ${result.taxid}`)),
    result.note ? el("p", { class: "muted" }, result.note) : null,
    el("label", { class: "form" }, "Save as (in taxonomy_files/, .txt is added)", fileInput),
    el("pre", {}, result.text),
    el("div", { class: "actions" }, save, cancel)));
}

// ---------- gaps ----------

const gapsResult = document.getElementById("gaps-result");

document.getElementById("gaps-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter || event.target.querySelector("button");
  const params = new URLSearchParams({
    taxon: document.getElementById("gaps-taxon").value,
    rank: document.getElementById("gaps-rank").value,
    refresh: document.getElementById("gaps-refresh").checked ? "1" : "0",
    all: document.getElementById("gaps-all").checked ? "1" : "0",
  });
  button.disabled = true;
  gapsResult.replaceChildren(el("p", { class: "muted" }, "Looking up NCBI (the first lookup of a group can take a few seconds)…"));
  try {
    const report = await api(`/api/gaps?${params}`);
    const speciesLevel = report.rank === "species";
    const describe = (group, missing) => el("li", {}, el("i", {}, group.name),
      group.common ? el("span", { class: "muted" }, ` (${group.common})`) : null,
      // At the species level each line is a food that can be added directly
      missing && speciesLevel ? addButton(group.name, group.common) : null,
      group.examples && group.examples.length
        ? el("span", {}, ": e.g. ", group.examples.map((example, i) => [
            i ? ", " : "", example.food, missing ? addButton(example.species, example.food) : null]))
        : null);
    const missingTitle = report.filtered ? "Not eaten yet, with common foods" : "Not eaten yet";
    gapsResult.replaceChildren(el("div", { class: "card" },
      el("h2", { style: "margin-top:0" }, `${report.name}: ${report.have.length} of ${report.total} ${report.plural} eaten`),
      el("div", { class: `gap-lists${report.missing.length > 20 ? " cols" : ""}` },
        el("div", {}, el("h3", {}, `Eaten (${report.have.length})`), el("ul", {}, report.have.map((g) => describe(g, false)))),
        el("div", {}, el("h3", {}, `${missingTitle} (${report.missing.length})`), el("ul", {}, report.missing.map((g) => describe(g, true))))),
      report.hidden
        ? el("p", { class: "muted" }, `${report.hidden} more ${report.plural} with no common foods aren't shown. ` +
            "Tick “Include groups with no common foods” to list them.")
        : null,
      report.unknown.length
        ? el("p", { class: "muted" }, `In the tree but not listed by NCBI as ${report.plural} of ${report.name}: ${report.unknown.join(", ")}`)
        : null));
  } catch (error) {
    gapsResult.replaceChildren(banner("error", error.message));
  } finally {
    button.disabled = false;
  }
});

// An "Add" button that looks the species up on NCBI and saves it in one step,
// using the food name as the file name
function addButton(species, food) {
  const button = el("button", { type: "button", class: "add-inline", title: `Add ${food} (${species}) to the tree` }, "Add");
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "Adding…";
    try {
      const added = await api("/api/add", { name: species, filename: food });
      button.replaceWith(el("span", { class: "added" }, `✓ added as ${added.filename}`));
      cladogramKey = null;
      loadTree();
    } catch (error) {
      button.replaceWith(el("span", { class: "add-error" }, `✗ ${error.message}`));
    }
  });
  return button;
}

// ---------- suggestions ----------

const RANK_LABELS = { kingdom: "kingdom", phylum: "phylum", class: "class", order: "order", family: "family",
  genus: "genus", species: "species" };

document.getElementById("suggest-button").addEventListener("click", async (event) => {
  const button = event.target;
  const taxon = document.getElementById("gaps-taxon").value.trim();
  const output = document.getElementById("suggest-result");
  button.disabled = true;
  output.replaceChildren(el("p", { class: "muted" }, "Ranking common foods…"));
  try {
    const result = await api(`/api/suggest?${new URLSearchParams({ taxon, limit: "30" })}`);
    if (!result.suggestions.length) {
      output.replaceChildren(el("p", { class: "muted" }, "You've eaten every common food here."));
      return;
    }
    output.replaceChildren(el("div", { class: "card" },
      el("h2", { style: "margin-top:0" }, `Foods that would add the most new branches${taxon ? ` in ${taxon}` : ""}`),
      el("p", { class: "muted" }, "Ranked by the highest new rank each would add (a new class beats a new genus), then by how many new clades."),
      el("ol", { class: "suggestions" }, result.suggestions.map((s) => el("li", {},
        el("strong", {}, s.food), " ", el("i", { class: "muted" }, s.species), addButton(s.species, s.food),
        el("div", { class: "chips" },
          Object.entries(s.new_major).map(([rank, name]) => el("span", { class: "chip" }, `new ${RANK_LABELS[rank]}: ${name}`)),
          el("span", { class: "muted" }, ` ${plural(s.new.length, "new clade", "new clades")} in all`)))))));
  } catch (error) {
    output.replaceChildren(banner("error", error.message));
  } finally {
    button.disabled = false;
  }
});

// ---------- relatives ----------

// Every organism as {name, foods, path: [nodes from the root]}
function organisms() {
  const found = [];
  const walk = (node, path) => {
    const here = [...path, node];
    if (node.eaten || node.children.length === 0) {
      found.push({ name: node.name, foods: (treeData.files[node.name] || []).map(foodName), path: here });
    }
    node.children.forEach((child) => walk(child, here));
  };
  walk(treeData.tree, []);
  return found;
}

function organismLabel(organism) {
  return organism.foods.length ? `${organism.foods.join(", ")} (${organism.name})` : organism.name;
}

function findOrganism(text) {
  const query = text.trim().toLowerCase();
  if (!query) return null;
  const all = organisms();
  return all.find((o) => organismLabel(o).toLowerCase() === query)
    || all.find((o) => o.foods.some((f) => f.toLowerCase() === query) || o.name.toLowerCase() === query)
    || all.find((o) => organismLabel(o).toLowerCase().includes(query));
}

// The deepest node two organisms share, and the index of it in their paths
function sharedAncestor(a, b) {
  let i = 0;
  while (i < a.path.length && i < b.path.length && a.path[i] === b.path[i]) i++;
  return i - 1;
}

function cladeLabel(node) {
  // Organisms without a formal rank (subspecies, varieties) get no rank tag
  const rank = node.code ? treeData.rankNames[node.code].toLowerCase() : node.eaten ? "" : "clade";
  return [el("strong", {}, node.name), node.meaning ? ` (${node.meaning})` : "", rank ? el("span", { class: "rank" }, rank) : null];
}

function renderRelatives() {
  const output = document.getElementById("relatives-result");
  if (!treeData) return;
  const a = findOrganism(document.getElementById("rel-a").value);
  const b = findOrganism(document.getElementById("rel-b").value);
  const typed = document.getElementById("rel-a").value.trim();
  if (!a) {
    output.replaceChildren(el("p", { class: "muted" }, typed
      ? `Nothing in your tree matches “${typed}”. Pick a food or organism from the suggestions.`
      : "Pick a food or organism from your tree."));
    return;
  }
  const parts = [];
  if (b && b.name !== a.name) {
    const at = sharedAncestor(a, b);
    const ancestor = a.path[at];
    parts.push(el("div", { class: "card" },
      el("h2", { style: "margin-top:0" }, `${organismLabel(a)} and ${organismLabel(b)}`),
      el("p", {}, "Closest shared ancestor: ", cladeLabel(ancestor)),
      el("div", { class: "columns two" },
        [a, b].map((o) => el("div", {}, el("h3", {}, `From there to ${o.foods[0] || o.name}`),
          el("ol", { class: "lineage" }, o.path.slice(at + 1).map((node) => el("li", {}, cladeLabel(node)))))))));
  }
  // The organisms that share the deepest ancestor with a
  const others = organisms().filter((o) => o.name !== a.name);
  const best = Math.max(...others.map((o) => sharedAncestor(a, o)));
  const closest = others.filter((o) => sharedAncestor(a, o) === best);
  parts.push(el("div", { class: "card" },
    el("h2", { style: "margin-top:0" }, `Closest relatives of ${organismLabel(a)} in your tree`),
    el("p", {}, "They share: ", cladeLabel(a.path[best])),
    el("ul", {}, closest.map((o) => el("li", {}, organismLabel(o))))));
  output.replaceChildren(...parts);
  const params = new URLSearchParams({ a: document.getElementById("rel-a").value, b: document.getElementById("rel-b").value });
  history.replaceState(null, "", `${location.search}#relatives?${params}`);
}

function fillRelativesOptions() {
  const options = organisms().map((o) => el("option", { value: organismLabel(o) }));
  document.getElementById("rel-options").replaceChildren(...options);
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  if (params.get("a")) document.getElementById("rel-a").value = params.get("a");
  if (params.get("b")) document.getElementById("rel-b").value = params.get("b");
  renderRelatives();
}

document.getElementById("relatives-form").addEventListener("submit", (event) => {
  event.preventDefault();
  renderRelatives();
});

// ---------- coverage sunburst ----------

const COVERAGE_STEPS = 6;
const RING_NAMES = ["Kingdom", "Phylum", "Class", "Order"];

function coverageStep(group) {
  // 0..5: share of the group's foods eaten, in six bins
  return Math.min(COVERAGE_STEPS - 1, Math.floor((group.eaten / group.total) * COVERAGE_STEPS));
}

function arcPath(r0, r1, a0, a1) {
  const point = (r, a) => `${(r * Math.sin(a)).toFixed(2)},${(-r * Math.cos(a)).toFixed(2)}`;
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${point(r1, a0)}A${r1},${r1} 0 ${large} 1 ${point(r1, a1)}L${point(r0, a1)}A${r0},${r0} 0 ${large} 0 ${point(r0, a0)}Z`;
}

function renderSunburst(top) {
  const svgNS = "http://www.w3.org/2000/svg";
  const size = 520, center = 70, ring = (size / 2 - center) / RING_NAMES.length;
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `${-size / 2} ${-size / 2} ${size} ${size}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Sunburst of ${top.total} common and eaten foods by kingdom, phylum, class and order, shaded by share eaten`);
  const tooltip = document.getElementById("sunburst-tip");
  const show = (event, group, path) => {
    tooltip.hidden = false;
    tooltip.replaceChildren(el("strong", {}, group.name), el("span", { class: "muted" }, ` ${group.rank}`),
      el("div", {}, `${group.eaten} of ${group.total} eaten (${Math.round((100 * group.eaten) / group.total)}%)`),
      path.length > 1 ? el("div", { class: "muted" }, path.slice(0, -1).join(" › ")) : null);
    const box = svg.parentElement.getBoundingClientRect();
    tooltip.style.left = `${Math.min(event.clientX - box.left + 14, box.width - 220)}px`;
    tooltip.style.top = `${event.clientY - box.top + 14}px`;
  };
  const draw = (group, depth, a0, a1, path) => {
    if (depth > 0) {
      const shape = document.createElementNS(svgNS, "path");
      shape.setAttribute("d", arcPath(center + (depth - 1) * ring, center + depth * ring, a0, a1));
      shape.setAttribute("class", `seg step-${coverageStep(group)}`);
      shape.addEventListener("mousemove", (event) => show(event, group, path));
      shape.addEventListener("mouseleave", () => { tooltip.hidden = true; });
      svg.append(shape);
      // Label segments with room for the name
      const middle = (a0 + a1) / 2, radius = center + (depth - 0.5) * ring;
      if ((a1 - a0) * radius > group.name.length * 6.2 && ring > 20) {
        const label = document.createElementNS(svgNS, "text");
        // Text runs along the ring, flipped on the lower half so it's never upside down
        let rotate = (middle * 180) / Math.PI;
        if (rotate > 90 && rotate < 270) rotate += 180;
        label.setAttribute("transform", `translate(${(radius * Math.sin(middle)).toFixed(1)},${(-radius * Math.cos(middle)).toFixed(1)}) rotate(${rotate.toFixed(1)})`);
        label.setAttribute("class", `seg-label step-${coverageStep(group)}`);
        label.textContent = group.name;
        svg.append(label);
      }
    }
    if (depth < RING_NAMES.length) {
      let start = a0;
      for (const child of group.children) {
        const end = start + ((a1 - a0) * child.total) / group.total;
        draw(child, depth + 1, start, end, [...path, child.name]);
        start = end;
      }
    }
  };
  draw(top, 0, 0, 2 * Math.PI, []);
  const middle = document.createElementNS(svgNS, "text");
  middle.setAttribute("class", "sun-center");
  middle.setAttribute("text-anchor", "middle");
  middle.innerHTML = "";
  for (const [dy, text] of [[-6, `${Math.round((100 * top.eaten) / top.total)}%`], [14, "eaten"]]) {
    const line = document.createElementNS(svgNS, "tspan");
    line.setAttribute("x", "0");
    line.setAttribute("y", String(dy));
    line.textContent = text;
    middle.append(line);
  }
  svg.append(middle);
  return svg;
}

async function loadCoverage() {
  const holder = document.getElementById("sunburst");
  try {
    const top = await api("/api/coverage");
    const legend = el("div", { class: "legend" }, el("span", { class: "muted" }, "Share of foods eaten: "),
      Array.from({ length: COVERAGE_STEPS }, (_, i) => el("span", { class: "legend-item" },
        el("span", { class: `swatch step-${i}` }),
        `${Math.round((100 * i) / COVERAGE_STEPS)}–${Math.round((100 * (i + 1)) / COVERAGE_STEPS)}%`)));
    holder.replaceChildren(
      el("p", { class: "muted" }, `Rings from the inside out: ${RING_NAMES.join(", ")}. Each slice is sized by how many common foods `
        + "(from the common-foods list, plus anything else you've eaten) it holds, and shaded by how many of them you've eaten. Hover for details."),
      legend, renderSunburst(top));
  } catch (error) {
    holder.replaceChildren(banner("error", `Couldn't load coverage: ${error.message}`));
  }
}

// ---------- start ----------

const TABS = ["tree", "cladogram", "stats", "relatives", "add", "gaps"];
if (window.STATIC_DATA) document.body.classList.add("static");
const startTab = location.hash.slice(1).split("?")[0];
showTab(TABS.includes(startTab) ? startTab : "tree");
loadTree();
// Links like #gaps?taxon=Rosaceae&rank=species (and &suggest=1) run those reports on load
if (startTab === "gaps") {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  if (params.get("taxon")) document.getElementById("gaps-taxon").value = params.get("taxon");
  if (params.get("rank")) document.getElementById("gaps-rank").value = params.get("rank");
  if (params.get("suggest")) document.getElementById("suggest-button").click();
  if (params.get("taxon")) document.getElementById("gaps-form").requestSubmit();
}
