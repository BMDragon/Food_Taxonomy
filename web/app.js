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
  if (name === "stats") loadStats();
  if (name === "cladogram") loadCladogram();
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
  const src = `/api/cladogram.svg?major=${major}&v=${Date.now()}`;
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
    const describe = (group) => el("li", {}, el("i", {}, group.name),
      group.common ? el("span", { class: "muted" }, ` (${group.common})`) : null,
      group.examples && group.examples.length ? el("span", {}, `: e.g. ${group.examples.join(", ")}`) : null);
    const missingTitle = report.filtered ? "Not eaten yet, with common foods" : "Not eaten yet";
    gapsResult.replaceChildren(el("div", { class: "card" },
      el("h2", { style: "margin-top:0" }, `${report.name}: ${report.have.length} of ${report.total} ${report.plural} eaten`),
      el("div", { class: `gap-lists${report.missing.length > 20 ? " cols" : ""}` },
        el("div", {}, el("h3", {}, `Eaten (${report.have.length})`), el("ul", {}, report.have.map(describe))),
        el("div", {}, el("h3", {}, `${missingTitle} (${report.missing.length})`), el("ul", {}, report.missing.map(describe)))),
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

// ---------- start ----------

showTab(["tree", "cladogram", "stats", "add", "gaps"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "tree");
loadTree();
