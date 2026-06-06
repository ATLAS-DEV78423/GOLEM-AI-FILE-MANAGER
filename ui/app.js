// ─── DEMO DATA ───────────────────────────────────────────────────────────────
// Used only when pywebview API is not available (e.g., opening index.html directly)

const DEMO = [
  {
    group: "TOP MATCHES",
    items: [
      {
        icon: "📄",
        name: "Pricing Strategy Q3 2024.pdf",
        type: "file",
        meta: "~/Documents/Business/ · 3 days ago",
        snip: "Value metric pricing outperforms seat-based by 3x in expansion revenue…",
        pill: "both",
        pillLabel: "keyword + semantic",
        terms: ["Pricing", "pricing"],
        _group: "TOP MATCHES"
      },
      {
        icon: "🎬",
        name: "How to Price SaaS — Patrick Campbell",
        type: "video",
        meta: "YouTube · ingested 12 days ago · timestamp 14:32",
        snip: "\"The value metric framework is what separates companies that scale from ones that plateau…\"",
        pill: "sem",
        pillLabel: "semantic",
        terms: [],
        _group: "TOP MATCHES"
      },
      {
        icon: "📝",
        name: "Meeting with Tariq — March.md",
        type: "note",
        meta: "~/Notes/Meetings/ · 2 weeks ago",
        snip: "Tariq mentioned the value metric framework — thinks per-seat model is leaving money on table…",
        pill: "ent",
        pillLabel: "via entity",
        terms: [],
        _group: "TOP MATCHES"
      }
    ]
  },
  {
    group: "ALSO RELATED",
    items: [
      {
        icon: "📊",
        name: "Competitor Analysis Jan 2024.xlsx",
        type: "file",
        meta: "~/Documents/Research/ · 5 months ago · section incomplete",
        snip: "Linear, Notion, Figma pricing tier breakdown — pricing section was never finished…",
        pill: "kw",
        pillLabel: "keyword",
        terms: ["pricing"],
        _group: "ALSO RELATED"
      },
      {
        icon: "🎙️",
        name: "Voice memo — freemium thoughts.m4a",
        type: "audio",
        meta: "~/Voice Memos/ · 3 weeks ago · transcribed",
        snip: "…freemium trains users to expect value for free — introducing pricing tiers feels like betrayal…",
        pill: "sem",
        pillLabel: "semantic",
        terms: ["pricing"],
        _group: "ALSO RELATED"
      }
    ]
  }
];

// ─── STATE ───────────────────────────────────────────────────────────────────
let selectedIndex = 0;
let flatItems = [];
let activeFilter = "all";
let debounceTimer = null;
let _isLoading = false;

// ─── HELPERS ─────────────────────────────────────────────────────────────────
function highlight(text, terms) {
  if (!terms || !terms.length) return escHtml(text);
  let result = escHtml(text);
  terms.forEach(t => {
    const re = new RegExp(`(${escRe(t)})`, "gi");
    result = result.replace(re, "<mark>$1</mark>");
  });
  return result;
}

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function escRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function isBackendAvailable() {
  return !!(window.pywebview && window.pywebview.api && window.pywebview.api.search);
}

// ─── UI STATES ───────────────────────────────────────────────────────────────

function showSkeletons() {
  const container = document.getElementById("results");
  _isLoading = true;
  container.innerHTML = `
    <div class="skeleton-list">
      <div class="skel-row">
        <div class="skel skel-ico"></div>
        <div class="skel-lines">
          <div class="skel skel-a" style="width:78%"></div>
          <div class="skel skel-b" style="width:55%"></div>
        </div>
        <div class="skel skel-pill"></div>
      </div>
      <div class="skel-row">
        <div class="skel skel-ico"></div>
        <div class="skel-lines">
          <div class="skel skel-a" style="width:65%"></div>
          <div class="skel skel-b" style="width:42%"></div>
        </div>
        <div class="skel skel-pill"></div>
      </div>
      <div class="skel-row">
        <div class="skel skel-ico"></div>
        <div class="skel-lines">
          <div class="skel skel-a" style="width:82%"></div>
          <div class="skel skel-b" style="width:60%"></div>
        </div>
        <div class="skel skel-pill"></div>
      </div>
      <div class="skel-row">
        <div class="skel skel-ico"></div>
        <div class="skel-lines">
          <div class="skel skel-a" style="width:70%"></div>
          <div class="skel skel-b" style="width:48%"></div>
        </div>
        <div class="skel skel-pill"></div>
      </div>
    </div>`;
}

function showIdleState() {
  const container = document.getElementById("results");
  _isLoading = false;
  container.innerHTML = `
    <div class="empty welcome">
      <div class="welcome-icon">
        <svg width="36" height="36" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <circle cx="11" cy="11" r="8" stroke="#f97316" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
          <line x1="21" y1="21" x2="16.65" y2="16.65" stroke="#f97316" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="welcome-title">Describe what you're looking for</div>
      <div class="welcome-sub">GOLEM searches by meaning, not just filenames</div>
    </div>`;
}

function showEmptyState(title, subtitle) {
  const container = document.getElementById("results");
  _isLoading = false;
  container.innerHTML = `
    <div class="empty">
      <div class="empty-icon">◎</div>
      <div class="empty-title">${escHtml(title || "Nothing found")}</div>
      <div class="empty-sub">${escHtml(subtitle || "Try describing the contents, not the filename")}</div>
    </div>`;
}

function showError(message) {
  const container = document.getElementById("results");
  _isLoading = false;
  container.innerHTML = `
    <div class="empty">
      <div class="empty-icon" style="opacity:0.35">⚠</div>
      <div class="empty-title">Search error</div>
      <div class="empty-sub">${escHtml(message || "Something went wrong. Please try again.")}</div>
    </div>`;
}

// ─── RENDER RESULTS ──────────────────────────────────────────────────────────
function renderResults(groups) {
  const container = document.getElementById("results");
  flatItems = [];
  _isLoading = false;

  if (!groups || !groups.length || groups.every(g => !g.items.length)) {
    showEmptyState("Nothing found", "Try describing the contents, not the filename");
    return;
  }

  let html = "";
  let globalIdx = 0;

  groups.forEach((group, gi) => {
    const filtered = activeFilter === "all"
      ? group.items
      : group.items.filter(i => i.type === activeFilter);

    if (!filtered.length) return;

    if (gi > 0) {
      html += `<div class="divider"></div>`;
    }

    html += `<div class="section-label">${escHtml(group.group)}</div>`;

    filtered.forEach((item) => {
      const idx = globalIdx++;
      flatItems.push(item);
      const sel = idx === selectedIndex ? " sel" : "";
      var relatedHtml = '';
      if (item.relatedTags && item.relatedTags.length > 0) {
        relatedHtml = '<div class="item-rel">' +
          item.relatedTags.map(function(t) { return '<span class="rel-chip tag">#' + escHtml(t) + '</span>'; }).join('') +
          (item.relatedFiles && item.relatedFiles.length > 0 ?
            item.relatedFiles.map(function(f) { return '<span class="rel-chip file">📎 ' + escHtml(f) + '</span>'; }).join('') : '') +
          '</div>';
      }
      html += `
        <div class="item${sel}" data-idx="${idx}" onclick="selectItem(${idx})" ondblclick="openItem(${idx})">
          <div class="icon-wrap">${item.icon}</div>
          <div class="item-body">
            <div class="item-name">${highlight(item.name, item.terms)}</div>
            <div class="item-meta">${escHtml(item.meta)}</div>
            ${relatedHtml ? '<div class="item-rel-row">' + relatedHtml + '</div>' : ''}
            <div class="item-snip">${item.snip ? highlight(item.snip, item.terms) : ''}</div>
          </div>
          <div class="mpill ${item.pill}">${escHtml(item.pillLabel)}</div>
        </div>`;
    });
  });

  container.innerHTML = html;
  updateFooterStatus();
}

// ─── SELECTION ───────────────────────────────────────────────────────────────
function selectItem(idx) {
  selectedIndex = idx;
  document.querySelectorAll(".item").forEach((el, i) => {
    el.classList.toggle("sel", i === idx);
    if (i === idx) {
      el.scrollIntoView({ block: "nearest" });
    }
  });
}

function openItem(idx) {
  const item = flatItems[idx];
  if (!item) return;
  if (isBackendAvailable()) {
    window.pywebview.api.open_file(item.path || item.name);
  } else {
    console.log("Open (demo):", item.name);
    // In browser demo mode, show an alert
    alert("Open: " + item.name + "\n" + (item.path || ""));
  }
}

function revealItem(idx) {
  const item = flatItems[idx];
  if (!item) return;
  if (isBackendAvailable()) {
    window.pywebview.api.reveal_in_finder(item.path || item.name);
  } else {
    console.log("Reveal (demo):", item.name);
  }
}

// ─── FILTER ──────────────────────────────────────────────────────────────────
function setFilter(el) {
  document.querySelectorAll(".tf").forEach(f => f.classList.remove("on"));
  el.classList.add("on");
  activeFilter = el.dataset.filter;
  selectedIndex = 0;
  // Re-render current results with new filter
  if (flatItems.length > 0) {
    // Re-group flatItems back into groups and re-render
    const groups = regroupItems(flatItems);
    renderResults(groups);
  } else {
    const query = document.getElementById("searchInput").value.trim();
    if (query.length >= 2) {
      doSearch(query);
    } else {
      showIdleState();
    }
  }
}

function regroupItems(items) {
  // Simple grouping: group by the last known group (stored on items)
  const groups = {};
  items.forEach(item => {
    const g = item._group || "FILES";
    if (!groups[g]) groups[g] = { group: g, items: [] };
    groups[g].items.push(item);
  });
  return Object.values(groups);
}

// ─── SEARCH ──────────────────────────────────────────────────────────────────
async function doSearch(query) {
  if (query.length < 2) {
    showIdleState();
    updateFooterStatus();
    return;
  }

  showSkeletons();
  updateFooterStatus("searching");

  try {
    let results;
    if (isBackendAvailable()) {
      results = await window.pywebview.api.search(query, 8);
    } else {
      // Demo fallback for browser testing — filter by first few characters
      // to simulate real search behavior
      await new Promise(r => setTimeout(r, 400 + Math.random() * 300));
      results = query.toLowerCase().includes("price") || query.toLowerCase().includes("pricing") ? DEMO : [];
    }
    renderResults(groupBySection(results));
  } catch (e) {
    console.error("Search failed:", e);
    // Fall back to demo data if backend fails
    if (!isBackendAvailable()) {
      await new Promise(r => setTimeout(r, 300));
      renderResults(DEMO);
    } else {
      showError("Search failed. Please try again.");
    }
  }
}

function groupBySection(results) {
  if (!results || !results.length) return [];
  const groups = {};
  results.forEach(r => {
    const g = r.group || "FILES";
    if (!groups[g]) groups[g] = { group: g, items: [] };
    const item = {
      icon: iconForType(r.file_type),
      name: r.file_name,
      type: r.file_type,
      meta: r.file_path + (r.modified_at ? " · " + r.modified_at : ""),
      snip: r.snippet || "",
      pill: pillClass(r.match_type),
      pillLabel: pillLabel(r.match_type),
      terms: r.matched_terms || [],
      path: r.file_path,
      _group: g,
      relatedTags: r.related_tags || [],
      relatedFiles: r.related_files || [],
      relatedCategories: r.related_categories || []
    };
    groups[g].items.push(item);
  });
  return Object.values(groups);
}

function iconForType(type) {
  const icons = {
    pdf: "📄", md: "📝", xlsx: "📊", docx: "📋",
    video: "🎬", youtube: "🎬", audio: "🎙️", m4a: "🎙️",
    image: "🖼️", code: "💻", folder: "📁", web: "🌐",
    archive: "📦", presentation: "📊"
  };
  return icons[type] || "📎";
}

function pillClass(matchType) {
  return { keyword: "kw", semantic: "sem", both: "both", entity: "ent" }[matchType] || "sem";
}

function pillLabel(matchType) {
  return { keyword: "keyword", semantic: "semantic", both: "keyword + semantic", entity: "via entity" }[matchType] || matchType;
}

// ─── STATUS ──────────────────────────────────────────────────────────────────
async function fetchStatus() {
  try {
    if (isBackendAvailable()) {
      const status = await window.pywebview.api.get_status();
      updateStatusDisplay(status);
    }
  } catch (e) {
    console.log("Status fetch not available:", e);
  }
}

function updateStatusDisplay(status) {
  const statusText = document.getElementById("statusText");
  const statusDot = document.getElementById("statusDot");
  if (!statusText || !statusDot) return;

  if (!status) {
    statusText.textContent = "ready";
    statusDot.className = "status-dot";
    return;
  }

  const count = status.file_count || 0;
  const statusMsg = status.status || "ready";

  if (statusMsg === "indexing") {
    statusText.textContent = `indexing · ${count} files so far`;
    statusDot.className = "status-dot indexing";
  } else if (statusMsg === "error") {
    statusText.textContent = status.message || "error";
    statusDot.className = "status-dot error";
  } else {
    statusText.textContent = count > 0
      ? `${count.toLocaleString()} file${count !== 1 ? 's' : ''} · indexed`
      : "ready · add files to get started";
    statusDot.className = "status-dot";
  }
}

function updateFooterStatus(state) {
  const statusText = document.getElementById("statusText");
  if (!statusText) return;
  if (state === "searching") {
    // Don't change the status text while skeletons are showing
    // (will be updated by renderResults or fetchStatus)
  }
}

// ─── KEYBOARD ────────────────────────────────────────────────────────────────
document.getElementById("searchInput").addEventListener("input", function () {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => doSearch(this.value.trim()), 150);
});

document.addEventListener("keydown", function (e) {
  // Ignore if typing in the search input (except navigation keys)
  if (e.target && e.target.id === "searchInput" &&
      ["ArrowDown", "ArrowUp", "Enter", "Escape", "Tab"].indexOf(e.key) === -1) {
    return;
  }

  const items = document.querySelectorAll(".item");
  if (!items.length && e.key !== "Escape" && e.key !== "Tab") return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    selectedIndex = (selectedIndex + 1) % flatItems.length;
    selectItem(selectedIndex);
  }

  if (e.key === "ArrowUp") {
    e.preventDefault();
    selectedIndex = (selectedIndex - 1 + flatItems.length) % flatItems.length;
    selectItem(selectedIndex);
  }

  if (e.key === "Enter") {
    if (!flatItems.length) return;
    if (e.metaKey || e.ctrlKey) revealItem(selectedIndex);
    else openItem(selectedIndex);
  }

  if (e.key === "Escape") {
    if (isBackendAvailable()) {
      window.pywebview.api.hide_window();
    } else {
      // In browser, just clear the search
      const input = document.getElementById("searchInput");
      if (input && input.value) {
        input.value = "";
        showIdleState();
      }
    }
  }

  if (e.key === "Tab") {
    e.preventDefault();
    const filters = document.querySelectorAll(".tf");
    if (!filters.length) return;
    const current = [...filters].findIndex(f => f.classList.contains("on"));
    const next = (current + 1) % filters.length;
    setFilter(filters[next]);
  }
});

// ─── INIT ────────────────────────────────────────────────────────────────────
document.getElementById("searchInput").focus();
showIdleState();

// Fetch status on load and every 30 seconds
fetchStatus();
setInterval(fetchStatus, 30000);
