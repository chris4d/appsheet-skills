# Views, actions, and navigation

## View types

| Type | Use for | Key settings |
|---|---|---|
| `table` | Dense lists, admin/back-office | column order, width, quick edit, sort, group |
| `card` | Visual browsing, images | main image, header, summary, action bar |
| `gallery` | Large images, samples, products | image size, primary/secondary text |
| `deck` | Compact cards with summary | deck image, headers, summary |
| `detail` | One row, read-first | column order, header column, inline refs |
| `form` | Add/edit one row | column order, auto-save, advance forms |
| `dashboard` | Composite landing page | ordered `ViewEntries` |
| `map` | Location data | address/latlong, pin, color |
| `chart` | Aggregates | chart type, dimension, measure |
| `calendar` | Date-based rows | start/end date, title |
| `onboarding` | First-run guidance | pages |

Auto-generated `_Detail`, `_Form`, and `_Inline` views exist for every table and
ref. Customize them instead of building duplicates.

## Position

| Value | Where it appears |
|---|---|
| `first`, `next`, `middle`, `later`, `last` | Primary bottom/top navigation slots, in order |
| `menu` | Main menu (hamburger) |
| `ref` | Reference views reached from a ref column or inline list |
| `left`, `center`, `left most` | Legacy desktop navigation positions seen in older exports |

House rule: 3–5 primary views; everything else `menu` or `ref`.

## View configuration checklist

- **Name** is unique and human-readable (`Pending Approvals`, not `View 3`).
- **For this data** points to the right table or slice.
- **Position** is intentional.
- **Column order** is explicit. Empty means all columns, including keys and audit
  fields.
- **Sort by** is set when order matters.
- **Group by** is set when scanning by category matters.
- **Show if** is used for role/state gating, not security.
- **Icon** is set for primary/menu views (`fas fa-*`).
- **Display name** is set when the internal name is not user-friendly.

### Detail views

Show the label and the fields a user needs to decide or act. Inline child views
(e.g., `Related ProjectMaterials`) should show a short label, status, and owner —
not every column.

### Form views

- Hide keys and workflow fields (`Show_If` false or omit from column order).
- Prefill via `LINKTOFORM` or `Initial value`.
- Put the required fields first.
- Use `Valid_If` for inline validation.
- For "add related row" flows, use a dedicated slice/form so the parent key is
  fixed and the key is generated.

### Dashboards

Build the component views first. A dashboard references view names; renaming a
component later breaks the dashboard. Use a dashboard for a landing page, not as
a substitute for navigation.

## Action types

| UI label | `ActionType` | Use |
|---|---|---|
| Data: set the values of some columns in this row | `SET_COLUMN_VALUE` | State transitions |
| Data: add a new row to another table using values from this row | `ADD_RECORD` | Create child rows |
| Data: delete this row | `DELETE_RECORD` | Delete with confirmation |
| Data: execute an action on a set of rows | `EXECUTE_ACTION` | Bulk operations |
| App: go to another view within this app | `NAVIGATE_APP` | `LINKTOFORM`, `LINKTOVIEW`, `LINKTOROW` |
| App: open a form to add a new row to this table | `ADD_RECORD` (form) | Add from a view |
| App: export this view to a CSV file | `EXPORT_VIEW` | Admin export |
| App: import a CSV file for this view | `IMPORT_FILE` | Admin import |
| External: go to a website | `NAVIGATE_URL` | Hyperlinks |
| External: open a file | `OPEN_FILE` | Cutsheets, PDFs |
| External: start an email / phone call / text | `EMAIL`, `CALL`, `SMS` | Contact actions |
| Grouped: execute a sequence of actions | `GROUPED` | Multi-step workflow |

## Action configuration

- **Name** is unique per table; it is what the appdef and logs show.
- **Only if** is the visibility/enabled condition. Put the transition guard here
  (`[Status] <> "Approved"`), not only in the display name.
- **Position**:
  - `Primary` — the one main action for the row/view.
  - `Prominent` — secondary, still visible.
  - `Inline` — row-level in a table/list.
  - `Hide` — internal, triggered by another action or automation.
- **Confirmation** for destructive actions; message should name the consequence.
- **Bulk applicable** only when the action is safe to run on many rows.
- **Icon** for primary/prominent actions (`fas fa-check`, `fas fa-times`,
  `fas fa-undo`, `fas fa-plus`, `fas fa-truck`, `fas fa-sign-out-alt`).

### State-change action template

| Column | Value |
|---|---|
| `ApprovalStatus` | `"Approved"` |
| `ApprovedBy` | `LOOKUP(USEREMAIL(), "Users", "Email", "Name")` |
| `LastChangedBy` | `USEREMAIL()` |
| `LastChangedDate` | `NOW()` |

Only if:

```appsheet
AND(
  [ApprovalStatus] <> "Approved",
  IN(LOOKUP(USEREMAIL(), "Users", "Email", "Role"), LIST("Admin", "Librarian", "Designer"))
)
```

### Add-related-row template

```appsheet
LINKTOFORM(
  "ProjectMaterials_Add",
  "MaterialID", [MaterialID],
  "SourceTab", "App",
  "ApprovalStatus", "Pending",
  "ApprovedBy", "",
  "ProjectApplication", [Application]
)
```

The target form should:

- use a slice that fixes the parent context;
- generate the child key (`CONCATENATE("PM-", UNIQUEID())`);
- hide the key and workflow fields;
- block exact duplicates with a `Valid_If` or an action condition.

### Bulk action template

Parent action: `Data: execute an action on a set of rows`.

- Referenced action: `Approve`
- Rows: `SELECT(ProjectMaterials[ProjectMaterialID], IN([ProjectMaterialID], [_THISROW].[SelectedIDs]))`

The selection column (`SelectedIDs`, `EnumList` of refs) lives on a control table
or user settings row. Do not build one action per row.

## Navigation patterns

- **Landing dashboard** → primary views.
- **List → detail → edit** is the default flow; do not add a custom detail view
  unless the auto one is wrong.
- **Ref columns** navigate to the referenced row's detail view automatically.
- **Inline child lists** on a detail view are the cheapest way to show related
  rows.
- **Menu** for admin/utility views (Users, Taxonomy, imports/exports).
- **Show if** on a menu view is acceptable for role gating, but the underlying
  data must still be secured.

## Icons

Use Font Awesome 5 solid classes:

```
fas fa-tachometer   fas fa-cube        fas fa-folder-open  fas fa-camera
fas fa-users        fas fa-sign-out-alt fas fa-truck        fas fa-clock
fas fa-list         fas fa-star        fas fa-sitemap      fas fa-question-circle
fas fa-building     fas fa-address-card fas fa-check       fas fa-times
fas fa-undo         fas fa-plus        fas fa-trash-alt    fas fa-edit
```

System-generated detail/form views may not expose the icon picker; leave their
default icon rather than forcing one.

## Common view/action bugs

| Symptom | Check |
|---|---|
| View shows all columns including IDs | `ColumnOrder` is empty or includes keys |
| View is missing from navigation | `Position` is `ref`, or `Show_If` is false |
| Sort/group ignored | Column not in the view's data source, or virtual column not synced |
| Action missing | Wrong table, `Position: Hide`, or false `Only if` |
| Action fails silently | Update rule blocks the write, or a required column is blank |
| `LINKTOFORM` opens blank | View name wrong, or the target form is not a form view |
| Duplicate rows after add | Form creates a new key instead of using the parent context |
| Dashboard blank | Component view renamed or not built yet |
