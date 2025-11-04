# validator.py
from typing import Any, Dict, List, Set, Tuple
import re

# ---- Constants ---------------------------------------------------------------

ALLOWED_FIELD_TYPES = {
    "checkbox", "combo", "text", "textarea", "fileupload",
    "datetime", "label", "list", "swfupload"
}

ALLOWED_BLOCK_TYPES = {
    "start", "stop", "update", "vote0007", "task",
    "notification", "quickaction", "if", "switch", "join"
}

REQUIRED_OFFERING_KEYS = {
    "catalog_item_name", "description", "category",
    "delivery_target_days", "user_permissions", "publishing_scope"
}

# ---- Small helpers -----------------------------------------------------------

def issue(sev: str, where: str, msg: str) -> Dict[str, str]:
    return {"severity": sev, "where": where, "message": msg}

def _norm_expr(s: str | None) -> str:
    """Collapse whitespace inside Ivanti $( ...) expressions so formatting differences don't false-flag."""
    if not isinstance(s, str):
        return ""
    t = s.strip()
    t = re.sub(r"\s+", " ", t)              # collapse runs of spaces
    t = re.sub(r"\$\(\s*", "$(", t)         # strip space after $(
    t = re.sub(r"\s*\)", ")", t)            # strip space before )
    return t

# ---- Offering ---------------------------------------------------------------

def validate_offering(offering: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    # required keys present?
    for k in REQUIRED_OFFERING_KEYS:
        if k not in offering:
            issues.append(issue("error", "offering", f"Missing key: {k}"))

    # empty description/category: warn (allowed via missing_fields, but highlight)
    for k in ("description", "category"):
        v = offering.get(k, "")
        if isinstance(v, str) and not v.strip():
            issues.append(issue("warn", f"offering.{k}", "Empty; supply or keep in missing_fields"))

    # delivery_target_days should be int
    if not isinstance(offering.get("delivery_target_days"), int):
        issues.append(issue("warn", "offering.delivery_target_days", "Should be an integer"))

    # user_permissions shape
    up = offering.get("user_permissions")
    if not isinstance(up, dict):
        issues.append(issue("error", "offering.user_permissions", "Must be an object"))
    else:
        for k in ("can_cancel", "can_edit"):
            if k in up and not isinstance(up[k], bool):
                issues.append(issue("error", f"offering.user_permissions.{k}", "Must be boolean"))

    # publishing_scope shape
    ps = offering.get("publishing_scope")
    if not isinstance(ps, dict):
        issues.append(issue("error", "offering.publishing_scope", "Must be an object"))
    else:
        mode = (ps.get("mode") or "").strip().lower()
        if mode not in {"all_users", "groups", "users"}:
            issues.append(issue("warn", "offering.publishing_scope.mode",
                                "Unexpected mode; expected all_users|groups|users"))
        for k in ("groups", "users"):
            if k in ps and not isinstance(ps[k], list):
                issues.append(issue("error", f"offering.publishing_scope.{k}", "Must be a list"))

    return issues

# ---- Form (fields) ----------------------------------------------------------

def collect_field_names(fields: List[Dict[str, Any]]) -> Tuple[Set[str], List[Dict[str, str]]]:
    issues: List[Dict[str, str]] = []
    names: Set[str] = set()
    for idx, f in enumerate(fields, 1):
        name = f.get("internal_name")
        if not name or not isinstance(name, str):
            issues.append(issue("error", f"form.fields[{idx}]", "Field missing valid internal_name"))
            continue
        if name in names:
            issues.append(issue("error", f"form.fields[{idx}]", f"Duplicate internal_name: {name}"))
        names.add(name)
    return names, issues

def check_field(field: Dict[str, Any], idx: int, known_names: Set[str]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    where = f"form.fields[{idx}]({field.get('internal_name','?')})"

    # type
    ftype = field.get("field_type")
    if ftype not in ALLOWED_FIELD_TYPES:
        issues.append(issue("error", where, f"Unsupported field_type: {ftype}"))

    # booleans
    if "required" in field and not isinstance(field["required"], bool):
        issues.append(issue("error", where, "required must be boolean"))
    if "read_only" in field and not isinstance(field["read_only"], bool):
        issues.append(issue("error", where, "read_only must be boolean"))

    # combo options (if present) must be a list
    if ftype == "combo" and field.get("options") is not None and not isinstance(field["options"], list):
        issues.append(issue("error", where, "combo field 'options' must be a list"))

    # conflict: required + required_expression together
    if field.get("required") is True and field.get("required_expression"):
        issues.append(issue("warn", where, "Avoid required=true when required_expression is present"))

    # BRD rules:

    # 1) employee_id gating: expressions should match even if spaced
    if field.get("internal_name") == "employee_id":
        want = _norm_expr("$( submit_on_behalf == true )")
        req_expr = _norm_expr(field.get("required_expression"))
        vis_expr = _norm_expr(field.get("visibility_expression"))
        if req_expr != want:
            issues.append(issue("warn", where, "Expected required_expression: $( submit_on_behalf == true )"))
        if vis_expr != want:
            issues.append(issue("warn", where, "Expected visibility_expression: $( submit_on_behalf == true )"))

    # 2) domain_name hidden
    if field.get("internal_name") == "domain_name":
        vis_expr = _norm_expr(field.get("visibility_expression"))
        if vis_expr and vis_expr != _norm_expr("$(false)"):
            issues.append(issue("warn", where, "domain_name should be hidden; set visibility_expression to $(false)"))

    return issues

def validate_form(form: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    fields = form.get("fields")
    if not isinstance(fields, list):
        return [issue("error", "form.fields", "fields must be a list")]

    names, name_issues = collect_field_names(fields)
    issues.extend(name_issues)

    # contiguous sequence numbers (if present)
    seqs = [f.get("sequence_number") for f in fields]
    if all(isinstance(x, int) for x in seqs):
        if sorted(seqs) != list(range(1, len(fields) + 1)):
            issues.append(issue("warn", "form.fields.sequence_number", "Sequence numbers should be 1..N contiguous"))

    for idx, f in enumerate(fields, 1):
        issues.extend(check_field(f, idx, names))

    # helpful hints for auto-fill (optional)
    for want, hint in (
        ("phone_number", "CurrentUser('Phone')"),
        ("extension",    "CurrentUser('Extension')"),
    ):
        fld = next((x for x in fields if x.get("internal_name") == want), None)
        if fld and not fld.get("auto_fill_expression"):
            issues.append(issue("warn", f"form.fields({want})",
                                f"Consider auto_fill_expression for {want} (e.g., {hint})"))
    return issues

# ---- Workflow ---------------------------------------------------------------

def validate_workflow(workflow: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    blocks = workflow.get("blocks")
    links  = workflow.get("links")

    if not isinstance(blocks, list) or not isinstance(links, list):
        return [issue("error", "workflow", "blocks and links must be lists")]

    ids: Set[str] = set()
    start_count = 0
    stop_count  = 0

    for i, b in enumerate(blocks, 1):
        bid = b.get("id")
        if not bid or not isinstance(bid, str):
            issues.append(issue("error", f"workflow.blocks[{i}]", "Missing/invalid id"))
            continue
        if bid in ids:
            issues.append(issue("error", f"workflow.blocks[{i}]", f"Duplicate block id: {bid}"))
        ids.add(bid)

        btype = b.get("type")
        if btype not in ALLOWED_BLOCK_TYPES:
            issues.append(issue("error", f"workflow.blocks[{i}]", f"Unknown block type: {btype}"))
        if btype == "start": start_count += 1
        if btype == "stop":  stop_count  += 1

        # vote0007: approvers shape
        if btype == "vote0007":
            props = b.get("properties", {}) or {}
            appr = props.get("approvers", {}) or {}
            mode = appr.get("mode")
            if mode == "group":
                if not appr.get("group_recid"):
                    issues.append(issue("error", f"workflow.blocks[{i}]", "vote0007 mode=group requires group_recid"))
            elif mode == "related_manager":
                if not appr.get("relation"):
                    issues.append(issue("error", f"workflow.blocks[{i}]", "vote0007 mode=related_manager requires relation"))
            else:
                issues.append(issue("warn", f"workflow.blocks[{i}]", "vote0007 approvers.mode is unusual"))

    if start_count != 1:
        issues.append(issue("error", "workflow.blocks", f"Expected exactly one start block; found {start_count}"))
    if stop_count < 1:
        issues.append(issue("error", "workflow.blocks", "Expected at least one stop block"))

    # links refer to real block ids
    for i, l in enumerate(links, 1):
        frm = l.get("from"); to = l.get("to")
        if frm not in ids:
            issues.append(issue("error", f"workflow.links[{i}]", f"Unknown from id: {frm}"))
        if to not in ids:
            issues.append(issue("error", f"workflow.links[{i}]", f"Unknown to id: {to}"))

    # status transitions shape
    sts = workflow.get("status_transitions", [])
    if sts and not isinstance(sts, list):
        issues.append(issue("error", "workflow.status_transitions", "Must be a list"))
    else:
        for j, t in enumerate(sts, 1):
            for k in ("from", "on", "to"):
                if k not in t:
                    issues.append(issue("error", f"workflow.status_transitions[{j}]", f"Missing '{k}'"))

    # notification placeholders (warn so mapping step can fill)
    for i, n in enumerate(workflow.get("notifications", []), 1):
        tmpl = n.get("template")
        if isinstance(tmpl, str) and tmpl.startswith("<") and ">" in tmpl:
            issues.append(issue("warn", f"workflow.notifications[{i}]",
                                "Notification template is a placeholder; map via tenant_config.json"))
    return issues

# ---- Tenant config ----------------------------------------------------------

def validate_tenant_config(cfg: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    groups = cfg.get("groups", {})
    emails = cfg.get("email_templates", {})

    if not isinstance(groups, dict):
        issues.append(issue("error", "tenant_config.groups", "Must be an object"))
    else:
        for k, v in groups.items():
            if isinstance(v, str) and v.strip().upper() == "REPLACE_ME":
                issues.append(issue("warn", f"tenant_config.groups.{k}", "Value still REPLACE_ME"))

    if not isinstance(emails, dict):
        issues.append(issue("error", "tenant_config.email_templates", "Must be an object"))
    else:
        for k, v in emails.items():
            if isinstance(v, str) and v.strip().upper() == "REPLACE_ME":
                issues.append(issue("warn", f"tenant_config.email_templates.{k}", "Value still REPLACE_ME"))

    return issues

# ---- Master entry -----------------------------------------------------------

def validate_all(
    offering: Dict[str, Any],
    form: Dict[str, Any],
    workflow: Dict[str, Any],
    tenant_cfg: Dict[str, Any],
) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    issues += validate_offering(offering)
    issues += validate_form(form)
    issues += validate_workflow(workflow)
    issues += validate_tenant_config(tenant_cfg)
    return issues
