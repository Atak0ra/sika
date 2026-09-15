/*
 * economat/static/economat/js/field-format.js
 * ================================================================
 * Comportements partagés de saisie, appliqués automatiquement au
 * chargement selon l'attribut `name` des champs — aucune modification
 * à faire ailleurs si un futur template utilise les mêmes noms.
 *
 * Montants (amount_fcfa, annual_fee_fcfa) :
 *   Le <input type="number"> ne peut pas afficher d'espaces (le
 *   navigateur rejette toute valeur non numérique), donc le formatage
 *   en direct passe par une paire d'inputs :
 *     - un champ texte visible, formaté avec des espaces fines
 *       insécables (même convention que le filtre `fcfa_long`) ;
 *     - un champ hidden jumeau, qui porte le vrai `name=` et ne
 *       contient que des chiffres — c'est lui qui est soumis au
 *       serveur et lu par le JS existant (ex. confirmation de
 *       montant élevé dans _payment_modal.html).
 *   Convention de gabarit :
 *     <input type="text" inputmode="numeric" data-amount-for="amount_fcfa" ...>
 *     <input type="hidden" name="amount_fcfa" value="...">
 *
 * Téléphones (mobile_number, manager_phone, parent_phone) :
 *   Filtre à la frappe — chiffres, espaces, un seul "+" en tête.
 *   Pas de paire hidden nécessaire : le champ garde son name=.
 * ================================================================
 */
(function () {
  var NBSP = " "; // espace fine insécable — même caractère que economat_tags._NBSP

  function formatThousands(digits) {
    if (!digits) return "";
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  }

  function initAmountField(display) {
    var name = display.dataset.amountFor;
    var hidden = display.form
      ? display.form.querySelector('input[type="hidden"][name="' + name + '"]')
      : document.querySelector('input[type="hidden"][name="' + name + '"]');
    if (!hidden) return;

    function sync() {
      var digits = display.value.replace(/\D/g, "");
      hidden.value = digits;
      display.value = formatThousands(digits);
    }

    display.addEventListener("input", sync);
    sync(); // formate une valeur initiale déjà présente (ex. montant pré-rempli)
  }

  function initPhoneField(input) {
    input.addEventListener("input", function () {
      var value = input.value.replace(/[^\d+ ]/g, "");
      // Un seul "+" toléré, uniquement en première position.
      value = value[0] === "+" ? "+" + value.slice(1).replace(/\+/g, "") : value.replace(/\+/g, "");
      input.value = value;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-amount-for]").forEach(initAmountField);
    document
      .querySelectorAll(
        'input[name="mobile_number"], input[name="manager_phone"], input[name="parent_phone"]'
      )
      .forEach(initPhoneField);
  });
})();
