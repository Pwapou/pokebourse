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

  // 2. Conversion d'un prix texte en centimes sans calcul en virgule flottante
  function parsePriceToCents(priceText) {
    if (!priceText) return null;
    const cleaned = priceText
      .replace(/\s+/g, "")
      .replace(/[^\d.,]/g, "")
      .replace(",", ".");
    if (!/^\d+(?:\.\d+)?$/.test(cleaned) || /-/.test(priceText)) return null;
    const [whole, fraction = ""] = cleaned.split(".");
    const cents = BigInt(whole) * 100n + BigInt((fraction + "00").slice(0, 2)) + (fraction.length > 2 && fraction[2] >= "5" ? 1n : 0n);
    return cents <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(cents) : null;
  }

  function extractCurrency(value) {
    if (!value) return null;
    const text = String(value).trim();
    if (/^[a-z]{3}$/i.test(text)) return text.toUpperCase();
    if (/€|\b(?:eur|euros?)\b/i.test(text)) return "EUR";
    if (/£|\bgbp\b/i.test(text)) return "GBP";
    return null;
  }

  const CARD_QUANTITY_SOURCE = "(?:[1-9]\\d*|une?|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)";
  const CARD_SELECTION_PATTERN = /\bcartes?\s+(?:pok[ée]mon\s+)?(?:au\s+choix|[àa]\s+choisir)\b/i;
  const NEGATED_LOT_PATTERN = new RegExp(`\\b(?:pas\\s+(?:un|de)\\s+|sans\\s+(?:un\\s+)?)(?:lot|lots)\\b(?:\\s+(?:de\\s+)?(?:${CARD_QUANTITY_SOURCE}\\s+)?cartes?(?:\\s+pok[ée]mon)?|\\s+pok[ée]mon)?`, "gi");
  const MULTI_CARD_PATTERN = /\b(?:[2-9]|[1-9]\d+|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)\s*cartes?\s+pok[ée]mon\b/i;
  // « pack » seul n'est pas une preuve de produit scellé (ex. Gem Pack 2).
  const PACK_PATTERN = /\bpacks?(?:\s+\d{1,3})?\s+(?:pok[ée]mon|scell[ée]s?|sous\s+blister|de\s+(?:\d+\s+)?(?:boosters?|cartes?))(?![A-Za-zÀ-ÿ0-9_])/i;
  const SERIAL_NUMBER_PATTERN = /\b(?:num[ée]ro\s+de\s+s[ée]rie|n[°o]\s*(?:de\s+)?s[ée]rie|serial(?:\s+(?:number|no))?|num[ée]ro\s+de\s+certificat(?:ion)?)\s*[:#=-]?\s*[a-z0-9]+(?:[/-][a-z0-9]+)*\b/gi;
  const LOT_PATTERNS = [
    new RegExp(`\\b(?:lot|lots)\\s+(?:de\\s+)?(?:${CARD_QUANTITY_SOURCE}\\s+)?cartes?\\b`, "i"),
    /\b(?:collection|classeur|vrac|album)\s+(?:de\s+)?cartes?\b/i,
    MULTI_CARD_PATTERN,
    /\b(?:display|booster|coffret|tin|deck|pokebox|tripack)\b/i,
    PACK_PATTERN,
    /\blot\s+pok[ée]mon\b/i,
    /\bcartes?\s+diverses\b/i,
    new RegExp(`\\bvendu(?:e|s|es)?\\s+avec\\s+${CARD_QUANTITY_SOURCE}\\s+cartes?\\b`, "i"),
    new RegExp(`(?:\\bavec\\s+|\\+\\s*)${CARD_QUANTITY_SOURCE}\\s+cartes?\\s+(?:en\\s+plus|suppl[ée]mentaires?|offertes?)\\b`, "i")
  ];

  // Mêmes exclusions qu'au backend ; ce garde-fou ne décide pas de l'identité.
  function isLotContext(text) {
    const exclusions = [...text.matchAll(NEGATED_LOT_PATTERN), ...text.matchAll(SERIAL_NUMBER_PATTERN)];
    const isSelection = CARD_SELECTION_PATTERN.test(text);
    return LOT_PATTERNS.some((pattern) => {
      if (isSelection && pattern === MULTI_CARD_PATTERN) return false;
      return Array.from(text.matchAll(new RegExp(pattern.source, "gi"))).some((match) => {
        const start = match.index;
        if (exclusions.some((excluded) => start < excluded.index + excluded[0].length && start + match[0].length > excluded.index)) return false;
        return !/\/\s*$/.test(text.slice(0, start));
      });
    });
  }

  const FAMOUS_POKEMON = [
    "dracaufeu", "charizard", "pikachu", "tortank", "blastoise", "florizarre",
    "venusaur", "mewtwo", "mew", "evoli", "eevee", "noctali", "umbreon",
    "mentali", "espeon", "voltali", "pyroli", "aquali", "nymphali", "phyllali",
    "givrali", "rayquaza", "lugia", "ho-oh", "gengar", "ectoplasma",
    "dracolosse", "galvagon", "lucario", "roucarnage", "salameche", "reptincel",
    "carapuce", "carabaffe", "bulbizarre", "herbizarre", "groudon", "kyogre",
    "tyranocif", "leviator", "alakazam", "ronflex", "gardevoir", "carchacrok",
    "dialga", "palkia", "giratina", "arceus", "darkrai", "mimiqui", "miraidon",
    "koraidon", "sulfura", "electhor", "artikodin", "suicune", "entei",
    "raikou", "deoxys", "celebi", "jirachi", "latios", "latias", "zacian",
    "zamazenta"
  ];

  const GENERIC_HEAD_WORDS = new Set([
    "album", "annonce", "article", "booster", "carte", "cartes", "classeur",
    "coffret", "collection", "deck", "display", "edition", "figurine", "item",
    "lot", "lots", "objet", "pack", "pokebox", "pokemon", "promo", "ref",
    "reference", "serie", "set", "tin", "tripack", "vrac"
  ]);

  const GRADING_COMPANY_SOURCE = "psa|pca|bgs|cgc|sgs|collect[\\s'’`]*aura";
  const GRADING_PATTERN = new RegExp(
    `\\b(?:${GRADING_COMPANY_SOURCE})\\s*(?:10|[1-9](?:\\.5)?)\\b(?![.,]\\d)`,
    "gi"
  );
  const GRADING_COMPANY_BEFORE_PATTERN = new RegExp(
    `\\b(?:${GRADING_COMPANY_SOURCE})\\s*$`,
    "i"
  );
  const CURRENCY_BEFORE_PATTERN = /(?:€|\b(?:eur|euros?))\s*$/i;
  const CURRENCY_OR_PERCENT_AFTER_PATTERN = /^\s*(?:€|%|(?:eur|euros?)\b)/i;

  function normalizePlainText(text) {
    if (!text) return "";
    return text
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/['’`]/g, " ")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function escapeRegExp(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function hasPotentialCardName(text) {
    const norm = normalizePlainText(text);
    if (!norm) return false;

    for (const pk of FAMOUS_POKEMON) {
      if (new RegExp(`\\b${escapeRegExp(pk)}\\b`).test(norm)) {
        return true;
      }
    }

    const cleanTitle = text.replace(/^\s*(?:carte\s+)?pok[ée]mon\s+/i, "").trim();
    if (cleanTitle.includes("-")) {
      const candidate = cleanTitle
        .split("-")[0]
        .replace(/\b\d{1,3}\/\d{1,3}\b/g, "")
        .trim();
      if (candidate.length >= 3 && !/^\d+$/.test(candidate)) {
        const firstWordNorm = normalizePlainText(candidate.split(/\s+/)[0]);
        if (firstWordNorm && !GENERIC_HEAD_WORDS.has(firstWordNorm)) {
          return true;
        }
      }
    }

    const cleanedStart = cleanTitle
      .replace(
        /^(?:superbe|magnifique|rare|tr[èe]s\s+rare|ancienne?|authentique|officielle?|ultra\s+rare|vintage|originale?|vends?|vente|belle|v[ée]ritable)\s+/i,
        ""
      )
      .trim();
    const words = cleanedStart.split(/\s+/);
    if (
      words.length > 0 &&
      words[0].length >= 3 &&
      /^[A-Za-zÀ-ÿ]+$/.test(words[0]) &&
      !GENERIC_HEAD_WORDS.has(normalizePlainText(words[0]))
    ) {
      return true;
    }
    return false;
  }

  // 3. Extraction d'un numéro de carte potentiel (fraction, préfixe ou numéro isolé sous garde-fous)
  function extractCardNumber(text) {
    if (!text) return null;

    const serialSpans = Array.from(text.matchAll(SERIAL_NUMBER_PATTERN));
    const isSerial = (match) => serialSpans.some((serial) => match.index < serial.index + serial[0].length && match.index + match[0].length > serial.index);
    const fracMatch = Array.from(text.matchAll(/\b([A-Za-z0-9]{1,4})\s*\/\s*([0-9]{2,3})\b/g)).find((match) => !isSerial(match));
    if (fracMatch) {
      return `${fracMatch[1]}/${fracMatch[2]}`;
    }

    const prefixMatch = Array.from(text.matchAll(/(?:#|n°|no\.?|num[ée]ro)\s*([A-Za-z0-9]{1,4})\b/gi)).find((match) => !isSerial(match));
    if (prefixMatch) {
      return prefixMatch[1];
    }

    if (isLotContext(text) || CARD_SELECTION_PATTERN.test(text)) {
      return null;
    }

    const setName = extractSetName(text);
    const hasSet = setName !== "Non identifiée";
    const hasName = hasPotentialCardName(text);
    if (!hasName && !hasSet) {
      return null;
    }

    const gradingSpans = [];
    GRADING_PATTERN.lastIndex = 0;
    let gMatch;
    while ((gMatch = GRADING_PATTERN.exec(text)) !== null) {
      gradingSpans.push([gMatch.index, gMatch.index + gMatch[0].length]);
    }

    const simplePattern = /(?<![\d.])(\d{2,3})(?![\d.])/g;
    const allSimpleMatches = Array.from(text.matchAll(simplePattern));

    for (const match of allSimpleMatches) {
      if (isSerial(match)) continue;
      const rawNum = match[1];
      const start = match.index;
      const end = start + rawNum.length;
      const value = parseInt(rawNum, 10);

      if (value === 0 || (value >= 1900 && value <= 2099) || value > 300) {
        continue;
      }

      if (start > 0 && /[A-Za-zÀ-ÿ]/.test(text[start - 1])) {
        continue;
      }
      if (end < text.length && /[A-Za-zÀ-ÿ]/.test(text[end])) {
        continue;
      }
      if (start >= 2 && text[start - 1] === "," && /\d/.test(text[start - 2])) {
        continue;
      }
      if (end + 1 < text.length && text[end] === "," && /\d/.test(text[end + 1])) {
        continue;
      }

      const before = text.slice(0, start);
      const after = text.slice(end);

      if (/\/\s*$/.test(before) || /^\s*\//.test(after)) {
        continue;
      }
      if (CURRENCY_BEFORE_PATTERN.test(before) || CURRENCY_OR_PERCENT_AFTER_PATTERN.test(after)) {
        continue;
      }
      if (gradingSpans.some(([gStart, gEnd]) => start < gEnd && end > gStart)) {
        continue;
      }
      if (GRADING_COMPANY_BEFORE_PATTERN.test(before)) {
        continue;
      }
      if (!hasName && setName === rawNum && allSimpleMatches.length < 2) {
        continue;
      }

      return rawNum;
    }

    return null;
  }

  // 4. Extraction d'une extension potentielle
  function extractSetName(text) {
    if (!text) return "Non identifiée";
    const sets = [
      ["Set de Base", "set de base"],
      ["Set de Base", "base set"],
      ["151", "151"],
      ["Ténèbres Embrasées", "tenebres embrasees"],
      ["Flammes Obsidiennes", "flammes obsidiennes"],
      ["Évolutions", "evolutions"],
      ["Évolution Céleste", "evolution celeste"],
      ["Origine Perdue", "origine perdue"],
      ["Zénith Suprême", "zenith supreme"],
      ["Tempête Argentée", "tempete argentee"],
      ["Forces Temporelles", "forces temporelles"],
      ["Mascarade Crépusculaire", "mascarade crepusculaire"],
      ["Couronne Stellaire", "couronne stellaire"],
      ["Étincelles Déferlantes", "etincelles deferlantes"],
      ["Stars Étincelantes", "stars etincelantes"],
      ["Voltage Éclatant", "voltage eclatant"]
    ];
    const norm = normalizePlainText(text);
    for (const [official, key] of sets) {
      if (new RegExp(`\\b${escapeRegExp(key)}\\b`).test(norm)) {
        return official;
      }
    }
    return "Non identifiée";
  }

  // 5. Extracteur Vinted
  function extractVinted() {
    const isItemPage = window.location.pathname.startsWith("/items/");
    if (isItemPage) {
      const titleElem = document.querySelector("h1") || document.querySelector("meta[property='og:title']");
      const title = (titleElem?.textContent || titleElem?.content || "").trim();
      if (!title) return null;

      // Les pages Vinted actuelles exposent les données de l'annonce en JSON-LD.
      // Ne pas utiliser un bloc générique « description » qui peut contenir
      // le texte de protection acheteur ou une annonce recommandée.
      let product = null;
      for (const script of document.querySelectorAll("script[type='application/ld+json']")) {
        try {
          const data = JSON.parse(script.textContent);
          const entries = Array.isArray(data) ? data : [data];
          product = entries.find((item) => item && (item["@type"] === "Product" || (Array.isArray(item["@type"]) && item["@type"].includes("Product")))) || null;
          if (product) break;
        } catch (_) { /* Bloc structuré illisible : continuer avec la page. */ }
      }
      const descElem = document.querySelector("[itemprop='description']") ||
                       document.querySelector("[data-testid='item-description']") ||
                       document.querySelector(".details-list--description") ||
                       document.querySelector(".item-description");
      const description = (typeof product?.description === "string" ? product.description.trim() : "") || descElem?.textContent?.trim() || "";
      const fullContext = `${title} ${description}`.trim();

      if (!isPokemonContext(fullContext) && !isPokemonContext(document.title)) return null;

      const offers = product?.offers;
      const offer = Array.isArray(offers) ? (offers.length === 1 ? offers[0] : null) : offers;
      const priceElem = document.querySelector("[data-testid='item-price']") || document.querySelector("[data-testid='price']") || document.querySelector("h2[class*='price']");
      const priceText = priceElem?.textContent || "";
      const structuredPrice = offer && offer.price != null ? parsePriceToCents(String(offer.price)) : null;
      const priceCents = structuredPrice ?? parsePriceToCents(priceText);
      const currency = extractCurrency(offer?.priceCurrency) || extractCurrency(priceText);

      const sellerElem = document.querySelector("[data-testid*='user']") || document.querySelector("a[href*='/member/']");
      const seller = sellerElem?.textContent?.trim() || null;

      const imgElem = document.querySelector("meta[property='og:image']") || document.querySelector("img[src*='images.vinted.net']");
      const structuredImage = Array.isArray(product?.image) ? product.image[0] : product?.image;
      const imageUrl = (typeof structuredImage === "string" ? structuredImage : null) || imgElem?.content || imgElem?.src || null;

      const idMatch = window.location.pathname.match(/\/items\/(\d+)/);
      const externalId = idMatch ? `vinted_${idMatch[1]}` : `vinted_${Date.now()}`;

      return [{
        external_id: externalId,
        name: title,
        set_name: extractSetName(fullContext),
        card_number: extractCardNumber(fullContext),
        price_cents: priceCents,
        currency,
        seller,
        url: window.location.href,
        image_url: imageUrl,
        description,
        raw_data: { title, description },
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
      if (!title) return null;

      const descElem = document.querySelector("[data-qa-id='adview_description_container']") ||
                       document.querySelector("[data-test-id='adview_description']") ||
                       document.querySelector("[itemprop='description']");
      const description = descElem?.textContent?.trim() || "";
      const fullContext = `${title} ${description}`.trim();

      if (!isPokemonContext(fullContext) && !isPokemonContext(document.title)) return null;

      const priceElem = document.querySelector("[data-qa-id='adview_price']") || document.querySelector("[class*='price']");
      const priceText = priceElem?.textContent || "";
      const priceCents = parsePriceToCents(priceText);

      const sellerElem = document.querySelector("[data-qa-id='adview_owner']") || document.querySelector("a[href*='/profile/']");
      const seller = sellerElem?.textContent?.trim() || null;

      const imgElem = document.querySelector("meta[property='og:image']") || document.querySelector("img[src*='leboncoin']");
      const imageUrl = imgElem?.content || imgElem?.src || null;

      const idMatch = window.location.pathname.match(/\/ad\/(?:.*\/)?(\d+)/);
      const externalId = idMatch ? `lbc_${idMatch[1]}` : `lbc_${Date.now()}`;

      return [{
        external_id: externalId,
        name: title,
        set_name: extractSetName(fullContext),
        card_number: extractCardNumber(fullContext),
        price_cents: priceCents,
        currency: extractCurrency(priceText),
        seller,
        url: window.location.href,
        image_url: imageUrl,
        description,
        raw_data: { title, description },
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
    let currency = null;
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
            if (offer.price != null) priceCents = parsePriceToCents(String(offer.price));
            currency = extractCurrency(offer.priceCurrency);
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
      const ogPrice = document.querySelector("meta[property='og:price:amount']")?.content || document.querySelector("meta[property='product:price:amount']")?.content;
      if (ogPrice) {
        priceCents = parsePriceToCents(ogPrice);
        currency = extractCurrency(document.querySelector("meta[property='og:price:currency']")?.content || document.querySelector("meta[property='product:price:currency']")?.content) || extractCurrency(ogPrice);
      } else {
        // Sélecteur générique de prix
        const priceElems = document.querySelectorAll("[class*='price'], [id*='price'], .amount");
        for (const el of priceElems) {
          const cents = parsePriceToCents(el.textContent);
          if (cents !== null && cents > 0) {
            priceCents = cents;
            currency = extractCurrency(el.textContent);
            break;
          }
        }
      }
    }

    if (!imageUrl) {
      imageUrl = document.querySelector("meta[property='og:image']")?.content || null;
    }

    if (!title) return null;

    const metaDesc = document.querySelector("meta[name='description']")?.content ||
                     document.querySelector("meta[property='og:description']")?.content || "";
    const fullContext = `${title} ${metaDesc}`.trim();

    const hostname = window.location.hostname.replace(/^www\./, "");
    const cleanId = `${hostname}_${Math.abs(hashCode(window.location.href))}`;

    return [{
      external_id: cleanId,
      name: title,
      set_name: extractSetName(fullContext),
      card_number: extractCardNumber(fullContext),
      price_cents: priceCents,
      currency,
      seller,
      url: window.location.href,
      image_url: imageUrl,
      description: metaDesc,
      raw_data: { title, description: metaDesc },
      source: hostname.includes("vinted")
        ? "vinted"
        : hostname.includes("leboncoin")
        ? "leboncoin"
        : hostname.includes("ebay")
        ? "ebay"
        : hostname.includes("wallapop")
        ? "wallapop"
        : "web"
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

    const priceFormatted = listing.price_cents == null ? "Prix inconnu" : (listing.price_cents / 100).toFixed(2).replace(".", ",") + " " + (listing.currency || "(devise inconnue)");
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

  if (typeof document !== "undefined" && typeof window !== "undefined") {
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

    if (document.body) {
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (typeof module === "object" && module && module.exports) {
    module.exports = {
      extractCardNumber,
      isLotContext,
      extractSetName,
      parsePriceToCents,
      isPokemonContext
    };
  }
})();
