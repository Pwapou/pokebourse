// Content script pour Pokébourse Capture
// Détecte les cartes Pokémon sur les sites visités et extrait les informations d'annonces.

(function () {
  "use strict";

  // Mots-clés indicateurs Pokémon
  const POKEMON_KEYWORDS = [
    "pokemon", "pokémon", "pikachu", "dracaufeu", "charizard", "mewtwo",
    "tortank", "blastoise", "florizarre", "venusaur", "evoli", "eevee",
    "noctali", "umbreon", "mentali", "rayquaza", "lugia", "ectoplasma", "gengar",
    "tcgdex", "carte pokemon", "cartes pokemon", "carte pokémon", "cartes pokémon"
  ];

  const processedUrls = new Set();
  let lastToastTime = 0;

  // 1. Vérification si la page ou le contexte concerne Pokémon
  function isPokemonContext(text) {
    if (!text) return false;
    const lower = text.toLowerCase();
    return POKEMON_KEYWORDS.some((kw) => lower.includes(kw));
  }

  // 2. Conversion sécurisée d'un prix texte en centimes d'euros
  function parsePriceToCents(priceText) {
    if (!priceText) return null;
    const cleaned = priceText
      .replace(/\s+/g, "")
      .replace(/[^\d.,]/g, "")
      .replace(",", ".");
    const val = parseFloat(cleaned);
    if (isNaN(val) || val < 0) return null;
    return Math.round(val * 100);
  }

  // 3. Extraction d'un numéro de carte potentiel (ex: 4/102, 136/189, 025/165)
  function extractCardNumber(text) {
    if (!text) return null;
    const match = text.match(/\b([A-Za-z0-9]{1,4})\s*\/\s*([0-9]{2,3})\b/);
    return match ? `${match[1]}/${match[2]}` : null;
  }

  // 4. Extraction d'une extension potentielle
  function extractSetName(text) {
    if (!text) return "Non identifiée";
    const sets = [
      "Set de Base", "151", "Ténèbres Embrasées", "Flammes Obsidiennes",
      "Évolutions", "Évolution Céleste", "Origine Perdue", "Zénith Suprême",
      "Forces Temporelles", "Mascarade Crépusculaire", "Couronne Stellaire",
      "Étincelles Déferlantes", "Stars Étincelantes", "Voltage Éclatant"
    ];
    const lower = text.toLowerCase();
    for (const s of sets) {
      if (lower.includes(s.toLowerCase())) return s;
    }
    return "Non identifiée";
  }

  // 5. Extracteur Vinted
  function extractVinted() {
    const isItemPage = window.location.pathname.startsWith("/items/");
    if (isItemPage) {
      const titleElem = document.querySelector("h1") || document.querySelector("meta[property='og:title']");
      const title = (titleElem?.textContent || titleElem?.content || "").trim();
      if (!isPokemonContext(title) && !isPokemonContext(document.title)) return null;

      const priceElem = document.querySelector("[data-testid*='price']") || document.querySelector("h2[class*='price']");
      const priceText = priceElem?.textContent || "";
      const priceCents = parsePriceToCents(priceText);
      if (priceCents === null) return null;

      const sellerElem = document.querySelector("[data-testid*='user']") || document.querySelector("a[href*='/member/']");
      const seller = sellerElem?.textContent?.trim() || "Vendeur Vinted";

      const imgElem = document.querySelector("meta[property='og:image']") || document.querySelector("img[src*='images.vinted.net']");
      const imageUrl = imgElem?.content || imgElem?.src || null;

      const idMatch = window.location.pathname.match(/\/items\/(\d+)/);
      const externalId = idMatch ? `vinted_${idMatch[1]}` : `vinted_${Date.now()}`;

      return [{
        external_id: externalId,
        name: title,
        set_name: extractSetName(title),
        card_number: extractCardNumber(title),
        price_cents: priceCents,
        currency: "EUR",
        seller,
        url: window.location.href,
        image_url: imageUrl,
        source: "vinted"
      }];
    }
    return null;
  }

  // 6. Extracteur Leboncoin
  function extractLeboncoin() {
    const isAdPage = window.location.pathname.startsWith("/ad/");
    if (isAdPage) {
      const titleElem = document.querySelector("h1") || document.querySelector("[data-qa-id='adview_title']");
      const title = titleElem?.textContent?.trim() || "";
      if (!isPokemonContext(title) && !isPokemonContext(document.title)) return null;

      const priceElem = document.querySelector("[data-qa-id='adview_price']") || document.querySelector("[class*='price']");
      const priceCents = parsePriceToCents(priceElem?.textContent || "");
      if (priceCents === null) return null;

      const sellerElem = document.querySelector("[data-qa-id='adview_owner']") || document.querySelector("a[href*='/profile/']");
      const seller = sellerElem?.textContent?.trim() || "Vendeur Leboncoin";

      const imgElem = document.querySelector("meta[property='og:image']") || document.querySelector("img[src*='leboncoin']");
      const imageUrl = imgElem?.content || imgElem?.src || null;

      const idMatch = window.location.pathname.match(/\/ad\/(?:.*\/)?(\d+)/);
      const externalId = idMatch ? `lbc_${idMatch[1]}` : `lbc_${Date.now()}`;

      return [{
        external_id: externalId,
        name: title,
        set_name: extractSetName(title),
        card_number: extractCardNumber(title),
        price_cents: priceCents,
        currency: "EUR",
        seller,
        url: window.location.href,
        image_url: imageUrl,
        source: "leboncoin"
      }];
    }
    return null;
  }

  // 7. Extracteur générique (Schema.org / OpenGraph / Heuristique)
  function extractGeneric() {
    const pageText = `${document.title} ${document.querySelector("meta[name='description']")?.content || ""}`;
    if (!isPokemonContext(pageText)) return null;

    let title = "";
    let priceCents = null;
    let imageUrl = null;
    let seller = null;

    // Tentative via Schema.org Product
    const jsonLdScripts = document.querySelectorAll("script[type='application/ld+json']");
    for (const script of jsonLdScripts) {
      try {
        const data = JSON.parse(script.textContent);
        const item = Array.isArray(data) ? data.find((d) => d["@type"] === "Product") : data;
        if (item && (item["@type"] === "Product" || item.name)) {
          title = item.name || "";
          if (item.offers) {
            const offer = Array.isArray(item.offers) ? item.offers[0] : item.offers;
            if (offer.price) priceCents = parsePriceToCents(String(offer.price));
            if (offer.seller?.name) seller = offer.seller.name;
          }
          if (item.image) {
            imageUrl = Array.isArray(item.image) ? item.image[0] : item.image;
          }
          break;
        }
      } catch (e) {
        // Ignorer JSON mal formé
      }
    }

    // Repli sur OpenGraph et DOM
    if (!title) {
      title = document.querySelector("meta[property='og:title']")?.content ||
              document.querySelector("h1")?.textContent?.trim() || "";
    }
    if (!isPokemonContext(title)) return null;

    if (priceCents === null) {
      const ogPrice = document.querySelector("meta[property='og:price:amount']")?.content;
      if (ogPrice) {
        priceCents = parsePriceToCents(ogPrice);
      } else {
        // Sélecteur générique de prix
        const priceElems = document.querySelectorAll("[class*='price'], [id*='price'], .amount");
        for (const el of priceElems) {
          const cents = parsePriceToCents(el.textContent);
          if (cents !== null && cents > 0) {
            priceCents = cents;
            break;
          }
        }
      }
    }

    if (!imageUrl) {
      imageUrl = document.querySelector("meta[property='og:image']")?.content || null;
    }

    if (!title || priceCents === null) return null;

    const hostname = window.location.hostname.replace(/^www\./, "");
    const cleanId = `${hostname}_${Math.abs(hashCode(window.location.href))}`;

    return [{
      external_id: cleanId,
      name: title,
      set_name: extractSetName(title),
      card_number: extractCardNumber(title),
      price_cents: priceCents,
      currency: "EUR",
      seller: seller || hostname,
      url: window.location.href,
      image_url: imageUrl,
      source: hostname.includes("vinted") ? "vinted" : hostname.includes("leboncoin") ? "leboncoin" : "web"
    }];
  }

  function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = (hash << 5) - hash + str.charCodeAt(i);
      hash |= 0;
    }
    return hash;
  }

  // 8. Affichage d'un toast visuel discret
  function showToast(listing) {
    const now = Date.now();
    if (now - lastToastTime < 2000) return; // Évite les spams
    lastToastTime = now;

    const existingToast = document.getElementById("pokebourse-toast");
    if (existingToast) existingToast.remove();

    const toast = document.createElement("div");
    toast.id = "pokebourse-toast";
    toast.className = "pokebourse-toast-container";

    const priceFormatted = (listing.price_cents / 100).toFixed(2).replace(".", ",") + " €";
    toast.innerHTML = `
      <div class="pokebourse-toast-content">
        <div class="pokebourse-toast-icon">⚡</div>
        <div class="pokebourse-toast-body">
          <span class="pokebourse-toast-title">Pokébourse Capture</span>
          <span class="pokebourse-toast-desc">${escapeHtml(listing.name.slice(0, 42))} · <b>${priceFormatted}</b></span>
        </div>
      </div>
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("pokebourse-toast-fadeout");
      setTimeout(() => toast.remove(), 400);
    }, 3200);
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // 9. Analyse et déclenchement de la capture
  function scanPage() {
    const currentUrl = window.location.href;
    if (processedUrls.has(currentUrl)) return;

    let listings = null;
    const host = window.location.hostname;

    if (host.includes("vinted.")) {
      listings = extractVinted();
    } else if (host.includes("leboncoin.")) {
      listings = extractLeboncoin();
    } else {
      listings = extractGeneric();
    }

    if (listings && listings.length > 0) {
      processedUrls.add(currentUrl);

      chrome.runtime.sendMessage(
        { action: "CAPTURE_LISTINGS", payload: listings },
        (response) => {
          if (response && response.success && response.addedCount > 0) {
            showToast(listings[0]);
          }
        }
      );
    }
  }

  // Exécution au chargement
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scanPage);
  } else {
    scanPage();
  }

  // Observer les changements d'URL ou de DOM pour les applications monopages (SPA)
  let lastHref = window.location.href;
  const observer = new MutationObserver(() => {
    if (window.location.href !== lastHref) {
      lastHref = window.location.href;
      setTimeout(scanPage, 1000);
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
})();
