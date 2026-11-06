# DOM recipes for the AppSheet editor

All snippets are plain IIFEs that return a small JSON-serializable value. They
work in the in-app `browser.evaluate` (script string) and in Playwright MCP
`browser_evaluate` (function body). Prefer returning a short status string or a
few fields — never `document.body.innerHTML`.

## 1. Find visible elements by text

```js
(() => {
  const text = 'Save';
  const exact = true;
  const els = [...document.querySelectorAll('button,[role="button"],a,[role="tab"],[role="treeitem"],h3,h5,h6')]
    .filter(e => e.offsetParent && (exact ? e.textContent.trim() === text : e.textContent.includes(text)));
  return els.slice(0, 20).map(e => ({
    tag: e.tagName,
    role: e.getAttribute('role'),
    text: e.textContent.trim().slice(0, 80),
    disabled: e.disabled === true || e.getAttribute('aria-disabled') === 'true'
  }));
})()
```

If this returns nothing, the element may be inside an iframe (preview) or behind
a collapsed accordion. Scope the query to the iframe's `contentDocument` only if
same-origin; otherwise use the browser tool's frame support.

## 2. Click by exact text

```js
(() => {
  const text = 'Data';
  const candidates = [...document.querySelectorAll('button,[role="button"],[role="tab"],[role="treeitem"],a')]
    .filter(e => e.offsetParent && e.textContent.trim() === text);
  if (!candidates.length) return 'not found: ' + text;
  const el = candidates[0];
  if (el.disabled || el.getAttribute('aria-disabled') === 'true') return 'disabled: ' + text;
  el.click();
  return 'clicked: ' + text;
})()
```

For accordions, the clickable element is often the header button, not the
heading. Search for the heading, then click its closest `button` or the element
with `aria-expanded`.

```js
(() => {
  const name = 'Materials';
  const heading = [...document.querySelectorAll('h3')]
    .find(h => h.offsetParent && h.textContent.trim() === name);
  if (!heading) return 'heading not found';
  const row = heading.closest('div');
  const btn = row?.querySelector('button[aria-expanded], button');
  if (!btn) return 'button not found';
  btn.click();
  return 'toggled ' + name;
})()
```

## 3. Set a React-controlled input

Material-UI inputs ignore `el.value = x`. Use the native setter and dispatch
`input` + `change`, then blur so validation runs.

```js
(() => {
  const el = document.querySelector('input[placeholder="User Email"]');
  if (!el) return 'input not found';
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
  setter.call(el, 'user@example.com');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.blur();
  return el.value;
})()
```

## 4. Read a field by its heading

AppSheet groups each setting under an `h6` heading, with the control in the same
block. This helper finds the closest ancestor that contains a control.

```js
(() => {
  const headingText = 'View name';
  const heading = [...document.querySelectorAll('h6')]
    .find(h => h.offsetParent && h.textContent.trim() === headingText);
  if (!heading) return 'heading not found';
  let box = heading.parentElement;
  for (let i = 0; i < 4 && box; i++, box = box.parentElement) {
    const input = box.querySelector('input, textarea');
    if (input) return { heading: headingText, value: input.value, disabled: input.disabled };
  }
  return 'no control near ' + headingText;
})()
```

## 5. Set a field by its heading (text/expression)

```js
(() => {
  const headingText = 'Display name';
  const value = '=CONCATENATE([MaterialName], " — ", [Finish])';
  const heading = [...document.querySelectorAll('h6')]
    .find(h => h.offsetParent && h.textContent.trim() === headingText);
  if (!heading) return 'heading not found';
  let box = heading.parentElement;
  for (let i = 0; i < 4 && box; i++, box = box.parentElement) {
    const input = box.querySelector('input:not([type="checkbox"]), textarea');
    if (input && !input.disabled) {
      const proto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      input.blur();
      return { set: headingText, value: input.value };
    }
  }
  return 'no editable control near ' + headingText;
})()
```

**Expression fields:** if the field is currently a checkbox or a plain value and
you need an expression, click the adjacent `science` button first, then set the
textbox. Strip the leading `=` from appdef expressions before pasting.

```js
(() => {
  const headingText = 'Show?';
  const heading = [...document.querySelectorAll('h6')]
    .find(h => h.offsetParent && h.textContent.trim() === headingText);
  if (!heading) return 'heading not found';
  let box = heading.parentElement;
  for (let i = 0; i < 4 && box; i++, box = box.parentElement) {
    const science = [...box.querySelectorAll('button')].find(b => b.textContent.trim() === 'science');
    if (science) { science.click(); return 'switched ' + headingText + ' to expression'; }
  }
  return 'no science button near ' + headingText;
})()
```

## 6. Open a column definition

```js
(() => {
  const table = 'Materials';
  const column = 'DisplayName';
  // Expand the table if needed.
  const heading = [...document.querySelectorAll('h3')]
    .find(h => h.offsetParent && h.textContent.trim() === table);
  if (!heading) return 'table heading not found';
  const tableBlock = heading.closest('div')?.parentElement;
  const edit = [...(tableBlock?.querySelectorAll('button') || [])]
    .find(b => b.textContent.includes(column) || b.closest('[role="row"]')?.textContent.includes(column));
  if (!edit) return 'column row not found (expand the table first)';
  edit.click();
  return 'opened ' + table + '.' + column;
})()
```

After clicking, verify the dialog heading:

```js
(() => {
  const dlg = document.querySelector('[role="dialog"]');
  if (!dlg) return 'no dialog';
  const h = dlg.querySelector('h3');
  return { heading: h?.textContent.trim(), buttons: [...dlg.querySelectorAll('button')].map(b => b.textContent.trim()).filter(Boolean).slice(0, 12) };
})()
```

## 7. Read the open dialog's structure

```js
(() => {
  const dlg = document.querySelector('[role="dialog"]');
  if (!dlg) return 'no dialog';
  return [...dlg.querySelectorAll('h3,h5,h6')]
    .filter(h => h.offsetParent)
    .map(h => h.tagName + ': ' + h.textContent.trim());
})()
```

Use this instead of a screenshot to confirm which panel opened. Then query only
the section you need.

## 8. Read a table row's current values

The Columns grid exposes textboxes and checkboxes inline. Scope to the row whose
first cell contains the column name.

```js
(() => {
  const column = 'MaterialID';
  const row = [...document.querySelectorAll('[role="row"]')]
    .find(r => r.offsetParent && r.textContent.includes(column));
  if (!row) return 'row not found';
  return [...row.querySelectorAll('input, textarea, [role="combobox"]')]
    .map((el, i) => ({ i, type: el.type || el.getAttribute('role'), value: el.value ?? el.textContent.trim(), disabled: el.disabled }));
})()
```

## 9. Click a tab, radio, or tree item by label

```js
(() => {
  const label = 'Columns';
  const el = [...document.querySelectorAll('[role="tab"],[role="radio"],[role="treeitem"],button')]
    .find(e => e.offsetParent && e.textContent.trim() === label);
  if (!el) return 'not found';
  el.click();
  return 'clicked ' + label;
})()
```

## 10. Wait for text (async)

```js
async () => {
  const text = 'Column Definition';
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    const found = [...document.querySelectorAll('h3,h5,h6,[role="dialog"]')]
      .some(e => e.offsetParent && e.textContent.includes(text));
    if (found) return 'found: ' + text;
    await new Promise(r => setTimeout(r, 200));
  }
  return 'timeout: ' + text;
}
```

## 11. Preview iframe

The preview is an iframe. If same-origin, read a small piece of it:

```js
(() => {
  const f = document.querySelector('iframe');
  if (!f) return 'no iframe';
  try {
    const doc = f.contentDocument;
    if (!doc) return 'cross-origin';
    return {
      title: doc.title,
      text: doc.body.innerText.slice(0, 500)
    };
  } catch (e) {
    return 'cross-origin: ' + e.message;
  }
})()
```

For a visual check, screenshot the preview element instead of reading its DOM.

## 12. Set the preview user

```js
(() => {
  const input = [...document.querySelectorAll('input')]
    .find(i => i.offsetParent && (i.placeholder === 'User Email' || i.getAttribute('aria-label') === 'User Email'));
  if (!input) return 'preview email input not found';
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(input, 'designer@example.com');
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  input.blur();
  return input.value;
})()
```

Then click `Apply` by text.

## 13. Locate a button by its aria-label when the text is an icon

Icon buttons (save, expand, science, edit) expose `aria-label` or a tooltip.
Search both:

```js
(() => {
  const label = 'Save';
  const el = [...document.querySelectorAll('button,[role="button"]')]
    .find(e => e.offsetParent && (
      e.getAttribute('aria-label') === label ||
      e.getAttribute('title') === label ||
      e.textContent.trim() === label
    ));
  return el ? 'found' : 'not found';
})()
```

## 14. Detect the editor mode

```js
(() => {
  const btn = [...document.querySelectorAll('button')]
    .find(b => /Switch to the (legacy|improved) editor/i.test(b.textContent));
  const appName = document.querySelector('input[aria-label="App Name"], input[placeholder="App Name"]')?.value;
  return {
    mode: btn ? (/legacy/i.test(btn.textContent) ? 'improved' : 'legacy') : 'unknown',
    switchLabel: btn?.textContent.trim() || null,
    appName: appName || null
  };
})()
```

## 15. Check whether the app has unsaved changes

```js
(() => {
  const save = [...document.querySelectorAll('button')]
    .find(b => b.offsetParent && b.textContent.trim() === 'Save');
  if (!save) return 'save button not found';
  return {
    disabled: save.disabled || save.getAttribute('aria-disabled') === 'true',
    text: save.textContent.trim()
  };
})()
```

`disabled: true` means the editor believes there is nothing to save. If you just
made a change and Save is still disabled, the change did not register — re-read
the field before clicking anything else.

## 16. Read the current preview context

```js
(() => {
  const text = document.body.innerText;
  const m = text.match(/View:\s*([^\n|]+)\|\s*Table:\s*([^\n]+)/);
  return m ? { view: m[1].trim(), table: m[2].trim() } : 'preview context not found';
})()
```

This is much cheaper than a screenshot when you only need to confirm which view
is previewing.

## 17. Improved-editor anchors

These are stable in the improved editor and are often more reliable than text
matching.

Navigation buttons expose `aria-label`:

```
Data  App  Actions  Automation  Security  Settings  Manage  Learn
```

```js
(() => {
  const label = 'Security';
  const el = document.querySelector(`button[aria-label="${label}"], [role="button"][aria-label="${label}"]`);
  if (!el) return 'not found: ' + label;
  el.click();
  return 'clicked ' + label;
})()
```

Table toolbar actions expose `title`:

```
Add virtual column   Regenerate schema   Table settings   More
```

```js
(() => {
  const title = 'Table settings';
  const el = [...document.querySelectorAll('[title]')]
    .find(e => e.offsetParent && e.getAttribute('title') === title);
  if (!el) return 'not found: ' + title;
  el.click();
  return 'clicked ' + title;
})()
```

Save controls:

```js
(() => {
  const save = [...document.querySelectorAll('button')]
    .find(b => b.offsetParent && (
      b.getAttribute('aria-label') === 'Save' ||
      b.textContent.trim() === 'SAVE' ||
      b.textContent.trim() === 'Save'
    ));
  const menu = document.querySelector('[aria-label="Open save menu"]');
  return {
    save: save ? { disabled: save.disabled, text: save.textContent.trim() } : null,
    saveMenu: !!menu
  };
})()
```

Column-grid rows expose an edit button with `title="edit"`:

```js
(() => {
  const column = 'MaterialName';
  const row = [...document.querySelectorAll('[role="row"]')]
    .find(r => r.offsetParent && r.textContent.includes(column));
  if (!row) return 'row not found';
  const edit = row.querySelector('button[title="edit"]');
  if (!edit) return 'edit button not found';
  edit.click();
  return 'opened ' + column;
})()
```

## 18. Guardrails

- Re-locate after every snapshot or navigation. Refs (`e123`) expire.
- Return counts and short strings, not DOM subtrees.
- If a query returns more than ~20 elements, narrow it by section or dialog.
- Never set `innerHTML`, dispatch synthetic `MouseEvent`s at coordinates, or
  click hidden duplicates. Filter by `offsetParent`.
- If a control is disabled, read the reason from the nearest `aria-describedby`
  or error text instead of forcing a value.
