// The native select remains the form's source of truth, including duplicate
// currency codes belonging to different countries.
const initialized = new WeakMap();
let sequence = 0;

export function initCurrencyCountryPicker(select, config = {}) {
  if (initialized.has(select)) { initialized.get(select).refresh(); return initialized.get(select); }
  const doc = select.ownerDocument;
  // cloneNode copies the presentation, but its listeners and WeakMap entry
  // belong to the original select. Rebuild that presentation with fresh IDs.
  if (select.nextElementSibling?.classList.contains('currency-country-picker')) select.nextElementSibling.remove();
  const lifecycle = new AbortController();
  const listen = (target, name, callback) => target?.addEventListener(name, callback, {signal: lifecycle.signal});
  const allowEmpty = config.allowEmpty ?? select.hasAttribute('data-currency-country-allow-empty');
  const wrapper = doc.createElement('span');
  wrapper.className = 'country-picker currency-country-picker';
  if (config.className) wrapper.classList.add(...config.className.split(/\s+/).filter(Boolean));
  const trigger = doc.createElement('button');
  trigger.type = 'button';
  trigger.className = 'country-picker-button currency-country-trigger';
  trigger.setAttribute('role', 'combobox');
  trigger.setAttribute('aria-haspopup', 'listbox');
  trigger.setAttribute('aria-expanded', 'false');
  const id = `currency-country-${++sequence}`;
  trigger.id = `${id}-trigger`;
  const label = select.closest('label');
  const heading = label?.querySelector('.field-label-line');
  if (label && label.querySelectorAll('select,input:not([type="hidden"]),textarea').length === 1) label.htmlFor = trigger.id;
  if (config.label) trigger.setAttribute('aria-label', config.label);
  else if (heading) {
    if (/^currency-country-\d+-label$/.test(heading.id)) heading.id = '';
    heading.id ||= `${id}-label`;
    trigger.setAttribute('aria-labelledby', heading.id);
  } else trigger.setAttribute('aria-label', select.getAttribute('aria-label') || 'Moneda');
  const list = doc.createElement('span');
  list.className = 'country-picker-menu currency-country-menu';
  list.id = `${id}-options`;
  list.setAttribute('role', 'listbox');
  list.setAttribute('aria-label', config.listLabel || 'País y moneda');
  list.hidden = true;
  trigger.setAttribute('aria-controls', list.id);
  const error = doc.createElement('span');
  error.className = 'form-error';
  error.id = `${id}-error`;
  error.setAttribute('role', 'alert');
  error.hidden = true;
  let active = -1;
  let search = '';
  let searchedAt = 0;
  let events;
  let options = [];
  const renderedContent = new WeakMap();
  const close = () => {
    search = '';
    searchedAt = 0;
    list.hidden = true;
    wrapper.classList.remove('is-open');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.removeAttribute('aria-activedescendant');
    events?.abort();
  };
  const content = (node, option) => {
    const signature = JSON.stringify([option?.dataset.logo, option?.dataset.logoMonochrome,
      option?.dataset.logoGlyphWhite, option?.dataset.country, option?.dataset.symbol,
      option?.dataset.label || option?.textContent || config.placeholder || 'Seleccionar moneda', option?.dataset.caption]);
    if (renderedContent.get(node) === signature && node.childNodes.length) return;
    renderedContent.set(node, signature);
    node.replaceChildren();
    const logo = option?.dataset.logo;
    if (logo && /^\/assets\/parking\/crypto\/[A-Z0-9_-]+\.png$/.test(logo)) {
      const icon = doc.createElement('img');
      icon.src = logo;
      icon.alt = '';
      icon.className = 'country-selected-flag currency-crypto-logo';
      icon.classList.toggle('is-monochrome', option?.dataset.logoMonochrome === 'true');
      icon.classList.toggle('is-white-glyph', option?.dataset.logoMonochrome === 'true' && option?.dataset.logoGlyphWhite === 'true');
      node.append(icon);
    } else if (option?.dataset.country) {
      const flag = doc.createElement('img');
      flag.src = `/assets/banderas/${option.dataset.country.toLowerCase()}.png`;
      flag.alt = '';
      flag.className = 'country-selected-flag';
      node.append(flag);
    }
    const text = doc.createElement('span');
    const symbol = option?.dataset.symbol;
    if (symbol && !logo) {
      const glyph = doc.createElement('span');
      glyph.className = 'currency-fiat-glyph';
      glyph.textContent = symbol;
      glyph.dir = 'auto';
      glyph.setAttribute('aria-hidden', 'true');
      text.append(glyph, ' ');
    }
    text.append(option?.dataset.label || option?.textContent || config.placeholder || 'Seleccionar moneda');
    node.append(text);
    if (option?.dataset.caption) {
      const caption = doc.createElement('span');
      caption.className = 'currency-option-quote';
      caption.textContent = option.dataset.caption;
      node.append(caption);
    }
  };
  const sync = () => {
    content(trigger, select.selectedOptions[0]);
    if (trigger.disabled !== select.disabled) trigger.disabled = select.disabled;
    const placeholder = config.isPlaceholder ? config.isPlaceholder(select.selectedOptions[0]) : !select.value;
    trigger.classList.toggle('is-placeholder', placeholder);
    const required = String(select.required);
    if (trigger.getAttribute('aria-required') !== required) trigger.setAttribute('aria-required', required);
    options.forEach(option => {
      const selected = Number(option.dataset.index) === select.selectedIndex;
      option.classList.toggle('is-selected', selected);
      if (option.getAttribute('aria-selected') !== String(selected)) option.setAttribute('aria-selected', String(selected));
    });
    if (select.disabled) close();
  };
  const activate = (index, {scroll = true} = {}) => {
    active = index < 0 ? -1 : Math.min(index, options.length - 1);
    options.forEach((option, i) => option.classList.toggle('is-active', i === active));
    if (options[active]) {
      trigger.setAttribute('aria-activedescendant', options[active].id);
      if (scroll && config.scrollMenuOnly) {
        // Floating menus are positioned after opening. Never move their page
        // or modal before that happens; the floating controller reveals the
        // initial active option and subsequent keys only scroll this list.
        if (!list.hasAttribute('popover') || list.matches(':popover-open')) {
          const option = options[active].getBoundingClientRect(), bounds = list.getBoundingClientRect();
          const top = bounds.top + list.clientTop, bottom = top + list.clientHeight;
          if (list.clientHeight && option.bottom > bottom) list.scrollTop += option.bottom - bottom;
          else if (list.clientHeight && option.top < top) list.scrollTop += option.top - top;
        }
      } else if (scroll) options[active].scrollIntoView({block: 'nearest'});
    } else trigger.removeAttribute('aria-activedescendant');
    const option = select.options[Number(options[active]?.dataset.index)];
    if (option) select.dispatchEvent(new CustomEvent('workraken:select-option-preview', {
      bubbles: true, detail: { value: option.value },
    }));
  };
  const choose = option => {
    if (!option || select.disabled) return;
    select.selectedIndex = Number(option.dataset.index);
    close();
    select.dispatchEvent(new Event('input', {bubbles: true}));
    select.dispatchEvent(new Event('change', {bubbles: true}));
    sync();
    if (trigger.isConnected) trigger.focus({preventScroll: true});
  };
  const refresh = () => {
    config.beforeRefresh?.();
    if (list.hidden) {sync(); return;}
    const activeIndex = options[active]?.dataset.index;
    list.replaceChildren();
    options = [...select.options].flatMap((option, index) => {
      if (option.hidden || option.disabled || option.parentElement?.disabled || (!option.value && !allowEmpty)) return [];
      const item = doc.createElement('span');
      item.className = 'country-picker-option currency-country-option';
      item.id = `${id}-option-${index}`;
      item.setAttribute('role', 'option');
      item.dataset.index = String(index);
      item.dataset.country = option.dataset.country || '';
      content(item, option);
      item.addEventListener('mousedown', event => event.preventDefault());
      item.addEventListener('click', event => {event.preventDefault(); choose(item);});
      item.addEventListener('pointerenter', () => select.dispatchEvent(new CustomEvent('workraken:select-option-preview', {
        bubbles: true, detail: { value: option.value },
      })));
      list.append(item);
      return [item];
    });
    sync();
    if (!list.hidden) {
      const kept = options.findIndex(option => option.dataset.index === activeIndex);
      const selected = options.findIndex(option => Number(option.dataset.index) === select.selectedIndex);
      activate(kept >= 0 ? kept : selected, {scroll: false});
    }
  };
  const open = () => {
    if (select.disabled) return;
    list.hidden = false;
    refresh();
    doc.querySelectorAll('.currency-country-trigger[aria-expanded="true"]').forEach(other => {
      if (other !== trigger) other.dispatchEvent(new Event('currencypickerclose'));
    });
    list.hidden = false;
    wrapper.classList.add('is-open');
    trigger.setAttribute('aria-expanded', 'true');
    activate(options.findIndex(option => Number(option.dataset.index) === select.selectedIndex));
    events = new AbortController();
    doc.addEventListener('pointerdown', event => {if (!wrapper.contains(event.target)) close();}, {signal: events.signal});
  };
  listen(trigger, 'currencypickerclose', close);
  listen(trigger, 'click', event => {event.preventDefault(); list.hidden ? open() : close();});
  listen(trigger, 'keydown', event => {
    const key = event.key;
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(key)) {
      event.preventDefault();
      const wasClosed = list.hidden;
      if (wasClosed) open();
      if (key === 'Home' || key === 'End') activate(key === 'Home' ? 0 : options.length - 1);
      else if (active < 0) activate(key === 'ArrowDown' ? 0 : options.length - 1);
      else if (!wasClosed) activate(Math.max(0, active + (key === 'ArrowDown' ? 1 : -1)));
    } else if (key === 'Enter' || key === ' ') {
      event.preventDefault(); list.hidden ? open() : choose(options[active]);
    } else if (key === 'Escape' && !list.hidden) {
      event.preventDefault(); event.stopPropagation(); close();
    } else if (key === 'Tab') close();
    else if (key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey) {
      if (list.hidden) open();
      search = Date.now() - searchedAt > 700 ? key : search + key;
      searchedAt = Date.now();
      const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
      const found = options.findIndex(option => {
        const native = select.options[Number(option.dataset.index)];
        return normalize(native?.dataset.label || native?.textContent || '').startsWith(normalize(search));
      });
      if (found >= 0) activate(found);
    }
  });
  listen(wrapper, 'focusout', event => {if (!wrapper.contains(event.relatedTarget)) close();});
  listen(select, 'change', sync);
  listen(select, 'invalid', event => {
    event.preventDefault();
    trigger.setAttribute('aria-invalid', 'true');
    trigger.setAttribute('aria-describedby', error.id);
    error.textContent = select.validationMessage || (config.label ? `Seleccioná ${config.label.toLocaleLowerCase()}.` : 'Seleccioná una moneda.');
    error.hidden = false;
    trigger.focus();
  });
  listen(select, 'change', () => {
    trigger.removeAttribute('aria-invalid');
    trigger.removeAttribute('aria-describedby');
    error.hidden = true;
  });
  listen(select.form, 'reset', () => queueMicrotask(() => {close(); refresh();}));
  const observer = new MutationObserver(refresh);
  observer.observe(select, {childList: true, subtree: true, characterData: true, attributes: true,
    attributeFilter: ['disabled', 'required', 'hidden', 'selected', 'value', 'label']});
  select.classList.add('currency-country-native');
  select.tabIndex = -1;
  select.setAttribute('aria-hidden', 'true');
  if (!config.clearable) select.dataset.selectClear = 'no';
  select.after(wrapper);
  wrapper.append(trigger, list, error);
  const api = {refresh, trigger, wrapper, close, focus: () => trigger.focus(),
    destroy: () => {close(); observer.disconnect(); lifecycle.abort(); initialized.delete(select);}};
  initialized.set(select, api);
  refresh();
  return api;
}

const simpleSelectLabel = select => {
  const explicit = select.getAttribute('aria-label');
  if (explicit) return explicit;
  const labelled = select.getAttribute('aria-labelledby')?.split(/\s+/)
    .map(id => select.ownerDocument.getElementById(id)?.textContent || '').join(' ').trim();
  if (labelled) return labelled;
  const label = select.labels?.[0] || select.closest('label');
  if (label) {
    const heading = (label.querySelector('.field-label-line,.field-label-row') || label).cloneNode(true);
    heading.querySelectorAll('select,input,textarea,button,a,.required-mark,.field-info,.gastos-field-tools,.currency-country-picker').forEach(node => node.remove());
    const text = heading.textContent.replace(/\s+/g, ' ').trim();
    if (text) return text;
  }
  return select.name?.replaceAll('_', ' ') || 'Seleccionar';
};

// The same opaque option surface used by Cajas, with a normal field label and
// an optional clear button. Empty filter values are choices, not examples.
export function initWorkrakenSingleSelect(select, config = {}) {
  const existing = initialized.get(select);
  if (existing) {existing.refresh(); return existing;}
  const label = config.label || simpleSelectLabel(select);
  const style = getComputedStyle(select);
  const copied = select.nextElementSibling?.classList.contains('currency-country-picker') ? select.nextElementSibling : null;
  const fontSize = select.dataset.workrakenFieldFontSize || copied?.style.getPropertyValue('--workraken-field-font-size') || style.fontSize;
  const fontWeight = select.dataset.workrakenFieldFontWeight || copied?.style.getPropertyValue('--workraken-field-font-weight') || style.fontWeight;
  const height = select.dataset.workrakenFieldHeight || copied?.style.getPropertyValue('--workraken-field-height') || style.height;
  select.dataset.workrakenFieldFontSize = fontSize;
  select.dataset.workrakenFieldFontWeight = fontWeight;
  if (height !== 'auto' && parseFloat(height) > 2) select.dataset.workrakenFieldHeight = height;
  select.dataset.workrakenSimpleSelect = '1';
  const api = initCurrencyCountryPicker(select, {
    label, listLabel: label, allowEmpty: true, clearable: select.dataset.selectClear !== 'no',
    className: 'workraken-single-select', placeholder: label, scrollMenuOnly: true,
    isPlaceholder: option => !select.value && (!option || option.hidden || option.disabled || option.dataset.placeholder === 'true'),
    ...config,
  });
  api.wrapper.style.setProperty('--workraken-field-font-size', fontSize);
  api.wrapper.style.setProperty('--workraken-field-font-weight', fontWeight);
  if (height !== 'auto' && parseFloat(height) > 2) api.wrapper.style.setProperty('--workraken-field-height', height);
  return api;
}

let commonRoot;
let commonObserver;
let commonLifecycle;
let commonScanQueued = false;

export function initCommonSimpleSelects(root = document) {
  const surface = root.nodeType === 9 ? root.querySelector('[data-partial-content]') || root.documentElement : root;
  const scan = (scope = surface, refreshExisting = true) => {
    const candidates = [...(scope.matches?.('select:not([multiple]):not([size])') ? [scope] : []),
      ...scope.querySelectorAll('select:not([multiple]):not([size])')];
    for (const select of candidates) {
      if (!select.closest('.app-shell') || select.closest('template,[data-gastos-new-template],.public-page-owner-preview,.public-page-preview')) continue;
      const existing = initialized.get(select);
      if (existing) {if (refreshExisting && select.dataset.workrakenSimpleSelect) existing.refresh(); continue;}
      // Specialized controls keep their own dialog/picker and form semantics.
      if (select.hidden || select.getAttribute('aria-haspopup') === 'dialog'
        || (select.getAttribute('aria-hidden') === 'true' && !select.dataset.workrakenSimpleSelect)) continue;
      const copied = select.dataset.workrakenSimpleSelect && select.nextElementSibling?.classList.contains('currency-country-picker');
      if (select.closest('[hidden]') && !copied) continue;
      const rect = select.getBoundingClientRect();
      const style = getComputedStyle(select);
      if (!copied && (rect.width <= 2 || rect.height <= 2 || style.display === 'none' || style.visibility === 'hidden')) continue;
      initWorkrakenSingleSelect(select);
    }
  };
  scan();
  if (commonRoot === surface) return;
  commonObserver?.disconnect();
  commonLifecycle?.abort();
  commonLifecycle = new AbortController();
  commonRoot = surface;
  const pendingScopes = new Map();
  const requestScan = (scope, refreshExisting = false) => {
    pendingScopes.set(scope, refreshExisting || pendingScopes.get(scope) || false);
    if (commonScanQueued) return;
    commonScanQueued = true;
    queueMicrotask(() => {
      commonScanQueued = false;
      const scopes = [...pendingScopes]; pendingScopes.clear();
      if (commonRoot !== surface || !surface.isConnected) return;
      for (const [scope, refresh] of scopes) if (scope.isConnected && surface.contains(scope)) scan(scope, refresh);
    });
  };
  commonObserver = new MutationObserver(records => {
    for (const record of records) {
      if (record.target.closest?.('.currency-country-picker')) continue;
      if (record.type === 'childList') {
        for (const node of record.addedNodes) if (node.matches?.('select') || node.querySelector?.('select')) requestScan(node);
        continue;
      }
      if (record.oldValue === record.target.getAttribute(record.attributeName)) continue;
      // Native select/option observers already synchronize their picker.
      // Visibility changes only need the selectors inside that container.
      if (record.target.matches?.('select,option,optgroup')) {
        const select = record.target.closest('select');
        if (select && !initialized.has(select)) requestScan(select);
      } else if (record.target.querySelector?.('select')) requestScan(record.target, true);
    }
  });
  commonObserver.observe(surface, {childList: true, subtree: true, attributes: true, attributeOldValue: true,
    attributeFilter: ['hidden', 'open', 'disabled', 'required', 'class', 'style', 'selected', 'value']});
  surface.addEventListener('focusin', event => {
    const wrapper = event.target.closest?.('.workraken-single-select');
    const select = wrapper?.previousElementSibling;
    if (select?.matches('select')) initialized.get(select)?.refresh();
  }, {signal: commonLifecycle.signal});
}
