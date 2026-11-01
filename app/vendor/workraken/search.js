// Buscadores compactos compartidos por las tablas de Estacionamiento.

export const normalizeFilterSearch = (value = "") =>
  String(value || "")
    .trim()
    .toLocaleLowerCase("es")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ");

const compactFilterSearch = (value = "") =>
  normalizeFilterSearch(value).replace(/[^a-z0-9]/g, "");

export const filterSearchMatches = (values, query = "") => {
  const normalizedQuery = normalizeFilterSearch(query);
  if (!normalizedQuery) {
    return true;
  }
  const haystack = (Array.isArray(values) ? values : [values])
    .map((value) => normalizeFilterSearch(value))
    .filter(Boolean)
    .join(" ");
  if (haystack.includes(normalizedQuery)) {
    return true;
  }
  const compactQuery = compactFilterSearch(normalizedQuery);
  return Boolean(compactQuery && compactFilterSearch(haystack).includes(compactQuery));
};

// A new fragment or explicit data update invalidates only its generation.
export const createFilterSearchIndex = (readValues) => {
  let rows = new WeakMap(), lastQuery, query = '', compactQuery = '';
  return {
    matches(row, value = '') {
      if (lastQuery !== value) {
        lastQuery = value; query = normalizeFilterSearch(value); compactQuery = compactFilterSearch(query);
      }
      if (!query) return true;
      let indexed = rows.get(row);
      if (!indexed) {
        const values = readValues(row);
        const text = (Array.isArray(values) ? values : [values]).map(normalizeFilterSearch).filter(Boolean).join(' ');
        indexed = {text, compact: compactFilterSearch(text)}; rows.set(row, indexed);
      }
      return indexed.text.includes(query) || Boolean(compactQuery && indexed.compact.includes(compactQuery));
    },
    invalidate(row) { rows.delete(row); },
    clear() { rows = new WeakMap(); },
  };
};

export const initExpandableFilterSearch = (root, { onSearch, emitInputOnReset = false } = {}) => {
  if (!root) {
    return null;
  }
  const toggle = root.querySelector("[data-filter-search-toggle]");
  const input = root.querySelector("[data-filter-search-input]");
  const clear = root.querySelector("[data-filter-search-clear]");
  if (!toggle || !input || !clear) {
    return null;
  }

  const openLabel = toggle.getAttribute("aria-label") || "Abrir búsqueda";
  const closeLabel = toggle.dataset.filterSearchCloseLabel || "Cerrar búsqueda";
  const alwaysExpanded = root.hasAttribute("data-filter-search-always-expanded");
  const notify = () => onSearch?.(input.value);
  const notifyReset = () => {
    if (emitInputOnReset) {
      input.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      notify();
    }
  };
  const syncClear = () => {
    clear.hidden = !root.classList.contains("is-expanded") || !input.value;
  };
  const setExpanded = (expanded, { focus = false, reset = false } = {}) => {
    const open = alwaysExpanded || Boolean(expanded);
    const changedValue = reset && Boolean(input.value);
    if (reset) {
      input.value = "";
    }
    root.classList.toggle("is-expanded", open);
    root.toggleAttribute("data-search-expanded", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute(
      "aria-label",
      open && !alwaysExpanded ? closeLabel : openLabel,
    );
    input.tabIndex = open ? 0 : -1;
    input.setAttribute("aria-hidden", open ? "false" : "true");
    syncClear();
    if (changedValue) {
      notifyReset();
    }
    if (focus) {
      queueMicrotask(() => (open ? input : toggle).focus());
    }
  };

  toggle.addEventListener("click", () => {
    if (alwaysExpanded) {
      setExpanded(true, { focus: true });
      return;
    }
    const open = !root.classList.contains("is-expanded");
    setExpanded(open, { focus: true, reset: !open });
  });
  input.addEventListener("input", () => {
    syncClear();
    notify();
  });
  // Los selectores vacían su búsqueda antes de abrirse. El foco sincroniza
  // también ese cambio programático, sin volver a filtrar ni borrar valores.
  root.addEventListener("focusin", syncClear);
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    setExpanded(false, { focus: true, reset: true });
  });
  clear.addEventListener("click", () => {
    const changedValue = Boolean(input.value);
    input.value = "";
    syncClear();
    if (changedValue) {
      notifyReset();
    }
    input.focus();
  });

  // Si el navegador restaura un valor al volver atrás, el filtro no queda
  // activo a escondidas: se vuelve a abrir el control para hacerlo visible.
  setExpanded(alwaysExpanded || Boolean(input.value));
  return { input, setExpanded };
};

// Los filtros que ya escuchan input reutilizan la misma lupa, X y Escape.
// El evento de limpiar llega a su controlador sin registrar otro filtrado.
export const initStandaloneFilterSearches = (scope = document) => {
  for (const root of scope.querySelectorAll("[data-filter-search-standalone]")) {
    if (root.dataset.filterSearchReady) continue;
    if (initExpandableFilterSearch(root, { emitInputOnReset: true })) {
      root.dataset.filterSearchReady = "true";
    }
  }
};
