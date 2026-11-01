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
  const btnClearAll = document.getElementById("btn-clear-all");

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
    } else {
      checkboxSelectAll.disabled = false;
      checkboxSelectAll.checked = selectedCount === total;
      btnSendPokebourse.disabled = selectedCount === 0;
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

      const priceFormatted = (item.price_cents / 100).toFixed(2).replace(".", ",") + " €";
      const sourceClass = (item.source || "web").toLowerCase();

      let thumbHtml = `<div class="listing-thumb-placeholder">🎴</div>`;
      if (item.image_url) {
        thumbHtml = `<img src="${escapeHtml(item.image_url)}" class="listing-thumb" alt="Carte" onerror="this.outerHTML='<div class=\\'listing-thumb-placeholder\\'>🎴</div>'">`;
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
              <a href="${escapeHtml(ev.url_add_cote || 'http://localhost:8000/profitability#cotes')}" target="_blank" rel="noopener noreferrer" class="eval-link-cote">+ Renseigner une cote Cardmarket / eBay</a>
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
    div.textContent = str;
    return div.innerHTML;
  }

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
          price_cents: Number(item.price_cents) || 0,
          currency: item.currency || "EUR",
          seller: item.seller || null,
          url: item.url || null,
          description: item.description || null,
          raw_data: item.raw_data || null,
        };
        return JSON.stringify(payload);
      })
      .join("\n");
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

    try {
      const jsonlContent = generateJsonl(true);
      await navigator.clipboard.writeText(jsonlContent);
      showMessage(`Copié : ${selectedCount} ligne(s) JSONL dans le presse-papier`);
    } catch (err) {
      showMessage("Erreur lors de la copie.", true);
    }
  });

  // 9. Envoi direct à l'instance Pokébourse locale avec affichage du prix de revente
  btnSendPokebourse.addEventListener("click", async () => {
    const toSend = currentListings.filter((item) => selectedIds.has(getItemKey(item)));
    if (toSend.length === 0) {
      showMessage("Veuillez sélectionner au moins une carte à envoyer.", true);
      return;
    }

    showMessage(`Connexion à Pokébourse locale (${toSend.length} carte(s))...`);

    try {
      const jsonlContent = generateJsonl(true);
      const formData = new FormData();
      const blob = new Blob([jsonlContent], { type: "text/plain" });
      formData.append("file", blob, "chrome_capture.jsonl");

      const response = await fetch("http://localhost:8000/imports", {
        method: "POST",
        headers: {
          Accept: "application/json",
        },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json().catch(() => ({}));
        const count = data.imported ?? toSend.length;

        // Associe les évaluations financières retournées aux cartes envoyées
        let cotationsTrouvees = 0;
        if (Array.isArray(data.evaluations)) {
          data.evaluations.forEach((ev) => {
            const match = currentListings.find(
              (it) => it.external_id === ev.external_id || it.url === ev.external_id
            );
            if (match) {
              match.evaluation = ev;
              if (ev.has_reference_price) {
                cotationsTrouvees++;
              }
            }
          });
        }

        renderListings();

        if (cotationsTrouvees > 0) {
          showMessage(
            `✓ ${count} carte(s) analysée(s) ! Revente et rentabilité calculées (voir détails ci-dessous).`
          );
        } else {
          showMessage(
            `✓ ${count} carte(s) importée(s) dans Pokébourse ! Cote de revente non renseignée pour ces cartes.`
          );
        }
      } else {
        const errorData = await response.json().catch(() => ({}));
        const detail = errorData.detail || `code ${response.status}`;
        showMessage(`Échec de l'import : ${detail}`, true);
      }
    } catch (err) {
      showMessage(
        "Pokébourse locale injoignable (http://localhost:8000). Vérifiez que docker compose est lancé !",
        true
      );
    }
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
