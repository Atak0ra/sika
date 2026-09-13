/**
 * economat/static/economat/js/matricule.js
 * ==========================================
 * Génère le numéro de reçu côté client (mode offline).
 *
 * Le matricule élève, lui, est TOUJOURS généré côté serveur
 * (economat/domain/student/matricule.py) — l'inscription d'élève n'est pas
 * un flux offline. Ce fichier ne fait que formater un numéro de reçu à
 * partir d'un matricule déjà connu (fourni par le serveur au chargement de
 * la page d'encaissement), pour permettre la génération d'un reçu
 * déterministe hors-ligne avant synchronisation.
 *
 * Utilisation :
 *   const rec = generateReceiptNumber('DIAAWA-7K9XQPR', 'CM2 A', 'T1', new Date());
 *   // → "DIAAWA-7K9XQPR/R-260915-093012/T1/CM2A"
 */

/** Formate un nombre sur N chiffres (zéro-padding). */
function _pad(n, digits) {
  return String(n).padStart(digits, '0');
}

/**
 * Génère le numéro de reçu déterministe à partir du matricule.
 *
 * @param {string} matricule        - Matricule élève (chaîne opaque, fournie par le serveur)
 * @param {string} className        - Nom de la classe (ex. "CM2 A" → "CM2A")
 * @param {string} installmentLabel - Tranche visée (ex. "T1", "T2", "M3")
 * @param {Date}   [paidAt]         - Date+heure du paiement (défaut : maintenant)
 * @returns {string}  Ex. "DIAAWA-7K9XQPR/R-260915-093012/T1/CM2A"
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
  module.exports = { generateReceiptNumber };
} else {
  window.SukuluMatricule = { generateReceiptNumber };
}
