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
const inputTheorique = document.getElementById("input-theorique");
const inputReel      = document.getElementById("input-reel");
const dropTheorique  = document.getElementById("drop-theorique");
const dropReel       = document.getElementById("drop-reel");
const nameTheorique  = document.getElementById("name-theorique");
const nameReel       = document.getElementById("name-reel");
const btnCompare     = document.getElementById("btn-compare");
const btnDownload    = document.getElementById("btn-download");
const loader         = document.getElementById("loader");
const errorBanner    = document.getElementById("error-banner");
const resultsSection = document.getElementById("results-section");
const statsGrid      = document.getElementById("stats-grid");
const tabsBar        = document.getElementById("tabs-bar");
const inventoryDate  = document.getElementById("inventory-date");

// Default date to today
if (inventoryDate) {
    inventoryDate.valueAsDate = new Date();
}

let fileTheorique = null;
let fileReel      = null;
let lastResult    = null;

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
        const formData = new FormData();
        formData.append("file_theorique", fileTheorique);
        formData.append("file_reel", fileReel);

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
            <div class="stat-label">Total produits</div>
        </div>
        <div class="stat-card green">
            <div class="stat-value">${s.ok_count}</div>
            <div class="stat-label">OK</div>
        </div>
        <div class="stat-card orange">
            <div class="stat-value">${s.discrepancy_count}</div>
            <div class="stat-label">Écarts</div>
        </div>
        <div class="stat-card red">
            <div class="stat-value">${s.missing_actual_count}</div>
            <div class="stat-label">Manq. stockage</div>
        </div>
        <div class="stat-card blue">
            <div class="stat-value">${s.missing_theoretical_count}</div>
            <div class="stat-label">Manq. Proconcept</div>
        </div>
        <div class="stat-card rate">
            <div class="stat-value">${s.match_rate}%</div>
            <div class="stat-label">Concordance</div>
        </div>
    `;

    // Tab counts in buttons
    document.querySelector('[data-tab="ok"]').textContent = `OK (${s.ok_count})`;
    document.querySelector('[data-tab="discrepancies"]').textContent = `Écarts (${s.discrepancy_count})`;
    document.querySelector('[data-tab="missing_actual"]').textContent = `Manquants Réel (${s.missing_actual_count})`;
    document.querySelector('[data-tab="missing_theoretical"]').textContent = `Manquants Théo. (${s.missing_theoretical_count})`;

    // Tables
    renderOkTable(data.ok);
    renderDiscrepancyTable(data.discrepancies);
    renderMissingActualTable(data.missing_actual);
    renderMissingTheoreticalTable(data.missing_theoretical);

    // Scroll to results
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderOkTable(items) {
    const panel = document.getElementById("panel-ok");
    if (!items.length) { panel.innerHTML = '<div class="empty-state">Aucun produit concordant.</div>'; return; }
    panel.innerHTML = `
        <table class="result-table">
            <thead><tr><th>Code</th><th>Description</th><th>Quantité</th></tr></thead>
            <tbody>${items.map(i => `
                <tr>
                    <td class="code-cell">${i.code}</td>
                    <td>${i.description_theorique || i.description_reel || "—"}</td>
                    <td class="qty-cell">${i.qty_theorique.toLocaleString("fr-FR")}</td>
                </tr>
            `).join("")}</tbody>
        </table>
    `;
}

function renderDiscrepancyTable(items) {
    const panel = document.getElementById("panel-discrepancies");
    if (!items.length) { panel.innerHTML = '<div class="empty-state">Aucun écart détecté.</div>'; return; }
    panel.innerHTML = `
        <table class="result-table">
            <thead><tr><th>Code</th><th>Description</th><th>Qté Théorique</th><th>Qté Réelle</th><th>Delta</th></tr></thead>
            <tbody>${items.map(i => {
                const cls = i.delta > 0 ? "delta-positive" : "delta-negative";
                const sign = i.delta > 0 ? "+" : "";
                return `
                <tr>
                    <td class="code-cell">${i.code}</td>
                    <td>${i.description_theorique || i.description_reel || "—"}</td>
                    <td class="qty-cell">${i.qty_theorique.toLocaleString("fr-FR")}</td>
                    <td class="qty-cell">${i.qty_reel.toLocaleString("fr-FR")}</td>
                    <td class="delta-cell ${cls}">${sign}${i.delta.toLocaleString("fr-FR")}</td>
                </tr>`;
            }).join("")}</tbody>
        </table>
    `;
}

function renderMissingActualTable(items) {
    const panel = document.getElementById("panel-missing_actual");
    if (!items.length) { panel.innerHTML = '<div class="empty-state">Tous les produits théoriques sont présents dans le stock réel.</div>'; return; }
    panel.innerHTML = `
        <table class="result-table">
            <thead><tr><th>Code</th><th>Description</th><th>Qté Théorique</th></tr></thead>
            <tbody>${items.map(i => `
                <tr>
                    <td class="code-cell">${i.code}</td>
                    <td>${i.description || "—"}</td>
                    <td class="qty-cell">${i.qty_theorique.toLocaleString("fr-FR")}</td>
                </tr>
            `).join("")}</tbody>
        </table>
    `;
}

function renderMissingTheoreticalTable(items) {
    const panel = document.getElementById("panel-missing_theoretical");
    if (!items.length) { panel.innerHTML = '<div class="empty-state">Tous les produits réels sont présents dans le stock théorique.</div>'; return; }
    panel.innerHTML = `
        <table class="result-table">
            <thead><tr><th>Code</th><th>Description</th><th>Qté Réelle</th></tr></thead>
            <tbody>${items.map(i => `
                <tr>
                    <td class="code-cell">${i.code}</td>
                    <td>${i.description || "—"}</td>
                    <td class="qty-cell">${i.qty_reel.toLocaleString("fr-FR")}</td>
                </tr>
            `).join("")}</tbody>
        </table>
    `;
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
