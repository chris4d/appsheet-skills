---
name: appsheet-build
description: Use when building or changing a Google AppSheet app end to end — new app, new table, schema/security/view/action work, or a brownfield change that must be verified and deployed. Provides the build order, the appdef-baseline → edit → diff → validate → preview → deploy loop, role-based test matrix, and definition-of-done checklists. Load alongside appsheet-appdef and appsheet-editor.
---

# Building and changing AppSheet apps

This skill is the **process**. Use `appsheet-appdef` for reading/verifying the
app and `appsheet-editor` for the UI mechanics.

The CLI is `scripts/appdef.py` inside the `appsheet-appdef` skill. In the
examples below, set:

```powershell
$CLI = "$env:USERPROFILE\.config\opencode\skills\appsheet-appdef\scripts\appdef.py"
```

(or the project-local equivalent).

## The loop (brownfield changes)

Every change, no matter how small, follows this loop:

1. **Baseline** — capture the current appdef and a readable spec.
   ```powershell
   python $CLI summary appdef/current.json
   python $CLI export-md appdef/current.json docs/app-spec.md
   ```
   The before-spec is intentionally overwritten on the next change; `diff` is
   the record of what changed. If you need history, commit the spec or keep the
   gzipped after snapshot, not both pretty-printed appdefs.
2. **Plan the delta** — write down the exact components and expected effect:
   table/column/view/action/slice names, expressions, security rule. If you
   cannot name the component, you are not ready to click.
3. **Edit** — one logical group at a time, via the editor or `POST /api/saveapp`
   for coordinated bulk changes. Save.
4. **Re-capture** — download the appdef as `appdef/after.json`.
5. **Prove the delta** — `snapshot.ps1` diffs the new capture against the
   previous snapshot; or run `python $CLI diff <previous>.json appdef/after.json`.
   Only the intended changes should appear. If not, fix before continuing.
6. **Validate** — `python $CLI validate after.json` must be error-free.
7. **Preview** — test as each affected role using `Preview app as`. Check the
   actual view/action, not just that the editor saved.
8. **Deploy** — `Manage deployment`. Record the new version.
9. **Record** — update `appdef/INDEX.md`, keep the gzipped after snapshot, delete
   the temporary before, regenerate `docs/app-spec.md`, and commit a short change
   note.

If step 5 or 6 fails, do not deploy. Roll back by restoring the previous version
in `Manage → Versions` (or by reversing the specific edits), then re-baseline.

## Build order (greenfield)

Build in dependency order. Most "AppSheet is fighting me" problems are caused by
building a later layer before its dependency exists.

### 1. Data source and tables

- Choose the source deliberately:
  - **AppSheet database** (`google_tables`) — best for new apps, native types,
    no sheet-structure fragility.
  - **Google Sheets** (`google`) — best when the sheet is the system of record
    or humans edit it directly.
  - SQL — when there is already a database and scale/transactions matter.
- One table per entity. Name tables and columns in `PascalCase` with no spaces
  for machine-facing names; use `DisplayName` for human labels.
- Every table needs:
  - a **stable key** (human-readable IDs like `MAT-0001`, or `UNIQUEID()` when
    the key is hidden);
  - a **label** column (the thing users see in refs and lists);
  - an **Active** flag when rows are retired rather than deleted;
  - audit columns where edits matter (`LastChangedBy`, `LastChangedDate`).
- Add `Ref` columns only after the target table exists. Set the referenced table
  and, when the child is a line item, `Is a part of?`.

### 2. Column definitions

- Set type before expressions. A `Text` column with a date expression is a
  future bug.
- Enum/EnumList values live in the column type options, not in a separate table,
  unless the list is managed by users — then use a lookup table and `Valid_If`.
- Required/editable/show-if belong on the column, not only in the form view.
- Prefer `App formula` for computed values; use `Initial value` only for values
  that must be captured once.
- Keep virtual columns intentional. Each one costs sync time. Avoid
  `SELECT()` over large tables in virtual columns.

### 3. Security model

Build security **before** sharing, but **after** the `Users` table exists and has
at least one Admin row.

- Create `Users` with `Email` (label, required, unique), `Role`, `Active`, and a
  hidden key. Some apps also carry a text mirror (`ActiveFlag`) for filter
  expressions; use whichever column the appdef actually has, consistently.
- Role helper expressions:
  ```appsheet
  LOOKUP(USEREMAIL(), "Users", "Email", "Role")
  LOOKUP(USEREMAIL(), "Users", "Email", "Name")
  LOOKUP(USEREMAIL(), "Users", "Email", "ActiveFlag") = "Yes"
  ```
- Table update rule:
  ```appsheet
  IF(IN(LOOKUP(USEREMAIL(), "Users", "Email", "Role"), LIST("Admin", "Librarian")), "ALL_CHANGES", "READ_ONLY")
  ```
- Table security filter: the active-user test above, applied to every data table.
- **Do not** put a security filter on `Users` that references `Users`. It makes
  the app non-runnable. Protect `Users` with an Admin-only update rule and share
  only with trusted users.
- Column-level `Editable_If` for fields that only some roles may change.
- `Show_If` is presentation, not security. Never rely on it to hide sensitive
  data.

### 4. Slices

Create slices only after the base table's columns and security are stable.
A slice is a named, filtered projection:

- name it for the question it answers (`Pending_Approvals`,
  `Outstanding_Orders`, `Active_Vendors`);
- row filter is an expression over the source table;
- include only the columns the view needs;
- remember the table's security filter still applies.

### 5. Views and navigation

- Decide the primary navigation first: 3–5 `first`/`next` views, everything else
  in `menu`.
- One table usually needs: a list/table view, a detail view, and a form. Ref
  views are auto-generated; customize them only when needed.
- Set `Position`, `Sort by`, `Group by`, and `Columns` deliberately. Empty
  column order means "all columns", which often leaks IDs and audit fields.
- Give every user-facing view an icon (`fas fa-*`) and a display name.
- Dashboard views reference existing view names; build the component views first.

### 6. Actions

- Prefer `Data: set the values of some columns in this row` for state changes
  (approve, receive, check out). Put the transition rule in `Only if`.
- Use `App: go to another view within this app` + `LINKTOFORM(...)` for
  "create a related row" flows.
- Set `Position` intentionally: `Primary` for the main action, `Prominent` for
  secondary, `Inline` for row-level, `Hide` for actions triggered by other
  actions.
- For bulk work, use `Data: execute an action on a set of rows` and a selection
  expression; do not duplicate the row action.
- Actions that modify data should set audit columns in the same assignment list.

### 7. Format rules

Add only after the view works. Format rules highlight state; they do not change
data. Keep conditions simple and mutually exclusive where possible.

### 8. Automations

- Event: data change on the table that owns the state transition.
- Condition: compare `[_THISROW_BEFORE]` and `[_THISROW_AFTER]` so the bot fires
  once per real transition.
- Process: notification/email/webhook. Keep templates short and test with a real
  row.
- Bots are the least stable part of the export format; verify them in the editor
  and in a test run, not only in the appdef.

## Role-based test matrix

Test each role that can reach the app, not just Admin:

| Check | Admin | Librarian | Designer | Viewer |
|---|---|---|---|---|
| Sees only intended rows | | | | |
| Can add/edit/delete per table | | | | |
| Cannot edit Admin-only columns | | | | |
| Actions appear/hide correctly | | | | |
| Approval/order/checkout transitions work | | | | |
| Forms prefill and validate | | | | |
| Detail views show the right columns | | | | |
| No blank/ID headers in normal mode | | | | |

Use `Preview app as` with a real email from `Users`. Change one role at a time.

Also test:

- empty state (slice returns no rows);
- duplicate/invalid input (unique validations);
- a ref with no match (blank label, not an error);
- mobile preview for primary views;
- offline/sync only if the app is expected to be used offline.

## Definition of done

- [ ] `appdef.py validate` reports 0 errors.
- [ ] `appdef.py diff before after` contains only intended changes.
- [ ] Every new table has a key and label.
- [ ] Every new Ref points to an existing table.
- [ ] Security filters and update rules match the role matrix.
- [ ] `Users` has no self-referencing security filter.
- [ ] Every new view has a position, data source, and intentional column order.
- [ ] Every new action has an `Only if` condition and the right prominence.
- [ ] Preview passes for each affected role.
- [ ] App is `Runnable: True` and `Valid: True`.
- [ ] Deployed, version recorded in `appdef/INDEX.md`.
- [ ] Gzipped after snapshot kept; temporary before deleted.
- [ ] `docs/app-spec.md` regenerated.

## Change note template

```markdown
## 2026-11-06 — Add sample checkout history

- Tables: `SampleCheckouts` (new), `Materials.SampleLabelID` (new Ref)
- Views: `Sample Checkouts` (table, menu, group by ProjectID)
- Actions: `Check Out`, `Check In` on `ProjectMaterials`
- Security: `SampleCheckouts` updates = Admin/Librarian; filter = active user
- Verified: Admin + Librarian preview; Designer cannot check out
- Deployed: v1.000210
```
