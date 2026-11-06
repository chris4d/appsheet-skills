---
name: appsheet-appdef
description: Use when you need to inspect, audit, diff, or verify a Google AppSheet app without clicking through the editor. Covers obtaining the app definition JSON, the capture/retention policy, the appdef object model (tables, columns, slices, views, menus, actions, security, automations), and a dependency-free CLI that answers structural questions, validates refs/menus/slices, diffs two versions, and produces a compact Markdown spec. Load this before any AppSheet editor automation so you work from ground truth instead of screenshots.
---

# AppSheet app definition (appdef)

The app definition JSON is the cheapest, most reliable view of an AppSheet app.
A 1–2 MB appdef compresses to a 20–30 KB Markdown spec, which fits in context far
better than editor screenshots or accessibility snapshots.

**Rule:** read the appdef before touching the editor, and re-read it after saving.
Use the editor only for mutations and visual checks.

## 1. Capture policy

Appdefs are large; the before/after *pair* is cheap, but unbounded retention is
not. One repo accumulated 18 copies / 30.6 MB raw (1.3 MB gzipped) in two days
under a “store every capture” rule.

| Artifact | Size |
|---|---|
| One appdef, pretty-printed | 1.35–2.24 MB |
| One appdef, compact | ~1.3 MB |
| One appdef, compact + gzipped | ~46–80 KB |
| `export-md` spec | ~23 KB |
| Semantic diff for one change | ~2 KB |

Policy:

- Keep **one rolling baseline** at `appdef/current.json`, compact (not
  pretty-printed). This is what tools read by default.
- Capture a `before` only for the duration of a change. Diff it, then delete it.
  The next change's `before` is the previous `after`.
- Keep **after-only** snapshots for deployed versions, gzipped:
  `appdef/<version>.json.gz`, pruned to the last 10.
- Regenerate `docs/app-spec.md` every change; it is the cheap, reviewable
  artifact.
- Maintain `appdef/INDEX.md`: version, date, file, commit/deploy note. Agents
  otherwise guess which JSON is current — this cost real time in one session.
- Never keep pretty-printed duplicates, and never keep both `-current` and
  `-backup` copies of the same version.

Steady state: `current.json` (~1.3 MB) + 10 × 80 KB gz + 23 KB spec ≈ **2 MB**,
not 30 MB.

`appdef/INDEX.md`:

```markdown
| Version | Date | File | Note |
|---|---|---|---|
| 1.000217 | 2026-11-06 | 20261106-1102-v1.000217.json.gz | Added sample checkout history |
| 1.000216 | 2026-11-05 | 20261105-1630-v1.000216.json.gz | CRM vendor sync |
```

`current.json` is the working copy; the index is the history.

Use the helper:

```powershell
# compact snapshot + rolling current.json + summary + diff + validate
powershell -File scripts\snapshot.ps1 -Appdef <current.json> -Dir appdef -Label before
# deployed snapshot, gzipped, keep last 10
powershell -File scripts\snapshot.ps1 -Appdef <current.json> -Dir appdef -Label v1.000217 -Compress -Prune 10
```

`python appdef.py compact <in> <out>` writes a compact copy directly.

### Get a fresh appdef

Preferred, in order:

1. **Existing baseline** — use `appdef/current.json` (or
   `app-definition-backup.json`), but check `LastModified` and `Version` first.
2. **Save API template** — `GET /api/template/{appId}` in an authenticated
   editor session returns `{Template, CommitHash, ...}`. This is the same
   template the editor saves and avoids a UI round-trip. See
   `appsheet-editor/references/saveapp.md`.
3. **AppSheet Toolbox extension** — command palette → “save app template” /
   “download app template as JSON”. This format includes `_index`, `_path`,
   `_isSystemGenerated`, and `_isMinor` annotations.
4. **Network capture** — with the editor open, capture the response body of the
   app-definition request (contains `AppData` and `Presentation`).

### Network-capture recipe

Tool names vary by harness; use the equivalents available to you.

1. List requests since the session started, filtered to the definition:
   - Playwright MCP: `browser_network_requests({ static: false, filter: "appdef|apptemplate|definition", all: true })`
   - Generic CDP: attach with `chromium.connectOverCDP("http://[::1]:9222")`,
     then read `page.on("response")` or `performance.getEntriesByType("resource")`.
2. Find the request whose response is the app object (it contains `AppData` and
   `Presentation`). Note its 1-based index.
3. Read the body:
   - Playwright MCP: `browser_network_request({ index: N, part: "response-body", filename: "appdef/raw.json" })`
   - Generic: `page.evaluate(() => fetch("/api/template/<id>", {credentials:"include"}).then(r => r.json()))`
4. If the body is wrapped (for example `{"result": {...}}`), unwrap it, then run
   `appdef.py summary` to confirm it parses.

The editor's **Settings → App documentation** link produces human-readable HTML,
not the JSON appdef. Do not confuse the two.

If you cannot obtain a fresh appdef, say so and fall back to editor inspection —
do not pretend a stale file is current.

## 2. Use the CLI

`scripts/appdef.py` is stdlib-only Python 3. Run it from anywhere:

```powershell
python <skill-dir>\scripts\appdef.py summary appdef/current.json
```

### Command map

| Question | Command |
|---|---|
| What is in this app? | `summary <appdef>` |
| List tables, keys, labels, update rules | `tables <appdef>` |
| Show every column in a table | `table <appdef> Materials` |
| Show one column in full (type, ref, all expressions) | `column <appdef> Materials DisplayName` |
| List views, types, data sources, positions | `views <appdef>` |
| Primary/menu views only (skip ref/system views) | `views <appdef> --primary` |
| Show one view's sort, group, columns, show-if | `view <appdef> "Pending Approvals"` |
| List navigation menu entries | `menus <appdef>` |
| List actions with conditions | `actions <appdef>` / `actions <appdef> --table Materials` |
| Show one action's assignments | `action <appdef> Approve --table ProjectMaterials` |
| List slices and row filters | `slices <appdef>` |
| Auth, roles, update rules, security filters | `security <appdef>` |
| Dump every expression | `exprs <appdef>` / `exprs <appdef> --table Users` |
| Find a name or expression | `search <appdef> "ApprovalStatus"` |
| Structural checks before deploy | `validate <appdef>` |
| Fold in server `AppErrors` from a save response | `validate <appdef> --server-errors save-response.json` |
| What changed after an edit? | `diff <before> <after>` |
| Compact spec for the repo / context | `export-md <appdef> docs/app-spec.md` |
| Compact copy (no whitespace) | `compact <in> <out>` |

Add `--json` to most commands when you need to post-process.

### Typical loop

```powershell
# 1. Baseline (writes a timestamped before, updates current.json)
powershell -File scripts\snapshot.ps1 -Appdef appdef/current.json -Dir appdef -Label before
python appdef.py export-md appdef/current.json docs/app-spec.md

# 2. ...make edits in the editor, Save...

# 3. Capture the after. The helper automatically diffs against the previous
#    snapshot and validates it.
powershell -File scripts\snapshot.ps1 -Appdef appdef/after.json -Dir appdef -Label after
# then delete the before; keep the after (gzipped if deployed)
```

Or use the helper, which copies the appdef to a timestamped file, summarizes it,
diffs it against the previous snapshot, and validates it:

```powershell
powershell -File scripts\snapshot.ps1 -Appdef <current.json> -Dir appdef -Label before
```

`diff` is semantic: it reports table/column/view/action/slice/security changes,
not JSON key reordering or annotation noise. If `diff` shows anything you did not
intend, stop and fix it before deploying.

## 3. Object model (where things live)

| Concept | JSON path | Notes |
|---|---|---|
| Tables | `AppData.DataSets[]` | one entry per table, including `_Per User Settings` |
| Columns | `AppData.DataSchemas[].Attributes[]` | matched to a table by `DataSet.SchemaName` |
| Slices | `AppData.TableSlices[]` | row filter is `FilterCondition` (leading `=`), sometimes `FilterExpression.Expression` |
| Actions | `AppData.DataActions[]` | `Table`, `ActionType`, `Condition`, `ActionSettings`/`ActionDefinition` |
| Views | `Presentation.Controls[]` | not under `AppData`; `Action` is the view type, `TableOrFolderName` is the data source |
| Navigation | `Presentation.MenuEntries[]` | one entry per view; `ViewName` must exist and be unique |
| Format rules | `Presentation.FormatRules[]` | often empty |
| Bots / automations | `Behavior.AppBots`, `AppProcesses`, `AppEvents`, `AppWorkflowRules`, `WorkflowRules`, `Tasks` | may be absent in older exports; `diff` covers all of them |
| Auth / roles | `Behavior`, top-level `UserRoles` | `AuthRequired`, `AllowAllSignedInUsers`, `DomainAuthRequired` |

### Gotchas that cause bad analysis

- **Expressions in appdef start with `=`** (`=IF(...)`, `=LOOKUP(...)`). The
  editor's expression box shows them **without** the leading `=`. Strip it when
  pasting into the UI; add it when writing appdef-shaped examples.
- **`TypeAuxData` is a JSON string**, not an object. Parse it to get `Show_If`,
  `Editable_If`, `Required_If`, `Valid_If`, `EnumValues`,
  `ReferencedTableName`, and numeric/type options.
- **`ActionSettings` and view `Settings` are also JSON strings.** Prefer
  `ActionDefinition` / `ViewDefinition` when present; otherwise parse.
- **Slices do not use `RowFilterCondition` in current exports.** Use
  `FilterCondition` or `FilterExpression.Expression`.
- **Views are not in `AppData`.** Searching only `AppData` will miss every view.
- **`_index`, `_path`, `_isSystemGenerated`, `_isMinor` are annotations**, not
  app semantics. Ignore them in diffs and when writing your own tooling.
- **Auto-generated ref views** inflate the view count. Use `views --primary` for
  the views a human actually built.
- **A view's data source may be a slice, not a table.** Resolve through
  `TableSlices` before checking column membership.
- **A Ref stores the target's `ReferencedKeyColumn`, not necessarily `Row ID`.**
  AppSheet-database tables carry an auto `Row ID`, but semantic keys coexist and
  are usually the actual join value. See `appsheet-patterns` schema conventions.
- **Navigation is `Presentation.MenuEntries[]`, separate from views.** A menu
  entry whose `ViewName` is missing or duplicated is a real error; `diff` now
  covers it.
- **Table security is split** between `UpdateModeExpression` (who can add/edit/
  delete) and `DataFilter` (which rows are visible). Neither is a substitute for
  the other.

## 4. What to report

When summarizing an app for a human, lead with:

1. app name, version, last modified, runnable/valid;
2. table/column/view/action/slice counts;
3. the table list with keys and labels;
4. the primary views and their data sources;
5. security model: auth mode, roles, per-table update rule and row filter;
6. anything `validate` flags.

Do not dump the whole appdef or the whole Markdown spec unless asked. Use
`search`, `view`, `column`, and `action` to pull only the relevant slice.

## 5. Local vs server validation

`appdef.py validate` is **structural**: keys, refs, slices, views, menu entries,
actions, duplicate names. It does not replace the AppSheet compiler.

Server errors such as `INFO_SIGNIN_ALLOWLIST` and `INFO_IMAGE_NOTPRESENT` only
come from:

- the `AppErrors` array in a `POST /api/saveapp` response, or
- `localStorage[appId + "_errors"]` in the editor.

Fold them into the local report:

```powershell
python appdef.py validate appdef/current.json --server-errors save-response.json
```

`INFO_*` codes are reported as warnings; everything else is an error. If you only
ran the local validator, say **“structurally clean, not server-verified”** — do
not claim the app is deployable.

## 6. Files

- `scripts/appdef.py` — the CLI (stdlib only).
- `scripts/snapshot.ps1` — compact snapshot, rolling baseline, diff, validate,
  gzip, prune.
- `references/appdef-schema.md` — field-by-field reference and examples for
  writing new queries or a custom exporter.
