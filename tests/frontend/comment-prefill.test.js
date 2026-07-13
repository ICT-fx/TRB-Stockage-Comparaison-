// Permanent test for the comment carry-forward logic.
// Keep these two functions byte-for-byte in sync with frontend/app.js.
function monthYear(dateStr) {
    const m = /^(\d{4})-(\d{2})-\d{2}$/.exec(dateStr || "");
    return m ? `${m[2]}/${m[1]}` : "";
}
function buildCommentPrefill(stored, invDate) {
    if (!stored || !stored.text) return "";
    const cur = monthYear(invDate);
    const storedM = monthYear(stored.updated);
    if (!cur) return stored.text;  // pas de date d'inventaire exploitable
    if (storedM && storedM === cur) return stored.text;
    if (stored.text.startsWith("previous comment")) return `${stored.text}\n[${cur}] `;
    return `previous comment [${storedM}]: ${stored.text}\n[${cur}] `;
}

const assert = require("assert");
assert.strictEqual(buildCommentPrefill(null, "2026-07-31"), "");
assert.strictEqual(buildCommentPrefill({text: "note", updated: "2026-07-15"}, "2026-07-31"), "note");
assert.strictEqual(
    buildCommentPrefill({text: "écart vérifié", updated: "2026-06-30"}, "2026-07-31"),
    "previous comment [06/2026]: écart vérifié\n[07/2026] ");
assert.strictEqual(
    buildCommentPrefill({text: "previous comment [06/2026]: a\n[07/2026] b", updated: "2026-07-31"}, "2026-08-31"),
    "previous comment [06/2026]: a\n[07/2026] b\n[08/2026] ");
// empty inventory date -> verbatim (no [] marker)
assert.strictEqual(buildCommentPrefill({text: "note", updated: "2026-06-30"}, ""), "note");
// same month different year -> treated as different
assert.strictEqual(
    buildCommentPrefill({text: "x", updated: "2025-07-31"}, "2026-07-31"),
    "previous comment [07/2025]: x\n[07/2026] ");
console.log("comment-prefill tests OK");
