# Security and roles

## The `Users` table

Minimum viable shape:

| Column | Type | Notes |
|---|---|---|
| `UserID` | Text | hidden key; `UNIQUEID()` |
| `Email` | Email | label; required; unique validation |
| `Name` | Text | used in `ApprovedBy`, audit fields |
| `Role` | Enum | `Admin`, `Librarian`, `Designer`, `Viewer` |
| `ActiveFlag` | Yes/No (or Enum Yes/No) | gates access |
| `DevMode` | Yes/No | hidden, default false; Admin toggles own row |

Keep the active column name consistent across every expression. A filter that
uses `[Active] = "Yes"` when the column is `ActiveFlag` silently returns nothing.
Some apps carry both: `Active` (Yes/No, user-facing) and `ActiveFlag` (Text
mirror used by security filters). Match the appdef; do not assume the name.

Unique email validation:

```appsheet
COUNT(
  SELECT(
    Users[Email],
    AND([Email] = [_THISROW].[Email], [UserID] <> [_THISROW].[UserID])
  )
) = 0
```

Error message: `"Email already exists. Use a unique email address."`

## Role helpers

```appsheet
LOOKUP(USEREMAIL(), "Users", "Email", "Role")
LOOKUP(USEREMAIL(), "Users", "Email", "Name")
LOOKUP(USEREMAIL(), "Users", "Email", "ActiveFlag") = "Yes"
```

If the app must work for an unlisted user, wrap the role lookup with a default:

```appsheet
IF(ISBLANK(LOOKUP(USEREMAIL(), "Users", "Email", "Role")), "Viewer", LOOKUP(USEREMAIL(), "Users", "Email", "Role"))
```

## Table update rules

`Are updates allowed?` controls adds/edits/deletes. Use one expression per table:

```appsheet
IF(IN(LOOKUP(USEREMAIL(), "Users", "Email", "Role"), LIST("Admin", "Librarian", "Designer")), "ALL_CHANGES", "READ_ONLY")
```

```appsheet
IF(LOOKUP(USEREMAIL(), "Users", "Email", "Role") = "Admin", "ALL_CHANGES", "READ_ONLY")
```

Read-only table:

```appsheet
"READ_ONLY"
```

Do not confuse this with a security filter. An update rule says *whether* a user
may write; a security filter says *which rows* they may see.

## Security filters

Apply the active-user test to every data table:

```appsheet
LOOKUP(USEREMAIL(), "Users", "Email", "ActiveFlag") = "Yes"
```

Per-user row scoping, when needed:

```appsheet
OR(
  LOOKUP(USEREMAIL(), "Users", "Email", "Role") = "Admin",
  [OwnerEmail] = USEREMAIL()
)
```

Per-project scoping through a child table:

```appsheet
COUNT(
  SELECT(
    ProjectAssignments[ProjectAssignmentID],
    AND([ProjectID] = [_THISROW].[ProjectID], [Email] = USEREMAIL())
  )
) > 0
```

### The `Users` exception

**Never** put a security filter on `Users` that references `Users`:

```appsheet
LOOKUP(USEREMAIL(), "Users", "Email", "ActiveFlag") = "Yes"   ← on Users: breaks runnability
```

The app needs to read `Users` to evaluate the filter, but the filter hides the
row it needs. The app becomes non-runnable. Protect `Users` with an Admin-only
update rule instead, and share the app only with trusted users.

If you inherit an app with this filter, remove it, save, and verify
`appdef.py summary` reports `Runnable: True`.

## Column-level editability

Use `Editable_If` on the column for field-level control:

```appsheet
IN(LOOKUP(USEREMAIL(), "Users", "Email", "Role"), LIST("Admin", "Librarian"))
```

```appsheet
LOOKUP(USEREMAIL(), "Users", "Email", "Role") = "Admin"
```

A common split:

| Column group | Editable by |
|---|---|
| Approval status, project notes | Admin, Librarian, Designer |
| ApprovedBy | Admin only (actions may set it for others) |
| Ordering, receiving, checkout fields | Admin, Librarian |
| Taxonomy, users, vendors | Admin |

Actions can write columns that the current user cannot edit manually. That is
intentional: `ApprovedBy` can be Admin-only editable while the Approve action
sets it for a Designer. Verify this in preview as the Designer.

## DevMode pattern

Goal: hide technical IDs from normal users, expose them to an Admin in DevMode.

1. `Users.DevMode` — Yes/No, hidden, default false.
2. `Toggle DevMode` action on `Users`:
   - type: set columns in this row
   - `DevMode` = `NOT([DevMode])`
   - only if: `AND(LOOKUP(USEREMAIL(), "Users", "Email", "Role") = "Admin", [Email] = USEREMAIL())`
   - position: overlay/inline as appropriate
3. `Show_If` on key/technical columns:

```appsheet
AND(
  LOOKUP(USEREMAIL(), "Users", "Email", "Role") = "Admin",
  LOOKUP(USEREMAIL(), "Users", "Email", "DevMode") = TRUE
)
```

4. Keep key columns in `ColumnOrder` and gate them with the same `Show_If`. If
   you omit them from the order, DevMode cannot reveal them without editing the
   view. Trade-off: some view types render an empty header for a hidden column;
   test both DevMode states. If the empty header is unacceptable, use a separate
   DevMode-only detail view instead of removing the column globally.

`Show_If` hides the column; it does not secure the value. Do not use this pattern
for sensitive data.

## Authentication settings

| Setting | Meaning | House default |
|---|---|---|
| `Require sign-in` | Users must authenticate | On |
| `Allow all signed-in users` | Any Google account may use the app | Off for internal apps |
| `Domain authentication` | Restrict to a Workspace domain | On when available |
| Auth provider | Google / Microsoft / etc. | Match the data source owner |

If `Allow all signed-in users` is on, the `Users` table is advisory, not
access control. Turn it off for apps with role-based data.

## Test matrix

For each role, use `Preview app as` with a real email:

1. Can the user open the app at all? (`ActiveFlag` filter)
2. Which rows are visible? (security filters)
3. Which tables allow add/edit/delete? (update rules)
4. Which columns are editable? (`Editable_If`)
5. Which actions are visible and do they succeed?
6. Do actions write columns the user cannot edit manually?
7. Does the app still load after the security change? (`Runnable`)

Test at least one non-Admin. Admin often bypasses mistakes because the role
expression short-circuits.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| App won't load after security edit | Self-referencing `Users` filter | Remove the filter on `Users` |
| Everyone sees all rows | Filter not applied, or `Allow all signed-in users` | Apply filter; restrict auth |
| Nobody sees rows | Active column name mismatch or no `Users` row | Match column name; add the user |
| Role always Viewer | Email case/whitespace mismatch | `LOWER(TRIM(...))` on both sides |
| User can edit a protected column | Only `Show_If` was set | Add `Editable_If` or table update rule |
| Action fails for Designer | Action writes an Admin-only column | Verify action-set columns are allowed, or relax `Editable_If` |
| `ApprovedBy` blank after approval | Action didn't assign it | Add the assignment |
