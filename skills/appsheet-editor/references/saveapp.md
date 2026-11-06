# Saving an appdef through `POST /api/saveapp`

The editor UI is the right tool for interactive work. `saveapp` is the supported
bulk/automation path when you need to apply many coordinated changes, or when a
UI-only change would take dozens of clicks. Either way: capture before/after and
diff.

This contract was verified on a live account. Treat it as version-sensitive; if
the endpoint shape changes, fall back to the editor and update this file.

## Contract

```
POST https://www.appsheet.com/api/saveapp
Content-Type: application/json
Content-Encoding: gzip
x-requested-with: XMLHttpRequest
```

Body (before gzip):

```json
{
  "appId": "<app guid>",
  "appJson": "<JSON.stringify(template)>",
  "validate": true
}
```

Critical details:

- The request body bytes must be **gzip-compressed**. Sending plain JSON returns
  `400 Unable to deserialize app.`
- `appJson` must be a **string**, not an object. Passing an object returns
  `400 ArgumentException`.
- `validate: true` asks the server to run its checks and return `AppErrors`.
- The response is JSON with `Success`, `App` (a JSON string), `AppErrors`,
  `CommitHash`, `BuildHash`, and `ErrorDescription`.

Success looks like:

```json
{
  "Success": true,
  "ErrorDescription": "App saved successfully",
  "AppErrors": [],
  "CommitHash": "...",
  "BuildHash": "...",
  "App": "{...new template...}"
}
```

The new `Version` and `LastModified` are inside the `App` string.

## Verify without reloading the editor

```
GET /api/template/{appId}
```

Returns `{Template, CommitHash, ...}`. Compare `Version` and `LastModified` with
the pre-save values. This is cheaper and safer than reloading the editor.

The editor reloads itself when `window.BUILD_HASH !== response.BuildHash`. If you
are scripting inside the editor page, expect a reload after a successful save.

## Which template to edit

Two templates are available and both save:

| Source | Approx size | Notes |
|---|---|---|
| `window.currentApp().appTemplate` | ~1.26 MB | In-memory editor template, includes editor annotations |
| `GET /api/template/{appId}` → `Template` | ~1.06 MB | API template, fewer annotations |

Pick one and use it consistently. Do not splice objects from one into the other;
the annotation differences can produce surprising diffs. The API template is the
better choice for scripted changes because it is reproducible.

## Browser-console / `page.evaluate` recipe

Run in the authenticated editor page (same origin, cookies included):

```js
async () => {
  const appId = '<appId>';

  // 1. Read the current template.
  const before = await fetch(`/api/template/${appId}`, { credentials: 'include' })
    .then(r => r.json());
  const template = before.Template;

  // 2. Modify only the intended components. Example: rename a view.
  const view = template.Presentation.Controls.find(v => v.Name === 'Old View Name');
  if (!view) throw new Error('view not found');
  view.Name = 'New View Name';
  // ... any other coordinated edits ...

  // 3. Save. Body must be gzip-compressed.
  const payload = JSON.stringify({
    appId,
    appJson: JSON.stringify(template),
    validate: true
  });
  const gz = new Blob([payload]).stream().pipeThrough(new CompressionStream('gzip'));
  const body = await new Response(gz).arrayBuffer();

  const res = await fetch('/api/saveapp', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'Content-Encoding': 'gzip',
      'x-requested-with': 'XMLHttpRequest'
    },
    body
  });
  const result = await res.json();

  // 4. Report the outcome; do not assume success.
  return {
    http: res.status,
    success: result.Success,
    description: result.ErrorDescription,
    appErrors: result.AppErrors,
    commitHash: result.CommitHash,
    buildHash: result.BuildHash
  };
}
```

If `CompressionStream` is unavailable, gzip in Node/PowerShell and send the bytes
through the same authenticated session. Do not send uncompressed JSON.

Node:

```js
const zlib = require("zlib");
const body = zlib.gzipSync(JSON.stringify({ appId, appJson: JSON.stringify(template), validate: true }));
```

PowerShell/.NET: use `System.IO.Compression.GZipStream` over the UTF-8 JSON bytes.
In both cases, reuse the editor session's cookie header; do not re-authenticate
with a different account.

## Safe workflow

1. **Capture before** — `snapshot.ps1` or `GET /api/template`.
2. **Clone** the template in memory. Never mutate the object you captured as the
   baseline.
3. **Apply the planned delta** — table/column/view/action/slice names and
   expressions. Keep a written list.
4. **Local structural check** — write the modified template to a temp file and run
   `appdef.py validate`. This catches missing refs, duplicate names, bad menu
   entries, and slice filter typos before the server sees them.
5. **Save** with `validate: true`.
6. **Inspect `Success` and `AppErrors`.** `INFO_*` codes are warnings; anything
   else is an error. If `Success` is false, stop. You can fold the response into
   the structural report:
   `python appdef.py validate appdef/after.json --server-errors save-response.json`.
7. **Verify** with `GET /api/template` — compare `Version` and `LastModified`.
8. **Diff** — `appdef.py diff appdef/current.json appdef/after.json`. Only the
   intended delta.
9. **Preview** as each affected role, then deploy.
10. **Record** the version in `appdef/INDEX.md` and keep the gzipped after
    snapshot.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `400 Unable to deserialize app.` | Body not gzipped | Gzip the bytes; keep `Content-Encoding: gzip` |
| `400 ArgumentException` | `appJson` sent as an object | `JSON.stringify(template)` |
| `Success: false` with `AppErrors` | Server validation failed | Read `AppErrors`; fix; re-save |
| Save succeeds but version unchanged | Wrong app id or a no-op template | Check `appId` and the diff |
| Editor reloads immediately | `BUILD_HASH` changed | Expected; re-read the template |
| Save appears to work but preview is stale | Preview not reloaded | Reload the preview after Save |

## Guardrails

- Do not use `saveapp` to bypass review on a production app. It is a bulk edit
  tool, not a license to skip the diff and role tests.
- Do not save a template from a different app or a different environment.
- Do not log the full request body; it contains the entire app definition.
- Do not mutate `window.currentApp().appTemplate` in place and then save it; keep
  a clean baseline for the diff.
- Do not treat `Success: true` as “no warnings”. Inspect `AppErrors`.
- Do not claim deployability from a local `validate` alone. See
  `appsheet-appdef` §5.
