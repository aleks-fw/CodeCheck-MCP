"""Самый короткий уникальный CSS-селектор элемента (выполняется в браузере)."""

# Порядок: #id → [data-testid] → [name] / [aria-label] → уникальный класс → путь из тегов и классов
# с :nth-of-type. Каждый кандидат проверяется через document.querySelectorAll(s).length === 1.
SELECTOR_JS = r"""
window.__ccSelector = (el) => {
  if (!el || el.nodeType !== 1) return '';
  const uniq = (s) => { try { return document.querySelectorAll(s).length === 1; } catch (e) { return false; } };
  const attr = (n, v) => `[${n}="${String(v).replace(/["\\]/g, '\\$&')}"]`;
  const own = (e) => {
    const tag = e.tagName.toLowerCase();
    if (e.id && uniq('#' + CSS.escape(e.id))) return '#' + CSS.escape(e.id);
    for (const a of ['data-testid', 'name', 'aria-label']) {
      const v = e.getAttribute(a);
      if (!v) continue;
      if (uniq(attr(a, v))) return attr(a, v);
      if (uniq(tag + attr(a, v))) return tag + attr(a, v);
    }
    for (const c of e.classList) {
      const s = '.' + CSS.escape(c);
      if (uniq(s)) return s;
      if (uniq(tag + s)) return tag + s;
    }
    return null;
  };
  const direct = own(el);
  if (direct) return direct;
  const parts = [];
  for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentElement) {
    const anchor = cur !== el ? own(cur) : null;
    if (anchor) { parts.unshift(anchor); break; }
    const tag = cur.tagName.toLowerCase();
    const sibs = cur.parentElement ? [...cur.parentElement.children].filter(x => x.tagName === cur.tagName) : [];
    const cls = cur.classList.length ? '.' + CSS.escape(cur.classList[0]) : '';
    parts.unshift(sibs.length > 1 ? `${tag}${cls}:nth-of-type(${sibs.indexOf(cur) + 1})` : tag + cls);
    if (uniq(parts.join(' > '))) return parts.join(' > ');
  }
  const s = parts.join(' > ');
  return uniq(s) ? s : '';
};
"""
