// Calendario reutilizable para campos `date` de la aplicación.
//
// El valor del input sigue siendo ISO (AAAA-MM-DD), de modo que los formularios
// y las validaciones nativas no cambian. La capa visual reemplaza únicamente el
// desplegable del navegador, que no permite aplicar el tema de WorKraken.

const DATE_PICKER_WEEKDAYS = Object.freeze([
  "Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do",
]);

const DATE_PICKER_SELECTORS = new WeakMap();
const DATE_PICKER_TRIGGER_WIDTH_PX = 42;
const DATE_PICKER_POINTER_CLICK_GUARD_MS = 1000;

const twoDigits = (value) => String(value).padStart(2, "0");

export const datePickerIso = ({ year, month, day } = {}) => (
  Number.isInteger(year)
  && Number.isInteger(month)
  && Number.isInteger(day)
  && month >= 1
  && month <= 12
  && day >= 1
  && day <= 31
    ? `${String(year).padStart(4, "0")}-${twoDigits(month)}-${twoDigits(day)}`
    : ""
);

export const datePickerParseIso = (value = "") => {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const candidate = new Date(year, month - 1, day, 12);
  if (
    candidate.getFullYear() !== year
    || candidate.getMonth() !== month - 1
    || candidate.getDate() !== day
  ) {
    return null;
  }
  return { year, month, day };
};

export const datePickerMonthGrid = (year, month) => {
  const first = new Date(Number(year), Number(month) - 1, 1, 12);
  if (
    !Number.isInteger(Number(year))
    || !Number.isInteger(Number(month))
    || Number(month) < 1
    || Number(month) > 12
    || Number.isNaN(first.getTime())
  ) {
    return [];
  }
  const mondayOffset = (first.getDay() + 6) % 7;
  const cursor = new Date(first);
  cursor.setDate(first.getDate() - mondayOffset);
  return Array.from({ length: 42 }, () => {
    const parts = {
      year: cursor.getFullYear(),
      month: cursor.getMonth() + 1,
      day: cursor.getDate(),
    };
    const cell = {
      ...parts,
      iso: datePickerIso(parts),
      adjacent: parts.month !== Number(month),
    };
    cursor.setDate(cursor.getDate() + 1);
    return cell;
  });
};

const isoIsWithinRange = (iso, minimum = "", maximum = "") => Boolean(
  iso
  && (!minimum || iso >= minimum)
  && (!maximum || iso <= maximum)
);

/**
 * Devuelve el primer día habilitado del mes pedido. Se usa al navegar entre
 * meses para que el foco nunca quede asignado a un botón deshabilitado por
 * `min` o `max`.
 */
export const datePickerFirstEnabledIso = (
  year,
  month,
  minimum = "",
  maximum = "",
) => datePickerMonthGrid(year, month).find((cell) => (
  !cell.adjacent && isoIsWithinRange(cell.iso, minimum, maximum)
))?.iso || "";

const localTodayIso = () => {
  const today = new Date();
  return datePickerIso({
    year: today.getFullYear(),
    month: today.getMonth() + 1,
    day: today.getDate(),
  });
};

const clampIso = (value, minimum = "", maximum = "") => {
  if (minimum && value < minimum) {
    return minimum;
  }
  if (maximum && value > maximum) {
    return maximum;
  }
  return value;
};

const monthTitleFormatter = new Intl.DateTimeFormat("es-AR", {
  month: "long",
  year: "numeric",
});

const dayLabelFormatter = new Intl.DateTimeFormat("es-AR", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

const sentenceCase = (value = "") => (
  value ? value.charAt(0).toLocaleUpperCase("es") + value.slice(1) : ""
);

const inputMatchesAnySelector = (input, selectors) => (
  input?.matches?.("input[type='date']")
  && Array.from(selectors).some((selector) => input.matches(selector))
);

// El calendario se abre desde el icono dibujado en el extremo derecho. El
// resto del control queda en manos del navegador para poder ubicar el cursor y
// escribir la fecha con el teclado.
export const datePickerPointerHitsTrigger = (input, event) => {
  const clientX = Number(event?.clientX);
  const clientY = Number(event?.clientY);
  if (
    !input?.getBoundingClientRect
    || !Number.isFinite(clientX)
    || !Number.isFinite(clientY)
  ) {
    return false;
  }
  const rect = input.getBoundingClientRect();
  return clientX >= Math.max(rect.left, rect.right - DATE_PICKER_TRIGGER_WIDTH_PX)
    && clientX <= rect.right
    && clientY >= rect.top
    && clientY <= rect.bottom;
};

const monthIntersectsRange = (year, month, minimum, maximum) => {
  const first = datePickerIso({ year, month, day: 1 });
  const lastDay = new Date(year, month, 0, 12).getDate();
  const last = datePickerIso({ year, month, day: lastDay });
  return (!minimum || last >= minimum) && (!maximum || first <= maximum);
};

const moveMonth = (year, month, offset) => {
  const moved = new Date(year, month - 1 + offset, 1, 12);
  return { year: moved.getFullYear(), month: moved.getMonth() + 1 };
};

const makeButton = (documentRef, className, label, textContent) => {
  const button = documentRef.createElement("button");
  button.type = "button";
  button.className = className;
  button.setAttribute("aria-label", label);
  button.textContent = textContent;
  return button;
};

/**
 * Activa un calendario temático mediante delegación, por lo que también cubre
 * inputs agregados más tarde desde templates de vehículos o contratos.
 */
export function initDatePicker({
  root = globalThis.document,
  selector = "input[data-app-date-picker]",
} = {}) {
  const documentRef = root?.nodeType === 9 ? root : root?.ownerDocument;
  if (!documentRef?.body) {
    return {};
  }
  const previous = DATE_PICKER_SELECTORS.get(documentRef);
  if (previous) {
    previous.selectors.add(selector);
    previous.prepareAll();
    return previous.api;
  }

  const selectors = new Set([selector]);
  const view = documentRef.defaultView || globalThis.window;
  const popover = documentRef.createElement("section");
  popover.id = "app-date-picker-popover";
  popover.className = "app-date-picker-popover";
  popover.hidden = true;
  popover.setAttribute("role", "dialog");
  popover.setAttribute("aria-modal", "false");
  popover.setAttribute("aria-labelledby", "app-date-picker-title");

  const header = documentRef.createElement("header");
  header.className = "app-date-picker-header";
  const previousButton = makeButton(
    documentRef,
    "app-date-picker-navigation is-previous",
    "Mes anterior",
    "‹",
  );
  previousButton.dataset.appDatePickerPrevious = "";
  const title = documentRef.createElement("strong");
  title.id = "app-date-picker-title";
  title.className = "app-date-picker-title";
  title.setAttribute("aria-live", "polite");
  const nextButton = makeButton(
    documentRef,
    "app-date-picker-navigation is-next",
    "Mes siguiente",
    "›",
  );
  nextButton.dataset.appDatePickerNext = "";
  header.append(previousButton, title, nextButton);

  const weekdayRow = documentRef.createElement("div");
  weekdayRow.className = "app-date-picker-weekdays";
  weekdayRow.setAttribute("aria-hidden", "true");
  for (const weekday of DATE_PICKER_WEEKDAYS) {
    const label = documentRef.createElement("span");
    label.textContent = weekday;
    weekdayRow.append(label);
  }
  const grid = documentRef.createElement("div");
  grid.className = "app-date-picker-grid";
  grid.setAttribute("role", "grid");
  grid.setAttribute("aria-label", "Días del mes");
  popover.append(header, weekdayRow, grid);
  documentRef.body.append(popover);

  let activeInput = null;
  let viewYear = 0;
  let viewMonth = 0;
  let desiredFocusIso = "";
  let pointerOpenedInput = null;
  let pointerOpenedReset = 0;

  const prepareInput = (input) => {
    if (!inputMatchesAnySelector(input, selectors)) {
      return;
    }
    input.classList.add("app-date-picker-input");
    input.dataset.appDatePickerReady = "1";
    input.setAttribute("aria-haspopup", "dialog");
    input.setAttribute("aria-controls", popover.id);
    input.setAttribute(
      "aria-expanded",
      activeInput === input && !popover.hidden ? "true" : "false",
    );
  };

  const prepareAll = () => {
    for (const currentSelector of selectors) {
      for (const input of documentRef.querySelectorAll(currentSelector)) {
        prepareInput(input);
      }
    }
  };

  const syncPopoverTheme = (input) => {
    const publicTheme = input?.closest?.("[data-public-theme]")?.dataset.publicTheme;
    const documentTheme = documentRef.documentElement?.dataset?.theme;
    const publicDocumentTheme = documentRef.documentElement?.dataset?.publicParkingTheme;
    const dark = publicTheme
      ? publicTheme === "dark"
      : documentTheme === "dark" || publicDocumentTheme === "dark";
    popover.dataset.appDatePickerTheme = dark ? "dark" : "light";
    popover.dataset.appDatePickerContext = input?.closest?.(".report-stay-calculator")
      ? "communication" : "";
  };

  const dateIsDisabled = (iso) => Boolean(
    (activeInput?.min && iso < activeInput.min)
    || (activeInput?.max && iso > activeInput.max),
  );

  const positionPopover = () => {
    if (!activeInput || popover.hidden) {
      return;
    }
    const rect = (activeInput.__workrakenDatePickerDisplay || activeInput).getBoundingClientRect();
    const margin = 12;
    const gap = 8;
    const width = popover.offsetWidth;
    const height = popover.offsetHeight;
    const viewportWidth = view.innerWidth;
    const viewportHeight = view.innerHeight;
    const left = Math.max(
      margin,
      Math.min(rect.left, viewportWidth - width - margin),
    );
    const below = rect.bottom + gap;
    const top = below + height <= viewportHeight - margin
      ? below
      : Math.max(margin, rect.top - height - gap);
    popover.style.left = `${Math.round(left)}px`;
    popover.style.top = `${Math.round(top)}px`;
  };

  const render = ({ focus = false } = {}) => {
    if (!activeInput) {
      return;
    }
    const titleDate = new Date(viewYear, viewMonth - 1, 1, 12);
    title.textContent = sentenceCase(monthTitleFormatter.format(titleDate));
    const selectedIso = activeInput.value;
    const todayIso = localTodayIso();
    const cells = datePickerMonthGrid(viewYear, viewMonth);
    const fallbackFocus = cells.find((cell) => (
      !cell.adjacent && !dateIsDisabled(cell.iso)
    ))?.iso || "";
    const focusIso = desiredFocusIso
      || (cells.some((cell) => cell.iso === selectedIso) ? selectedIso : "")
      || (cells.some((cell) => cell.iso === todayIso) ? todayIso : "")
      || fallbackFocus;
    const fragment = documentRef.createDocumentFragment();
    for (const cell of cells) {
      const button = documentRef.createElement("button");
      button.type = "button";
      button.className = "app-date-picker-day";
      button.dataset.appDatePickerDate = cell.iso;
      button.textContent = String(cell.day);
      button.setAttribute("role", "gridcell");
      button.setAttribute(
        "aria-label",
        sentenceCase(dayLabelFormatter.format(
          new Date(cell.year, cell.month - 1, cell.day, 12),
        )),
      );
      button.setAttribute("aria-selected", cell.iso === selectedIso ? "true" : "false");
      button.classList.toggle("is-adjacent", cell.adjacent);
      button.classList.toggle("is-today", cell.iso === todayIso);
      button.classList.toggle("is-selected", cell.iso === selectedIso);
      button.disabled = dateIsDisabled(cell.iso);
      button.tabIndex = cell.iso === focusIso ? 0 : -1;
      fragment.append(button);
    }
    grid.replaceChildren(fragment);
    const previousMonth = moveMonth(viewYear, viewMonth, -1);
    const nextMonth = moveMonth(viewYear, viewMonth, 1);
    previousButton.disabled = !monthIntersectsRange(
      previousMonth.year,
      previousMonth.month,
      activeInput.min,
      activeInput.max,
    );
    nextButton.disabled = !monthIntersectsRange(
      nextMonth.year,
      nextMonth.month,
      activeInput.min,
      activeInput.max,
    );
    desiredFocusIso = "";
    positionPopover();
    if (focus) {
      const focusTarget = grid.querySelector(
        ".app-date-picker-day[tabindex='0']",
      );
      const focusEnabledDay = () => {
        if (focusTarget?.isConnected && !focusTarget.disabled) {
          focusTarget.focus({ preventScroll: true });
          const popoverRect = popover.getBoundingClientRect();
          const targetRect = focusTarget.getBoundingClientRect();
          const focusMargin = 2;
          if (targetRect.bottom > popoverRect.bottom - focusMargin) {
            popover.scrollTop += (
              targetRect.bottom - popoverRect.bottom + focusMargin
            );
          } else if (targetRect.top < popoverRect.top + focusMargin) {
            popover.scrollTop -= (
              popoverRect.top - targetRect.top + focusMargin
            );
          }
        }
      };
      focusEnabledDay();
      // El click de la flecha puede devolver el foco a su propio botón como
      // acción predeterminada. Repetirlo en el checkpoint de microtareas deja
      // al día habilitado como destino final sin depender de tiempos de frame.
      view.queueMicrotask(focusEnabledDay);
    }
  };

  const close = ({ returnFocus = false } = {}) => {
    if (!activeInput) {
      return;
    }
    const input = activeInput;
    activeInput = null;
    popover.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.__workrakenDatePickerDisplay?.setAttribute("aria-expanded", "false");
    if (returnFocus && input.isConnected && !input.disabled) {
      view.requestAnimationFrame(() => {
        if (!activeInput && input.isConnected && !input.disabled) {
          (input.__workrakenDatePickerDisplay || input).focus();
        }
      });
    }
  };

  const open = (input, { focusGrid = true } = {}) => {
    if (!inputMatchesAnySelector(input, selectors) || input.disabled || input.readOnly) {
      return;
    }
    prepareInput(input);
    if (activeInput && activeInput !== input) {
      activeInput.setAttribute("aria-expanded", "false");
    }
    activeInput = input;
    syncPopoverTheme(input);
    const minimum = datePickerParseIso(input.min) ? input.min : "";
    const maximum = datePickerParseIso(input.max) ? input.max : "";
    const initialIso = clampIso(
      datePickerParseIso(input.value) ? input.value : localTodayIso(),
      minimum,
      maximum,
    );
    const initial = datePickerParseIso(initialIso);
    if (!initial) {
      return;
    }
    viewYear = initial.year;
    viewMonth = initial.month;
    desiredFocusIso = initialIso;
    popover.hidden = false;
    popover.scrollTop = 0;
    input.setAttribute("aria-expanded", "true");
    input.__workrakenDatePickerDisplay?.setAttribute("aria-expanded", "true");
    render({ focus: focusGrid });
  };

  const changeMonth = (offset) => {
    const next = moveMonth(viewYear, viewMonth, offset);
    if (!monthIntersectsRange(
      next.year,
      next.month,
      activeInput?.min || "",
      activeInput?.max || "",
    )) {
      return;
    }
    viewYear = next.year;
    viewMonth = next.month;
    desiredFocusIso = datePickerFirstEnabledIso(
      viewYear,
      viewMonth,
      activeInput?.min || "",
      activeInput?.max || "",
    );
    render({ focus: true });
  };

  const choose = (iso) => {
    if (!activeInput || dateIsDisabled(iso) || !datePickerParseIso(iso)) {
      return;
    }
    const changed = activeInput.value !== iso;
    activeInput.value = iso;
    activeInput.setCustomValidity?.("");
    if (changed) {
      activeInput.dispatchEvent(new Event("input", { bubbles: true }));
      activeInput.dispatchEvent(new Event("change", { bubbles: true }));
    }
    close({ returnFocus: true });
  };

  const onPointerMove = (event) => {
    const input = event.target?.closest?.("input[type='date']");
    if (!inputMatchesAnySelector(input, selectors)) {
      return;
    }
    input.classList.toggle(
      "is-calendar-trigger-hovered",
      !input.disabled && !input.readOnly && datePickerPointerHitsTrigger(input, event),
    );
  };

  const onPointerOut = (event) => {
    const input = event.target?.closest?.("input[type='date']");
    if (inputMatchesAnySelector(input, selectors)) {
      input.classList.remove("is-calendar-trigger-hovered");
    }
  };

  const onPointerDown = (event) => {
    const input = event.target?.closest?.("input[type='date']");
    if (inputMatchesAnySelector(input, selectors)) {
      if (!datePickerPointerHitsTrigger(input, event)) {
        pointerOpenedInput = null;
        // El indicador nativo está oculto por CSS. Conservar el gesto permite
        // enfocar directamente día, mes o año y editar ese segmento; cancelar
        // pointerdown dejaba el foco en el segmento anterior.
        if (activeInput) {
          close();
        }
        return;
      }
      view.clearTimeout(pointerOpenedReset);
      pointerOpenedInput = input;
      event.preventDefault();
      input.focus({ preventScroll: true });
      open(input);
      return;
    }
    pointerOpenedInput = null;
    if (activeInput && !popover.contains(event.target)) {
      close();
    }
  };

  const onPointerUp = () => {
    if (!pointerOpenedInput) {
      return;
    }
    view.clearTimeout(pointerOpenedReset);
    pointerOpenedReset = view.setTimeout(() => {
      pointerOpenedInput = null;
    }, DATE_PICKER_POINTER_CLICK_GUARD_MS);
  };

  const onPointerCancel = () => {
    view.clearTimeout(pointerOpenedReset);
    if (activeInput && activeInput === pointerOpenedInput) {
      close();
    }
    pointerOpenedInput = null;
  };

  const onClick = (event) => {
    const input = event.target?.closest?.("input[type='date']");
    if (inputMatchesAnySelector(input, selectors)) {
      if (!datePickerPointerHitsTrigger(input, event)) {
        return;
      }
      event.preventDefault();
      // El gesto normal ya abrió el calendario en `pointerdown`. El `click`
      // posterior no debe reconstruir la grilla ni volver a mover el foco.
      if (pointerOpenedInput === input) {
        view.clearTimeout(pointerOpenedReset);
        pointerOpenedInput = null;
        return;
      }
      open(input);
      return;
    }
    if (event.target?.closest?.("[data-app-date-picker-previous]")) {
      changeMonth(-1);
      return;
    }
    if (event.target?.closest?.("[data-app-date-picker-next]")) {
      changeMonth(1);
      return;
    }
    const day = event.target?.closest?.("[data-app-date-picker-date]");
    if (day && popover.contains(day)) {
      choose(day.dataset.appDatePickerDate || "");
    }
  };

  const onKeyDown = (event) => {
    const input = event.target?.closest?.("input[type='date']");
    if (inputMatchesAnySelector(input, selectors)) {
      const opensCalendar = ["Enter", " "].includes(event.key)
        || (event.altKey && event.key === "ArrowDown");
      if (opensCalendar) {
        event.preventDefault();
        open(input);
      } else if (event.key === "Escape" && activeInput) {
        event.preventDefault();
        close({ returnFocus: true });
      }
      return;
    }
    if (event.key === "Escape" && activeInput) {
      event.preventDefault();
      close({ returnFocus: true });
      return;
    }
    const day = event.target?.closest?.("[data-app-date-picker-date]");
    if (!day || !popover.contains(day)) {
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      choose(day.dataset.appDatePickerDate || "");
      return;
    }
    const movements = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -7,
      ArrowDown: 7,
    };
    if (!(event.key in movements)) {
      if (event.key === "PageUp" || event.key === "PageDown") {
        event.preventDefault();
        changeMonth(event.key === "PageUp" ? -1 : 1);
      }
      return;
    }
    event.preventDefault();
    const current = datePickerParseIso(day.dataset.appDatePickerDate || "");
    if (!current) {
      return;
    }
    const target = new Date(current.year, current.month - 1, current.day, 12);
    target.setDate(target.getDate() + movements[event.key]);
    const targetIso = datePickerIso({
      year: target.getFullYear(),
      month: target.getMonth() + 1,
      day: target.getDate(),
    });
    if (dateIsDisabled(targetIso)) {
      return;
    }
    viewYear = target.getFullYear();
    viewMonth = target.getMonth() + 1;
    desiredFocusIso = targetIso;
    render({ focus: true });
  };

  const onInput = (event) => {
    if (event.target === activeInput && !popover.hidden) {
      const parsed = datePickerParseIso(activeInput.value);
      if (parsed) {
        viewYear = parsed.year;
        viewMonth = parsed.month;
        desiredFocusIso = activeInput.value;
        render();
      }
    }
  };

  const observer = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType !== 1) {
          continue;
        }
        prepareInput(node);
        for (const currentSelector of selectors) {
          for (const input of node.querySelectorAll?.(currentSelector) || []) {
            prepareInput(input);
          }
        }
      }
    }
  });
  observer.observe(root?.nodeType === 1 ? root : documentRef.body, {
    childList: true,
    subtree: true,
  });
  const installListeners = () => {
    documentRef.addEventListener("pointermove", onPointerMove, true);
    documentRef.addEventListener("pointerout", onPointerOut, true);
    documentRef.addEventListener("pointerdown", onPointerDown, true);
    documentRef.addEventListener("pointerup", onPointerUp, true);
    documentRef.addEventListener("pointercancel", onPointerCancel, true);
    documentRef.addEventListener("click", onClick, true);
    documentRef.addEventListener("keydown", onKeyDown, true);
    documentRef.addEventListener("input", onInput, true);
    view.addEventListener("resize", positionPopover);
    view.addEventListener("scroll", positionPopover, true);
  };
  // La instancia y sus delegados duran lo mismo que el documento. El runtime
  // renueva los eventos de cada vista al navegar, pero conserva este singleton.
  // cleanup retira estos listeners cuando se libera el calendario completo.
  if (view.WorKrakenRuntime?.withoutAppSignal) {
    view.WorKrakenRuntime.withoutAppSignal(installListeners);
  } else {
    installListeners();
  }
  prepareAll();

  const cleanup = () => {
    close();
    observer.disconnect();
    view.clearTimeout(pointerOpenedReset);
    documentRef.removeEventListener("pointermove", onPointerMove, true);
    documentRef.removeEventListener("pointerout", onPointerOut, true);
    documentRef.removeEventListener("pointerdown", onPointerDown, true);
    documentRef.removeEventListener("pointerup", onPointerUp, true);
    documentRef.removeEventListener("pointercancel", onPointerCancel, true);
    documentRef.removeEventListener("click", onClick, true);
    documentRef.removeEventListener("keydown", onKeyDown, true);
    documentRef.removeEventListener("input", onInput, true);
    view.removeEventListener("resize", positionPopover);
    view.removeEventListener("scroll", positionPopover, true);
    popover.remove();
    DATE_PICKER_SELECTORS.delete(documentRef);
  };
  const api = { close, open, prepareAll, cleanup };
  DATE_PICKER_SELECTORS.set(documentRef, { selectors, prepareAll, api });
  return api;
}
