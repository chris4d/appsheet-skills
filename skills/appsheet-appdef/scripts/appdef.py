#!/usr/bin/env python3
"""
appdef.py - inspect, validate, and diff AppSheet app definition JSON.

Designed for agents: output is compact, deterministic, and can be emitted as
JSON for further processing. No third-party dependencies.

Usage:
  python appdef.py summary <appdef.json>
  python appdef.py tables <appdef.json>
  python appdef.py table <appdef.json> <table>
  python appdef.py column <appdef.json> <table> <column>
  python appdef.py views <appdef.json> [--primary]
  python appdef.py view <appdef.json> <view>
  python appdef.py actions <appdef.json> [--table NAME]
  python appdef.py action <appdef.json> <action> [--table NAME]
  python appdef.py slices <appdef.json>
  python appdef.py slice <appdef.json> <slice>
  python appdef.py security <appdef.json>
  python appdef.py exprs <appdef.json> [--table NAME]
  python appdef.py search <appdef.json> <regex>
  python appdef.py validate <appdef.json>
  python appdef.py diff <before.json> <after.json>
  python appdef.py export-md <appdef.json> [out.md]

Add --json to most commands for machine-readable output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict, defaultdict

# Windows consoles default to cp1252; avoid UnicodeEncodeError on table output.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Loading and low-level accessors
# ---------------------------------------------------------------------------


def load_appdef(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    if "AppData" not in data:
        raise SystemExit(f"{path}: not an AppSheet app definition (missing AppData)")
    return data


def app_data(d: dict) -> dict:
    return d.get("AppData") or {}


def datasets(d: dict) -> list[dict]:
    return app_data(d).get("DataSets") or []


def schemas(d: dict) -> list[dict]:
    return app_data(d).get("DataSchemas") or []


def slices(d: dict) -> list[dict]:
    return app_data(d).get("TableSlices") or []


def actions(d: dict) -> list[dict]:
    return app_data(d).get("DataActions") or []


def controls(d: dict) -> list[dict]:
    return (d.get("Presentation") or {}).get("Controls") or []


def table_map(d: dict) -> dict[str, dict]:
    return {t.get("Name"): t for t in datasets(d) if t.get("Name")}


def schema_map(d: dict) -> dict[str, dict]:
    """Map table name -> schema, using DataSet.SchemaName when possible."""
    out: dict[str, dict] = {}
    by_name = {s.get("Name"): s for s in schemas(d)}
    for ds in datasets(d):
        name = ds.get("Name")
        if not name:
            continue
        s = (by_name.get(ds.get("SchemaName"))
             or by_name.get(f"{name}_Schema")
             or by_name.get(name))
        if s:
            out[name] = s
    # Include schemas that have no dataset (rare, but useful for diagnostics)
    for s in schemas(d):
        n = (s.get("Name") or "").removesuffix("_Schema")
        out.setdefault(n, s)
    return out


def columns(d: dict, table: str) -> list[dict]:
    s = schema_map(d).get(table)
    return (s or {}).get("Attributes") or []


def column_map(d: dict, table: str) -> dict[str, dict]:
    return {c.get("Name"): c for c in columns(d, table) if c.get("Name")}


def as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            v = json.loads(value)
            return v if isinstance(v, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def aux(col: dict) -> dict:
    return as_dict(col.get("TypeAuxData"))


def col_get(col: dict, key: str, default=None):
    a = aux(col)
    if key in a and a[key] not in (None, ""):
        return a[key]
    if key in col and col[key] not in (None, ""):
        return col[key]
    return default


def ref_table(col: dict) -> str | None:
    a = aux(col)
    for k in ("ReferencedTableName", "ReferencedRootTableName"):
        if a.get(k):
            return a[k]
    return None


def enum_values(col: dict) -> list:
    a = aux(col)
    return a.get("EnumValues") or []


def view_settings(c: dict) -> dict:
    vd = c.get("ViewDefinition")
    if isinstance(vd, dict) and vd:
        return vd
    return as_dict(c.get("Settings"))


def view_type(c: dict) -> str:
    return (c.get("Action") or view_settings(c).get("$type") or "").lower()


def view_data(c: dict) -> str:
    return c.get("TableOrFolderName") or ""


def action_definition(a: dict) -> dict:
    ad = a.get("ActionDefinition")
    if isinstance(ad, dict) and ad:
        return ad
    return as_dict(a.get("ActionSettings"))


def action_assignments(a: dict) -> list[dict]:
    ad = action_definition(a)
    v = ad.get("Assignments")
    if isinstance(v, list):
        return v
    return []


def action_prominence(a: dict) -> str:
    ad = action_definition(a)
    return ad.get("Prominence") or ""


def action_condition(a: dict) -> str:
    return a.get("Condition") or ""


def slice_filter(s: dict) -> str:
    for key in ("FilterCondition", "RowFilterCondition"):
        v = s.get(key)
        if isinstance(v, str) and v.strip():
            return v
    fe = s.get("FilterExpression")
    if isinstance(fe, dict):
        v = fe.get("Expression")
        if isinstance(v, str) and v.strip():
            return v
        desc = fe.get("Description")
        if isinstance(desc, dict) and desc.get("Content"):
            return desc["Content"]
    return ""


def clean_expr(v) -> str:
    if not isinstance(v, str):
        return ""
    return v[1:] if v.startswith("=") else v


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def truncate(s: str, width: int) -> str:
    s = " ".join(str(s).split())
    if len(s) <= width:
        return s
    return s[: max(0, width - 3)] + "..."


def print_table(headers: list[str], rows: list[list], max_widths: dict[int, int] | None = None):
    max_widths = max_widths or {}
    widths = []
    for i, h in enumerate(headers):
        w = len(h)
        for r in rows:
            w = max(w, len(str(r[i])) if i < len(r) else 0)
        widths.append(min(w, max_widths.get(i, 48)))
    fmt = "  ".join("{:<%d}" % w for w in widths)
    print(fmt.format(*headers).rstrip())
    print(fmt.format(*["-" * w for w in widths]).rstrip())
    for r in rows:
        cells = [truncate(r[i] if i < len(r) else "", widths[i]) for i in range(len(headers))]
        print(fmt.format(*cells).rstrip())


def eprint(*a):
    print(*a, file=sys.stderr)


# ---------------------------------------------------------------------------
# Summary / tables
# ---------------------------------------------------------------------------


def app_summary(d: dict) -> dict:
    tm = table_map(d)
    cols = sum(len(columns(d, t)) for t in tm)
    return {
        "name": d.get("ShortName") or d.get("Name"),
        "id": d.get("Id"),
        "version": d.get("Version"),
        "platform": d.get("PlatformVersion"),
        "modified": d.get("LastModified"),
        "status": d.get("Status"),
        "runnable": d.get("IsRunnable"),
        "valid": d.get("IsValid"),
        "tables": len(tm),
        "columns": cols,
        "views": len(controls(d)),
        "user_views": len([c for c in controls(d)
                           if not c.get("_isSystemGenerated") and c.get("Position") != "ref"]),
        "actions": len(actions(d)),
        "slices": len(slices(d)),
        "format_rules": len((d.get("Presentation") or {}).get("FormatRules") or []),
        "bots": len((d.get("Behavior") or {}).get("AppBots") or []),
    }


def cmd_compact(d: dict, args):
    """Write a compact (no indentation) copy, preserving UTF-8 and key order."""
    out = args.out
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, separators=(",", ":"), ensure_ascii=False)
    print(f"wrote {out}")


def cmd_summary(d: dict, args):
    s = app_summary(d)
    if args.json:
        print(json.dumps(s, indent=2))
        return
    print(f"App:       {s['name']}")
    print(f"Id:        {s['id']}")
    print(f"Version:   {s['version']}   Platform: {s['platform']}")
    print(f"Modified:  {s['modified']}")
    print(f"Status:    {s['status']}   Runnable: {s['runnable']}   Valid: {s['valid']}")
    print()
    print(f"Tables: {s['tables']}   Columns: {s['columns']}   Views: {s['views']} ({s['user_views']} user)")
    print(f"Actions: {s['actions']}   Slices: {s['slices']}   Format rules: {s['format_rules']}   Bots: {s['bots']}")
    print()
    rows = []
    for t in datasets(d):
        name = t.get("Name")
        cs = columns(d, name)
        key = next((c["Name"] for c in cs if c.get("IsKey")), "")
        label = next((c["Name"] for c in cs if c.get("IsLabel")), "")
        rows.append([name, len(cs), key, label, truncate(clean_expr(t.get("UpdateModeExpression")) or "ALL_CHANGES", 40)])
    print_table(["TABLE", "COLS", "KEY", "LABEL", "UPDATES"], rows)


def cmd_tables(d: dict, args):
    rows = []
    for t in datasets(d):
        name = t.get("Name")
        cs = columns(d, name)
        key = next((c["Name"] for c in cs if c.get("IsKey")), "")
        label = next((c["Name"] for c in cs if c.get("IsLabel")), "")
        refs = [c["Name"] for c in cs if ref_table(c)]
        rows.append({
            "name": name,
            "columns": len(cs),
            "key": key,
            "label": label,
            "refs": refs,
            "updates": clean_expr(t.get("UpdateModeExpression")),
            "security_filter": clean_expr(t.get("DataFilter")),
            "provider": t.get("ProviderName"),
            "source": t.get("SourcePath"),
        })
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    print_table(
        ["TABLE", "COLS", "KEY", "LABEL", "UPDATES", "SECURITY FILTER"],
        [[r["name"], r["columns"], r["key"], r["label"],
          truncate(r["updates"] or "ALL_CHANGES", 28),
          truncate(r["security_filter"] or "-", 28)] for r in rows],
    )


def cmd_table(d: dict, args):
    name = args.table
    if name not in table_map(d):
        raise SystemExit(f"unknown table: {name}")
    cs = columns(d, name)
    ds = table_map(d)[name]
    if args.json:
        print(json.dumps({"table": ds, "columns": cs}, indent=2))
        return
    print(f"Table: {name}")
    print(f"Source: {ds.get('ProviderName')} / {ds.get('SourcePath')} / {ds.get('SourceQualifier')}")
    print(f"Schema: {ds.get('SchemaName')}")
    print(f"Updates: {clean_expr(ds.get('UpdateModeExpression')) or 'ALL_CHANGES'}")
    print(f"Security filter: {clean_expr(ds.get('DataFilter')) or '-'}")
    print(f"Columns: {len(cs)}")
    print()
    rows = []
    for c in cs:
        flags = []
        if c.get("IsKey"):
            flags.append("KEY")
        if c.get("IsLabel"):
            flags.append("LABEL")
        if c.get("IsVirtual"):
            flags.append("VIRTUAL")
        if c.get("IsRequired"):
            flags.append("REQ")
        if c.get("IsHidden"):
            flags.append("HIDDEN")
        if c.get("IsReadOnly"):
            flags.append("RO")
        formula = c.get("AppFormula") or c.get("Formula") or ""
        initial = c.get("Default") or ""
        if not initial:
            de = c.get("DefaultExpression")
            if isinstance(de, dict):
                initial = de.get("SourceExpr") or ""
        show = col_get(c, "Show_If") or ""
        editable = col_get(c, "Editable_If") or ""
        rows.append([
            c.get("Name"), c.get("Type") or "", " ".join(flags),
            truncate(clean_expr(formula), 46),
            truncate(clean_expr(initial), 24),
            truncate(clean_expr(show), 30),
            truncate(clean_expr(editable), 24),
        ])
    print_table(["NAME", "TYPE", "FLAGS", "FORMULA", "INITIAL", "SHOW IF", "EDITABLE IF"], rows,
                max_widths={0: 26, 3: 46, 5: 30})


def cmd_column(d: dict, args):
    table, name = args.table, args.column
    cm = column_map(d, table)
    if name not in cm:
        raise SystemExit(f"unknown column: {table}.{name}")
    c = cm[name]
    if args.json:
        print(json.dumps(c, indent=2))
        return
    a = aux(c)
    print(f"Column: {table}.{name}")
    print(f"Type: {c.get('Type')}   Virtual: {c.get('IsVirtual')}   Key: {c.get('IsKey')}   Label: {c.get('IsLabel')}")
    print(f"Required: {c.get('IsRequired')}   Read-only: {c.get('IsReadOnly')}   Hidden: {c.get('IsHidden')}   Searchable: {c.get('Searchable')}")
    if ref_table(c):
        print(f"References: {ref_table(c)}")
    if enum_values(c):
        print(f"Enum values: {enum_values(c)}")
    for label, key in [
        ("App formula", "AppFormula"), ("Formula", "Formula"),
        ("Initial value", "Default"), ("Display name", "DisplayName"),
        ("Description", "Description"),
    ]:
        v = c.get(key)
        if v not in (None, "", []):
            print(f"{label}: {v}")
    de = c.get("DefaultExpression")
    if isinstance(de, dict) and de.get("SourceExpr") and not c.get("Default"):
        print(f"Initial value: {de['SourceExpr']}")
    print()
    for label, key in [
        ("Show if", "Show_If"), ("Editable if", "Editable_If"),
        ("Required if", "Required_If"), ("Reset if", "Reset_If"),
        ("Valid if", "Valid_If"), ("Error message", "Error_Message_If_Invalid"),
        ("Suggested values", "Suggested_Values"),
    ]:
        v = a.get(key)
        if v not in (None, "", []):
            print(f"{label}: {clean_expr(v) if isinstance(v, str) else v}")
    extra = {k: v for k, v in a.items() if k not in {
        "Show_If", "Editable_If", "Required_If", "Reset_If", "Valid_If",
        "Error_Message_If_Invalid", "Suggested_Values", "EnumValues",
        "ReferencedTableName", "ReferencedRootTableName", "ReferencedType",
        "ReferencedTypeQualifier", "MaxLength", "MinLength", "LongTextFormatting",
        "IsMulticolumnKey", "YesLabel", "NoLabel", "AllowOtherValues",
        "AutoCompleteOtherValues", "BaseType", "BaseTypeQualifier", "EnumInputMode",
        "MaxValue", "MinValue", "StepValue", "NumericDigits",
        "ShowThousandsSeparator", "NumberDisplayMode",
    } and v not in (None, "", [], False)}
    if extra:
        print()
        print("Other type options:")
        for k, v in extra.items():
            print(f"  {k}: {v}")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def view_record(c: dict) -> dict:
    vs = view_settings(c)
    return {
        "name": c.get("Name"),
        "type": view_type(c),
        "data": view_data(c),
        "position": c.get("Position"),
        "show_if": clean_expr(c.get("ShowIf")),
        "icon": vs.get("Icon") or "",
        "sort": vs.get("SortBy") or [],
        "group": vs.get("GroupBy") or [],
        "columns": vs.get("ColumnOrder") or [],
        "system": bool(c.get("_isSystemGenerated")),
        "settings": vs,
    }


def cmd_views(d: dict, args):
    recs = [view_record(c) for c in controls(d)]
    if getattr(args, "primary", False):
        recs = [r for r in recs if r["position"] != "ref" and not r["system"]]
    if args.json:
        print(json.dumps(recs, indent=2))
        return
    rows = []
    for r in recs:
        sort = ", ".join(f"{s.get('Column')}:{s.get('Order','')[:1]}" for s in r["sort"] if isinstance(s, dict))
        group = ", ".join(g.get("Column", "") for g in r["group"] if isinstance(g, dict))
        rows.append([r["name"] + (" [sys]" if r["system"] else ""), r["type"], r["data"],
                     r["position"] or "", truncate(sort, 30), truncate(group, 24),
                     truncate(r["show_if"], 30)])
    print_table(["VIEW", "TYPE", "DATA", "POSITION", "SORT", "GROUP", "SHOW IF"], rows,
                max_widths={0: 30, 4: 30, 6: 30})


def cmd_menus(d: dict, args):
    entries = (d.get("Presentation") or {}).get("MenuEntries") or []
    if args.json:
        print(json.dumps(entries, indent=2))
        return
    rows = []
    for m in entries:
        rows.append([
            m.get("ViewName") or "",
            m.get("Position") or "",
            truncate(clean_expr(m.get("ShowIf")), 46),
            m.get("Icon") or "",
        ])
    print_table(["VIEW", "POSITION", "SHOW IF", "ICON"], rows, max_widths={2: 46})


def cmd_view(d: dict, args):
    match = [c for c in controls(d) if c.get("Name") == args.view]
    if not match:
        raise SystemExit(f"unknown view: {args.view}")
    c = match[0]
    r = view_record(c)
    if args.json:
        print(json.dumps(r, indent=2))
        return
    print(f"View: {r['name']}" + (" [system generated]" if r["system"] else ""))
    print(f"Type: {r['type']}   Data: {r['data']}   Position: {r['position']}")
    if r["show_if"]:
        print(f"Show if: {r['show_if']}")
    if r["icon"]:
        print(f"Icon: {r['icon']}")
    sort = ", ".join(f"{x.get('Column')} ({x.get('Order')})" for x in r["sort"] if isinstance(x, dict))
    group = ", ".join(f"{x.get('Column')} ({x.get('Order')})" for x in r["group"] if isinstance(x, dict))
    print(f"Sort: {sort or '-'}")
    print(f"Group: {group or '-'}")
    print(f"Columns ({len(r['columns'])}): {', '.join(r['columns']) or '-'}")
    extra = {k: v for k, v in r["settings"].items() if k not in {
        "ColumnOrder", "SortBy", "GroupBy", "Icon", "MenuOrder", "Events",
        "GroupAggregate", "PrimarySortColumn", "IsPrimarySortDescending", "$type",
        "ColumnWidth", "EnableQuickEdit", "IconRunnerUps",
    } and v not in (None, "", [], False)}
    if extra:
        print()
        print("Other settings:")
        for k, v in extra.items():
            print(f"  {k}: {json.dumps(v) if not isinstance(v, str) else v}")


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def action_record(a: dict) -> dict:
    return {
        "name": a.get("Name"),
        "table": a.get("Table"),
        "type": a.get("ActionType"),
        "condition": clean_expr(action_condition(a)),
        "icon": a.get("Icon") or "",
        "prominence": action_prominence(a),
        "column": a.get("ColumnToEdit"),
        "assignments": action_assignments(a),
        "settings": action_definition(a),
        "embedded": bool(a.get("IsEmbedded")),
    }


def cmd_actions(d: dict, args):
    recs = [action_record(a) for a in actions(d)]
    if getattr(args, "table", None):
        recs = [r for r in recs if r["table"] == args.table]
    if args.json:
        print(json.dumps(recs, indent=2))
        return
    rows = []
    for r in recs:
        rows.append([r["table"] or "", r["name"] or "", r["type"] or "",
                     r["prominence"] or "", truncate(r["condition"], 52)])
    print_table(["TABLE", "ACTION", "TYPE", "PROMINENCE", "ONLY IF"], rows,
                max_widths={1: 30, 4: 52})


def cmd_action(d: dict, args):
    recs = [a for a in actions(d) if a.get("Name") == args.action]
    if getattr(args, "table", None):
        recs = [a for a in recs if a.get("Table") == args.table]
    if not recs:
        raise SystemExit(f"unknown action: {args.action}")
    if len(recs) > 1 and not getattr(args, "table", None):
        tables = ", ".join(sorted({a.get("Table") or "?" for a in recs}))
        raise SystemExit(f"action name is ambiguous ({tables}); add --table")
    a = recs[0]
    r = action_record(a)
    if args.json:
        print(json.dumps(r, indent=2))
        return
    print(f"Action: {r['name']}")
    print(f"Table: {r['table']}   Type: {r['type']}   Prominence: {r['prominence']}")
    if r["icon"]:
        print(f"Icon: {r['icon']}")
    if r["condition"]:
        print(f"Only if: {r['condition']}")
    if r["assignments"]:
        print("Assignments:")
        for x in r["assignments"]:
            print(f"  {x.get('ColumnToEdit')} = {clean_expr(x.get('NewColumnValue'))}")
    elif r["column"]:
        print(f"Set: {r['column']} = {a.get('Value')}")
    s = r["settings"]
    for k in ("NavigateTarget", "NeedsConfirmation", "ConfirmationMessage", "BulkApplicable", "ModifiesData"):
        if s.get(k) not in (None, "", False):
            print(f"{k}: {s[k]}")


# ---------------------------------------------------------------------------
# Slices
# ---------------------------------------------------------------------------


def slice_record(s: dict) -> dict:
    return {
        "name": s.get("Name"),
        "table": s.get("SourceTable"),
        "filter": clean_expr(slice_filter(s)),
        "columns": s.get("Columns") or [],
        "updates": clean_expr(s.get("UpdateModeExpression")),
    }


def cmd_slices(d: dict, args):
    recs = [slice_record(s) for s in slices(d)]
    if args.json:
        print(json.dumps(recs, indent=2))
        return
    print_table(["SLICE", "SOURCE TABLE", "ROW FILTER", "COLS"],
                [[r["name"], r["table"], truncate(r["filter"] or "-", 70), len(r["columns"])] for r in recs],
                max_widths={0: 32, 2: 70})


def cmd_slice(d: dict, args):
    match = [s for s in slices(d) if s.get("Name") == args.slice]
    if not match:
        raise SystemExit(f"unknown slice: {args.slice}")
    r = slice_record(match[0])
    if args.json:
        print(json.dumps(r, indent=2))
        return
    print(f"Slice: {r['name']}")
    print(f"Source table: {r['table']}")
    print(f"Row filter: {r['filter'] or '-'}")
    print(f"Columns ({len(r['columns'])}): {', '.join(r['columns']) or '-'}")
    if r["updates"]:
        print(f"Updates: {r['updates']}")


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


def cmd_security(d: dict, args):
    b = d.get("Behavior") or {}
    recs = []
    for t in datasets(d):
        recs.append({
            "table": t.get("Name"),
            "updates": clean_expr(t.get("UpdateModeExpression")) or "ALL_CHANGES",
            "security_filter": clean_expr(t.get("DataFilter")),
            "access": t.get("DataAccessMode"),
        })
    out = {
        "auth": {
            "require_sign_in": b.get("AuthRequired"),
            "allow_all_signed_in": b.get("AllowAllSignedInUsers"),
            "domain_auth": b.get("DomainAuthRequired"),
            "domain": b.get("AuthDomain"),
            "auth_provider": b.get("AuthProvider"),
        },
        "roles": d.get("UserRoles") or [],
        "tables": recs,
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    a = out["auth"]
    print("AUTH")
    for k, v in a.items():
        print(f"  {k}: {v}")
    print()
    print("ROLES")
    print("  " + ", ".join(str(r.get("Name")) if isinstance(r, dict) else str(r) for r in out["roles"]))
    print()
    print("TABLES")
    rows = [[r["table"], truncate(r["updates"], 46), truncate(r["security_filter"] or "-", 46), r["access"] or ""]
            for r in recs]
    print_table(["TABLE", "UPDATES", "SECURITY FILTER", "ACCESS"], rows, max_widths={1: 46, 2: 46})


# ---------------------------------------------------------------------------
# Expressions / search
# ---------------------------------------------------------------------------


def iter_expressions(d: dict):
    for t in datasets(d):
        tn = t.get("Name")
        for key in ("UpdateModeExpression", "DataFilter"):
            v = t.get(key)
            if isinstance(v, str) and v.strip():
                yield tn, f"table.{key}", v
    for t in datasets(d):
        tn = t.get("Name")
        for c in columns(d, tn):
            cn = c.get("Name")
            for key in ("AppFormula", "Formula", "Default"):
                v = c.get(key)
                if isinstance(v, str) and v.strip():
                    yield tn, f"{cn}.{key}", v
            a = aux(c)
            for key in ("Show_If", "Editable_If", "Required_If", "Reset_If", "Valid_If",
                        "Error_Message_If_Invalid", "Suggested_Values"):
                v = a.get(key)
                if isinstance(v, str) and v.strip():
                    yield tn, f"{cn}.{key}", v
    for s in slices(d):
        v = slice_filter(s)
        if v:
            yield s.get("Name"), "slice.filter", v
    for a in actions(d):
        v = action_condition(a)
        if v:
            yield a.get("Table"), f"action:{a.get('Name')}.Condition", v
        for x in action_assignments(a):
            v = x.get("NewColumnValue")
            if isinstance(v, str) and v.strip():
                yield a.get("Table"), f"action:{a.get('Name')}.{x.get('ColumnToEdit')}", v
        ad = action_definition(a)
        v = ad.get("NavigateTarget")
        if isinstance(v, str) and v.strip():
            yield a.get("Table"), f"action:{a.get('Name')}.NavigateTarget", v
    for c in controls(d):
        v = c.get("ShowIf")
        if isinstance(v, str) and v.strip():
            yield c.get("TableOrFolderName"), f"view:{c.get('Name')}.ShowIf", v


def cmd_exprs(d: dict, args):
    rows = []
    for table, where, expr in iter_expressions(d):
        if getattr(args, "table", None) and table != args.table:
            continue
        rows.append([table or "", where, clean_expr(expr)])
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    for table, where, expr in rows:
        print(f"[{table}] {where}")
        print(f"  {expr}")
        print()


def cmd_search(d: dict, args):
    try:
        rx = re.compile(args.regex, re.I)
    except re.error as e:
        raise SystemExit(f"bad regex: {e}")
    hits = []
    for table, where, expr in iter_expressions(d):
        if rx.search(expr) or rx.search(where):
            hits.append((table, where, expr))
    for t in datasets(d):
        if rx.search(t.get("Name") or ""):
            hits.append((t.get("Name"), "table", ""))
    for c in controls(d):
        if rx.search(c.get("Name") or ""):
            hits.append((c.get("TableOrFolderName"), f"view:{c.get('Name')}", ""))
    for a in actions(d):
        if rx.search(a.get("Name") or ""):
            hits.append((a.get("Table"), f"action:{a.get('Name')}", ""))
    if args.json:
        print(json.dumps(hits, indent=2))
        return
    if not hits:
        print("(no matches)")
        return
    for table, where, expr in hits:
        print(f"[{table}] {where}")
        if expr:
            print(f"  {clean_expr(expr)}")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _names(items) -> set[str]:
    return {i.get("Name") for i in items if i.get("Name")}


def _check_expr_refs(expr: str, table: str, all_columns: dict, where: str,
                     errors: list[str], warnings: list[str]):
    """Resolve Table[Column] and bare [Column] references against a table.

    Bare references are scoped heuristically: columns of tables named in
    SELECT()/FILTER()/LOOKUP() are treated as in-scope, which avoids false
    positives for expressions like SELECT(Users[Role], [Email] = USEREMAIL()).
    """
    if not isinstance(expr, str) or not expr.strip():
        return

    source_cols = all_columns.get(table, {})

    # Explicit Table[Column] references.
    for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_ ]*)\[([^\]]+)\]", expr):
        t, c = m.group(1).strip(), m.group(2).strip()
        if t in all_columns and c not in all_columns[t]:
            errors.append(f"{where}: references missing column {t}.{c}")

    # Tables explicitly opened by SELECT/FILTER/LOOKUP.
    scope_tables = set(re.findall(r"\b(?:SELECT|FILTER)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\[", expr))
    scope_tables |= set(re.findall(r'FILTER\s*\(\s*"([^"]+)"', expr))
    scope_tables |= set(re.findall(r'LOOKUP\s*\([^,]+,\s*"([^"]+)"', expr))

    # [Ref].[Column] chains: check the ref column, skip the target column.
    chain = re.compile(r"\[([^\]]+)\]\.\[([^\]]+)\]")
    for m in chain.finditer(expr):
        ref = m.group(1).strip()
        if not ref.startswith("_") and ref not in source_cols:
            errors.append(f"{where}: references missing ref column {table}.{ref}")
    without_chains = chain.sub("", expr)
    without_explicit = re.sub(r"\b[A-Za-z_][A-Za-z0-9_ ]*\[[^\]]+\]", "", without_chains)

    for m in re.finditer(r"\[([^\]]+)\]", without_explicit):
        c = m.group(1).strip()
        if c.startswith("_"):
            continue
        if c in source_cols:
            continue
        if any(c in all_columns.get(t, {}) for t in scope_tables):
            continue
        errors.append(f"{where}: references missing column {table}.{c}")


def cmd_validate(d: dict, args):
    errors: list[str] = []
    warnings: list[str] = []
    tm = table_map(d)
    sm = schema_map(d)
    all_columns = {t: column_map(d, t) for t in tm}
    view_names = [c.get("Name") for c in controls(d) if c.get("Name")]
    slice_names = [s.get("Name") for s in slices(d) if s.get("Name")]

    # Tables
    for t in datasets(d):
        name = t.get("Name") or "?"
        raw_cols = columns(d, name)
        cs = all_columns.get(name, {})
        if not cs:
            errors.append(f"table {name}: no columns/schema")
            continue

        key_cols = [c for c in cs.values() if c.get("IsKey")]
        if not key_cols:
            errors.append(f"table {name}: no key column")
        elif len(key_cols) > 1:
            names = ", ".join(str(c.get("Name")) for c in key_cols)
            errors.append(f"table {name}: multiple key columns ({names})")

        if not name.startswith("_") and not any(c.get("IsLabel") for c in cs.values()):
            warnings.append(f"table {name}: no label column (rows will use the key)")

        raw_names = [c.get("Name") for c in raw_cols if c.get("Name")]
        dupes = sorted({n for n in raw_names if raw_names.count(n) > 1})
        for n in dupes:
            errors.append(f"table {name}: duplicate column name {n}")

        for c in cs.values():
            cn = c.get("Name")
            rt = ref_table(c)
            if rt and rt not in tm:
                errors.append(f"column {name}.{cn}: Ref to missing table {rt}")
            elif rt:
                a = aux(c)
                rk = a.get("ReferencedKeyColumn")
                if rk:
                    target_cols = all_columns.get(rt, {})
                    if rk not in target_cols:
                        errors.append(
                            f"column {name}.{cn}: Ref key {rt}.{rk} does not exist")
                    elif not target_cols[rk].get("IsKey"):
                        errors.append(
                            f"column {name}.{cn}: Ref key {rt}.{rk} is not a key column")
                else:
                    warnings.append(
                        f"column {name}.{cn}: Ref has no ReferencedKeyColumn")

        _check_expr_refs(t.get("DataFilter"), name, all_columns,
                         f"table {name} security filter", errors, warnings)

    # Duplicate names
    for label, names in (("view", view_names), ("slice", slice_names)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        for n in dupes:
            errors.append(f"duplicate {label} name: {n}")

    # Navigation menu entries must point at real, unique views.
    view_name_set = set(view_names)
    seen_menu: list[str] = []
    for m in ((d.get("Presentation") or {}).get("MenuEntries") or []):
        vn = m.get("ViewName")
        if not vn:
            errors.append("menu entry: missing ViewName")
            continue
        if vn not in view_name_set:
            errors.append(f"menu entry: unknown view {vn}")
        if vn in seen_menu:
            errors.append(f"menu entry: duplicate view {vn}")
        seen_menu.append(vn)

    # Slices
    for s in slices(d):
        sn = s.get("Name") or "?"
        st = s.get("SourceTable")
        if st not in tm:
            errors.append(f"slice {sn}: missing source table {st}")
            continue
        for c in (s.get("Columns") or []):
            if not str(c).startswith("**") and c not in all_columns.get(st, {}):
                warnings.append(f"slice {sn}: column {c} not in table {st}")
        _check_expr_refs(slice_filter(s), st, all_columns,
                         f"slice {sn} filter", errors, warnings)

    # Views
    slice_map = {s.get("Name"): s for s in slices(d)}
    for c in controls(d):
        vn = c.get("Name") or "?"
        src = view_data(c)
        if not src:
            continue
        if src in tm:
            valid_cols = set(all_columns.get(src, {}))
        elif src in slice_map:
            s = slice_map[src]
            slice_cols = [c for c in (s.get("Columns") or []) if not str(c).startswith("**")]
            valid_cols = set(slice_cols) if slice_cols else set(all_columns.get(s.get("SourceTable"), {}))
        else:
            errors.append(f"view {vn}: unknown table/slice {src}")
            continue
        for col in (view_settings(c).get("ColumnOrder") or []):
            if col not in valid_cols and not str(col).startswith("**"):
                warnings.append(f"view {vn}: column {col} not in {src}")
        for spec in (view_settings(c).get("SortBy") or []) + (view_settings(c).get("GroupBy") or []):
            if isinstance(spec, dict) and spec.get("Column") and spec["Column"] not in valid_cols:
                warnings.append(f"view {vn}: sort/group column {spec['Column']} not in {src}")

        show_table = src if src in tm else (
            slice_map[src].get("SourceTable") if src in slice_map else None)
        if show_table:
            _check_expr_refs(c.get("ShowIf"), show_table, all_columns,
                             f"view {vn} show-if", errors, warnings)

    # Actions
    action_names_by_table = defaultdict(list)
    for a in actions(d):
        an = a.get("Name") or "?"
        at = a.get("Table")
        action_names_by_table[at].append(an)
        if not at:
            errors.append(f"action {an}: no table")
            continue
        if at not in tm:
            errors.append(f"action {an}: missing table {at}")
            continue
        ac = all_columns.get(at, {})
        if a.get("ColumnToEdit") and a["ColumnToEdit"] not in ac:
            errors.append(f"action {an}: missing column {at}.{a['ColumnToEdit']}")
        for x in action_assignments(a):
            col = x.get("ColumnToEdit")
            if col and col not in ac:
                errors.append(f"action {an}: assignment to missing column {at}.{col}")

    for table, names in action_names_by_table.items():
        dupes = sorted({n for n in names if names.count(n) > 1})
        for n in dupes:
            warnings.append(f"table {table}: duplicate action name {n}")

    # App-level
    if d.get("IsRunnable") is False:
        errors.append("app is not runnable")
    if d.get("IsValid") is False:
        errors.append("app is marked invalid")

    # Optional: fold in the AppErrors from a POST /api/saveapp response.
    if getattr(args, "server_errors", None):
        try:
            with open(args.server_errors, "r", encoding="utf-8-sig") as f:
                resp = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"server-errors file: {e}")
        else:
            if resp.get("Success") is False:
                errors.append("saveapp: Success=false")
            for e in (resp.get("AppErrors") or []):
                code = e.get("ErrorCode") or "SERVER"
                msg = e.get("Description") or e.get("DetailedErrorMessage") or json.dumps(e)
                line = f"server {code}: {msg}"
                if code.startswith("INFO_") or e.get("Severity") in (0, 1):
                    warnings.append(line)
                else:
                    errors.append(line)

    out = {"errors": errors, "warnings": warnings}
    if args.json:
        print(json.dumps(out, indent=2))
        return
    print(f"Errors:   {len(errors)}")
    for e in errors:
        print(f"  ERROR  {e}")
    print(f"Warnings: {len(warnings)}")
    for w in warnings:
        print(f"  WARN   {w}")
    if not errors:
        print("\nOK - no structural errors.")


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


VOLATILE_KEYS = {
    "_index", "_path", "_isSystemGenerated", "_isMinor", "ComponentId",
    "IsValid", "Visibility", "DisableAutoUpdate", "ExprLookup", "CreatedBy", "$type",
}


def strip_volatile(value):
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    return value


def _by_name(items, prefix: str) -> dict:
    out = {}
    for i, item in enumerate(items or []):
        if isinstance(item, dict):
            out[item.get("Name") or f"{prefix}[{i}]"] = item
    return out


def normalized(d: dict) -> dict:
    out = {"tables": {}, "columns": {}, "views": {}, "actions": {}, "slices": {},
           "format_rules": {}, "security": {}}
    for t in datasets(d):
        tn = t.get("Name")
        out["tables"][tn] = {
            "updates": clean_expr(t.get("UpdateModeExpression")) or "ALL_CHANGES",
            "security_filter": clean_expr(t.get("DataFilter")),
            "access": t.get("DataAccessMode"),
            "provider": t.get("ProviderName"),
            "source_path": t.get("SourcePath"),
            # Source carries the provider's stable frame/table identity. Without
            # it, two different tables in the same database diff clean.
            "source_id": t.get("Source"),
        }
        for c in columns(d, tn):
            cn = c.get("Name")
            a = aux(c)
            de = c.get("DefaultExpression")
            out["columns"][f"{tn}.{cn}"] = {
                "type": c.get("Type"),
                "key": bool(c.get("IsKey")),
                "label": bool(c.get("IsLabel")),
                "virtual": bool(c.get("IsVirtual")),
                "required": bool(c.get("IsRequired")),
                "read_only": bool(c.get("IsReadOnly")),
                "hidden": bool(c.get("IsHidden")),
                "formula": clean_expr(c.get("AppFormula") or c.get("Formula")),
                "initial": clean_expr(c.get("Default") or (de.get("SourceExpr") if isinstance(de, dict) else "")),
                "show_if": clean_expr(a.get("Show_If")),
                "editable_if": clean_expr(a.get("Editable_If")),
                "required_if": clean_expr(a.get("Required_If")),
                "valid_if": clean_expr(a.get("Valid_If")),
                "ref": ref_table(c),
                "ref_key": a.get("ReferencedKeyColumn"),
                "display_name": c.get("DisplayName"),
                "description": c.get("Description"),
            }
    for c in controls(d):
        out["views"][c.get("Name")] = {
            "type": view_type(c),
            "data": view_data(c),
            "position": c.get("Position"),
            "show_if": clean_expr(c.get("ShowIf")),
            "columns": view_settings(c).get("ColumnOrder") or [],
            "sort": view_settings(c).get("SortBy") or [],
            "group": view_settings(c).get("GroupBy") or [],
            "icon": view_settings(c).get("Icon") or "",
        }
    for a in actions(d):
        key = f"{a.get('Table')}.{a.get('Name')}"
        out["actions"][key] = {
            "type": a.get("ActionType"),
            "condition": clean_expr(action_condition(a)),
            "icon": a.get("Icon") or "",
            "prominence": action_prominence(a),
            "column": a.get("ColumnToEdit"),
            "assignments": action_assignments(a),
            "settings": {k: v for k, v in action_definition(a).items()
                         if k in ("NavigateTarget", "NeedsConfirmation", "ConfirmationMessage", "BulkApplicable")},
        }
    for s in slices(d):
        out["slices"][s.get("Name")] = {
            "table": s.get("SourceTable"),
            "filter": clean_expr(slice_filter(s)),
            "columns": s.get("Columns") or [],
            "updates": clean_expr(s.get("UpdateModeExpression")),
        }
    out["format_rules"] = strip_volatile(_by_name((d.get("Presentation") or {}).get("FormatRules"), "format_rule"))

    out["menus"] = {}
    for i, m in enumerate(((d.get("Presentation") or {}).get("MenuEntries") or [])):
        key = m.get("ViewName") or f"menu[{i}]"
        if key in out["menus"]:
            key = f"{key}#{i}"
        out["menus"][key] = strip_volatile(m)

    behavior = d.get("Behavior") or {}
    out["automations"] = {}
    for key in ("AppBots", "AppProcesses", "AppEvents", "AppWorkflowRules",
                "WorkflowRules", "Tasks"):
        value = behavior.get(key) if isinstance(behavior, dict) else None
        if value is None:
            value = d.get(key)
        for name, body in _by_name(value, key).items():
            out["automations"][f"{key}.{name}"] = strip_volatile(body)
    b = behavior
    out["security"] = {
        "require_sign_in": b.get("AuthRequired"),
        "allow_all_signed_in": b.get("AllowAllSignedInUsers"),
        "domain_auth": b.get("DomainAuthRequired"),
        "domain": b.get("AuthDomain"),
        "roles": d.get("UserRoles") or [],
    }
    return out


def compact_delta(old, new, width: int = 180) -> str:
    """Render a readable single-line delta, keeping the changed region."""
    if isinstance(old, str) and isinstance(new, str):
        i = 0
        while i < min(len(old), len(new)) and old[i] == new[i]:
            i += 1
        j = 0
        while (j < min(len(old) - i, len(new) - i)
               and old[-1 - j] == new[-1 - j]):
            j += 1
        prefix = old[:i]
        suffix = old[len(old) - j:] if j else ""
        old_mid = old[i:len(old) - j] if j else old[i:]
        new_mid = new[i:len(new) - j] if j else new[i:]
        if not old_mid or not new_mid:
            return f"{truncate(old, width)} -> {truncate(new, width)}"
        if len(prefix) > 40:
            prefix = "..." + prefix[-37:]
        if len(suffix) > 40:
            suffix = suffix[:37] + "..."
        return f"{prefix}[-{old_mid}-]{{+{new_mid}+}}{suffix}"
    return f"{truncate(json.dumps(old), width)} -> {truncate(json.dumps(new), width)}"


def diff_dicts(before: dict, after: dict, label: str, lines: list[str], changes: list[dict]):
    b, a = before.get(label, {}), after.get(label, {})
    for key in sorted(set(b) | set(a)):
        if key not in b:
            lines.append(f"  + {key}")
            changes.append({"kind": label, "op": "add", "key": key, "after": a[key]})
        elif key not in a:
            lines.append(f"  - {key}")
            changes.append({"kind": label, "op": "remove", "key": key, "before": b[key]})
        else:
            delta = {k: (b[key].get(k), a[key].get(k)) for k in set(b[key]) | set(a[key])
                     if b[key].get(k) != a[key].get(k)}
            if delta:
                lines.append(f"  ~ {key}")
                for k, (old, new) in sorted(delta.items()):
                    lines.append(f"      {k}: {compact_delta(old, new)}")
                changes.append({"kind": label, "op": "change", "key": key, "delta": delta})


def cmd_diff(d_before: dict, d_after: dict, args):
    before, after = normalized(d_before), normalized(d_after)
    lines: list[str] = []
    changes: list[dict] = []
    for label, title in [
        ("tables", "TABLES"), ("columns", "COLUMNS"), ("views", "VIEWS"),
        ("actions", "ACTIONS"), ("slices", "SLICES"),
        ("menus", "MENUS"), ("format_rules", "FORMAT RULES"),
        ("automations", "AUTOMATIONS"),
    ]:
        before_set = set(before[label])
        after_set = set(after[label])
        if before_set != after_set or any(before[label][k] != after[label][k] for k in before_set & after_set):
            lines.append(title)
            diff_dicts(before, after, label, lines, changes)
            lines.append("")
    if before["security"] != after["security"]:
        lines.append("SECURITY")
        for k in sorted(set(before["security"]) | set(after["security"])):
            old, new = before["security"].get(k), after["security"].get(k)
            if old != new:
                lines.append(f"  ~ {k}: {old} -> {new}")
        lines.append("")

    if args.json:
        print(json.dumps({"changes": changes, "text": "\n".join(lines)}, indent=2))
        return
    if not lines:
        print("No semantic differences.")
        return
    print("\n".join(lines).rstrip())


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def cmd_export_md(d: dict, args):
    s = app_summary(d)
    out: list[str] = []
    out.append(f"# {s['name']} - AppSheet app specification\n")
    out.append(f"- App ID: `{s['id']}`")
    out.append(f"- Version: `{s['version']}` (platform {s['platform']})")
    out.append(f"- Last modified: {s['modified']}")
    out.append(f"- Tables: {s['tables']} | Columns: {s['columns']} | Views: {s['views']} | Actions: {s['actions']} | Slices: {s['slices']}\n")

    out.append("## Tables\n")
    for t in datasets(d):
        tn = t.get("Name")
        out.append(f"### {tn}\n")
        out.append(f"- Source: `{t.get('ProviderName')}` / `{t.get('SourcePath')}` / `{t.get('SourceQualifier')}`")
        out.append(f"- Updates: `{clean_expr(t.get('UpdateModeExpression')) or 'ALL_CHANGES'}`")
        if t.get("DataFilter"):
            out.append(f"- Security filter: `{clean_expr(t.get('DataFilter'))}`")
        out.append("")
        out.append("| Column | Type | Flags | Formula / initial | Show if | Editable if |")
        out.append("|---|---|---|---|---|---|")
        for c in columns(d, tn):
            flags = []
            if c.get("IsKey"): flags.append("key")
            if c.get("IsLabel"): flags.append("label")
            if c.get("IsVirtual"): flags.append("virtual")
            if c.get("IsRequired"): flags.append("required")
            if c.get("IsReadOnly"): flags.append("read-only")
            if c.get("IsHidden"): flags.append("hidden")
            formula = clean_expr(c.get("AppFormula") or c.get("Formula"))
            initial = c.get("Default") or ""
            expr = formula or (f"initial: {initial}" if initial else "")
            show = clean_expr(col_get(c, "Show_If") or "")
            edit = clean_expr(col_get(c, "Editable_If") or "")
            out.append(f"| `{c.get('Name')}` | {c.get('Type')} | {', '.join(flags)} | {md_code(expr)} | {md_code(show)} | {md_code(edit)} |")
        out.append("")

    out.append("## Slices\n")
    out.append("| Slice | Source | Row filter |")
    out.append("|---|---|---|")
    for sl in slices(d):
        out.append(f"| `{sl.get('Name')}` | `{sl.get('SourceTable')}` | {md_code(clean_expr(slice_filter(sl)))} |")
    out.append("")

    out.append("## Views\n")
    out.append("| View | Type | Data | Position | Sort | Group | Show if |")
    out.append("|---|---|---|---|---|---|---|")
    for c in controls(d):
        r = view_record(c)
        sort = ", ".join(f"{x.get('Column')}" for x in r["sort"] if isinstance(x, dict))
        group = ", ".join(x.get("Column", "") for x in r["group"] if isinstance(x, dict))
        out.append(f"| `{r['name']}` | {r['type']} | `{r['data']}` | {r['position']} | {sort} | {group} | {md_code(r['show_if'])} |")
    out.append("")

    out.append("## Actions\n")
    out.append("| Table | Action | Type | Only if | Assignments |")
    out.append("|---|---|---|---|---|")
    for a in actions(d):
        r = action_record(a)
        assigns = "; ".join(f"{x.get('ColumnToEdit')}={x.get('NewColumnValue')}" for x in r["assignments"])
        out.append(f"| `{r['table']}` | `{r['name']}` | {r['type']} | {md_code(r['condition'])} | {md_code(assigns)} |")
    out.append("")

    out.append("## Security\n")
    b = d.get("Behavior") or {}
    out.append(f"- Require sign-in: {b.get('AuthRequired')}")
    out.append(f"- Allow all signed-in users: {b.get('AllowAllSignedInUsers')}")
    out.append(f"- Domain auth: {b.get('DomainAuthRequired')} {b.get('AuthDomain') or ''}")
    out.append(f"- Roles: {', '.join(str(x) for x in (d.get('UserRoles') or []))}\n")
    out.append("| Table | Updates | Security filter |")
    out.append("|---|---|---|")
    for t in datasets(d):
        out.append(f"| `{t.get('Name')}` | {md_code(clean_expr(t.get('UpdateModeExpression')) or 'ALL_CHANGES')} | {md_code(clean_expr(t.get('DataFilter')))} |")
    out.append("")

    rules = _by_name((d.get("Presentation") or {}).get("FormatRules"), "format_rule")
    if rules:
        out.append("## Format rules\n")
        out.append("| Rule | Table | Condition |")
        out.append("|---|---|---|")
        for name, r in rules.items():
            out.append(f"| `{name}` | `{r.get('TableName') or r.get('Table') or ''}` | {md_code(clean_expr(r.get('Condition')))} |")
        out.append("")

    bots = _by_name((d.get("Behavior") or {}).get("AppBots"), "bot")
    if bots:
        out.append("## Bots\n")
        out.append("| Bot | Event | Table |")
        out.append("|---|---|---|")
        for name, b in bots.items():
            out.append(f"| `{name}` | {b.get('EventType') or b.get('Event') or ''} | `{b.get('TableName') or b.get('Table') or ''}` |")
        out.append("")

    text = "\n".join(out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)


def md_code(s: str) -> str:
    if not s:
        return ""
    s = str(s).replace("|", "\\|")
    return f"`{s}`"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Inspect, validate, and diff AppSheet app definitions.")
    p.add_argument("--json", action="store_true", help="emit JSON")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, help_):
        sp = sub.add_parser(name, help=help_)
        # SUPPRESS lets `appdef.py --json <cmd>` work as well as `<cmd> --json`.
        sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="emit JSON")
        return sp

    sp = add("summary", "app metadata and counts")
    sp.add_argument("appdef")

    sp = add("tables", "list tables")
    sp.add_argument("appdef")

    sp = add("table", "show a table's columns")
    sp.add_argument("appdef")
    sp.add_argument("table")

    sp = add("column", "show one column in full")
    sp.add_argument("appdef")
    sp.add_argument("table")
    sp.add_argument("column")

    sp = add("views", "list views")
    sp.add_argument("appdef")
    sp.add_argument("--primary", action="store_true", help="exclude ref and system views")

    sp = add("view", "show one view")
    sp.add_argument("appdef")
    sp.add_argument("view")

    sp = add("menus", "list navigation menu entries")
    sp.add_argument("appdef")

    sp = add("actions", "list actions")
    sp.add_argument("appdef")
    sp.add_argument("--table")

    sp = add("action", "show one action")
    sp.add_argument("appdef")
    sp.add_argument("action")
    sp.add_argument("--table")

    sp = add("slices", "list slices")
    sp.add_argument("appdef")

    sp = add("slice", "show one slice")
    sp.add_argument("appdef")
    sp.add_argument("slice")

    sp = add("security", "auth, roles, table update/security filters")
    sp.add_argument("appdef")

    sp = add("exprs", "dump all expressions")
    sp.add_argument("appdef")
    sp.add_argument("--table")

    sp = add("search", "search names and expressions")
    sp.add_argument("appdef")
    sp.add_argument("regex")

    sp = add("validate", "structural checks")
    sp.add_argument("appdef")
    sp.add_argument("--server-errors", help="AppErrors JSON from POST /api/saveapp")

    sp = add("diff", "semantic diff of two appdefs")
    sp.add_argument("before")
    sp.add_argument("after")

    sp = add("export-md", "write a readable app spec")
    sp.add_argument("appdef")
    sp.add_argument("out", nargs="?")
    sp.add_argument("--out", dest="out_opt")

    sp = add("compact", "write a compact (no whitespace) appdef")
    sp.add_argument("appdef")
    sp.add_argument("out")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "diff":
        cmd_diff(load_appdef(args.before), load_appdef(args.after), args)
        return 0
    d = load_appdef(args.appdef)
    handlers = {
        "summary": cmd_summary,
        "tables": cmd_tables,
        "table": cmd_table,
        "column": cmd_column,
        "views": cmd_views,
        "view": cmd_view,
        "menus": cmd_menus,
        "actions": cmd_actions,
        "action": cmd_action,
        "slices": cmd_slices,
        "slice": cmd_slice,
        "security": cmd_security,
        "exprs": cmd_exprs,
        "search": cmd_search,
        "validate": cmd_validate,
        "compact": cmd_compact,
    }
    if args.command == "export-md":
        if getattr(args, "out_opt", None):
            args.out = args.out_opt
        cmd_export_md(d, args)
        return 0
    handlers[args.command](d, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
