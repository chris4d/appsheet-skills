# AppSheet expression cookbook

Expressions in this file are written the way the **editor** expects them — no
leading `=`. When you see them in appdef JSON, they have a leading `=`.

## Core forms

```appsheet
[Column]                                  current row column
[_THISROW].[Column]                       explicit current row (inside SELECT)
[RefColumn].[Column]                      dereference one hop
[Ref].[Ref2].[Column]                     dereference two hops
TableName[Column]                         list of values from a table
SELECT(Table[Key], condition)             list of keys matching condition
FILTER("Table", condition)                same, as a row list
ANY(SELECT(...))                          first/only value
LOOKUP(value, "Table", "KeyCol", "Return")  single value or blank
COUNT(SELECT(...))                        count
IN(value, LIST("A", "B"))                 membership
IN(value, Table[Column])                  membership in a column list
```

## User and role

```appsheet
LOOKUP(USEREMAIL(), "Users", "Email", "Role")
LOOKUP(USEREMAIL(), "Users", "Email", "Name")
LOOKUP(USEREMAIL(), "Users", "Email", "ActiveFlag") = "Yes"
LOWER(USEREMAIL())
USERROLE()
USERNAME()
USERSETTINGS("Option 1")
CONTEXT("View")
CONTEXT("ViewType")
```

Guard a missing user row:

```appsheet
IF(
  ISBLANK(LOOKUP(USEREMAIL(), "Users", "Email", "Role")),
  "Viewer",
  LOOKUP(USEREMAIL(), "Users", "Email", "Role")
)
```

## Display and labels

Optional suffix:

```appsheet
[MaterialName] & IF(ISBLANK([Finish]), "", " — " & [Finish])
```

Ref-aware label:

```appsheet
[ProjectID].[ProjectName] & " — " & [MaterialID].[MaterialName]
```

Status line:

```appsheet
[ApprovalStatus]
& IF([ReceivedSeattle] = "Yes", " · Seattle received", "")
& IF([ReceivedLA] = "Yes", " · LA received", "")
```

Safe text join:

```appsheet
CONCATENATE([First], " ", [Last])
```

Trim/normalize:

```appsheet
UPPER(TRIM([Email]))
SUBSTITUTE([Phone], " ", "")
SUBSTITUTE([Phone], "-", "")
```

## Counts and rollups

```appsheet
COUNT(SELECT(ProjectMaterials[ProjectMaterialID], [ProjectID] = [_THISROW].[ProjectID]))
COUNT(SELECT(ProjectMaterials[ProjectMaterialID], AND([ProjectID] = [_THISROW].[ProjectID], [ApprovalStatus] = "Approved")))
COUNT(SELECT(Materials[MaterialID], [VendorID] = [_THISROW].[VendorID]))
COUNT(SELECT(Materials[MaterialID], [CSIDivisionID] = [_THISROW].[CSIDivisionID]))
```

Do not put a `SELECT` over a large table in a virtual column unless you accept
the sync cost. Prefer a slice or a security filter for the view, and store
rollups if they are read often.

## Duplicate detection

Same name + finish + vendor, excluding self:

```appsheet
COUNT(
  SELECT(
    Materials[MaterialID],
    AND(
      [MaterialName] = [_THISROW].[MaterialName],
      [Finish] = [_THISROW].[Finish],
      [VendorID] = [_THISROW].[VendorID],
      [MaterialID] <> [_THISROW].[MaterialID]
    )
  )
) > 0
```

Exact project/material link, excluding self:

```appsheet
COUNT(
  SELECT(
    ProjectMaterials[ProjectMaterialID],
    AND(
      [ProjectID] = [_THISROW].[ProjectID],
      [MaterialID] = [_THISROW].[MaterialID],
      [ProjectMaterialID] <> [_THISROW].[ProjectMaterialID]
    )
  )
) > 0
```

## Dates and ageing

```appsheet
IF(ISBLANK([DateOrderPlaced]), "", TODAY() - [DateOrderPlaced])
TODAY() - [CheckedOutDate]
EOMONTH(TODAY(), 0)
WEEKNUM(TODAY())
YEAR(TODAY())
```

Outstanding order:

```appsheet
AND(
  NOT(ISBLANK([DateOrderPlaced])),
  [ReceivedSeattle] = "No",
  [ReceivedLA] = "No"
)
```

## Conditional editability

```appsheet
IN(LOOKUP(USEREMAIL(), "Users", "Email", "Role"), LIST("Admin", "Librarian"))
LOOKUP(USEREMAIL(), "Users", "Email", "Role") = "Admin"
AND(
  LOOKUP(USEREMAIL(), "Users", "Email", "Role") = "Admin",
  LOOKUP(USEREMAIL(), "Users", "Email", "DevMode") = TRUE
)
```

## Validation

Unique email:

```appsheet
COUNT(
  SELECT(
    Users[Email],
    AND([Email] = [_THISROW].[Email], [UserID] <> [_THISROW].[UserID])
  )
) = 0
```

Positive quantity:

```appsheet
[QtyOrdered] > 0
```

Date not in the future:

```appsheet
[DateOrderPlaced] <= TODAY()
```

Error message: `"Quantity must be greater than zero."`

## Navigation and forms

Prefill a form:

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

Open a view:

```appsheet
LINKTOVIEW("Pending Approvals")
```

Open a specific row:

```appsheet
LINKTOROW([ProjectID], "Projects_Detail")
```

## Action assignments

`Data: set the values of some columns in this row`:

```appsheet
"Approved"
```

```appsheet
LOOKUP(USEREMAIL(), "Users", "Email", "Name")
```

```appsheet
TODAY()
```

```appsheet
NOW()
```

```appsheet
USEREMAIL()
```

```appsheet
NOT([DevMode])
```

A good state-change action sets both the state and the audit fields:

| Column | Value |
|---|---|
| `ApprovalStatus` | `"Approved"` |
| `ApprovedBy` | `LOOKUP(USEREMAIL(), "Users", "Email", "Name")` |
| `LastChangedBy` | `USEREMAIL()` |
| `LastChangedDate` | `NOW()` |

## Action conditions

Only show approve when not already approved and the role allows it:

```appsheet
AND(
  [ApprovalStatus] <> "Approved",
  IN(LOOKUP(USEREMAIL(), "Users", "Email", "Role"), LIST("Admin", "Librarian", "Designer"))
)
```

Only show check-in when checked out:

```appsheet
NOT(ISBLANK([CheckedOutBy]))
```

Only show check-out when available:

```appsheet
ISBLANK([CheckedOutBy])
```

## Bot conditions

Approval changed:

```appsheet
[_THISROW_BEFORE].[ApprovalStatus] <> [_THISROW_AFTER].[ApprovalStatus]
```

Order just placed:

```appsheet
AND(
  ISBLANK([_THISROW_BEFORE].[DateOrderPlaced]),
  NOT(ISBLANK([_THISROW_AFTER].[DateOrderPlaced]))
)
```

Received in either location:

```appsheet
OR(
  AND([_THISROW_BEFORE].[ReceivedSeattle] <> "Yes", [_THISROW_AFTER].[ReceivedSeattle] = "Yes"),
  AND([_THISROW_BEFORE].[ReceivedLA] <> "Yes", [_THISROW_AFTER].[ReceivedLA] = "Yes")
)
```

## Template expressions

```appsheet
<<Start: SELECT(ProjectMaterials[ProjectMaterialID], [ApprovalStatus] = "Pending")>>
<<[ProjectName]>> — <<[DisplayName]>> — pending approval
<<End>>
```

```appsheet
<<Start: SELECT(ProjectMaterials[ProjectMaterialID], AND(NOT(ISBLANK([DateOrderPlaced])), [ReceivedSeattle] = "No", [ReceivedLA] = "No"))>>
<<[ProjectName]>> — <<[DisplayName]>> — ordered <<[DateOrderPlaced]>> (<<[DaysSinceOrder]>> days)
<<End>>
```

## Text utilities

```appsheet
LEN([Text])
LEFT([Text], 3)
RIGHT([Text], 4)
MID([Text], 2, 3)
FIND("x", [Text])
SPLIT([Tags], ",")
INDEX(SPLIT([Tags], ","), 1)
SUBSTITUTE([Text], "old", "new")
TRIM([Text])
UPPER([Text])
LOWER([Text])
TEXT([Number])
NUMBER([Text])
```

## Debugging checklist

1. Strip the leading `=` before pasting into the editor.
2. Check quote balance. AppSheet uses `"`, not curly quotes.
3. Check parentheses from the outside in.
4. Replace `[Column]` with a literal to see whether the expression or the data is
   wrong.
5. Use a temporary virtual column of type `Text` to display an intermediate
   value; delete it after debugging.
6. Check the appdef: `appdef.py column <table> <column>` shows the stored
   expression and every conditional.
7. If a `SELECT` returns blank, test the condition alone in a virtual column.
