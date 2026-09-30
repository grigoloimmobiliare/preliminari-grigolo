// Interazioni della pagina pratica: righe dinamiche, caricamento file, attesa analisi, calcolo saldo.
(function () {
  "use strict";
  let contatore = Date.now() % 100000;

  // aggiungi righe (persone, unità catastali, versamenti, clausole)
  document.querySelectorAll("[data-aggiungi]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const nome = btn.dataset.aggiungi;
      const modello = document.querySelector('template[data-modello="' + nome + '"]');
      const lista = document.querySelector('[data-lista="' + nome + '"]');
      contatore += 1;
      const html = modello.innerHTML.replace(/__i__/g, String(contatore));
      const tmp = document.createElement(lista.tagName === "TBODY" ? "tbody" : "div");
      tmp.innerHTML = html;
      while (tmp.firstElementChild) lista.appendChild(tmp.firstElementChild);
      aggiornaSaldo();
    });
  });

  document.addEventListener("click", function (e) {
    const b = e.target.closest("[data-rimuovi]");
    if (!b) return;
    const riga = b.closest("[data-riga]");
    if (riga && confirm("Rimuovere questa riga?")) { riga.remove(); aggiornaSaldo(); }
  });

  // persona fisica / società
  document.addEventListener("change", function (e) {
    if (e.target.matches("[data-tipo]")) {
      const box = e.target.closest(".persona").querySelector(".societa");
      box.hidden = e.target.value !== "societa";
    }
    if (e.target.matches("[data-importo], [name='accordi.prezzo']")) aggiornaSaldo();
  });
  document.addEventListener("input", function (e) {
    if (e.target.matches("[data-importo], [name='accordi.prezzo']")) aggiornaSaldo();
  });

  // conferme
  document.querySelectorAll("form[data-conferma]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!confirm(f.dataset.conferma)) e.preventDefault(); });
  });

  // caricamento file: invio automatico dopo la scelta o il trascinamento
  document.querySelectorAll("[data-zona]").forEach(function (zona) {
    const input = zona.querySelector("[data-file]");
    input.addEventListener("change", function () { if (input.files.length) { zona.classList.add("sopra"); zona.submit(); } });
    ["dragenter", "dragover"].forEach(function (ev) { zona.addEventListener(ev, function () { zona.classList.add("sopra"); }); });
    ["dragleave", "drop"].forEach(function (ev) { zona.addEventListener(ev, function () { zona.classList.remove("sopra"); }); });
  });

  // attesa della fine dell'analisi
  const attesa = document.querySelector("[data-attesa]");
  if (attesa) {
    const fase = attesa.querySelector("[data-fase]");
    const controlla = function () {
      fetch(attesa.dataset.attesa).then(function (r) { return r.json(); }).then(function (s) {
        if (s.in_corso) {
          if (s.fase) fase.textContent = s.fase;
          setTimeout(controlla, 2000);
        } else {
          location.hash = "#venditori";
          location.reload();
        }
      }).catch(function () { setTimeout(controlla, 4000); });
    };
    setTimeout(controlla, 2000);
  }

  // saldo = prezzo - caparre - acconti
  function numero(s) {
    s = (s || "").replace(/[€\s'`’]/g, "").replace(/euro/i, "");
    if (!s) return 0;
    if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", ".");
    else if (/\.\d{3}$/.test(s)) s = s.replace(/\./g, "");
    const n = parseFloat(s);
    return isNaN(n) ? 0 : n;
  }
  function aggiornaSaldo() {
    const out = document.querySelector("[data-saldo]");
    if (!out) return;
    const prezzo = numero((document.querySelector("[name='accordi.prezzo']") || {}).value);
    let versato = 0;
    document.querySelectorAll("[data-importo]").forEach(function (i) { versato += numero(i.value); });
    if (!prezzo) { out.textContent = "—"; return; }
    const saldo = prezzo - versato;
    out.textContent = "Euro " + saldo.toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    out.style.color = saldo < 0 ? "#b3261e" : "";
  }
  aggiornaSaldo();

  // avviso se si lascia la pagina con modifiche non salvate
  const modulo = document.getElementById("modulo-dati");
  if (modulo) {
    let modificato = false;
    modulo.addEventListener("input", function () { modificato = true; });
    modulo.addEventListener("submit", function () { modificato = false; });
    window.addEventListener("beforeunload", function (e) { if (modificato) { e.preventDefault(); e.returnValue = ""; } });
  }
})();
