---
name: appsheet-patterns
description: Use when designing or debugging AppSheet behavior — expressions, schema conventions, roles and security filters, slices, views, actions, and automations. Provides the house patterns that keep apps runnable and maintainable, the correct mechanism for each job, and the expression/security gotchas that otherwise cost a debugging session.
---

# AppSheet patterns and conventions

Use this skill for the *what* and *why*; use `appsheet-editor` for the *where to
click* and `appsheet-appdef` for verification.

## 1. Choose the right mechanism

| Goal | Mechanism | Not this |
|---|---|---|
| Hide rows from a user entirely | Table **security filter** | Slice or `Show_If` |
| Show a subset in one view | **Slice** row filter | Security filter |
| Hide a column in one view/form | View column order / `Show_If` | Security filter |
| Prevent a role from editing a column | `Editable_If` / table update rule | `Show_If` |
| Prevent invalid input | `Valid_If` + error message | Format rule |
| Highlight a row | Format rule | Action |
| Change data on a button | Action (`SET_COLUMN_VALUE`) | Automation |
| React to a data change | Bot / automation | Action |
| Prefill a new row | `Initial value` or `LINKTOFORM` | App formula |
| Compute a value continuously | App formula (virtual column) | Initial value |

`Show_If` is presentation only. It does not secure data. A determined user can
reach hidden columns through refs, exports, or the API.

## 2. Expression essentials

- Column reference: `[ColumnName]`.
- Current row: `[_THISROW]`; in bots: `[_THISROW_BEFORE]`, `[_THISROW_AFTER]`.
- Dereference a ref: `[RefColumn].[Column]`, including multi-hop
  `[MaterialID].[CSIDivisionID].[CSIDivisionName]`.
- Table column list: `TableName[ColumnName]`.
- Select rows: `SELECT(Table[Key], condition)`; `FILTER("Table", condition)` is
  the row-list equivalent.
- One value: `ANY(SELECT(...))` or `LOOKUP(value, "Table", "KeyColumn", "ReturnColumn")`.
- Membership: `IN(value, LIST("A","B"))` or `IN(value, Table[Column])`.
- Count: `COUNT(SELECT(...))`.
- Text: `CONCATENATE(...)`, `&`, `IF(ISBLANK(x), "", ...)`.
- Dates: `TODAY()`, `NOW()`, `DATE(...)`, `YEAR/MONTH/DAY`, `EOMONTH`.
- User: `USEREMAIL()`, `USERNAME()`, `USERSETTINGS("...")`.
- Navigation: `LINKTOFORM("ViewName", "Column", value, ...)`,
  `LINKTOVIEW("ViewName")`, `LINKTOROW(key, "ViewName")`.

Rules that prevent most expression bugs:

1. Text literals use double quotes. Escape embedded quotes by doubling them or
   use `CONCATENATE` with `CHAR(34)`.
2. The appdef stores expressions with a leading `=`; the editor does not. Strip
   it when pasting into the UI.
3. `[_THISROW]` is required when a `SELECT` condition refers to the current row:
   `SELECT(ProjectMaterials[ProjectMaterialID], [ProjectID] = [_THISROW].[ProjectID])`.
4. `LOOKUP` returns blank when no row matches. Guard it:
   `IF(ISBLANK(LOOKUP(...)), "Viewer", LOOKUP(...))`.
5. `USEREMAIL()` is case-sensitive in some data sources. Normalize with
   `LOWER(USEREMAIL())` if the `Users` table may contain mixed case.
6. `SELECT` over a large table in a virtual column runs on every sync. Prefer a
   slice, a security filter, or a stored rollup.
7. `AND`/`OR` short-circuit is not guaranteed in every context; keep conditions
   side-effect free.
8. `IN()` on an empty list is false; handle the empty case explicitly.
9. Date/time comparisons need matching types: compare `Date` to `TODAY()`, not
   to `NOW()`.
10. Use `ISBLANK()` rather than `= ""` for refs and numbers.

See `references/expressions.md` for a function cookbook and worked examples.

## 3. Schema conventions

- `PascalCase` for table and column names, no spaces.
- Stable, human-readable keys when users see them (`MAT-0001`, `PRJ-001`);
  `UNIQUEID()` only for hidden keys.
- Every table: key, label, `Active` (when retireable), audit columns
  (`LastChangedBy`, `LastChangedDate`).
- `Ref` columns end in `ID` and point to the target table's key.
- Enum values are stored in the column definition; use a lookup table when users
  must maintain the list.
- Virtual columns are named for what they return (`DisplayName`,
  `ProjectCount`), not for how they are computed.
- Money uses `Price`; percentages use `Percent`; quantities use `Number` or
  `Decimal` deliberately.
- Keep a `DevMode` pattern for exposing technical IDs only to Admins:
  a hidden `Users.DevMode` flag plus `Show_If` on key columns.

See `references/schema-conventions.md`.

## 4. Security patterns

The house pattern is a `Users` table keyed by email:

```
Users: Email (label, required, unique), Name, Role, ActiveFlag, DevMode, UserID (hidden key)
```

Role helper:

```appsheet
LOOKUP(USEREMAIL(), "Users", "Email", "Role")
```

Table update rule:

```appsheet
IF(IN(LOOKUP(USEREMAIL(), "Users", "Email", "Role"), LIST("Admin", "Librarian")), "ALL_CHANGES", "READ_ONLY")
```

Table security filter:

```appsheet
LOOKUP(USEREMAIL(), "Users", "Email", "ActiveFlag") = "Yes"
```

Non-negotiables:

- Never put a security filter on `Users` that references `Users`. The app becomes
  non-runnable.
- `Users` rows are visible to all app users unless you accept the self-filter
  risk; protect edits with an Admin-only update rule and share only with trusted
  users.
- Unique email validation:
  ```appsheet
  COUNT(SELECT(Users[Email], AND([Email] = [_THISROW].[Email], [UserID] <> [_THISROW].[UserID]))) = 0
  ```
- Test with a real non-Admin user. Admin bypasses many mistakes.

See `references/security.md`.

## 5. Views and actions

- Primary navigation: 3–5 views. Everything else `menu`.
- One list view + one detail + one form per table; customize the auto-generated
  ref views instead of duplicating them.
- Always set column order; empty means "all columns", including IDs and audit
  fields.
- `Group by` is for scanning; `Sort by` is for ordering. Do not use both to
  simulate one another.
- Actions: `Primary` for the one main action, `Prominent` for secondary,
  `Inline` for row-level, `Hide` for internal.
- `SET_COLUMN_VALUE` actions should set audit columns in the same assignment
  list.
- `LINKTOFORM` prefills a form; it does not create the row. The form's save does.
- Bulk actions use `execute an action on a set of rows`; do not duplicate logic.

See `references/views-actions.md`.

## 6. Debugging workflow

1. Reproduce with the smallest role and the smallest view.
2. `appdef.py search <expr-fragment>` to find every place the expression or
   column appears.
3. `appdef.py column <table> <column>` to see the full definition, including
   `Show_If`, `Editable_If`, `Valid_If`, and the app formula.
4. Check the table's `UpdateModeExpression` and `DataFilter` before blaming the
   view.
5. Check `appdef.py summary` for `Runnable: False` after security changes.
6. Only then open the editor. Use `Preview app as` with the failing user.
7. After the fix, diff the appdef and add a regression note to the app repo.

## 7. Anti-patterns

| Anti-pattern | Why it hurts | Do instead |
|---|---|---|
| `Show_If` as security | Data still reachable | Security filter / `Editable_If` |
| Security filter on `Users` | App can become non-runnable | Admin-only update rule |
| `SELECT` in many virtual columns | Slow sync | Slice, stored rollup, security filter |
| Duplicating an action per row | Maintenance burden | Bulk action + selection expression |
| Empty view column order | Leaks IDs/audit fields | Explicit order |
| `UNIQUEID()` as a visible key | Unreadable refs | Human-readable key or label |
| Editing appdef JSON directly | No deployment path | Editor + diff |
| Screenshot-driven UI work | Context burn, fragile | DOM-first + appdef |
