# Schema conventions

## Naming

| Thing | Convention | Example |
|---|---|---|
| Table | `PascalCase`, plural | `Materials`, `ProjectMaterials` |
| Column | `PascalCase`, no spaces | `MaterialName`, `DateOrderPlaced` |
| Key | `<Entity>ID` | `MaterialID`, `ProjectID` |
| Ref | `<Target>ID` | `VendorID`, `CSIDivisionID` |
| Virtual column | what it returns | `DisplayName`, `ProjectCount` |
| Slice | what it selects | `Pending_Approvals`, `Active_Vendors` |
| View | user-facing title | `Pending Approvals`, `Outstanding Orders` |
| Action | verb phrase | `Approve`, `Mark Received`, `Add to Project` |

Avoid spaces and punctuation in machine-facing names. Use `DisplayName` for the
human label instead of renaming the column.

## Keys

- Keys must be stable and unique. Never use a mutable value (name, email,
  status).
- Prefer human-readable keys when users see them in refs: `MAT-0001`,
  `PRJ-001`, `VEN-0010`.
- Use `UNIQUEID()` for hidden surrogate keys.
- Composite keys are possible but make refs and debugging harder; prefer a
  single key.
- Do not expose a generated key in normal views unless the workflow needs it.
  Use the DevMode pattern for Admin-only visibility.

## Row ID vs semantic keys

AppSheet-database (`google_tables`) tables always get an auto `Row ID` column
(`UNIQUEID("PackedUUID")`). It is hidden and **cannot be deleted**.

This is not a duplicate of your semantic key (`MAT-0001`, `PRJ-001`):

- A `Ref` stores the value of the target's `IsKey` column. That column is named
  in the Ref's `TypeAuxData.ReferencedKeyColumn`.
- Semantic keys are the actual join values stored in Ref cells. They coexist with
  `Row ID`; they are not redundant.
- Repointing Refs to `Row ID` means rewriting every Ref cell to
  backend-generated UUIDs. That is a data migration, not a config toggle. Do not
  do it casually.
- Sheets-backed tables have no auto `Row ID`. That is why behavior differs
  between app types and why “just use the row id” advice from a Sheets app does
  not transfer.

When a Ref points at the wrong column, check `ReferencedKeyColumn` before
blaming the data. `appdef.py validate` now checks that the named key exists and
is actually `IsKey` in the target table.

## Labels

Every table needs a label: the value users see when the row appears in a ref,
inline list, or detail header.

- `Materials` → `MaterialName` (or a virtual `DisplayName`).
- `Projects` → `ProjectName`.
- `Vendors` → `VendorName`.
- `Users` → `Email`.
- Join tables → a virtual label combining the two parents
  (`Material - Project - Mark`).

Without a label, AppSheet falls back to the key, which is usually unreadable.

## Ref columns

- Create the target table first.
- Set the column type to `Ref` and choose the source table.
- The ref stores the target key; the UI displays the target label.
- Dereference with `[RefColumn].[Column]`.
- Mark `Is a part of?` when the child rows are line items of the parent. This
  enables inline add and cascade delete.
- Add a virtual reverse column (`REF_ROWS("Child", "ParentID")`) when the parent
  detail view should show children. AppSheet often creates this automatically.
- Avoid refs to a slice; refs point to tables.

## Enums vs lookup tables

Use an **Enum** when:

- the list is small and stable;
- only the app owner changes it;
- the values are part of the schema (status, role, yes/no).

Use a **lookup table** when:

- users maintain the list;
- the list is long or changes often;
- you need metadata per value (code, description, sort order).

For a lookup table, the column is a `Ref` to the lookup table, not an Enum. Use
`Valid_If` only when you need to restrict the allowed rows.

## Audit columns

Add to tables where edits matter:

| Column | Type | Initial value | Editable |
|---|---|---|---|
| `LastChangedBy` | Email/Text | `USEREMAIL()` | no (actions set it) |
| `LastChangedDate` | DateTime | `NOW()` | no (actions set it) |
| `CreatedBy` | Email/Text | `USEREMAIL()` | no |
| `CreatedDate` | DateTime | `NOW()` | no |

Set them in actions, not only as initial values, so every state change is
auditable.

## Active / soft delete

Prefer an `Active` (Yes/No or Enum Yes/No) flag over deleting rows that are
referenced elsewhere.

- Default new rows to active.
- Security filters usually do **not** filter on `Active`; instead use an
  `Active_*` slice for the views that should hide retired rows. This keeps refs
  resolvable.
- Admin views can show inactive rows for cleanup.

## Virtual columns

Use for:

- display labels (`DisplayName`);
- dereferenced values (`VendorName`, `CSIDivisionName`);
- counts and rollups (`ProjectCount`);
- computed flags (`PossibleDuplicate`, `Outstanding`);
- reverse ref lists (`REF_ROWS(...)`).

Rules:

- Mark them read-only.
- Keep expressions cheap. A virtual column is computed on sync and on every row
  render in some contexts.
- Avoid `SELECT` over a large table in a virtual column. Prefer a slice filter
  for the view, a security filter for access, or a stored rollup for reporting.
- Do not duplicate a physical column "just in case". Add virtual columns when a
  view or action needs them.

## Data sources

| Source | Best for | Watch out for |
|---|---|---|
| AppSheet database (`google_tables`) | New apps, native types, structured data | Column structure is managed in the database, not the sheet |
| Google Sheets (`google`) | Existing sheet workflows, human editing | Header changes break the schema; formatting is not data |
| SQL | Existing systems, scale, transactions | Type mapping, keys, permissions |
| Excel/CSV import | One-time migration | Import order, key preservation, duplicates |

For a Sheets-backed app:

- Row 1 is the header; no merged cells, no blank header cells.
- One table per tab.
- Keys in their own column, no formulas that change them.
- Dates in real date format, not text.
- After changing headers, use `Regenerate Structure` deliberately and diff the
  appdef.

For an AppSheet database:

- Create tables and columns in the database UI first.
- Import CSVs in dependency order (parents before children).
- Set keys/labels/refs after import.
- Regenerating the schema is safer than with Sheets but still diff afterward.

## Import order

Parents before children:

```
CSIDivisions
CSISpecs
Vendors
Materials
Projects
ProjectMaterials
Users
```

Then:

1. keys and labels;
2. refs;
3. virtual columns;
4. security;
5. slices;
6. views;
7. actions;
8. format rules;
9. automations.

## New table checklist

- [ ] Table name is `PascalCase`, plural.
- [ ] Key column exists, is unique, and is stable.
- [ ] Label column exists.
- [ ] `Active` flag exists if rows are retired.
- [ ] Audit columns exist if edits matter.
- [ ] Ref columns point to existing tables.
- [ ] Enum values are defined in the column, not hard-coded in expressions.
- [ ] Virtual columns are read-only and named for their result.
- [ ] Security filter and update rule are set.
- [ ] At least one list view and one detail view exist.
- [ ] Form view hides keys and workflow fields.
- [ ] `appdef.py validate` is clean.
