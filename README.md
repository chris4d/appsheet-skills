# AppSheet skills

A four-skill set for developing and managing Google AppSheet apps without
rediscovering the editor every session.

The design premise: **the app definition JSON is the source of truth, the DOM is
the control surface, and screenshots are a last resort.** A 1–2 MB appdef
compresses to a 20–30 KB Markdown spec; an accessibility snapshot of one editor
panel is often larger than the entire app spec. Work from the appdef, drive the
editor by accessible names, and spend the image budget only on visual proof.

## The skills

| Skill | Use it for | Load it when |
|---|---|---|
| [`appsheet-appdef`](skills/appsheet-appdef/SKILL.md) | Reading, searching, auditing, diffing, and validating the app definition JSON; generating a compact app spec | Before any editor work, and after every save |
| [`appsheet-editor`](skills/appsheet-editor/SKILL.md) | Navigating the legacy/improved editor, editing columns/views/actions/security, expression fields, save/preview/deploy, DOM recipes, and the verified `saveapp` bulk-save API | When you must click or bulk-edit |
| [`appsheet-build`](skills/appsheet-build/SKILL.md) | End-to-end build/change process: baseline → edit → diff → validate → preview → deploy; build order; test matrix; definition of done | Starting a new app or a multi-step change |
| [`appsheet-patterns`](skills/appsheet-patterns/SKILL.md) | Expressions, schema conventions, roles/security, slices, views/actions, anti-patterns | Designing behavior or debugging a rule |

They are complementary, not alternatives. A typical task loads
`appsheet-appdef` first, `appsheet-build` for the plan, `appsheet-editor` for the
clicks, and `appsheet-patterns` for the expression or security rule.

## Install

Run the installer (copies all four, replaces existing copies, strips
`__pycache__`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\appsheet-skills\install.ps1
```

For a project-local install instead:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\appsheet-skills\install.ps1 -ProjectLocal
```

Or copy manually:

```powershell
$src = "C:\dev\appsheet-skills\skills"
$dst = "$env:USERPROFILE\.config\opencode\skills"
Copy-Item "$src\appsheet-appdef"  "$dst\appsheet-appdef"  -Recurse -Force
Copy-Item "$src\appsheet-editor"  "$dst\appsheet-editor"  -Recurse -Force
Copy-Item "$src\appsheet-build"   "$dst\appsheet-build"   -Recurse -Force
Copy-Item "$src\appsheet-patterns" "$dst\appsheet-patterns" -Recurse -Force
```

The `appdef.py` script is stdlib-only Python 3; no install step. After editing a
skill in `C:\dev\appsheet-skills`, rerun `install.ps1` to refresh the global copy.

## Quick start on an existing app

```powershell
$repo   = "C:\dev\<your-app-repo>"
$appdef = "$repo\appdef\current.json"
$cli    = "C:\dev\appsheet-skills\skills\appsheet-appdef\scripts\appdef.py"

python $cli summary  $appdef
python $cli validate $appdef
python $cli export-md $appdef "$repo\docs\app-spec.md"
```

Or use the snapshot helper to timestamp the capture, summarize it, diff it
against the previous snapshot, and validate it in one step:

```powershell
powershell -File skills\appsheet-appdef\scripts\snapshot.ps1 `
  -Appdef $appdef -Dir "$repo\appdef" -Label before
```

Then ask targeted questions instead of taking screenshots:

```powershell
python $cli table   $appdef ProjectMaterials
python $cli view    $appdef "Pending Approvals"
python $cli action  $appdef Approve --table ProjectMaterials
python $cli search  $appdef "ApprovalStatus"
```

## The change loop

1. Ensure `appdef/current.json` is the current compact baseline.
2. Write the intended delta (component names + expressions).
3. Edit one logical group; Save (editor or `saveapp`).
4. Capture the after appdef; `snapshot.ps1` diffs it against the previous
   snapshot and validates it.
5. `appdef.py diff before after` — only the intended delta.
6. `appdef.py validate after` — zero structural errors; add
   `--server-errors` when a `saveapp` response is available.
7. Preview as each affected role.
8. Deploy; record the version in `appdef/INDEX.md`.
9. Keep the gzipped after snapshot, regenerate `docs/app-spec.md`, delete the
   temporary before.

If step 5 or 6 fails, do not deploy. Restore the previous version in
`Manage → Versions` or reverse the edit, then re-baseline.

### Bulk edits

For coordinated changes that would take dozens of clicks, `appsheet-editor`
documents the verified `POST /api/saveapp` path (gzipped body, `validate: true`,
`AppErrors`, version verification). It is a speed tool, not a shortcut around the
diff/validate/preview loop.

## Screenshot budget

The model provider caps context at 30 images. Treat images as a scarce resource:

- **Never** use a screenshot to find an element. Use `browser_find`,
  `browser_evaluate`, or a scoped `browser_snapshot`.
- **Never** take a full-page screenshot "to see what's there".
- Take **0–2 screenshots per task**, after the change, to verify color, icon,
  layout, or mobile fit. Save to a file; don't return them inline unless the user
  needs to see them.
- Prefer reading the appdef or the dialog heading to confirm state.

## Working in an app repo

Keep app-specific artifacts in the app repo, not in this skills repo.

| Repo | What is there | Start with |
|---|---|---|
| `C:\dev\<app-repo>` | `appdef/current.json`, `docs/app-spec.md`, the app's build notes, import CSVs, Playwright snapshots | The repo README → appdef `summary` |

Keep `appdef/current.json` as the rolling compact baseline,
gzip deployed snapshots to `appdef/<version>.json.gz` and prune to the last 10,
and regenerate `docs/app-spec.md` after each accepted change. Keep a short
`appdef/INDEX.md` so nobody has to guess which JSON is current.

## Files

```
appsheet-skills/
  README.md
  skills/
    appsheet-appdef/
      SKILL.md
      scripts/appdef.py
      scripts/snapshot.ps1
      references/appdef-schema.md
    appsheet-editor/
      SKILL.md
      references/dom-recipes.md
      references/saveapp.md
    appsheet-build/
      SKILL.md
    appsheet-patterns/
      SKILL.md
      references/expressions.md
      references/security.md
      references/views-actions.md
      references/schema-conventions.md
```

## Provenance

The editor map and expression patterns were derived from real sessions against
a live production AppSheet app and its saved Playwright accessibility snapshots,
plus the app's own build guide. The `appdef.py` field accessors were verified
against a PlatformVersion 5.1 appdef. The `POST /api/saveapp` contract was
verified on a live account, and the validator/diff blind spots called out by that
session are now covered.

AppSheet changes its UI. When a selector or heading no longer matches, update
`appsheet-editor` rather than working around it silently; the skill is meant to
be the durable memory of the interface.
