/* L'OCR propose des pistes ; seule une confirmation humaine modifie l'identité. */
(() => {
  const form = document.getElementById("ocr-assist-form");
  if (!form) return;

  const status = document.getElementById("ocr-status");
  const results = document.getElementById("ocr-results");
  const button = form.querySelector("button[type=submit]");
  const photo = document.getElementById("ocr-photo");
  const itemId = form.dataset.listingId;
  const crop = document.getElementById("ocr-crop");
  const canvas = document.getElementById("ocr-canvas");
  const enabled = document.getElementById("ocr-crop-enabled");
  const fields = Object.fromEntries(["crop_x", "crop_y", "crop_width", "crop_height", "image_width", "image_height", "crop_rotation"].map(name => [name, form.elements[name]]));
  let generation = 0, controller = null, preview = null, start = null;
  const invalidate = () => {
    generation++;
    if (controller) controller.abort();
    results.replaceChildren();
    status.textContent = "";
    button.disabled = false;
  };
  const draw = () => {
    if (!preview) return;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(preview, 0, 0);
    if (enabled.checked) {
      ctx.strokeStyle = "#e11d48";
      ctx.lineWidth = Math.max(2, canvas.width / 400);
      ctx.strokeRect(Number(fields.crop_x.value), Number(fields.crop_y.value), Number(fields.crop_width.value), Number(fields.crop_height.value));
    }
  };
  const point = event => {
    const rect = canvas.getBoundingClientRect();
    return [Math.max(0, Math.min(canvas.width, Math.round((event.clientX - rect.left) * canvas.width / rect.width))),
      Math.max(0, Math.min(canvas.height, Math.round((event.clientY - rect.top) * canvas.height / rect.height)))];
  };
  canvas.addEventListener("pointerdown", event => {
    start = point(event); canvas.setPointerCapture(event.pointerId); enabled.checked = true; invalidate();
  });
  canvas.addEventListener("pointermove", event => {
    if (!start) return;
    const end = point(event);
    fields.crop_x.value = Math.min(start[0], end[0]); fields.crop_y.value = Math.min(start[1], end[1]);
    fields.crop_width.value = Math.abs(end[0] - start[0]); fields.crop_height.value = Math.abs(end[1] - start[1]);
    draw();
  });
  canvas.addEventListener("pointerup", () => { start = null; });
  canvas.addEventListener("pointercancel", () => { start = null; });
  crop.addEventListener("input", () => { invalidate(); draw(); });
  const appendText = (parent, tag, value, className = "") => {
    const element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    parent.appendChild(element);
    return element;
  };

  photo.addEventListener("change", async () => {
    invalidate();
    const current = generation;
    crop.hidden = true; preview = null; enabled.checked = false;
    if (!photo.files.length) return;
    button.disabled = true;
    status.textContent = "Préparation locale de la photo…";
    const data = new FormData(); data.set("file", photo.files[0]);
    try {
      const response = await fetch("/ocr/preview", {method: "POST", body: data});
      if (!response.ok) throw new Error((await response.json()).detail || "Photo illisible.");
      const url = URL.createObjectURL(await response.blob());
      const image = new Image();
      try { image.src = url; await image.decode(); } finally { URL.revokeObjectURL(url); }
      if (current !== generation) return;
      preview = image; canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
      fields.image_width.value = image.naturalWidth; fields.image_height.value = image.naturalHeight;
      fields.crop_x.value = 0; fields.crop_y.value = 0; fields.crop_width.value = image.naturalWidth; fields.crop_height.value = image.naturalHeight; fields.crop_rotation.value = "0";
      crop.hidden = false; draw(); status.textContent = "Photo prête à être analysée.";
    } catch (error) {
      if (current === generation) status.textContent = error instanceof Error ? error.message : "Photo illisible.";
    } finally { if (current === generation) button.disabled = false; }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    invalidate();
    const current = generation;
    controller = new AbortController();
    results.replaceChildren();
    status.textContent = "Analyse locale de la photo en cours…";
    button.disabled = true;
    const data = new FormData(form);
    if (!enabled.checked) Object.keys(fields).forEach(name => data.delete(name));
    data.set("listing_id", itemId);
    try {
      const response = await fetch(form.action, { method: "POST", body: data, headers: { Accept: "application/json" }, signal: controller.signal });
      const payload = await response.json();
      if (current !== generation) return;
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
      if (current === generation) status.textContent = error instanceof Error ? error.message : "Analyse indisponible. Réessayez.";
    } finally {
      if (current === generation) { button.disabled = false; controller = null; }
    }
  });
})();
