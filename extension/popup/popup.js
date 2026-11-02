// Logique de l'interface popup Pokébourse Capture

document.addEventListener("DOMContentLoaded", async () => {
  const listingCountEl = document.getElementById("listing-count");
  const listingsListEl = document.getElementById("listings-list");
  const emptyStateEl = document.getElementById("empty-state");
  const toggleAutoCapture = document.getElementById("toggle-auto-capture");
  const toggleLabel = document.getElementById("toggle-label");
  const statusMessageEl = document.getElementById("status-message");

  const checkboxSelectAll = document.getElementById("checkbox-select-all");
  const selectionCountEl = document.getElementById("selection-count");
  const sendCountEl = document.getElementById("send-count");

  const btnExportJsonl = document.getElementById("btn-export-jsonl");
  const btnCopyJsonl = document.getElementById("btn-copy-jsonl");
  const btnSendPokebourse = document.getElementById("btn-send-pokebourse");
  const btnPreviewPokebourse = document.getElementById("btn-preview-pokebourse");
  const btnClearAll = document.getElementById("btn-clear-all");
  const ocrImage = document.getElementById("ocr-image");
  const ocrButton = document.getElementById("btn-ocr");
  const ocrResult = document.getElementById("ocr-result");

  let currentListings = [];
  const selectedIds = new Set();

  function showMessage(text, isError = false, durationMs = 4500) {
    statusMessageEl.textContent = text;
    statusMessageEl.style.display = "block";
    statusMessageEl.style.backgroundColor = isError ? "rgba(239, 68, 68, 0.2)" : "rgba(16, 185, 129, 0.15)";
    statusMessageEl.style.color = isError ? "#f87171" : "#34d399";
    statusMessageEl.style.borderColor = isError ? "rgba(239, 68, 68, 0.4)" : "rgba(52, 211, 153, 0.3)";

    setTimeout(() => {
      statusMessageEl.style.display = "none";
    }, durationMs);
  }

  function getItemKey(item) {
    return String(item.external_id || item.url || "");
  }

  // 1. Mise à jour de l'UI de sélection
  function updateSelectionUI() {
    const total = currentListings.length;
    const selectedCount = selectedIds.size;

    selectionCountEl.textContent = `${selectedCount} sélectionnée(s) sur ${total}`;
    sendCountEl.textContent = String(selectedCount);

    if (total === 0) {
      checkboxSelectAll.checked = false;
      checkboxSelectAll.disabled = true;
      btnSendPokebourse.disabled = true;
      btnPreviewPokebourse.disabled = true;
    } else {
      checkboxSelectAll.disabled = false;
      checkboxSelectAll.checked = selectedCount === total;
      btnSendPokebourse.disabled = selectedCount === 0;
      btnPreviewPokebourse.disabled = false;
    }
  }

  // 2. Chargement de l'état initial
  async function loadState() {
    chrome.runtime.sendMessage({ action: "GET_STATUS" }, (response) => {
      if (response) {
        toggleAutoCapture.checked = Boolean(response.autoCaptureEnabled);
        toggleLabel.textContent = response.autoCaptureEnabled ? "Auto : Actif" : "Auto : Pause";
      }
    });

    chrome.runtime.sendMessage({ action: "GET_LISTINGS" }, (response) => {
      currentListings = response?.listings || [];
      // Sélectionne toutes les cartes par défaut
      selectedIds.clear();
      currentListings.forEach((item) => {
        selectedIds.add(getItemKey(item));
      });
      renderListings();
    });
  }

  // 3. Affichage des annonces
  function renderListings() {
    listingCountEl.textContent = String(currentListings.length);

    if (currentListings.length === 0) {
      emptyStateEl.style.display = "flex";
      listingsListEl.innerHTML = "";
      updateSelectionUI();
      return;
    }

    emptyStateEl.style.display = "none";
    listingsListEl.innerHTML = "";

    currentListings.forEach((item) => {
      const itemKey = getItemKey(item);
      const isSelected = selectedIds.has(itemKey);

      const card = document.createElement("div");
      card.className = "listing-card";
      card.id = `card-${escapeHtml(itemKey)}`;

      const priceFormatted = item.price_cents == null ? "Prix inconnu" : (item.price_cents / 100).toFixed(2).replace(".", ",") + " " + escapeHtml(item.currency || "(devise inconnue)");
      const sourceClass = (item.source || "web").toLowerCase();

      let thumbHtml = `<div class="listing-thumb-placeholder">🎴</div>`;
      if (item.image_url) {
        // Pas de gestionnaire d'événement en ligne : la CSP Manifest V3
        // (script-src 'self') bloque les attributs on* — le repli est branché
        // en JavaScript après l'insertion du nœud (voir plus bas).
        thumbHtml = `<img src="${escapeHtml(item.image_url)}" class="listing-thumb" alt="Carte">`;
      }

      // Construction de la boîte d'évaluation financière si disponible
      let evalHtml = "";
      if (item.evaluation) {
        const ev = item.evaluation;
        const verdictClass = escapeHtml(ev.verdict || "sans_cote");
        const verdictLabel = escapeHtml(ev.verdict_label || "Sans cote");
        const cardTitle = escapeHtml(ev.name || item.name);
        const cardSet = escapeHtml(ev.set_name || item.set_name || "");
        const cardNum = ev.card_number ? `#${escapeHtml(ev.card_number)}` : "";

        let profitHtml = "";
        if (ev.net_profit_formatted) {
          const isPos = (ev.net_profit_cents || 0) >= 0;
          profitHtml = `
            <div class="eval-profit">
              <span>Bénéfice net estimé :</span>
              <strong class="${isPos ? 'profit-pos' : 'profit-neg'}">
                ${escapeHtml(ev.net_profit_formatted)} ${ev.roi_percent ? '(' + escapeHtml(ev.roi_percent) + ')' : ''}
              </strong>
            </div>
          `;
        } else {
          profitHtml = `
            <div class="eval-no-cote-tip">
              <span>ℹ️ Aucune cote enregistrée dans Pokébourse pour cette carte.</span>
              <a href="${escapeHtml(ev.url_add_cote || 'http://localhost:8000/reglages#cotes')}" target="_blank" rel="noopener noreferrer" class="eval-link-cote">+ Renseigner une cote Cardmarket / eBay</a>
            </div>
          `;
        }

        const sourceLabel = ev.reference_source_name ? `<span class="eval-source">(${escapeHtml(ev.reference_source_name)})</span>` : "";
        let identityHtml = "";
        if (ev.identification_status === "identified") {
          identityHtml = `<div class="eval-identification">✓ ${ev.decision_source === "human" ? "Carte confirmée manuellement" : "Carte identifiée"}${ev.has_reference_price ? "" : " · cote non renseignée"}</div>`;
        } else if (ev.identification_status === "ambiguous") {
          identityHtml = `<div class="eval-identification">Plusieurs cartes possibles · <a href="${escapeHtml(ev.url_identify || ev.url_detail)}" target="_blank" rel="noopener noreferrer">Comparer les candidats</a></div>`;
        } else if (ev.identification_status === "lot") {
          identityHtml = `<div class="eval-identification">Lot / produit scellé · aucune carte unitaire attribuée</div>`;
        } else {
          identityHtml = `<div class="eval-identification">Carte à identifier · <a href="${escapeHtml(ev.url_identify || ev.url_detail)}" target="_blank" rel="noopener noreferrer">Identifier cette carte</a></div>`;
        }

        evalHtml = `
          <div class="eval-box ${verdictClass}">
            <div class="eval-header">
              <span class="eval-verdict-badge ${verdictClass}">${verdictLabel}</span>
              <span class="eval-name" title="${cardTitle} - ${cardSet}">${cardTitle} · ${cardSet} ${cardNum}</span>
            </div>
            <div class="eval-prices">
              <div class="eval-col">
                <span class="eval-lbl">Prix d'achat :</span>
                <span class="eval-val">${escapeHtml(ev.purchase_price_formatted || priceFormatted)}</span>
              </div>
              <div class="eval-col">
                <span class="eval-lbl">Prix de revente :</span>
                <span class="eval-val ${ev.has_reference_price ? 'has-price' : 'no-price'}">
                  ${escapeHtml(ev.reference_price_formatted || 'Non renseignée')}
                  ${sourceLabel}
                </span>
              </div>
            </div>
            ${identityHtml}
            ${profitHtml}
            <div class="eval-footer">
              <a href="${escapeHtml(ev.url_detail || 'http://localhost:8000/catalog')}" target="_blank" rel="noopener noreferrer" class="eval-link-detail">
                Ouvrir la fiche dans Pokébourse ↗
              </a>
            </div>
          </div>
        `;
      }

      card.innerHTML = `
        <div class="listing-card-main">
          <input type="checkbox" class="item-checkbox" data-id="${escapeHtml(itemKey)}" ${isSelected ? "checked" : ""} title="Sélectionner pour l'envoi">
          ${thumbHtml}
          <div class="listing-details">
            <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" class="listing-title" title="${escapeHtml(item.name)}">
              ${escapeHtml(item.name)}
            </a>
            <span class="listing-meta">${escapeHtml(item.set_name || "Non identifiée")}${item.card_number ? " · N° " + escapeHtml(item.card_number) : ""}</span>
            <div class="listing-bottom">
              <span class="listing-price">${priceFormatted}</span>
              <span class="source-badge ${sourceClass}">${escapeHtml(item.source || "web")}</span>
            </div>
          </div>
          <button class="btn-card-del" title="Retirer de la liste" data-id="${escapeHtml(itemKey)}">✕</button>
        </div>
        ${evalHtml}
      `;

      // Écouteur sur la case à cocher unitaire
      const checkbox = card.querySelector(".item-checkbox");
      checkbox.addEventListener("change", (e) => {
        if (e.target.checked) {
          selectedIds.add(itemKey);
        } else {
          selectedIds.delete(itemKey);
        }
        updateSelectionUI();
      });

      // Écouteur sur le bouton supprimer
      card.querySelector(".btn-card-del").addEventListener("click", () => {
        deleteListing(itemKey);
      });

      // Repli de la vignette : l'échec de chargement remplace l'image par le
      // pictogramme, conformément à la CSP (aucun attribut on* en ligne).
      const thumb = card.querySelector(".listing-thumb");
      if (thumb) {
        const fallbackThumb = () => {
          const placeholder = document.createElement("div");
          placeholder.className = "listing-thumb-placeholder";
          placeholder.textContent = "🎴";
          thumb.replaceWith(placeholder);
        };
        thumb.addEventListener("error", fallbackThumb, { once: true });
        if (thumb.complete && thumb.naturalWidth === 0) fallbackThumb();
      }

      listingsListEl.appendChild(card);
    });

    updateSelectionUI();
  }

  // 4. Écouteur Tout sélectionner / Tout désélectionner
  checkboxSelectAll.addEventListener("change", (e) => {
    if (e.target.checked) {
      currentListings.forEach((item) => selectedIds.add(getItemKey(item)));
    } else {
      selectedIds.clear();
    }
    document.querySelectorAll(".item-checkbox").forEach((cb) => {
      cb.checked = e.target.checked;
    });
    updateSelectionUI();
  });

  function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = String(str);
    // Les guillemets sont échappés aussi : la valeur sert dans des attributs
    // (title="…", href="…", src="…") et une quote brute pourrait les faire
    // éclater, créant de fait un attribut injecté (puis bloqué par la CSP).
    return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // L'identifiant doit provenir d'une fiche locale déjà renvoyée après import.
  function localListingId(item) {
    try {
      const detail = new URL(item.evaluation?.url_detail || "");
      const match = detail.origin === "http://localhost:8000" && detail.pathname.match(/^\/catalog\/(\d+)\/?$/);
      return match ? match[1] : null;
    } catch (_) {
      return null;
    }
  }

  function appendOcrLine(text, className) {
    const line = document.createElement("p");
    if (className) line.className = className;
    line.textContent = text;
    ocrResult.appendChild(line);
  }

  ocrButton.addEventListener("click", async () => {
    ocrResult.replaceChildren();
    const selected = currentListings.filter((item) => selectedIds.has(getItemKey(item)));
    if (selected.length !== 1) {
      appendOcrLine("Sélectionnez exactement une annonce avant d’analyser sa photo.", "ocr-error");
      return;
    }
    const file = ocrImage.files?.[0];
    if (!file) {
      appendOcrLine("Choisissez d’abord une photo sur votre appareil.", "ocr-error");
      return;
    }
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 8 * 1024 * 1024) {
      appendOcrLine("Choisissez une image JPEG, PNG ou WebP de 8 Mo maximum.", "ocr-error");
      return;
    }
    const item = selected[0];
    const listingId = localListingId(item);
    const formData = new FormData();
    formData.append("file", file);
    // Le titre sert notamment à préserver la détection des lots avant import.
    formData.append("title", String(item.raw_data?.title || item.name || ""));
    if (listingId) formData.append("listing_id", listingId);
    ocrButton.disabled = true;
    appendOcrLine("Analyse locale en cours…");
    try {
      const response = await fetch("http://localhost:8000/ocr/suggestions", { method: "POST", body: formData });
      const data = await response.json().catch(() => ({}));
      ocrResult.replaceChildren();
      if (!response.ok) {
        appendOcrLine(typeof data.detail === "string" ? data.detail : `Analyse indisponible (code ${response.status}).`, "ocr-error");
        return;
      }
      appendOcrLine(`Photo de l’annonce : ${item.name || "sans titre"}. Suggestions à vérifier, aucune identité confirmée.`);
      if (data.message) appendOcrLine(String(data.message));
      const recognized = data.recognized || {};
      const names = Array.isArray(recognized.names) ? recognized.names : [];
      const numbers = Array.isArray(recognized.numbers) ? recognized.numbers : [];
      if (names.length || numbers.length) {
        appendOcrLine(`Indices reconnus : ${[...names, ...numbers].join(" · ")}`);
      }
      const candidates = Array.isArray(data.candidates) ? data.candidates : [];
      if (data.status !== "lot" && candidates.length) {
        const list = document.createElement("ul");
        candidates.forEach((candidate) => {
          const row = document.createElement("li");
          row.textContent = `${candidate.name || "Carte"} · ${candidate.set_name || "Extension inconnue"} · N° ${candidate.local_id || "?"} — à vérifier`;
          list.appendChild(row);
        });
        ocrResult.appendChild(list);
      }
      if (listingId) {
        const link = document.createElement("a");
        link.href = `http://localhost:8000/catalog/${listingId}#ident-title`;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "Ouvrir la fiche pour vérifier l’identité ↗";
        ocrResult.appendChild(link);
      } else {
        appendOcrLine("Cette annonce n’est pas encore associée à une fiche : envoyez-la d’abord à Pokébourse pour poursuivre sa vérification.");
      }
    } catch (_) {
      ocrResult.replaceChildren();
      appendOcrLine("Analyse impossible : vérifiez que Pokébourse locale est démarrée et que l’OCR est disponible.", "ocr-error");
    } finally {
      ocrButton.disabled = false;
    }
  });

  // 5. Suppression d'une annonce
  function deleteListing(id) {
    chrome.runtime.sendMessage({ action: "DELETE_LISTING", payload: { id } }, (response) => {
      if (response?.success) {
        currentListings = currentListings.filter(
          (item) => getItemKey(item) !== id
        );
        selectedIds.delete(id);
        renderListings();
      }
    });
  }

  // 6. Génération des lignes JSONL pour les cartes sélectionnées
  function generateJsonl(onlySelected = true) {
    const list = onlySelected
      ? currentListings.filter((item) => selectedIds.has(getItemKey(item)))
      : currentListings;

    return list
      .map((item) => {
        const payload = {
          external_id: item.external_id || `web_${Math.abs(hashCode(item.url))}`,
          name: item.name || "Carte non identifiée",
          set_name: item.set_name || "Non identifiée",
          card_number: item.card_number || null,
          price_cents: item.price_cents,
          currency: item.currency.toUpperCase(),
          seller: item.seller || null,
          url: item.url || null,
          description: item.description || null,
          raw_data: item.raw_data || null,
        };
        return JSON.stringify(payload);
      })
      .join("\n");
  }

  function validateSelectedForDirect() {
    const selected = currentListings.filter((item) => selectedIds.has(getItemKey(item)));
    if (selected.some((item) => !Number.isInteger(item.price_cents) || item.price_cents < 0 || typeof item.currency !== "string" || !/^[A-Za-z]{3}$/.test(item.currency))) {
      showMessage("Prix ou devise manquants : ouvrez la prévisualisation pour les renseigner avant l'import. Ces captures ne peuvent pas être exportées directement.", true);
      return false;
    }
    return true;
  }

  function hashCode(str) {
    let hash = 0;
    if (!str) return hash;
    for (let i = 0; i < str.length; i++) {
      hash = (hash << 5) - hash + str.charCodeAt(i);
      hash |= 0;
    }
    return hash;
  }

  // 7. Export JSONL en téléchargement direct
  btnExportJsonl.addEventListener("click", () => {
    const selectedCount = selectedIds.size;
    if (selectedCount === 0) {
      showMessage("Aucune annonce sélectionnée à exporter.", true);
      return;
    }

    if (!validateSelectedForDirect()) return;
    const jsonlContent = generateJsonl(true);
    const blob = new Blob([jsonlContent], { type: "application/x-jsonlines;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const now = new Date();
    const dateStr = now.toISOString().slice(0, 10).replace(/-/g, "");
    const timeStr = now.toTimeString().slice(0, 5).replace(/:/g, "");
    const filename = `pokebourse_capture_${dateStr}_${timeStr}.jsonl`;

    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showMessage(`Exporté : ${filename} (${selectedCount} sélectionnée(s))`);
  });

  // 8. Copie JSONL dans le presse-papier
  btnCopyJsonl.addEventListener("click", async () => {
    const selectedCount = selectedIds.size;
    if (selectedCount === 0) {
      showMessage("Aucune annonce sélectionnée à copier.", true);
      return;
    }

    if (!validateSelectedForDirect()) return;
    try {
      const jsonlContent = generateJsonl(true);
      await navigator.clipboard.writeText(jsonlContent);
      showMessage(`Copié : ${selectedCount} ligne(s) JSONL dans le presse-papier`);
    } catch (err) {
      showMessage("Erreur lors de la copie.", true);
    }
  });

  // L'envoi ouvre un formulaire vérifiable, même lorsque le prix manque.
  btnSendPokebourse.addEventListener("click", () => runAutomaticPreview());

  async function automaticOcr(item) {
    if (!item.image_url) return { message: "Image absente : OCR automatique indisponible." };
    try {
      const url = new URL(item.image_url);
      // Ne jamais laisser une image fournie par une page accéder au réseau local.
      const host = url.hostname.toLowerCase();
      const allowed = ["vinted.net", "vinted.fr", "ebayimg.com", "ebaystatic.com", "leboncoin.fr", "lbcfrance.com", "wallapop.com", "wallapopcdn.com"];
      if (url.protocol !== "https:" || url.username || url.password ||
          !allowed.some((domain) => host === domain || host.endsWith("." + domain))) throw new Error("Adresse d’image non autorisée");
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 8000);
      let response;
      let chunks = [], total = 0;
      try {
        response = await fetch(url.href, { redirect: "error", credentials: "omit", signal: controller.signal });
        if (!response.ok || !/^image\/(jpeg|png|webp)(;|$)/i.test(response.headers.get("content-type") || "")) throw new Error("Image inaccessible");
        const reader = response.body.getReader();
        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          total += value.length;
          if (total > 8 * 1024 * 1024) { await reader.cancel(); throw new Error("Image trop volumineuse"); }
          chunks.push(value);
        }
      } finally { clearTimeout(timer); }
      const data = new FormData();
      data.append("file", new Blob(chunks, {type: response.headers.get("content-type")}), "annonce-image");
      data.append("title", String(item.raw_data?.title || item.name || ""));
      const result = await fetch("http://localhost:8000/ocr/suggestions", {method: "POST", body: data});
      if (!result.ok) throw new Error("Analyse OCR indisponible");
      return await result.json();
    } catch (_) {
      return { message: "OCR automatique indisponible : image inaccessible ou analyse échouée. Vous pouvez continuer sans OCR." };
    }
  }

  async function runAutomaticPreview() {
    const selected = currentListings.filter((item) => selectedIds.has(getItemKey(item)));
    if (selected.length !== 1) {
      showMessage("Sélectionnez une annonce à la fois pour l’analyser et vérifier les données.", true, 6000);
      return;
    }
    btnSendPokebourse.disabled = true;
    showMessage("Analyse de l’image en cours, puis ouverture de Pokébourse…", false, 30000);
    try {
      const health = await fetch("http://localhost:8000/health", {cache: "no-store"});
      if (!health.ok) throw new Error("Pokébourse indisponible");
      const ocr = await automaticOcr(selected[0]);
      openPreviewTab(selected[0], ocr);
      showMessage("Analyse ouverte dans Pokébourse : vérifiez puis confirmez.");
    } catch (_) {
      showMessage("Pokébourse locale indisponible : votre capture reste dans l’extension.", true, 6000);
    } finally { btnSendPokebourse.disabled = false; }
  }

  // 9b. Prévisualisation : une annonce à la fois, ouverte dans un nouvel onglet,
  // sans enregistrement. Les captures restent dans l'extension quoi qu'il arrive.
  function formatEuros(cents) {
    if (cents === null || cents === undefined || cents === "") return "";
    const value = Number(cents);
    if (!Number.isFinite(value)) return "";
    return (value / 100).toFixed(2).replace(".", ",");
  }

  function openPreviewTab(item, ocr = null) {
    const form = document.createElement("form");
    form.method = "POST";
    form.action = "http://localhost:8000/previsualiser-capture";
    form.target = "_blank";
    form.style.display = "none";
    // Seules les données déjà capturées depuis la page ouverte sont transmises.
    const fields = {
      platform: String(item.source || "web").toLowerCase(),
      external_id: String(item.external_id || ""),
      url: String(item.url || ""),
      title: String(item.raw_data?.title || ""),
      description: String(item.description || item.raw_data?.description || ""),
      name: String(item.name || ""),
      set_name: item.set_name && item.set_name !== "Non identifiée" ? String(item.set_name) : "",
      card_number: String(item.card_number || ""),
      condition: String(item.condition || ""),
      seller: String(item.seller || ""),
      price: formatEuros(item.price_cents),
      shipping: item.shipping_cents !== null && item.shipping_cents !== undefined ? formatEuros(item.shipping_cents) : "",
      currency: String(item.currency || ""),
      image_url: String(item.image_url || ""),
      ocr_result: ocr ? JSON.stringify(ocr) : "",
    };
    Object.entries(fields).forEach(([key, value]) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = key;
      input.value = value;
      form.appendChild(input);
    });
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
  }

  btnPreviewPokebourse.addEventListener("click", async () => {
    const toPreview = currentListings.filter((item) => selectedIds.has(getItemKey(item)));
    // Comportement explicite : une prévisualisation à la fois, jamais de lot validé silencieusement.
    if (toPreview.length !== 1) {
      showMessage(
        "Sélectionnez exactement une annonce pour la prévisualiser. Les captures restent enregistrées dans l’extension.",
        true,
        6000
      );
      return;
    }
    showMessage("Connexion à Pokébourse locale…");
    try {
      const health = await fetch("http://localhost:8000/health", { cache: "no-store" });
      if (!health.ok) throw new Error("Pokébourse indisponible");
    } catch (_) {
      showMessage(
        "Pokébourse locale indisponible : vos captures restent enregistrées dans l’extension. Réessayez quand l’application est démarrée.",
        true,
        6000
      );
      return;
    }
    openPreviewTab(toPreview[0]);
    showMessage("Prévisualisation ouverte dans un nouvel onglet : vérifiez puis confirmez dans Pokébourse.");
  });

  // 10. Vider toute la liste
  btnClearAll.addEventListener("click", () => {
    if (currentListings.length === 0) return;
    if (confirm("Supprimer toutes les annonces capturées ?")) {
      chrome.runtime.sendMessage({ action: "CLEAR_LISTINGS" }, (response) => {
        if (response?.success) {
          currentListings = [];
          selectedIds.clear();
          renderListings();
          showMessage("Toute la liste a été vidée.");
        }
      });
    }
  });

  // 11. Interrupteur capture automatique
  toggleAutoCapture.addEventListener("change", () => {
    chrome.runtime.sendMessage({ action: "TOGGLE_AUTO_CAPTURE" }, (response) => {
      if (response) {
        toggleLabel.textContent = response.autoCaptureEnabled ? "Auto : Actif" : "Auto : Pause";
        showMessage(
          response.autoCaptureEnabled
            ? "Capture automatique activée"
            : "Capture automatique en pause"
        );
      }
    });
  });

  // Initialisation
  loadState();
});
