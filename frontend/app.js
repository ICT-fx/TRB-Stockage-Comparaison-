/**
 * TRB Chemedica — Stock Comparison Tool
 * Frontend logic: upload, API calls, results display, Excel download.
 */

// ── Config ──────────────────────────────────────
// When running locally, the backend is on port 8000.
// In production (Render), change this to the deployed backend URL.
const API_BASE = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "https://trb-stock-compare-api.onrender.com";

// ── DOM refs ────────────────────────────────────
const inputTheorique   = document.getElementById("input-theorique");
const inputReel        = document.getElementById("input-reel");
const dropTheorique    = document.getElementById("drop-theorique");
const dropReel         = document.getElementById("drop-reel");
const nameTheorique    = document.getElementById("name-theorique");
const nameReel         = document.getElementById("name-reel");
const btnCompare       = document.getElementById("btn-compare");
const btnDownload      = document.getElementById("btn-download");
const loader           = document.getElementById("loader");
const errorBanner      = document.getElementById("error-banner");
const resultsSection   = document.getElementById("results-section");
const statsGrid        = document.getElementById("stats-grid");
const tabsBar          = document.getElementById("tabs-bar");
const inventoryDate    = document.getElementById("inventory-date");
const layoutTheorique  = document.getElementById("layout-theorique");
const layoutReel       = document.getElementById("layout-reel");

// Default date to today
if (inventoryDate) {
    inventoryDate.valueAsDate = new Date();
}

let fileTheorique = null;
let fileReel      = null;
let lastResult    = null;

// ── Templates (espace de stockage) ──────────────
// NOTE : `layoutReel` est DÉJÀ déclaré plus haut dans app.js (ligne ~29,
// `const layoutReel = document.getElementById("layout-reel")`). Ne pas le
// re-déclarer ici (sinon SyntaxError : redéclaration de const).
const btnTemplateNew   = document.getElementById("btn-template-new");
const btnTemplateEdit  = document.getElementById("btn-template-edit");
const btnTemplateDel   = document.getElementById("btn-template-delete");
const LAST_TPL_KEY = "trb_last_template";

const tplState = { list: [] };

function selectedTemplateId() {
    return layoutReel.value || "basic-stock";
}

async function refreshTemplates(selectId) {
    try {
        const res = await fetch(`${API_BASE}/templates`);
        const data = await res.json();
        tplState.list = data.templates || [];
    } catch {
        tplState.list = [{ id: "basic-stock", name: "Template RK Logistics", builtin: true }];
    }
    const remembered = selectId || localStorage.getItem(LAST_TPL_KEY) || "basic-stock";
    const exists = tplState.list.some(t => t.id === remembered);
    const target = exists ? remembered : "basic-stock";

    layoutReel.innerHTML = tplState.list
        .map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`)
        .join("");
    layoutReel.value = target;
    onTemplateSelectionChange();
}

function currentTemplate() {
    return tplState.list.find(t => t.id === selectedTemplateId());
}

function onTemplateSelectionChange() {
    const t = currentTemplate();
    const isBuiltin = !t || t.builtin;
    btnTemplateEdit.disabled = isBuiltin;
    btnTemplateDel.disabled = isBuiltin;
    localStorage.setItem(LAST_TPL_KEY, selectedTemplateId());
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

layoutReel.addEventListener("change", onTemplateSelectionChange);
refreshTemplates();

// ── Enregistrement des commentaires d'écart ─────
async function saveComment(box) {
    if (!box || box.value === box.dataset.initial) return;  // inchangé
    const payload = {
        code: box.dataset.code,
        lot: box.dataset.lot,
        text: box.value,
        inventory_date: inventoryDate.value || "",
    };
    try {
        await fetch(`${API_BASE}/comments`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        box.dataset.initial = box.value;
    } catch { /* réseau indisponible : on réessaiera à la prochaine perte de focus */ }
}

let pendingCommentSave = Promise.resolve();
document.getElementById("panel-discrepancies").addEventListener("focusout", (e) => {
    if (e.target.classList && e.target.classList.contains("comment-box")) {
        pendingCommentSave = saveComment(e.target);
    }
});

// ── File selection ──────────────────────────────
function handleFileSelect(file, type) {
    if (!file) return;
    if (type === "theorique") {
        fileTheorique = file;
        nameTheorique.textContent = file.name;
        nameTheorique.classList.add("selected");
        dropTheorique.classList.add("has-file");
    } else {
        fileReel = file;
        nameReel.textContent = file.name;
        nameReel.classList.add("selected");
        dropReel.classList.add("has-file");
    }
    btnCompare.disabled = !(fileTheorique && fileReel);
}

inputTheorique.addEventListener("change", (e) => handleFileSelect(e.target.files[0], "theorique"));
inputReel.addEventListener("change", (e) => handleFileSelect(e.target.files[0], "reel"));

// ── Drag & drop ─────────────────────────────────
function setupDrop(zone, type) {
    zone.addEventListener("dragover", (e) => {
        e.preventDefault();
        zone.classList.add("dragover");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("dragover");
        const file = e.dataTransfer.files[0];
        if (file) handleFileSelect(file, type);
    });
}
setupDrop(dropTheorique, "theorique");
setupDrop(dropReel, "reel");

// ── Compare ─────────────────────────────────────
btnCompare.addEventListener("click", async () => {
    if (!fileTheorique || !fileReel) return;

    // UI state
    loader.classList.remove("hidden");
    errorBanner.classList.add("hidden");
    resultsSection.classList.add("hidden");
    btnCompare.disabled = true;

    try {
        const formData = new FormData();
        formData.append("file_theorique", fileTheorique);
        formData.append("file_reel", fileReel);
        formData.append("storage_template_id", selectedTemplateId());

        const res = await fetch(`${API_BASE}/compare`, {
            method: "POST",
            body: formData,
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: "Erreur réseau" }));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        lastResult = await res.json();
        renderResults(lastResult);
    } catch (err) {
        errorBanner.textContent = err.message;
        errorBanner.classList.remove("hidden");
    } finally {
        loader.classList.add("hidden");
        btnCompare.disabled = false;
    }
});

// ── Download Excel ──────────────────────────────
btnDownload.addEventListener("click", async () => {
    if (!fileTheorique || !fileReel) return;

    btnDownload.disabled = true;
    btnDownload.textContent = "⏳ Génération…";

    try {
        // Le clic sur Télécharger fait perdre le focus au champ commentaire
        // (focusout) et déclenche son enregistrement : on l'attend avant l'export.
        await pendingCommentSave;

        const formData = new FormData();
        formData.append("file_theorique", fileTheorique);
        formData.append("file_reel", fileReel);
        formData.append("storage_template_id", selectedTemplateId());

        const res = await fetch(`${API_BASE}/compare/download`, {
            method: "POST",
            body: formData,
        });

        if (!res.ok) throw new Error("Erreur lors du téléchargement");

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        
        // Use selected date or fallback to today
        const dateStr = inventoryDate.value || new Date().toISOString().split('T')[0];
        a.download = `Comparaison_Stock_${dateStr}.xlsx`;
        
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (err) {
        errorBanner.textContent = err.message;
        errorBanner.classList.remove("hidden");
    } finally {
        btnDownload.disabled = false;
        btnDownload.innerHTML = 'Télécharger le rapport Excel';
    }
});

// ── Render results ──────────────────────────────
function renderResults(data) {
    resultsSection.classList.remove("hidden");

    // Stats
    const s = data.stats;
    statsGrid.innerHTML = `
        <div class="stat-card total">
            <div class="stat-value">${s.total_products}</div>
            <div class="stat-label">Total lots</div>
        </div>
        <div class="stat-card green">
            <div class="stat-value">${s.ok_count}</div>
            <div class="stat-label">OK</div>
        </div>
        <div class="stat-card orange">
            <div class="stat-value">${s.discrepancy_count}</div>
            <div class="stat-label">Écarts</div>
        </div>
        <div class="stat-card rate">
            <div class="stat-value">${s.match_rate}%</div>
            <div class="stat-label">Concordance</div>
        </div>
    `;

    // Tab counts in buttons
    document.querySelector('[data-tab="ok"]').textContent = `OK (${s.ok_count})`;
    document.querySelector('[data-tab="discrepancies"]').textContent = `Écarts (${s.discrepancy_count})`;

    // Tables
    renderOkTable(data.ok);
    renderDiscrepancyTable(data.discrepancies);

    // Onglet Écarts affiché par défaut
    tabsBar.querySelectorAll(".tab").forEach(t =>
        t.classList.toggle("active", t.dataset.tab === "discrepancies"));
    document.querySelectorAll(".tab-panel").forEach(p =>
        p.classList.toggle("active", p.id === "panel-discrepancies"));

    // Scroll to results
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderOkTable(items) {
    const panel = document.getElementById("panel-ok");
    if (!items.length) { panel.innerHTML = '<div class="empty-state">Aucun lot concordant.</div>'; return; }

    panel.innerHTML = `
        <table class="result-table">
            <thead><tr><th>Code</th><th>N° de lot</th><th>Date Proconcept</th><th>Date RK</th><th>Description</th><th>Quantité</th></tr></thead>
            <tbody>${items.map(i => `
                <tr>
                    <td class="code-cell">${i.code}</td>
                    <td class="lot-cell">${i.lot || '—'}</td>
                    <td class="date-cell">${i.date_proconcept || '—'}</td>
                    <td class="date-cell">${i.date_rk || '—'}</td>
                    <td>${i.description_theorique || i.description_reel || '—'}</td>
                    <td class="qty-cell">${i.qty_theorique.toLocaleString('fr-FR')}</td>
                </tr>`).join('')}</tbody>
        </table>
    `;
}

// ── Commentaires d'écart ────────────────────────
function monthYear(dateStr) {
    const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(dateStr || "");
    return m ? `${m[2]}/${m[1]}` : "";
}

// Pré-remplissage du commentaire d'une ligne d'écart (report « previous comment »).
function buildCommentPrefill(stored, invDate) {
    if (!stored || !stored.text) return "";
    const cur = monthYear(invDate);
    const storedM = monthYear(stored.updated);
    if (!cur) return stored.text;  // pas de date d'inventaire exploitable
    if (storedM && storedM === cur) return stored.text;
    if (stored.text.startsWith("previous comment")) return `${stored.text}\n[${cur}] `;
    return `previous comment [${storedM}]: ${stored.text}\n[${cur}] `;
}

function renderDiscrepancyTable(items) {
    const panel = document.getElementById("panel-discrepancies");
    if (!items.length) { panel.innerHTML = '<div class="empty-state">Aucun écart détecté.</div>'; return; }

    const inv = inventoryDate.value || "";
    panel.innerHTML = `
        <table class="result-table">
            <thead><tr><th>Code</th><th>N° de lot</th><th>Date Proconcept</th><th>Date RK</th><th>Description</th><th>Qté Proconcept</th><th>Qté Réelle</th><th>Delta</th><th>Commentaire</th></tr></thead>
            <tbody>${items.map(i => {
                const cls = i.delta > 0 ? 'delta-positive' : 'delta-negative';
                const sign = i.delta > 0 ? '+' : '';
                const prefill = buildCommentPrefill(i.stored_comment, inv);
                return `
                <tr>
                    <td class="code-cell">${i.code}</td>
                    <td class="lot-cell">${i.lot || '—'}</td>
                    <td class="date-cell">${i.date_proconcept || '—'}</td>
                    <td class="date-cell">${i.date_rk || '—'}</td>
                    <td>${i.description_theorique || i.description_reel || '—'}</td>
                    <td class="qty-cell">${i.qty_theorique.toLocaleString('fr-FR')}</td>
                    <td class="qty-cell">${i.qty_reel.toLocaleString('fr-FR')}</td>
                    <td class="delta-cell ${cls}">${sign}${i.delta.toLocaleString('fr-FR')}</td>
                    <td class="comment-cell"><textarea class="comment-box" rows="2" data-code="${i.code}" data-lot="${i.lot || ''}">${escapeHtml(prefill)}</textarea></td>
                </tr>`;
            }).join('')}</tbody>
        </table>
    `;
    // Mémoriser la valeur initiale de chaque champ (pour détecter les modifs).
    panel.querySelectorAll(".comment-box").forEach(box => { box.dataset.initial = box.value; });
}


// ── Tabs ────────────────────────────────────────
tabsBar.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    const tabName = btn.dataset.tab;

    // Update active tab
    tabsBar.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    btn.classList.add("active");

    // Show correct panel
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    document.getElementById(`panel-${tabName}`).classList.add("active");
});

// ── Modale template ─────────────────────────────
const modal          = document.getElementById("template-modal");
const modalTitle     = document.getElementById("tpl-modal-title");
const tplFileInput   = document.getElementById("tpl-file-input");
const tplDrop        = document.getElementById("tpl-drop");
const tplFileName    = document.getElementById("tpl-file-name");
const tplHeaderRow   = document.getElementById("tpl-header-row");
const tplMapping     = document.getElementById("tpl-mapping");
const tplName        = document.getElementById("tpl-name");
const tplSave        = document.getElementById("tpl-save");
const tplCancel      = document.getElementById("tpl-cancel");
const tplError       = document.getElementById("tpl-error");

const FIELDS = [
    { key: "sku",         label: "SKU",             required: true },
    { key: "lot",         label: "N° de lot",       required: true },
    { key: "date",        label: "Date d'expir.",   required: false },
    { key: "description", label: "Description",     required: false },
    { key: "qty",         label: "Quantité",        required: true },
];

const GUESS = {
    sku: ["sku", "artikel", "article", "référence", "reference", "code", "ref"],
    lot: ["lot", "lagerort", "charge", "batch"],
    date: ["date", "exp", "mhd", "verfall", "péremption", "peremption", "g"],
    description: ["desc", "kurztext", "bezeichnung", "libellé", "libelle", "désignation", "designation", "produit"],
    qty: ["qte", "qté", "quantité", "quantite", "menge", "bestand", "stock", "qty"],
};

let modalState = { columns: [], fileBytes: null, editId: null, lastFile: null };

function guessColumn(fieldKey, columns) {
    const kws = GUESS[fieldKey] || [];
    // Pass 1 — exact header match (case-insensitive). Handles short headers like
    // RK's "G" date column, which a substring match would wrongly assign to
    // "Lagerort" (the lot column) because it also contains the letter "g".
    for (const col of columns) {
        const n = String(col.name).toLowerCase().trim();
        if (kws.includes(n)) return col.index;
    }
    // Pass 2 — substring match, but only for keywords of 3+ chars, so
    // single/double-letter tokens can't over-match longer column names.
    for (const col of columns) {
        const n = String(col.name).toLowerCase();
        if (kws.some(k => k.length >= 3 && n.includes(k))) return col.index;
    }
    return null;
}

function renderMapping(columns, preset) {
    modalState.columns = columns;
    const optionsFor = (allowNone) => {
        let opts = allowNone ? `<option value="">— aucune —</option>` : "";
        opts += columns.map(c => {
            const ex = c.samples && c.samples.length ? ` (ex: ${escapeHtml(c.samples[0])})` : "";
            return `<option value="${c.index}">${escapeHtml(c.name)}${ex}</option>`;
        }).join("");
        return opts;
    };
    tplMapping.innerHTML = FIELDS.map(f => `
        <div class="tpl-map-row">
            <label for="map-${f.key}">${f.label}${f.required ? " *" : ""}</label>
            <select id="map-${f.key}" data-field="${f.key}">${optionsFor(!f.required)}</select>
        </div>`).join("");

    FIELDS.forEach(f => {
        const sel = document.getElementById(`map-${f.key}`);
        let val = preset && preset.columns && preset.columns[f.key];
        if (val === undefined || val === null) {
            const g = guessColumn(f.key, columns);
            val = g === null ? "" : g;
        }
        sel.value = val === null ? "" : String(val);
        sel.addEventListener("change", validateModal);
    });
    validateModal();
}

function validateModal() {
    const named = tplName.value.trim().length > 0;
    const hasCols = modalState.columns.length > 0;
    const requiredMapped = FIELDS.filter(f => f.required).every(f => {
        const sel = document.getElementById(`map-${f.key}`);
        return sel && sel.value !== "";
    });
    tplSave.disabled = !(named && hasCols && requiredMapped);
}

async function previewFile(file, headerRow) {
    tplError.classList.add("hidden");
    const fd = new FormData();
    fd.append("file", file);
    if (headerRow) fd.append("header_row", String(headerRow));
    const res = await fetch(`${API_BASE}/templates/preview`, { method: "POST", body: fd });
    if (!res.ok) {
        const e = await res.json().catch(() => ({ detail: "Erreur" }));
        throw new Error(e.detail || "Fichier illisible");
    }
    return res.json();
}

async function handleTemplateFile(file, preset) {
    if (!file) return;
    modalState.lastFile = file;
    tplFileName.textContent = file.name;
    try {
        const data = await previewFile(file, null);
        tplHeaderRow.disabled = false;
        tplHeaderRow.value = data.header_row;
        renderMapping(data.columns, preset);
    } catch (err) {
        tplError.textContent = err.message;
        tplError.classList.remove("hidden");
    }
}

tplFileInput.addEventListener("change", e => handleTemplateFile(e.target.files[0], null));

tplDrop.addEventListener("dragover", e => { e.preventDefault(); tplDrop.classList.add("dragover"); });
tplDrop.addEventListener("dragleave", () => tplDrop.classList.remove("dragover"));
tplDrop.addEventListener("drop", e => {
    e.preventDefault(); tplDrop.classList.remove("dragover");
    if (e.dataTransfer.files[0]) handleTemplateFile(e.dataTransfer.files[0], null);
});

tplHeaderRow.addEventListener("change", async () => {
    if (!modalState.lastFile) return;
    try {
        const data = await previewFile(modalState.lastFile, parseInt(tplHeaderRow.value, 10));
        renderMapping(data.columns, null);
    } catch (err) {
        tplError.textContent = err.message;
        tplError.classList.remove("hidden");
    }
});

tplName.addEventListener("input", validateModal);

function collectColumns() {
    const cols = {};
    FIELDS.forEach(f => {
        const v = document.getElementById(`map-${f.key}`).value;
        cols[f.key] = v === "" ? null : parseInt(v, 10);
    });
    return cols;
}

async function saveTemplate() {
    tplError.classList.add("hidden");
    const payload = {
        name: tplName.value.trim(),
        header_row: parseInt(tplHeaderRow.value, 10) || 1,
        columns: collectColumns(),
    };
    const editing = modalState.editId;
    const url = editing ? `${API_BASE}/templates/${editing}` : `${API_BASE}/templates`;
    const method = editing ? "PUT" : "POST";
    try {
        const res = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            const e = await res.json().catch(() => ({ detail: "Erreur" }));
            throw new Error(e.detail || "Enregistrement impossible");
        }
        const saved = await res.json();
        closeTemplateModal();
        await refreshTemplates(saved.id);
    } catch (err) {
        tplError.textContent = err.message;
        tplError.classList.remove("hidden");
    }
}

function openTemplateModal(template) {
    modalState = { columns: [], fileBytes: null, editId: template ? template.id : null, lastFile: null };
    modalTitle.textContent = template ? "Modifier le template" : "Nouveau template";
    tplName.value = template ? template.name : "";
    tplFileName.textContent = "Aucun fichier";
    tplError.classList.add("hidden");
    tplSave.disabled = true;
    if (template) {
        // Pré-remplir sans fichier : colonnes génériques jusqu'à l'indice max connu.
        const maxIdx = Math.max(...Object.values(template.columns).filter(v => v !== null), 0);
        const cols = Array.from({ length: maxIdx + 1 }, (_, i) => ({ index: i, name: `Colonne ${i + 1}`, samples: [] }));
        tplHeaderRow.disabled = false;
        tplHeaderRow.value = template.header_row;
        renderMapping(cols, template);
    } else {
        tplHeaderRow.disabled = true;
        tplHeaderRow.value = 1;
        tplMapping.innerHTML = `<p class="tpl-step-label">Dépose d'abord un fichier exemple ci-dessus.</p>`;
    }
    modal.classList.remove("hidden");
}

function closeTemplateModal() {
    modal.classList.add("hidden");
}

tplSave.addEventListener("click", saveTemplate);
tplCancel.addEventListener("click", closeTemplateModal);
modal.addEventListener("click", e => { if (e.target === modal) closeTemplateModal(); });
btnTemplateNew.addEventListener("click", () => openTemplateModal(null));

// ── Modifier / Supprimer ────────────────────────
btnTemplateEdit.addEventListener("click", () => {
    const t = tplState.list.find(x => x.id === selectedTemplateId());
    if (t && !t.builtin) openTemplateModal(t);
});

btnTemplateDel.addEventListener("click", async () => {
    const t = tplState.list.find(x => x.id === selectedTemplateId());
    if (!t || t.builtin) return;
    if (!confirm(`Supprimer le template « ${t.name} » ?`)) return;
    try {
        const res = await fetch(`${API_BASE}/templates/${t.id}`, { method: "DELETE" });
        if (!res.ok) {
            const e = await res.json().catch(() => ({ detail: "Erreur" }));
            throw new Error(e.detail || "Suppression impossible");
        }
        await refreshTemplates("basic-stock");
    } catch (err) {
        errorBanner.textContent = err.message;
        errorBanner.classList.remove("hidden");
    }
});
