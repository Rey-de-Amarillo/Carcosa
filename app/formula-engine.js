/** Named pre-match variables, safe expressions, and settled flat-stake metrics. */
export const DEFAULT_EXPRESSION = 'ev >= 0.03 Y referencias >= 3 Y cuota >= 1.2 Y cuota <= 5';

export const FIELD_DICTIONARY = Object.freeze([
  { name: 'cuota', label: 'Cuota decimal', type: 'number', unit: 'decimal', description: 'Pago total ofrecido por la casa por cada unidad apostada.', aliases: ['odds'] },
  { name: 'probabilidad_min', label: 'Probabilidad mínima', type: 'number', unit: 'probability', description: 'La menor probabilidad de las otras casas, después de retirar su margen por el método power.', aliases: ['probability'] },
  { name: 'probabilidad_media', label: 'Probabilidad media', type: 'number', unit: 'probability', description: 'Media de las probabilidades de referencia sin margen.', aliases: ['referenceMean'] },
  { name: 'dispersion', label: 'Dispersión entre casas', type: 'number', unit: 'probability', description: 'Desviación estándar de las probabilidades de referencia.', aliases: ['referenceSd'] },
  { name: 'referencias', label: 'Otras casas', type: 'number', unit: 'count', description: 'Cantidad de casas de referencia. Excluye siempre a la casa que ofrece la cuota.', aliases: ['refs', 'references'] },
  { name: 'ev', label: 'EV estimado', type: 'number', unit: 'percentage', description: 'Beneficio esperado por unidad según la probabilidad mínima de referencia.', formula: 'probabilidad_min * cuota - 1' },
  { name: 'prob_equilibrio', label: 'Probabilidad de equilibrio', type: 'number', unit: 'probability', description: 'Probabilidad necesaria para cubrir el precio ofrecido.', formula: '1 / cuota' },
  { name: 'probabilidad_casa', label: 'Probabilidad de la casa', type: 'number', unit: 'probability', description: 'Probabilidad de esta selección en la casa evaluada, después de retirar el margen por power.', aliases: ['own_probability', 'ownProbability'] },
  { name: 'margen_casa', label: 'Margen de la casa', type: 'number', unit: 'percentage', description: 'Suma de las probabilidades implícitas 1/cuota de los tres resultados, menos uno.', aliases: ['bookmaker_margin', 'bookmakerMargin'] },
  { name: 'ventaja_probabilidad', label: 'Ventaja sobre el equilibrio', type: 'number', unit: 'probability', description: 'Probabilidad mínima de referencia menos la probabilidad necesaria para cubrir la cuota.', formula: 'probabilidad_min - 1 / cuota', aliases: ['edge_probability'] },
  { name: 'acierto', label: 'Acierto', type: 'boolean', unit: 'boolean', description: 'Resultado conocido después del partido; se usa para medir, no para seleccionar.', preMatch: false },
  { name: 'beneficio', label: 'Beneficio realizado', type: 'number', unit: 'units', description: 'Cuota − 1 si ganó; −1 si perdió, por cada unidad apostada.', preMatch: false },
]);

const fields = new Map();
for (const field of FIELD_DICTIONARY) {
  fields.set(field.name, field);
  for (const alias of field.aliases || []) fields.set(alias.toLowerCase(), field);
}
const futureFields = new Set(['goles_local', 'goles_visitante', 'goles', 'resultado', 'won', 'profit', 'homegoals', 'awaygoals']);
const functions = new Map([
  ['min', { count: 2, run: Math.min }],
  ['max', { count: 2, run: Math.max }],
  ['abs', { count: 1, run: Math.abs }],
]);

export class FormulaError extends Error {
  constructor(message, position = 0) {
    super(`${message} (posición ${position + 1}).`);
    this.name = 'FormulaError';
    this.position = position;
  }
}

function tokenize(expression) {
  const tokens = [];
  let pos = 0;
  while (pos < expression.length) {
    if (/\s/u.test(expression[pos])) { pos++; continue; }
    const start = pos;
    const number = expression.slice(pos).match(/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?/);
    if (number) {
      pos += number[0].length;
      let value = Number(number[0]);
      if (expression[pos] === '%') { value /= 100; pos++; }
      if (!Number.isFinite(value)) throw new FormulaError('El número debe ser finito', start);
      tokens.push({ kind: 'number', value, pos: start });
    } else {
      const identifier = expression.slice(pos).match(/^[a-zA-Z_áéíóúÁÉÍÓÚñÑ][a-zA-Z_0-9áéíóúÁÉÍÓÚñÑ]*/u);
      if (identifier) {
        pos += identifier[0].length;
        const value = identifier[0].toLowerCase();
        const logic = { y: 'and', and: 'and', o: 'or', or: 'or', no: 'not', not: 'not' }[value];
        tokens.push({ kind: logic ? 'operator' : 'identifier', value: logic || value, pos: start });
      } else {
        const match = expression.slice(pos).match(/^(>=|<=|==|!=|<>|&&|\|\||[+*/()!,<>=-])/);
        if (!match) throw new FormulaError(`Símbolo no permitido «${expression[pos]}»`, pos);
        pos += match[0].length;
        tokens.push({ kind: 'operator', value: ({ '&&': 'and', '||': 'or', '!': 'not', '==': '=', '<>': '!=' })[match[0]] || match[0], pos: start });
      }
    }
    if (tokens.length > 600) throw new FormulaError('La fórmula tiene demasiados elementos', start);
  }
  tokens.push({ kind: 'end', value: '', pos });
  return tokens;
}

function parse(expression) {
  const tokens = tokenize(expression);
  const used = new Set();
  let cursor = 0, depth = 0;
  const peek = () => tokens[cursor];
  const take = () => tokens[cursor++];
  const is = (...values) => values.includes(peek().value);
  const requireType = (node, type, token) => {
    if (node.type !== type) throw new FormulaError(type === 'number' ? 'Se esperaba un número o una variable numérica' : 'Se esperaba una condición; por ejemplo ev >= 0.03', token.pos);
  };
  function binary(left, op, right, type) {
    const numeric = !['and', 'or'].includes(op.value);
    requireType(left, numeric ? 'number' : 'boolean', op);
    requireType(right, numeric ? 'number' : 'boolean', op);
    return { kind: 'binary', op: op.value, left, right, type };
  }
  function primary() {
    if (++depth > 60) throw new FormulaError('Hay demasiados paréntesis anidados', peek().pos);
    const token = take();
    let node;
    if (token.kind === 'number') node = { kind: 'number', value: token.value, type: 'number' };
    else if (token.value === '(') {
      node = or();
      if (!is(')')) throw new FormulaError('Falta cerrar el paréntesis', peek().pos);
      take();
    } else if (token.kind === 'identifier') {
      if (is('(')) {
        const fn = functions.get(token.value);
        if (!fn) throw new FormulaError(`Función desconocida «${token.value}». Podés usar min, max o abs`, token.pos);
        take();
        const args = [or()];
        while (is(',')) { take(); args.push(or()); }
        if (!is(')')) throw new FormulaError('Falta cerrar la función', peek().pos);
        take();
        if (args.length !== fn.count) throw new FormulaError(`${token.value} necesita ${fn.count} argumento${fn.count > 1 ? 's' : ''}`, token.pos);
        for (const arg of args) requireType(arg, 'number', token);
        node = { kind: 'function', name: token.value, args, type: 'number' };
      } else {
        const field = fields.get(token.value);
        if (field?.preMatch === false || futureFields.has(token.value)) throw new FormulaError(`«${token.value}» se conoce después del partido. Usá variables previas para seleccionar jugadas`, token.pos);
        if (!field) throw new FormulaError(`Variable desconocida «${token.value}»`, token.pos);
        used.add(field.name);
        node = { kind: 'field', name: field.name, type: field.type };
      }
    } else throw new FormulaError('Se esperaba una variable, un número o un paréntesis', token.pos);
    depth--;
    return node;
  }
  function unary() {
    if (is('+', '-')) {
      const token = take(), arg = unary();
      requireType(arg, 'number', token);
      return { kind: 'unary', op: token.value, arg, type: 'number' };
    }
    // NOT is parsed over a comparison below, so “NO ev > 0” means “NO (ev > 0)”.
    return primary();
  }
  function product() {
    let node = unary();
    while (is('*', '/')) { const op = take(); node = binary(node, op, unary(), 'number'); }
    return node;
  }
  function sum() {
    let node = product();
    while (is('+', '-')) { const op = take(); node = binary(node, op, product(), 'number'); }
    return node;
  }
  function comparison() {
    if (is('not')) {
      const token = take();
      if (++depth > 60) throw new FormulaError('Hay demasiados operadores anidados', token.pos);
      const arg = comparison();
      depth--;
      requireType(arg, 'boolean', token);
      return { kind: 'unary', op: 'not', arg, type: 'boolean' };
    }
    let node = sum();
    if (is('>', '>=', '<', '<=', '=', '!=')) { const op = take(); node = binary(node, op, sum(), 'boolean'); }
    if (is('>', '>=', '<', '<=', '=', '!=')) throw new FormulaError('Separá las comparaciones con Y; por ejemplo cuota >= 1.2 Y cuota <= 5', peek().pos);
    return node;
  }
  function and() {
    let node = comparison();
    while (is('and')) { const op = take(); node = binary(node, op, comparison(), 'boolean'); }
    return node;
  }
  function or() {
    let node = and();
    while (is('or')) { const op = take(); node = binary(node, op, and(), 'boolean'); }
    return node;
  }
  const ast = or();
  if (peek().kind !== 'end') throw new FormulaError(`Elemento inesperado «${peek().value}»`, peek().pos);
  requireType(ast, 'boolean', { pos: 0 });
  return { ast, used: [...used] };
}

function fieldValue(row, name) {
  switch (name) {
    case 'cuota': return row.odds ?? row.cuota;
    case 'probabilidad_min': return row.probability ?? row.probabilidad_min;
    case 'probabilidad_media': return row.referenceMean ?? row.probabilidad_media;
    case 'dispersion': return row.referenceSd ?? row.dispersion;
    case 'referencias': {
      const refs = row.references ?? row.refs ?? row.referencias;
      return Array.isArray(refs) ? refs.length : refs;
    }
    case 'ev': return row.ev ?? fieldValue(row, 'probabilidad_min') * fieldValue(row, 'cuota') - 1;
    case 'prob_equilibrio': return 1 / fieldValue(row, 'cuota');
    case 'probabilidad_casa': return row.ownProbability ?? row.own_probability ?? row.probabilidad_casa;
    case 'margen_casa': return row.bookmakerMargin ?? row.bookmaker_margin ?? row.margen_casa;
    case 'ventaja_probabilidad': return fieldValue(row, 'probabilidad_min') - 1 / fieldValue(row, 'cuota');
    default: return NaN;
  }
}

function calculate(node, row) {
  if (node.kind === 'number') return node.value;
  if (node.kind === 'field') { const v = fieldValue(row, node.name); return typeof v === 'number' && Number.isFinite(v) ? v : NaN; }
  if (node.kind === 'function') return functions.get(node.name).run(...node.args.map(arg => calculate(arg, row)));
  if (node.kind === 'unary') {
    const value = calculate(node.arg, row);
    return node.op === 'not' ? !value : node.op === '-' ? -value : value;
  }
  const a = calculate(node.left, row);
  if (node.op === 'and') return a && calculate(node.right, row);
  if (node.op === 'or') return a || calculate(node.right, row);
  const b = calculate(node.right, row);
  // Missing values and division by zero never make a row eligible, including !=.
  if (!Number.isFinite(a) || !Number.isFinite(b)) return node.type === 'boolean' ? false : NaN;
  switch (node.op) {
    case '+': return a + b;
    case '-': return a - b;
    case '*': return a * b;
    case '/': return b === 0 ? NaN : a / b;
    case '>': return a > b;
    case '>=': return a >= b;
    case '<': return a < b;
    case '<=': return a <= b;
    case '=': return a === b;
    case '!=': return a !== b;
    default: return false;
  }
}

export function compileFormula(expression = DEFAULT_EXPRESSION) {
  if (typeof expression !== 'string' || !expression.trim()) throw new FormulaError('Escribí al menos una condición');
  if (expression.length > 5000) throw new FormulaError('La fórmula es demasiado larga');
  const { ast, used } = parse(expression);
  return Object.freeze({ expression, ast, fields: used, test: row => used.every(name => Number.isFinite(fieldValue(row, name))) && calculate(ast, row) === true });
}

// Python select_event uses max(ev, book, market, -side), not insertion order.
function isBetter(candidate, previous) {
  const ae = fieldValue(candidate, 'ev'), be = fieldValue(previous, 'ev');
  if (ae !== be) return ae > be;
  const ab = candidate.book || '', bb = previous.book || '';
  if (ab !== bb) return ab > bb;
  const am = candidate.market || 'h2h', bm = previous.market || 'h2h';
  if (am !== bm) return am > bm;
  return Number(candidate.side) < Number(previous.side);
}

export function matchAndRank(rows, expressionOrCompiled = DEFAULT_EXPRESSION, { onePerMatch = true } = {}) {
  const compiled = typeof expressionOrCompiled === 'string' ? compileFormula(expressionOrCompiled) : expressionOrCompiled;
  if (typeof compiled?.test !== 'function') throw new FormulaError('La fórmula no está compilada');
  let result;
  if (onePerMatch) {
    const best = new Map();
    for (const row of rows) {
      if (!compiled.test(row)) continue;
      if (!row.id) throw new Error('Cada jugada necesita el identificador de su partido.');
      const previous = best.get(row.id);
      if (!previous || isBetter(row, previous)) best.set(row.id, row);
    }
    result = [...best.values()];
  } else result = rows.filter(row => compiled.test(row));
  return result.sort((a, b) => String(a.date).localeCompare(String(b.date)) || String(a.id).localeCompare(String(b.id)) || String(a.book).localeCompare(String(b.book)) || Number(a.side) - Number(b.side));
}

function average(rows, getter) {
  let sum = 0, n = 0;
  for (const row of rows) { const value = getter(row); if (Number.isFinite(value)) { sum += value; n++; } }
  return n ? sum / n : null;
}

function basicSummary(rows, stake) {
  const n = rows.length;
  const wins = rows.reduce((sum, row) => sum + Number(row.won === true), 0);
  const profit = rows.reduce((sum, row) => sum + (row.won === true ? fieldValue(row, 'cuota') - 1 : -1) * stake, 0);
  return { n, wins, losses: n - wins, profit, stake: n * stake, roi: n ? profit / (n * stake) : null,
    meanEV: average(rows, row => fieldValue(row, 'ev')),
    meanOdds: average(rows, row => fieldValue(row, 'cuota')),
    meanProbability: average(rows, row => fieldValue(row, 'probabilidad_min')),
    breakEven: average(rows, row => fieldValue(row, 'prob_equilibrio')),
    winRate: n ? wins / n : null };
}

export function summarize(rows, stake = 1) {
  if (!Number.isFinite(stake) || stake <= 0) throw new Error('El importe por jugada debe ser mayor que cero.');
  const sorted = [...rows].sort((a, b) => String(a.date).localeCompare(String(b.date)) || String(a.id).localeCompare(String(b.id)));
  const summary = basicSummary(sorted, stake);
  let cumulative = 0, peak = 0, drawdown = 0;
  const equity = [];
  const yearly = new Map();
  for (const row of sorted) {
    cumulative += (row.won === true ? fieldValue(row, 'cuota') - 1 : -1) * stake;
    peak = Math.max(peak, cumulative);
    drawdown = Math.max(drawdown, peak - cumulative);
    equity.push({ date: row.date, id: row.id, profit: cumulative });
    const year = String(row.date).slice(0, 4);
    if (!yearly.has(year)) yearly.set(year, []);
    yearly.get(year).push(row);
  }
  return { ...summary, drawdown, equity, firstDate: sorted[0]?.date ?? null, lastDate: sorted.at(-1)?.date ?? null,
    years: [...yearly].map(([year, selected]) => ({ year, ...basicSummary(selected, stake) })) };
}
