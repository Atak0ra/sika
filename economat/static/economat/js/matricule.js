/**
 * economat/static/economat/js/matricule.js
 * ==========================================
 * Générateur déterministe de matricule élève et de numéro de reçu.
 *
 * Format matricule : NOM3PRENOM3-AAMMJJ-HHMMSS
 * Format reçu      : MATRICULE/R-AAMMJJ-HHMMSS/TRANCHE/CLASSE
 *
 * DOIT rester en sync avec :
 *   economat/domain/student/matricule.py (Python, même règles, même format)
 *
 * Utilisation :
 *   const mat = generateMatricule('Diallo', 'Awa', new Date());
 *   // → "DIAAWA-260911-143052"
 *   const rec = generateReceiptNumber(mat, 'CM2 A', 'T1', new Date());
 *   // → "DIAAWA-260911-143052/R-260915-093012/T1/CM2A"
 */

/* ── Normalisation ─────────────────────────────────────────────────────────── */

/**
 * Supprime les accents via décomposition Unicode (NFD → ASCII).
 * Compatible avec tous les navigateurs modernes.
 */
function _removeAccents(str) {
  return str.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

/**
 * Produit un slug alphabétique en majuscules de longueur `len`.
 * Supprime accents, espaces, tirets, apostrophes, tout sauf A-Z.
 * Complète avec 'X' si trop court.
 */
function _slug(text, len) {
  const clean = _removeAccents(text)
    .replace(/[^a-zA-Z]/g, '')   // ne garde que les lettres
    .toUpperCase();
  if (!clean) return 'X'.repeat(len);
  return (clean + 'X'.repeat(len)).slice(0, len);
}

/** Formate un nombre sur N chiffres (zéro-padding). */
function _pad(n, digits) {
  return String(n).padStart(digits, '0');
}

/* ── Générateurs ───────────────────────────────────────────────────────────── */

/**
 * Génère le matricule déterministe d'un élève.
 *
 * @param {string} lastName   - Nom de famille (ex. "Diallo", "Ben Ali")
 * @param {string} firstName  - Prénom (ex. "Awa", "Aïcha")
 * @param {Date}   [enrolledAt] - Date+heure d'inscription (défaut : maintenant)
 * @returns {string}  Ex. "DIAAWA-260911-143052"
 */
function generateMatricule(lastName, firstName, enrolledAt) {
  const dt = enrolledAt instanceof Date ? enrolledAt : new Date();
  const nomSlug    = _slug(lastName.replace(/[-']/g, ''), 3);
  const prenomSlug = _slug(firstName.replace(/[-']/g, ''), 3);
  const yy  = _pad(dt.getFullYear() % 100, 2);
  const mm  = _pad(dt.getMonth() + 1, 2);
  const dd  = _pad(dt.getDate(), 2);
  const hh  = _pad(dt.getHours(), 2);
  const min = _pad(dt.getMinutes(), 2);
  const ss  = _pad(dt.getSeconds(), 2);
  return `${nomSlug}${prenomSlug}-${yy}${mm}${dd}-${hh}${min}${ss}`;
}

/**
 * Génère le numéro de reçu déterministe à partir du matricule.
 *
 * @param {string} matricule        - Matricule élève (généré par generateMatricule)
 * @param {string} className        - Nom de la classe (ex. "CM2 A" → "CM2A")
 * @param {string} installmentLabel - Tranche visée (ex. "T1", "T2", "M3")
 * @param {Date}   [paidAt]         - Date+heure du paiement (défaut : maintenant)
 * @returns {string}  Ex. "DIAAWA-260911-143052/R-260915-093012/T1/CM2A"
 */
function generateReceiptNumber(matricule, className, installmentLabel, paidAt) {
  const dt = paidAt instanceof Date ? paidAt : new Date();
  const classSlug = className.replace(/\s+/g, '').toUpperCase();
  const yy  = _pad(dt.getFullYear() % 100, 2);
  const mm  = _pad(dt.getMonth() + 1, 2);
  const dd  = _pad(dt.getDate(), 2);
  const hh  = _pad(dt.getHours(), 2);
  const min = _pad(dt.getMinutes(), 2);
  const ss  = _pad(dt.getSeconds(), 2);
  return `${matricule}/R-${yy}${mm}${dd}-${hh}${min}${ss}/${installmentLabel}/${classSlug}`;
}

/* ── Exports (ES module + compat script tag) ───────────────────────────────── */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { generateMatricule, generateReceiptNumber, _slug, _removeAccents };
} else {
  window.SukuluMatricule = { generateMatricule, generateReceiptNumber };
}
