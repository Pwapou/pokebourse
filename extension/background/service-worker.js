// Service Worker Manifest V3 pour Pokébourse Capture

const BADGE_COLOR = "#625df5"; // Couleur Indigo Pokébourse

// Initialisation à l'installation
chrome.runtime.onInstalled.addListener(async () => {
  const { listings, autoCaptureEnabled } = await chrome.storage.local.get([
    "listings",
    "autoCaptureEnabled",
  ]);

  if (!listings) {
    await chrome.storage.local.set({ listings: [] });
  }
  if (autoCaptureEnabled === undefined) {
    await chrome.storage.local.set({ autoCaptureEnabled: true });
  }

  await updateBadge((listings || []).length);
  console.log("Pokébourse Capture initialisé.");
});

// Mise à jour du badge numérique sur l'icône de l'extension
async function updateBadge(count) {
  try {
    const text = count > 0 ? String(count > 99 ? "99+" : count) : "";
    await chrome.action.setBadgeText({ text });
    await chrome.action.setBadgeBackgroundColor({ color: BADGE_COLOR });
  } catch (error) {
    console.error("Erreur mise à jour badge:", error);
  }
}

// Gestion des messages depuis les content scripts et le popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      const { action, payload } = message || {};

      if (action === "CAPTURE_LISTINGS") {
        const { autoCaptureEnabled = true, listings = [] } =
          await chrome.storage.local.get(["autoCaptureEnabled", "listings"]);

        if (!autoCaptureEnabled) {
          sendResponse({ success: false, reason: "Capture automatique désactivée" });
          return;
        }

        const newListings = Array.isArray(payload) ? payload : [payload];
        let addedCount = 0;

        // Index des annonces existantes pour déduplication stricte
        const existingKeys = new Set(
          listings.map((item) => `${item.source || "web"}::${item.external_id || item.url}`)
        );

        const updatedListings = [...listings];

        for (const item of newListings) {
          // Une capture partielle peut être complétée dans la prévisualisation.
          const hasValidPrice =
            item && (item.price_cents == null || (Number.isInteger(item.price_cents) && item.price_cents >= 0));
          const hasTitle =
            (typeof item?.raw_data?.title === "string" && item.raw_data.title.trim()) ||
            (typeof item?.name === "string" && item.name.trim());
          if (
            !item ||
            !hasTitle ||
            !hasValidPrice ||
            !item.url
          )
            continue;

          const key = `${item.source || "web"}::${item.external_id || item.url}`;
          if (!existingKeys.has(key)) {
            existingKeys.add(key);
            updatedListings.unshift({
              ...item,
              captured_at: new Date().toISOString(),
            });
            addedCount++;
          }
        }

        if (addedCount > 0) {
          // Limiter aux 500 dernières annonces pour préserver le quota de stockage
          const trimmed = updatedListings.slice(0, 500);
          await chrome.storage.local.set({ listings: trimmed });
          await updateBadge(trimmed.length);
        }

        sendResponse({
          success: true,
          addedCount,
          totalCount: updatedListings.length,
        });
      } else if (action === "GET_LISTINGS") {
        const { listings = [] } = await chrome.storage.local.get("listings");
        sendResponse({ listings });
      } else if (action === "CLEAR_LISTINGS") {
        await chrome.storage.local.set({ listings: [] });
        await updateBadge(0);
        sendResponse({ success: true });
      } else if (action === "DELETE_LISTING") {
        const { id } = payload || {};
        const { listings = [] } = await chrome.storage.local.get("listings");
        const filtered = listings.filter(
          (item) => item.external_id !== id && item.url !== id
        );
        await chrome.storage.local.set({ listings: filtered });
        await updateBadge(filtered.length);
        sendResponse({ success: true, totalCount: filtered.length });
      } else if (action === "GET_STATUS") {
        const { autoCaptureEnabled = true, listings = [] } =
          await chrome.storage.local.get(["autoCaptureEnabled", "listings"]);
        sendResponse({ autoCaptureEnabled, count: listings.length });
      } else if (action === "TOGGLE_AUTO_CAPTURE") {
        const { autoCaptureEnabled = true } = await chrome.storage.local.get(
          "autoCaptureEnabled"
        );
        const newState = !autoCaptureEnabled;
        await chrome.storage.local.set({ autoCaptureEnabled: newState });
        sendResponse({ autoCaptureEnabled: newState });
      } else {
        sendResponse({ error: "Action inconnue" });
      }
    } catch (err) {
      console.error("Erreur service worker:", err);
      sendResponse({ error: err.message });
    }
  })();

  return true; // Garde le canal de communication ouvert pour la réponse asynchrone
});
