import re


def find_placeholders(obj, path="$", hits=None):
    if hits is None: hits = []
    if isinstance(obj, dict):
        for k,v in obj.items():
            find_placeholders(v, f"{path}.{k}", hits)
    elif isinstance(obj, list):
        for i,v in enumerate(obj):
            find_placeholders(v, f"{path}[{i}]", hits)
    elif isinstance(obj, str) and re.fullmatch(r"<[^>]+>", obj):
        hits.append({"path": path, "value": obj})
    return hits



# this check every link["from"] and link["to"] points to a real block ID and it is counts outgoing links for each block
def check_links(blocks, links):
    ids = {b["id"] for b in blocks}
    errors, warnings = [], []
    for L in links:
        if L["from"] not in ids: errors.append(f"Link from '{L['from']}' missing block")
        if L["to"]   not in ids: errors.append(f"Link to '{L['to']}' missing block")

    out = {b["id"]:0 for b in blocks}
    for L in links: out[L["from"]] = out.get(L["from"], 0) + 1
    for bid, cnt in out.items():
        btype = next(b["type"] for b in blocks if b["id"]==bid)
        if btype != "stop" and cnt == 0:
            warnings.append(f"Block '{bid}' has no outgoing links")
    return errors, warnings




# here the real replace between the default placeholder with the real one
def deep_replace(obj, mapping, audit, path="$"):

    if isinstance(obj, dict):
        return {k: deep_replace(v, mapping, audit, f"{path}.{k}") for k, v in obj.items()}
    
    if isinstance(obj, list):
        return [deep_replace(v, mapping, audit, f"{path}[{i}]") for i, v in enumerate(obj)]
    
    if isinstance(obj, str) and obj.startswith("<") and obj.endswith(">"):
        key = obj.strip("<>")
        if key in mapping:
            audit.append({"path": path, "old": obj, "new": mapping[key]})
            return mapping[key]
        else:
            audit.append({"path": path, "old": obj, "new": None, "warning": "unmapped_placeholder"})

    return obj



def build_placeholder_mapping(tenant_cfg: dict) -> dict:
    groups = tenant_cfg.get("groups", {})
    emails = tenant_cfg.get("email_templates", {})
    statuses = tenant_cfg.get("statuses", {})
    catalog = tenant_cfg.get("catalog", {})

    return {
        "GROUP_REC_ID_IT_KNOWLEDGE": groups.get("NETWORK_TEAM_GROUP_RECID", ""),
        "TEMPLATE_ON_SUBMISSION":    emails.get("on_submission", ""),
        "TEMPLATE_ON_APPROVAL":      emails.get("on_approval", ""),
        "TEMPLATE_ON_REJECTION":     emails.get("on_rejection", ""),

        
        "TEMPLATE_NOTIFY_APPROVERS": emails.get("notify_approvers", ""),
        "STATUS_SUBMITTED":          statuses.get("submitted", ""),
        "STATUS_WAITING_FOR_APPROVAL": statuses.get("waiting_for_approval", ""),
        "STATUS_APPROVED":           statuses.get("approved", ""),
        "STATUS_REJECTED":           statuses.get("rejected", ""),
        "STATUS_COMPLETED":          statuses.get("completed", ""),
        "DEFAULT_CATALOG_CATEGORY":  catalog.get("category", ""),
        "DEFAULT_PUBLISHING_MODE":   catalog.get("publishing_mode", "")
    }

