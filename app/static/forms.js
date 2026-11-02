(() => {
  const dirtyState = new WeakMap();
  const supportsUserInvalid =
    typeof CSS !== "undefined" &&
    typeof CSS.supports === "function" &&
    CSS.supports("selector(:user-invalid)");

  const syncAria = (el) => {
    if (!el || typeof el.checkValidity !== "function") return;
    if (supportsUserInvalid) {
      el.setAttribute("aria-invalid", el.matches(":user-invalid") ? "true" : "false");
    } else {
      const valid = el.checkValidity();
      el.classList.toggle("user-invalid-fallback", !valid);
      el.classList.toggle("user-valid-fallback", valid);
      if (!valid) {
        el.setAttribute("aria-invalid", "true");
      } else {
        el.removeAttribute("aria-invalid");
      }
    }
  };

  document.addEventListener(
    "blur",
    (event) => {
      const input = event.target;
      if (!input || typeof input.checkValidity !== "function") return;
      if (supportsUserInvalid) {
        syncAria(input);
        return;
      }
      const state = dirtyState.get(input) || { hasInteracted: false, hasBlurred: false };
      state.hasBlurred = true;
      dirtyState.set(input, state);
      if (state.hasInteracted) {
        syncAria(input);
      }
    },
    true
  );

  document.addEventListener("input", (event) => {
    const input = event.target;
    if (!input || typeof input.checkValidity !== "function") return;
    if (supportsUserInvalid) {
      if (input.hasAttribute("aria-invalid")) {
        syncAria(input);
      }
      return;
    }
    const state = dirtyState.get(input) || { hasInteracted: false, hasBlurred: false };
    state.hasInteracted = true;
    dirtyState.set(input, state);
    if (state.hasBlurred) {
      syncAria(input);
    }
  });

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (target instanceof HTMLInputElement && target.type === "radio") {
      const form = target.form;
      if (form && form.dataset.autosubmit === "true") {
        form.requestSubmit();
      }
    }
  });

  // Navigation mobile : sidebar repliable, bouton libellé, Échap et fermeture après navigation.
  const sidebar = document.getElementById("sidebar");
  const menuButton = document.getElementById("menu-button");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (sidebar && menuButton && backdrop) {
    const setOpen = (open) => {
      sidebar.classList.toggle("open", open);
      backdrop.classList.toggle("visible", open);
      menuButton.setAttribute("aria-expanded", open ? "true" : "false");
    };
    menuButton.addEventListener("click", () => {
      setOpen(!sidebar.classList.contains("open"));
    });
    backdrop.addEventListener("click", () => setOpen(false));
    sidebar.addEventListener("click", (event) => {
      const link = event.target.closest("a");
      if (link) setOpen(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && sidebar.classList.contains("open")) {
        setOpen(false);
        menuButton.focus();
      }
    });
    window.addEventListener("resize", () => {
      if (window.innerWidth > 900) setOpen(false);
    });
  }

  // Menus dépliables (ajout d'annonces) : Échap, clic à l'extérieur et aria-expanded.
  const popupMenus = document.querySelectorAll("details.add-menu-wrap");
  popupMenus.forEach((details) => {
    const summary = details.querySelector("summary");
    if (!summary) return;
    details.addEventListener("toggle", () => {
      summary.setAttribute("aria-expanded", details.open ? "true" : "false");
    });
  });
  document.addEventListener("click", (event) => {
    popupMenus.forEach((details) => {
      if (details.open && !details.contains(event.target)) {
        details.removeAttribute("open");
      }
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    popupMenus.forEach((details) => {
      if (!details.open) return;
      details.removeAttribute("open");
      const summary = details.querySelector("summary");
      if (summary) summary.focus();
    });
  });

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.method.toLowerCase() !== "post") return;
    if (!form.checkValidity()) return;
    const submitter = event.submitter;
    if (
      submitter instanceof HTMLButtonElement &&
      submitter.dataset.confirm &&
      !window.confirm(submitter.dataset.confirm)
    ) {
      event.preventDefault();
      return;
    }
    if (submitter instanceof HTMLButtonElement) {
      submitter.disabled = true;
    }
  });
})();
