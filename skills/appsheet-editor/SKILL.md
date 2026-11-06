---
name: appsheet-editor
description: Use when driving the Google AppSheet editor UI (legacy or improved) with browser automation, or when applying coordinated bulk edits through the verified POST /api/saveapp path. Covers editor mode detection, deep links, navigation paths, the DOM structure of the Data/Columns, UX/Views, Behavior/Actions, and Security panes, expression-field handling, save/preview/deploy, the gzipped save API, and a strict DOM-first screenshot budget. Load this before clicking through AppSheet so you do not rediscover the interface each session.
---

# AppSheet editor automation

The AppSheet editor is a Material-UI single-page app. CSS classes are generated
and unstable; **accessible names, headings, and panel structure are stable**.
Automate by role/name and scoped DOM queries, not by coordinates or CSS classes.

## 0. Non-negotiables

1. **Read the appdef first.** Load the `appsheet-appdef` skill and run
   `summary`/`export-md`. Know the table, column, view, and action names before
   you click. This alone eliminates most trial and error.
2. **Screenshots are for visual verification only.** The provider caps context at
   30 images. Budget **0–2 screenshots per task**, taken *after* the change to
   verify color/icon/layout. Never use a screenshot to locate an element.
3. **Prefer `browser_evaluate` + `browser_find` over full snapshots.** A scoped
   query returns a few hundred bytes; a full accessibility snapshot can return
   tens of thousands of tokens.
4. **One logical change, then Save, then appdef-diff.** Do not batch a dozen
   edits and hope.
5. **Verify every write.** After setting a field, read it back. A click that
   "looks right" is not evidence.

## 1. Detect and choose the editor mode

Open the app in the editor and inspect the top-right header button:

| Button text | Mode | Notes |
|---|---|---|
| `Switch to the improved editor` | Legacy editor | Most of the detailed map below was verified here |
| `Switch to the legacy editor` | Improved editor | Equally automatable with the anchors in §4 and `references/dom-recipes.md` |

Use whichever mode the app is already in. Legacy has the most documented detail;
the improved editor has stable `aria-label`/`title` anchors (see the recipes).
Do not mix selectors from both in one task. Switching modes does not change the
app; it reloads the editor.

- **Legacy top nav:** `Home`, `Info`, `Data`, `UX`, `Behavior`, `Automation`,
  `Chat apps`, `Security`, `Intelligence`, `Manage`.
- **Legacy Data tabs:** `Tables`, `Columns`, `Slices`, `User Settings`, `Options`.
- **Improved top nav:** `Data`, `App`, `Actions`, `Automation`, `Chat apps`,
  `Intelligence`, `Security`, `Settings`, `Manage`, `Learn`.
- **Improved Security left nav:** `Require sign-in`, `Security Filters`,
  `Domain Authentication`, `Options`.

## 2. Get to the app

The stable deep link is:

```
https://www.appsheet.com/template/appdef?appId=<appId>&appName=<appName>
```

`appId` is the app GUID; `appName` is the `Name` field. Both are in the appdef.
This saves several clicks versus the app picker.

Fallback: `https://www.appsheet.com/` → sign in → **My Apps** → open the app.
If a session is already open on the editor, reuse it.

## 3. Legacy editor map

### Data → Columns (most common)

1. Click the `Data` nav button, then the `Columns` tab.
2. Each table is an accordion: `heading "<Table>" [level=3]` with an
   `Expand`/`Collapse` button. The header summarizes `N columns:` and shows the
   key/label columns.
3. Inside an expanded table:
   - `button "Add Virtual Column"`
   - `button "Regenerate Structure"` — **destructive-ish**; do not click casually
   - `button "View Table"`
   - a grid with headers: `Name`, `Type`, `Key?`, `Label?`, `Formula`, `Show?`,
     `Editable?`, `Require?`, `Initial Value`, `Display Name`, `Description`,
     `Search?`, `Scan?`, `NFC?`, `PII?`.
4. Click the row's `edit` button (`cell "edit <n> <ColumnName>"`) to open the
   **Column Definition** dialog.

Column Definition dialog structure:

```
dialog "Column Definition"
  heading "<Table> : <Column>"      Type: <type>
  button "Done"
  heading "Column name"             (read-only textbox)
  heading "Show?"                   checkbox + science (expression) button
  heading "Type"                    combobox
  heading "Type Details"            collapsible
  heading "Data Validity"           collapsible
  heading "Auto Compute"            collapsible
  heading "Update Behavior"         collapsible
  heading "Display"                 collapsible (Label, Display name, Description)
  heading "Other Properties"        collapsible
```

Use the `science` button next to a boolean/value field to switch it to an
expression. The expression textbox displays a leading `=` as a **glyph**, not as
part of the value: paste the expression **without** the `=`.

### Data → Tables (table settings)

Select the table, then `Table settings` (or the `More` menu → `Table settings`).
The dialog contains:

- `heading "Table name"`
- `heading "Are updates allowed?"` with `Updates` / `Adds` / `Deletes` /
  `Read-Only` buttons plus a `science` button for an expression
- collapsible `Storage`, `Security`, `Localization`, `Documentation`
- `button "Done"`

Use the `science` button to enter the role-based `ALL_CHANGES` / `READ_ONLY`
expression. Do not toggle the three buttons and assume it equals an expression.

### Data → Slices

Create with `New Slice` (or, in the improved editor, the table's
`Add Slice to filter data`). Fields: slice name, source table, row filter
condition (expression), columns, update mode. After saving, confirm the filter
with `appdef.py slices` — the editor and appdef sometimes disagree on where the
filter is stored.

### UX → Views

Each view is an accordion:

```
heading "<View name>"
  Data: <table or slice>
  Type: <table|card|gallery|detail|form|deck|dashboard|map|chart|calendar>
```

Expanded view editor:

- `heading "View name"` — unique name textbox
- `heading "For this data"` — table/slice picker + `Edit this table`
- `heading "View type"` — icon buttons labelled `table`, `card`, `gallery`,
  `detail`, `form`, `deck`, `dashboard`, `map`, `chart`, `calendar`, `onboarding`
- `heading "Position"` — radios `first`, `next`, `middle`, `later`, `last`,
  `menu`, `ref`
- `View Options` — `Sort by`, `Group by`, `Columns`, image size, etc.
- `Display` — icon, display name, show-if
- `Behavior` — row-selected event, actions
- `Documentation`

The `Position` radio labels are the literal UI values (`next`, `middle`, ...),
not the human labels. `menu` = main menu; `ref` = reference view.

### Behavior → Actions

Left tree is grouped by table: `treeitem "<Table> (N)"`, with child
`treeitem "<Action>"`. Buttons: `Add Action`, `More`, `toggle search`.

Action editor:

- `heading "Action name"` — unique per table
- `heading "For a record of this table"` — table combobox
- `heading "Do this"` — action type combobox. Values include:
  `Data: set the values of some columns in this row`,
  `Data: add a new row to another table using values from this row`,
  `Data: delete this row`, `Data: execute an action on a set of rows`,
  `App: go to another view within this app`,
  `App: open a form to add a new row to this table`,
  `App: export this view to a CSV file`, `App: import a CSV file`,
  `External: go to a website`, `External: open a file`,
  `External: start an email`, `External: start a phone call`,
  `External: start a text message`, `Grouped: execute a sequence of actions`.
- `heading "Position"` — `Primary`, `Prominent`, `Inline`, `Hide`
- `Display` — icon, display name
- `Behavior` — only-if condition, confirmation, bulk applicability
- `Documentation`

For `SET_COLUMN_VALUE`, the `Behavior` section holds the assignment table. Add
one row per column. For `NAVIGATE_APP`, the target is a `LINKTOFORM(...)` /
`LINKTOVIEW(...)` expression.

### Security → Security Filters

Legacy: `Security` nav → `Security Filters` tree item. The list shows each
table with `Access:` and `Filter:` summaries. Expand a table to edit
`heading "Security filter (APPSHEET CORE)"` — a textbox with a `science` button.

Other Security tree items: `Require sign-in`, `Domain Authentication`, `Options`.

> A security filter is not a view filter, and `Show_If` is not security. If a
> table's filter references the same table (notably `Users`), the app can become
> non-runnable. Check `appdef.py summary` → `Runnable` after such a change.

### Preview, Save, Deploy

- **Preview** is the right-hand panel, often an iframe. It shows `Preview app as`
  with a `User Email` textbox and `Apply` button — use this to test role-based
  behavior without a second browser profile.
- **Save** is the top-bar `Save` button (`Ctrl+S`). The adjacent `Open save menu`
  may offer `Save & Verify Data`; use it when schema/data changes are involved.
- **Deploy** is `Manage deployment` in the top bar. Deploy only after
  `appdef.py validate` is clean and the preview passes.

## 4. Improved editor map

- **Data** → left tree of tables, plus `Options` → `User settings`. Table detail
  header: `View data source`, `Table settings`, `Regenerate schema`,
  `Add virtual column`, `More`. The column grid is the same shape as legacy.
- **App** → views. Prefer the legacy `UX → Views` map when possible; the improved
  App pane moves views into `Primary navigation` / `Menu navigation` /
  `Other views` groups.
- **Actions** → left tree grouped by table; `Add Action`; same action editor
  headings as legacy.
- **Security** → `Security Filters` → per-table `Access:` / `Filter:` summaries,
  expand to edit.
- **Settings** → app properties, documentation, etc.

The improved editor's left nav uses `treeitem` roles and `heading [level=3]`
labels. Use `browser_find` for the table name and then scope the snapshot to the
adjacent detail pane.

Stable anchors (verified):

- nav buttons: `aria-label` = `Data`, `App`, `Actions`, `Automation`, `Security`,
  `Settings`, `Manage`, `Learn`
- table toolbar: `title` = `Add virtual column`, `Regenerate schema`,
  `Table settings`, `More`
- save: button text `SAVE` or `aria-label="Save"`, plus
  `aria-label="Open save menu"`
- column rows: `button[title="edit"]` inside the grid row

## 5. DOM-first recipes

See `references/dom-recipes.md` for copy-paste JavaScript. The core loop:

```js
// 1. Locate a visible element by exact accessible text, return a tiny summary.
(() => {
  const els = [...document.querySelectorAll('button,[role="button"],a,div')]
    .filter(e => e.offsetParent && e.textContent.trim() === 'Save');
  return els.map(e => ({tag: e.tagName, text: e.textContent.trim()}));
})()
```

```js
// 2. Click it.
(() => {
  const el = [...document.querySelectorAll('button,[role="button"]')]
    .find(e => e.offsetParent && e.textContent.trim() === 'Save');
  if (!el) return 'not found';
  el.click();
  return 'clicked';
})()
```

```js
// 3. Read a dialog's headings and current values (scoped, small).
(() => {
  const dlg = document.querySelector('[role="dialog"]');
  if (!dlg) return 'no dialog';
  return [...dlg.querySelectorAll('h3,h5,h6')].map(h => h.textContent.trim());
})()
```

Use the browser's accessibility snapshot with a **target** and **depth** when you
need structure, not the whole page:

```
browser_snapshot(target: '[role="dialog"]', depth: 4)
```

### Tooling equivalents

Tool names vary by harness. The capability matters, not the name:

| Capability | Playwright MCP | Generic |
|---|---|---|
| Evaluate JS in the page | `browser_evaluate` | `page.evaluate(...)` |
| Find by text | `browser_find` | `page.getByText(...)` |
| Scoped snapshot | `browser_snapshot({target, depth})` | `page.accessibility.snapshot({root})` |
| Network log | `browser_network_requests` | CDP `Network.responseReceived` |
| Read a response body | `browser_network_request` | `response.text()` |
| Attach to an existing Chrome | — | `chromium.connectOverCDP("http://[::1]:9222")` |
| Read the app template | — | `page.evaluate(() => fetch("/api/template/<id>", {credentials:"include"}).then(r => r.json()))` |
| Enumerate loaded bundles | — | `performance.getEntriesByType("resource")` |

If your harness has no network tool, attach over CDP or fetch the template from
the authenticated page. Do not fall back to screenshots.

## 6. Context budget

| Method | Typical cost | Use for |
|---|---|---|
| `browser_evaluate` returning 5–20 elements | < 300 tokens | Locating, reading state, clicking |
| `browser_find` by text | 200–800 tokens | “Where is this control?” |
| `browser_snapshot` with `target` + `depth: 3–4` | 1–5k tokens | Understanding a dialog/panel |
| Full-page accessibility snapshot | 20–200k tokens | **Avoid** |
| Screenshot | ~1–2k tokens, plus one of 30 images | Visual verification only |

## 7. Screenshot budget

| Situation | Allowed |
|---|---|
| Finding a field or button | **No** — use DOM |
| Confirming a dialog opened | **No** — read its heading |
| Confirming an expression saved | **No** — read the textbox / appdef |
| Verifying theme, icon, color, layout, mobile fit | **Yes** — 1 screenshot, saved to a file |
| Reporting a visual regression to the user | **Yes** — 1 before/after max |

When you do screenshot, target the element or the preview pane, not the full
page, and save it to the workspace rather than returning it inline when the tool
allows.

## 8. Failure modes and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `Save` disabled | No pending change, or invalid expression | Re-read the field; check for a red error under the expression |
| Expression rejected | Leading `=` pasted into the UI, unbalanced quotes/parens | Paste without `=`; count quotes/parens |
| Wrong table's column opened | Table accordion collapsed/expanded state changed | Re-read the dialog heading `<Table> : <Column>` |
| Ref/selector stale | Snapshot regenerated | Re-locate by name; never reuse old refs |
| Preview shows old data | Preview not reloaded after Save | Save, then reload the preview iframe |
| App not runnable after security edit | Self-referencing security filter (often `Users`) | Remove the filter, Save, verify `Runnable: True` |
| View missing | Position `ref` or `Show_If` false | Check `appdef.py view <name>` |
| Action not visible | `Position: Hide`, false only-if, or wrong table | Check `appdef.py action ...` |

## 9. Bulk and scripted saves

Prefer the editor for interactive work. For coordinated bulk changes, the
supported automation path is:

```
POST https://www.appsheet.com/api/saveapp
```

with a gzipped body `{appId, appJson: JSON.stringify(template), validate: true}`.
It returns `Success`, `AppErrors`, `CommitHash`, `BuildHash`, and the new app in
`App`. This is verified and works; it is not a read-only endpoint. It is also
version-sensitive — if the response shape changes, fall back to the editor and
update the reference.

Do not confuse this with editing a JSON file on disk — that does nothing until it
is sent through `saveapp` (or applied in the editor). The full contract, gzip
requirement, failure modes, verification via `GET /api/template/{appId}`, and a
safe workflow are in `references/saveapp.md`.

Guardrails:

- Capture `before`, apply only the planned delta, save, verify the version,
  `diff`, preview, then deploy.
- Use `validate: true` and inspect `AppErrors`; `Success: true` is not “no
  warnings”.
- `saveapp` creates a version but does not populate the editor's undo stack.
  Rollback is the previous version in `Manage → Versions`, not Ctrl+Z.
- Do not bypass the diff/role-test loop just because a script can write fast.

## 10. Do not

- Do not scrape `document.body.innerText` or take a full-page screenshot to
  "see what's there". Both are context bombs.
- Do not use pixel coordinates or CSS class names.
- Do not edit an appdef JSON file and assume it is live. The save path is the
  editor or `POST /api/saveapp`; a file on disk is only a baseline.
- Do not click `Regenerate Structure` to "fix" a column. It can drop virtual
  columns and reorder the schema. Use it only when the data source structure
  genuinely changed, and diff afterward.
- Do not leave the app in a half-saved state. Save, diff, then continue.

## 11. References

- `references/dom-recipes.md` — copy-paste DOM queries for both editor modes.
- `references/saveapp.md` — `POST /api/saveapp` contract and safe bulk-edit
  workflow.
