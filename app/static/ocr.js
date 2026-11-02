/* L'OCR propose des pistes ; seule une confirmation humaine modifie l'identité. */
(() => {
  const form = document.getElementById("ocr-assist-form");
  if (!form) return;

  const status = document.getElementById("ocr-status");
  const results = document.getElementById("ocr-results");
  const button = form.querySelector("button[type=submit]");
  const photo = document.getElementById("ocr-photo");
  const itemId = form.dataset.listingId;
  const appendText = (parent, tag, value, className = "") => {
    const element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    parent.appendChild(element);
    return element;
  };

  photo.addEventListener("change", () => {
    results.replaceChildren();
    status.textContent = "";
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    results.replaceChildren();
    status.textContent = "Analyse locale de la photo en cours…";
    button.disabled = true;
    const data = new FormData(form);
    data.set("listing_id", itemId);
    photo.disabled = true;
    try {
      const response = await fetch(form.action, { method: "POST", body: data, headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(typeof payload.detail === "string" ? payload.detail : "Analyse indisponible. Réessayez.");
      }
      status.textContent = payload.message || "Analyse terminée : vérifiez les propositions.";
      const recognized = payload.recognized || {};
      const names = Array.isArray(recognized.names) ? recognized.names : [];
      const numbers = Array.isArray(recognized.numbers) ? recognized.numbers : [];
      if (names.length || numbers.length) {
        appendText(results, "p", `Indices lus sur la photo : ${[...names, ...numbers].join(" · ")}`, "cell-sub");
      }
      const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
      if (!candidates.length) return;
      appendText(results, "h4", "Candidats à vérifier");
      appendText(results, "p", "Comparez chaque proposition à la photo avant de confirmer. Aucun choix n’a été enregistré.", "cell-sub");
      for (const candidate of candidates) {
        if (!Number.isSafeInteger(candidate.card_id) || candidate.card_id < 1) continue;
        const card = document.createElement("div");
        card.className = "ocr-candidate";
        appendText(card, "strong", candidate.name || "Carte");
        appendText(card, "span", ` · ${candidate.set_name || "Extension inconnue"} · N° ${candidate.local_id || "inconnu"}`);
        appendText(card, "p", candidate.tcgdex_id || "", "cell-sub");
        const confirmation = document.createElement("form");
        confirmation.method = "post";
        confirmation.action = `/catalog/${encodeURIComponent(itemId)}/identification/confirm`;
        for (const [name, value] of Object.entries({
          reference_card_id: candidate.card_id,
          evidence_hash: form.dataset.evidenceHash,
          revision: form.dataset.revision,
        })) {
          const input = document.createElement("input");
          input.type = "hidden";
          input.name = name;
          input.value = String(value ?? "");
          confirmation.appendChild(input);
        }
        const submit = appendText(confirmation, "button", "Confirmer cette carte", "button secondary small");
        submit.type = "submit";
        submit.setAttribute("aria-label", `Confirmer ${candidate.name || "cette carte"}, ${candidate.set_name || "extension inconnue"}, numéro ${candidate.local_id || "inconnu"}`);
        card.appendChild(confirmation);
        results.appendChild(card);
      }
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : "Analyse indisponible. Réessayez.";
    } finally {
      photo.disabled = false;
      button.disabled = false;
    }
  });
})();
