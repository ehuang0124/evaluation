/* Political Content Explorer — dependency-free browser client. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => (Number(n) || 0).toLocaleString();
  const pct = (a, b) => b ? (100 * a / b).toFixed(2) + "%" : "—";

  const COLORS = {
    strict: "#5fd3a0", probable: "#f7b267", broad: "#94a0c0",
    prompt: "#6ea8fe", response: "#b79cff", both: "#5fd3a0",
    blue: "#6ea8fe", violet: "#b79cff", green: "#5fd3a0", orange: "#f7b267", red: "#f2848c",
  };
  const state = {
    scope: "core", q: "", tier: "all", basis: "all", topic: "all", lang: "all",
    winner: "all", model: "all", code: "all", date_from: "", date_to: "",
    min_score: 0, sort: "score", limit: 25, offset: 0,
  };
  let bootstrap = null, current = null, currentTab = "prompt", debounce = null, lastTotal = 0;

  /* ---------------- SVG chart helpers ---------------- */
  function hbar(el, obj, color, opts = {}) {
    const entries = Object.entries(obj || {}).filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1]).slice(0, opts.limit || 9);
    if (!entries.length) return void (el.innerHTML = '<div class="empty">No rows match</div>');
    const max = Math.max(...entries.map(e => e[1]));
    const W = 620, labelW = opts.labelW || 148, barW = W - labelW - 66, rowH = 25;
    let s = `<svg viewBox="0 0 ${W} ${entries.length * rowH + 6}" role="img">`;
    entries.forEach(([k, v], i) => {
      const y = i * rowH + 4, bw = Math.max(2, v / max * barW);
      const label = k.length > 24 ? k.slice(0, 23) + "…" : k;
      const fill = typeof color === "function" ? color(k) : color;
      s += `<text x="${labelW - 8}" y="${y + 13}" text-anchor="end" fill="#94a0c0" font-size="11">${esc(label)}</text>`;
      s += `<rect x="${labelW}" y="${y + 2}" width="${barW}" height="13" rx="3" fill="#18213c"/>`;
      s += `<rect x="${labelW}" y="${y + 2}" width="${bw}" height="13" rx="3" fill="${fill}"/>`;
      s += `<text x="${labelW + barW + 8}" y="${y + 13}" fill="#e8ecf8" font-size="11">${fmt(v)}</text>`;
    });
    el.innerHTML = s + "</svg>";
  }

  function vbar(el, obj, color) {
    const entries = Object.entries(obj || {}).filter(([, v]) => v > 0);
    if (!entries.length) return void (el.innerHTML = '<div class="empty">No rows match</div>');
    const max = Math.max(...entries.map(e => e[1]));
    const W = 620, H = 175, padL = 34, padB = 30, padT = 12;
    const bw = (W - padL - 12) / entries.length;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
    s += `<line x1="${padL}" y1="${H - padB}" x2="${W - 6}" y2="${H - padB}" stroke="#26304d"/>`;
    s += `<text x="2" y="${padT + 4}" fill="#94a0c0" font-size="10">${fmt(max)}</text>`;
    entries.forEach(([k, v], i) => {
      const h = v / max * (H - padB - padT);
      const x = padL + i * bw + 3, y = H - padB - h;
      s += `<rect x="${x}" y="${y}" width="${Math.max(3, bw - 7)}" height="${h}" rx="3" fill="${color}"><title>${esc(k)}: ${fmt(v)}</title></rect>`;
      s += `<text x="${x + (bw - 7) / 2}" y="${H - padB + 14}" text-anchor="middle" fill="#94a0c0" font-size="9">${esc(k.length > 10 ? k.slice(0, 9) : k)}</text>`;
      s += `<text x="${x + (bw - 7) / 2}" y="${y - 3}" text-anchor="middle" fill="#e8ecf8" font-size="9">${fmt(v)}</text>`;
    });
    el.innerHTML = s + "</svg>";
  }

  function lineChart(el, obj, color) {
    const entries = Object.entries(obj || {}).filter(([k, v]) => k && v > 0).sort();
    if (entries.length < 2) return void (el.innerHTML = '<div class="empty">Not enough time points</div>');
    const max = Math.max(...entries.map(e => e[1]));
    const W = 620, H = 175, padL = 40, padB = 28, padT = 14;
    const step = (W - padL - 14) / (entries.length - 1);
    const pts = entries.map(([, v], i) => [padL + i * step, H - padB - v / max * (H - padB - padT)]);
    const path = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
    const area = path + ` L${pts[pts.length-1][0].toFixed(1)},${H-padB} L${padL},${H-padB} Z`;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".38"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>`;
    s += `<line x1="${padL}" y1="${H-padB}" x2="${W-6}" y2="${H-padB}" stroke="#26304d"/>`;
    s += `<path d="${area}" fill="url(#g)"/><path d="${path}" fill="none" stroke="${color}" stroke-width="2.5"/>`;
    entries.forEach(([k, v], i) => {
      const [x, y] = pts[i];
      s += `<circle cx="${x}" cy="${y}" r="3.5" fill="${color}"><title>${esc(k)}: ${fmt(v)}</title></circle>`;
      s += `<text x="${x}" y="${H-padB+15}" text-anchor="middle" fill="#94a0c0" font-size="9">${esc(k.slice(2))}</text>`;
    });
    s += `<text x="2" y="${padT+4}" fill="#94a0c0" font-size="10">${fmt(max)}</text></svg>`;
    el.innerHTML = s;
  }

  function stackedTier(el, cross) {
    const tiers = ["strict", "probable", "broad"];
    const bases = ["prompt", "response", "both"];
    const rows = tiers.filter(t => (cross?.[t] && Object.values(cross[t]).some(v => v > 0)));
    if (!rows.length) return void (el.innerHTML = '<div class="empty">No rows match</div>');
    const W = 620, labelW = 92, barW = W - labelW - 80, rowH = 34;
    let s = `<svg viewBox="0 0 ${W} ${rows.length * rowH + 12}" role="img">`;
    rows.forEach((t, i) => {
      const y = i * rowH + 8, total = bases.reduce((a, b) => a + (cross[t]?.[b] || 0), 0);
      let x = labelW;
      s += `<text x="${labelW-10}" y="${y+15}" text-anchor="end" fill="${COLORS[t]||'#e8ecf8'}" font-size="12" font-weight="600">${esc(t)}</text>`;
      bases.forEach(b => {
        const v = cross[t]?.[b] || 0;
        const w = total ? v / total * barW : 0;
        if (w > 0) {
          s += `<rect x="${x.toFixed(1)}" y="${y+2}" width="${w.toFixed(1)}" height="18" fill="${COLORS[b]}"><title>${esc(t)} / ${esc(b)}: ${fmt(v)}</title></rect>`;
          if (w > 34) s += `<text x="${(x+w/2).toFixed(1)}" y="${y+15}" text-anchor="middle" fill="#08122b" font-size="10" font-weight="700">${fmt(v)}</text>`;
          x += w;
        }
      });
      s += `<text x="${labelW+barW+8}" y="${y+15}" fill="#e8ecf8" font-size="11">${fmt(total)}</text>`;
    });
    s += "</svg>";
    const legend = `<div style="margin-top:6px;display:flex;gap:14px;flex-wrap:wrap;color:#94a0c0;font-size:11px">` +
      bases.map(b => `<span><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${COLORS[b]};margin-right:5px"></span>${b}</span>`).join("") +
      `<span style="opacity:.7">signal carried by prompt / answer / both</span></div>`;
    el.innerHTML = s + legend;
  }

  /* ---------------- rendering ---------------- */
  function renderKpis(data) {
    const c = bootstrap?.corpus?.counts || {};
    const n = bootstrap?.corpus?.rows_scanned || 0;
    const cards = [
      ["Corpus votes", fmt(n), "full train split"],
      ["Strict political prompts", fmt(c.rows_prompt_strict || 0), pct(c.rows_prompt_strict || 0, n) + " of votes"],
      ["Strict political answers", fmt(c.responses_union_strict || 0), pct(c.responses_union_strict || 0, c.responses_judged || 0) + " of answers"],
      ["Full-text conversations", fmt(bootstrap?.data_counts?.conversations || 0), fmt(bootstrap?.data_counts?.prompts_all || 0) + " full prompts indexed"],
      ["Rows matching filters", fmt(data.total), data.scope === "core" ? "core shortlist" : "all flagged prompts"],
    ];
    $("kpis").innerHTML = cards.map(([l, v, d]) =>
      `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div><div class="d">${d}</div></div>`).join("");
  }

  function renderCharts(f) {
    stackedTier($("chart-tier"), f.cross);
    hbar($("chart-topic"), f.topic, (k) => k === "public_policy" ? COLORS.blue : COLORS.violet, { limit: 8, labelW: 148 });
    hbar($("chart-lang"), f.language, COLORS.green, { limit: 9, labelW: 90 });
    lineChart($("chart-month"), f.month, COLORS.orange);
    hbar($("chart-winner"), f.winner, (k) => ({ model_a: COLORS.blue, model_b: COLORS.violet, tie: COLORS.orange, both_bad: COLORS.red }[k] || COLORS.blue), { limit: 4, labelW: 90 });
    hbar($("chart-model"), f.model, COLORS.blue, { limit: 9, labelW: 175 });
    vbar($("chart-score"), f.score_band, COLORS.violet);
  }

  function renderTable(rows) {
    if (!rows.length) {
      $("tbody").innerHTML = '<tr><td colspan="9" class="empty">No conversations match these filters.</td></tr>';
      return;
    }
    $("tbody").innerHTML = rows.map(r => {
      const tags = (r.categories || []).slice(0, 3).map(t => `<span class="tag">${esc(t)}</span>`).join("") +
        ((r.categories || []).length > 3 ? `<span class="tag">+${r.categories.length - 3}</span>` : "");
      const models = [r.model_a, r.model_b].filter(Boolean).map(m => esc(m.length > 18 ? m.slice(0, 17) + "…" : m)).join(" <span class='muted'>vs</span> ");
      return `<tr data-id="${esc(r.id)}">
        <td class="pcell" title="${esc(r.prompt_preview)}">${esc(r.prompt_preview || "(empty)")}</td>
        <td class="tier-${esc(r.tier)}">${esc(r.tier)}</td>
        <td class="muted">${esc(r.basis)}</td>
        <td>${tags}</td>
        <td class="muted">${esc(r.language)}</td>
        <td class="muted">${models}</td>
        <td class="muted">${esc(r.winner)}</td>
        <td class="muted">${esc((r.timestamp || "").slice(0, 10))}</td>
        <td class="muted">${fmt(r.score)}</td>
      </tr>`;
    }).join("");
    $("tbody").querySelectorAll("tr[data-id]").forEach(tr =>
      tr.addEventListener("click", () => openRow(tr.dataset.id)));
  }

  function queryParams(extra = {}) {
    const p = new URLSearchParams();
    Object.entries(state).forEach(([k, v]) => { if (v !== "" && v !== "all" && v !== 0) p.set(k, v); });
    Object.entries(extra).forEach(([k, v]) => p.set(k, v));
    return p;
  }

  async function refresh() {
    const res = await fetch("/api/query?" + queryParams());
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    lastTotal = data.total;
    renderKpis(data);
    renderCharts(data.facets);
    renderTable(data.rows);
    $("result-count").textContent = fmt(data.total) + " rows";
    const pages = Math.max(1, Math.ceil(data.total / state.limit));
    $("pageinfo").textContent = `Page ${Math.floor(state.offset / state.limit) + 1} / ${pages}`;
    $("prev").disabled = state.offset === 0;
    $("next").disabled = state.offset + state.limit >= data.total;
  }

  function schedule() { clearTimeout(debounce); debounce = setTimeout(() => { state.offset = 0; refresh().catch(showError); }, 180); }
  function showError(e) { $("result-count").textContent = "error"; $("tbody").innerHTML = `<tr><td colspan="9" class="empty">${esc(e.message || e)}</td></tr>`; }

  /* ---------------- detail drawer ---------------- */
  function textFor(tab) {
    if (!current) return "";
    if (tab === "prompt") {
      const turns = current.user_turns || [current.prompt || ""];
      return turns.length > 1
        ? turns.map((t, i) => `── USER TURN ${i + 1} / ${turns.length} ──\n\n${t}`).join("\n\n")
        : (current.prompt || "");
    }
    if (tab === "a") return current.assistant_a || "";
    if (tab === "b") return current.assistant_b || "";
    return "";
  }

  function renderTab(tab) {
    currentTab = tab;
    $("d-tabs").querySelectorAll("button").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
    const box = $("d-content");
    if (tab === "meta") {
      const skip = new Set(["prompt", "user_turns", "assistant_a", "assistant_b", "categories"]);
      const entries = Object.entries(current || {}).filter(([k]) => !skip.has(k) && !k.startsWith("_"));
      box.innerHTML = `<div class="metagrid">${entries.map(([k, v]) =>
        `<div class="k">${esc(k)}</div><div class="v">${esc(Array.isArray(v) ? v.join(", ") : v)}</div>`).join("")}
        <div class="k">categories</div><div class="v">${esc((current?.categories || []).join(", "))}</div></div>`;
    } else {
      const t = textFor(tab);
      if (!t) {
        box.innerHTML = `<div class="empty">This row is not in the core full-conversation shortlist.<br>Switch the data scope to <strong>All flagged prompts</strong> to see it, or pick another row.<br><br>Full model answers are stored only for the ~6.8k core political conversations.</div>`;
      } else {
        const turns = tab === "prompt" && (current.user_turns || []).length > 1
          ? current.user_turns.map((u, i) => `<div class="turn"><div class="turn-label">User turn ${i+1}/${current.user_turns.length}</div><pre class="fulltext">${esc(u)}</pre></div>`).join("")
          : `<pre class="fulltext">${esc(t)}</pre>`;
        box.innerHTML = turns;
      }
    }
    $("d-length").textContent = fmt(textFor(tab).length) + " characters · verbatim";
    $("d-content").scrollTop = 0;
  }

  async function openRow(id) {
    $("drawer").classList.remove("hidden");
    $("d-content").innerHTML = '<div class="empty">Loading full text…</div>';
    const res = await fetch("/api/row?id=" + encodeURIComponent(id));
    current = await res.json();
    $("d-title").textContent = "Conversation " + (current.id || "").slice(0, 8);
    $("d-meta").textContent = [current.tier, current.basis, current.language, current.winner,
      (current.timestamp || "").slice(0, 19), current.model_a + " vs " + current.model_b]
      .filter(Boolean).join(" · ");
    renderTab("prompt");
  }
  function closeDrawer() { $("drawer").classList.add("hidden"); current = null; }

  /* ---------------- wiring ---------------- */
  async function init() {
    const res = await fetch("/api/bootstrap");
    bootstrap = await res.json();
    const o = bootstrap.options || {};
    const fill = (id, items, labelFn = x => x) => {
      $(id).innerHTML += items.map(x => `<option value="${esc(x)}">${esc(labelFn(x))}</option>`).join("");
    };
    fill("topic", o.topics || []);
    fill("lang", o.languages || []);
    fill("winner", o.winners || []);
    fill("model", o.models || []);
    const m = bootstrap.manifest || {};
    $("topmeta").innerHTML = `Dataset revision <code>${esc((m.dataset_revision || "").slice(0, 8))}</code> · ` +
      `${fmt(bootstrap.data_counts?.conversations || 0)} full conversations · ` +
      `${fmt(bootstrap.data_counts?.prompts_all || 0)} full prompts<br>` +
      `Extracted ${esc((m.generated_at_utc || "").slice(0, 19).replace("T", " "))} UTC · verbatim text, no truncation`;
    $("sidenote").innerHTML = `Every prompt here is the <strong>complete, untruncated</strong> user text from the dataset. ` +
      `Core scope also includes both complete model answers. Prompts are CC-BY-4.0; model outputs carry their providers' terms.`;
    $("footer").innerHTML = `Source: <code>lmarena-ai/arena-human-preference-140k</code> (train, 135,634 votes). ` +
      `Labels come from a keyword screen with strict / probable / broad tiers and are <strong>not</strong> human gold labels. ` +
      `Files: <code>arena/results/summary.json</code>, <code>arena/explorer/data/*.jsonl.gz</code>.`;

    const bind = (id, key, transform = v => v) => $(id).addEventListener("input", e => {
      state[key] = transform(e.target.value); schedule();
    });
    bind("q", "q"); bind("tier", "tier"); bind("basis", "basis"); bind("topic", "topic");
    bind("lang", "lang"); bind("winner", "winner"); bind("model", "model"); bind("code", "code");
    bind("date_from", "date_from"); bind("date_to", "date_to"); bind("sort", "sort");
    bind("min_score", "min_score", v => parseInt(v || "0", 10) || 0);
    $("scope").addEventListener("change", e => { state.scope = e.target.value; schedule(); });
    $("reset").addEventListener("click", () => {
      Object.assign(state, { q: "", tier: "all", basis: "all", topic: "all", lang: "all", winner: "all",
        model: "all", code: "all", date_from: "", date_to: "", min_score: 0, sort: "score", offset: 0 });
      ["q","date_from","date_to"].forEach(i => $(i).value = "");
      ["tier","basis","topic","lang","winner","model","code","sort"].forEach(i => $(i).value = "all");
      $("sort").value = "score"; $("min_score").value = "0";
      refresh().catch(showError);
    });
    $("prev").addEventListener("click", () => { state.offset = Math.max(0, state.offset - state.limit); refresh().catch(showError); });
    $("next").addEventListener("click", () => { state.offset += state.limit; refresh().catch(showError); });
    $("export").addEventListener("click", () => {
      const a = document.createElement("a");
      a.href = "/api/export?" + queryParams();
      a.download = "political_prompts_full.csv";
      document.body.appendChild(a); a.click(); a.remove();
    });
    $("d-close").addEventListener("click", closeDrawer);
    $("backdrop").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });
    $("d-tabs").addEventListener("click", e => { if (e.target.dataset.tab) renderTab(e.target.dataset.tab); });
    $("d-copy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(textFor(currentTab)); $("d-copy").textContent = "Copied ✓"; }
      catch (_) { $("d-copy").textContent = "Copy failed"; }
      setTimeout(() => $("d-copy").textContent = "Copy text", 1400);
    });
    await refresh();
  }
  init().catch(showError);
})();
