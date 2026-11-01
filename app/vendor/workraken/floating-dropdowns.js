// Conserva los menús en su formulario y delega sólo su dibujo a la capa superior.
// Así siguen funcionando las etiquetas, los eventos y los selectores del tema.
const MENU_SELECTOR = [
  '.country-picker-menu', '.location-country-menu', '.parking-cashbox-menu',
  '.split-picker-menu', '.payment-month-picker-menu',
  '.payment-discount-picker-menu', '.style-font-options',
  '.parking-registration-delivery-options', '.availability-state-filter-menu',
  '.payment-amount-suggestions',
].join(',');
const initialized = new WeakSet();

export function focusDropdownOption(option, menu) {
  const focus = () => {
    if (option?.isConnected && !menu.hidden) option.focus({preventScroll: true});
  };
  // El observer abre la capa superior después del controlador del selector.
  if (menu.hasAttribute('popover') && !menu.matches(':popover-open')) queueMicrotask(focus);
  else focus();
}

export function initFloatingDropdowns(doc = document) {
  if (initialized.has(doc) || !('showPopover' in HTMLElement.prototype)) return;
  initialized.add(doc);
  // El observador y sus delegados duran tanto como el documento. La señal
  // propia conserva scroll, resize y Escape después de reloadApp; el WeakSet
  // impide volver a registrarlos al inicializar la siguiente sección.
  const controller = new AbortController();
  const listenerOptions = {signal: controller.signal};
  const controls = new Map();
  const forwardedEscapes = new WeakSet();
  const properties = ['position', 'inset', 'margin', 'width', 'max-width', 'max-height', 'left', 'top'];
  const close = control => {
    const { menu, original } = control;
    if (menu.matches(':popover-open')) menu.hidePopover();
    if (original) {
      for (const [property, value, priority] of original) {
        if (value) menu.style.setProperty(property, value, priority);
        else menu.style.removeProperty(property);
      }
      control.original = null;
    }
  };
  const dismiss = (control, restoreFocus = false) => {
    const { trigger } = control;
    if (trigger.matches('input[role="combobox"]')) {
      // El clic abre las sugerencias de Cobros. Su Escape original las cierra.
      // Primero recuperamos el foco porque focus también puede abrir el menú.
      if (restoreFocus) trigger.focus({preventScroll: true});
      const escape = new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', cancelable: true});
      forwardedEscapes.add(escape);
      trigger.dispatchEvent(escape);
    } else {
      trigger.click();
      if (restoreFocus) trigger.focus({preventScroll: true});
    }
    close(control);
  };
  const position = control => {
    const { menu, trigger } = control;
    const rect = trigger.getBoundingClientRect();
    const viewport = window.visualViewport;
    const left = viewport?.offsetLeft || 0, top = viewport?.offsetTop || 0;
    const width = viewport?.width || window.innerWidth;
    const height = viewport?.height || window.innerHeight;
    if (!rect.width || !rect.height || rect.bottom < top || rect.top > top + height) {
      if (trigger.getAttribute('aria-expanded') === 'true') dismiss(control);
      close(control);
      return;
    }
    const below = Math.max(0, top + height - rect.bottom - 14);
    const above = Math.max(0, rect.top - top - 14);
    const desired = Math.min(control.height, menu.scrollHeight + 2);
    const upwards = below < Math.min(desired, 180) && above > below;
    const maxHeight = Math.min(control.height, upwards ? above : below);
    const menuWidth = Math.min(Math.max(rect.width, control.width), width - 16);
    menu.style.position = 'fixed';
    menu.style.inset = 'auto';
    menu.style.margin = '0';
    menu.style.width = `${menuWidth}px`;
    menu.style.maxWidth = `${width - 16}px`;
    menu.style.maxHeight = `${maxHeight}px`;
    menu.style.left = `${Math.max(left + 8, Math.min(rect.left, left + width - menuWidth - 8))}px`;
    const actualHeight = menu.getBoundingClientRect().height;
    menu.style.top = `${upwards ? rect.top - actualHeight - 6 : rect.bottom + 6}px`;
  };
  const sync = () => {
    for (const [menu, control] of controls) {
      const { trigger } = control;
      if (!menu.isConnected) { close(control); controls.delete(menu); continue; }
      const expanded = trigger.getAttribute('aria-expanded') === 'true';
      // Un selector cerrado no necesita geometría. Medir todos los botones
      // ocultos en cada mutación forzaba layout al cargar grillas grandes.
      const triggerUnavailable = expanded && (
        trigger.closest('[hidden], [inert]') || !trigger.getClientRects().length
      );
      const visible = expanded && !menu.hidden && !triggerUnavailable;
      if (!visible) {
        // El selector conserva su estado al cerrar un modal sin destruirlo.
        // Su propio controlador debe cerrar también aria-expanded y hidden.
        if (expanded && triggerUnavailable) dismiss(control);
        close(control);
        continue;
      }
      const opening = !menu.matches(':popover-open');
      if (opening) {
        const css = getComputedStyle(menu);
        control.width = parseFloat(css.width) || trigger.getBoundingClientRect().width;
        control.height = parseFloat(css.maxHeight) || 330;
        control.original = properties.map(property => [property, menu.style.getPropertyValue(property), menu.style.getPropertyPriority(property)]);
        menu.showPopover();
      }
      position(control);
      if (opening && menu.matches(':popover-open')) {
        const active = doc.getElementById(trigger.getAttribute('aria-activedescendant') || '');
        if (active && menu.contains(active)) {
          const option = active.getBoundingClientRect(), bounds = menu.getBoundingClientRect();
          const top = bounds.top + menu.clientTop, bottom = top + menu.clientHeight;
          // Sólo desplaza el menú: scrollIntoView también puede mover su modal.
          if (option.bottom > bottom) menu.scrollTop += option.bottom - bottom;
          else if (option.top < top) menu.scrollTop += option.top - top;
        }
      }
    }
  };
  const discover = root => {
    const menus = [...root.querySelectorAll?.(MENU_SELECTOR) || []];
    if (root.matches?.(MENU_SELECTOR)) menus.push(root);
    for (const menu of menus) {
      if (controls.has(menu)) continue;
      const trigger = menu.parentElement?.querySelector('button[aria-expanded], input[role="combobox"][aria-expanded]');
      if (!trigger) continue;
      menu.setAttribute('popover', 'manual');
      menu.dataset.floatingDropdown = '';
      controls.set(menu, {menu, trigger});
    }
  };
  discover(doc);
  const observer = new MutationObserver(records => {
    const added = new Set();
    for (const record of records) {
      if (record.type === 'childList') for (const node of record.addedNodes) {
        if (node.nodeType === 1 && node.isConnected) added.add(node);
      }
    }
    // Un formulario agregado ya incluye sus filas, controles y opciones.
    // Buscar sólo las raíces de la tanda evita recorrer esos árboles otra vez.
    for (const node of added) {
      let parent = node.parentElement;
      while (parent && !added.has(parent)) parent = parent.parentElement;
      if (!parent) discover(node);
    }
    sync();
  });
  observer.observe(doc.documentElement, {subtree: true, childList: true, attributes: true,
    attributeFilter: ['aria-expanded', 'hidden', 'open', 'class', 'inert']});
  window.addEventListener('resize', sync, listenerOptions);
  window.addEventListener('scroll', sync, {...listenerOptions, capture: true, passive: true});
  window.visualViewport?.addEventListener('resize', sync, listenerOptions);
  window.visualViewport?.addEventListener('scroll', sync, listenerOptions);
  // Escape cierra primero el selector; el siguiente Escape puede cerrar el modal.
  doc.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || forwardedEscapes.has(event)) return;
    const open = [...controls.values()].filter(({menu}) => menu.matches(':popover-open'));
    const control = open.find(({menu, trigger}) => menu.contains(event.target) || trigger === event.target) || open.at(-1);
    if (!control) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    dismiss(control, true);
  }, {...listenerOptions, capture: true});
  sync();
}
