import os,json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from datetime import datetime, timezone


load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")


APPROVED = {
  "offering": [
    'exact:"Catalog Item Name"',
    'exact:"Description"',
    'exact:"Category"',
    'exact:"Self Service Category"',
    'exact:"Delivery Target"',
    'exact:"User Ability to Cancel"',
    'exact:"User Ability to Edit"',
    'exact:"Publish to"',
    "Overview", "Purpose", "Summary", "Request Offering",
    "Description :", "Category :",
    "Self Service category",
    "SLA business days delivery timeframe",
    "publishing scope visibility",
    "audience scope",
    "All users specific groups specific users"
  ],
  "fields": [
    'exact:"Field internal name"',
    'exact:"Field display name"',
    'exact:"Field description"',
    'exact:"Field type"',
    'exact:"Required"',
    'exact:"Read-only"',
    'exact:"Default value"',
    'exact:"Auto Fill"',
    'exact:"Required expression"',
    'exact:"Visibility expression"',
    'exact:"Validation list RecID"',
    'exact:"Validation constraints"',
    'exact:"Sequence/Order"',
    
    'exact:"Submit on behalf"',
    'exact:"Employee ID"',
    'exact:"Service Type"',
    'exact:"Domain Name"',
    'exact:"Location"',
    
    "Drop down list options choices values",
    "Enable Port Disable Port",
    "Riyadh - Digital City Riyadh - Nemyar district Jeddah Makkah Yanbu Haql Tabuk Arar Jubail Dammam Sulyyil",
    
    "required when",
    "visible when",
    "depends on"
  ],
  "workflow": [
    "Get Approval vote0007 approval exits approved denied cancelled timedout",
    "Workflow blocks start stop update notification task quick action quickaction",
   
    "approver Line Manager related manager",
    "approver group IT Knowledge group",
    "approval rule all any majority",
    "timeout hours reminder hours",
    
    "Email notifications on submission",
    "Email notifications on approval",
    "Email notifications on rejection",
    "Status transitions changes",
    "Change Status to Waiting for Approval",
    "Approved Approval Rejected"
  ]
}
MAX_FOLLOWUPS = 2


def load_retriever(kb_path: str, collection: str = "ivanti_kb", k: int = 12):
    vs = Chroma(
        collection_name= collection,
        embedding_function=OpenAIEmbeddings(model="text-embedding-3-small"),
        persist_directory=kb_path
    )
    return vs.as_retriever(
        search_type="mmr", 
        search_kwargs={"k": k, "fetch_k": 80, "lambda_mult": 0.2}
        )


def get_context(retriever, queries, max_docs=20):
    docs = []
    for q in queries:
        res = retriever.invoke(q)
        docs.extend(res)

    uniq, seen = [], set()
    for d in docs:
        src = d.metadata.get("source")
        page = d.metadata.get("page")
        key = (src, page, (d.page_content or "")[:60])
        if key not in seen:
            seen.add(key)
            uniq.append(d)
        if len(uniq) >= max_docs:
            break

    parts = [] # so this for make header or explain number page as example for the LLM later
    for d in uniq:
        src = d.metadata.get("source")
        page = d.metadata.get("page")
        header = f"[SOURCE: {src} | PAGE: {page}]"
        parts.append(header + "\n" + d.page_content)
    return "\n\n---\n\n".join(parts)


    

def check_gap_result(llm , bucket ,context_v1):
    prompt = f"""
    You will NOT extract the final JSON now.
    From the context below, decide if information is missing for the {bucket} schema.

    Return JSON:
    {{
    "enough": true|false,
    "why": "short reason",
    "followups": ["q1","q2"]  // at most {MAX_FOLLOWUPS}, chosen ONLY from this allowed set:
    }}
    Allowed: {APPROVED[bucket]}

    Context:
    {context_v1}

    """

    response = llm.invoke([{"role":"user" , "content":prompt}]).content

    try:
        obj = json.loads(response)
    except:
        obj = {"enough": True, "why": "parse_error", "followups": []}
    

    allowed = set(APPROVED[bucket])
    obj["followups"] = [q for q in obj.get("followups", []) if q in allowed][:MAX_FOLLOWUPS]
    return obj



def complete_extract_data(retriever, base_queries , llm , bucket, system_prompt, user_prompt):

    context = get_context(retriever ,base_queries , max_docs=20)
    if len(context) < 200:  
        gap = {"enough": False, "why": "context too short", "followups": APPROVED[bucket][:MAX_FOLLOWUPS]}
    else:
        gap = check_gap_result(llm, bucket , context)

    
    if not gap.get("enough") and gap.get("followups"):
        context2_iteration = get_context(retriever , gap["followups"], max_docs=10)
        final_context = context +  ("\n\n---\n\n" + context2_iteration)
    else:
        final_context = context

    
    messages= [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt.format(context=final_context)}
    ]

    raw = llm.invoke(messages).content
    return raw, {"followup_used": (not gap.get("enough")) and bool(gap.get("followups")),
                 "why": gap.get("why"), "followups": gap.get("followups", [])}
        



def json_only(text: str):
    """Extract JSON object/array from an LLM message that might contain fences."""
    t = text.strip()
    
    if t.startswith("```"):
        t = t.strip("`")
    
    if t.lstrip().startswith(("{", "[")):
        return json.loads(t[t.find("{"):t.rfind("}")+1])
    
    start = t.find("{"); end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(t[start:end+1])
    raise ValueError("Model did not return JSON.")



def minimal_normalize_offering(offering: dict) -> dict:
    # set default data if those missing values
    offering.setdefault("publishing_scope", {"mode": "", "groups": [], "users": []})
    offering.setdefault("user_permissions", {"can_cancel": False, "can_edit": False})

    
    dt = offering.get("delivery_target_days")
    if isinstance(dt, str):
        import re
        m = re.search(r"\d+", dt)
        offering["delivery_target_days"] = int(m.group()) if m else 0  # check if it return text move it to int on delivery_target_days
        offering["delivery_target_days"] = 0

    
    # here to validate if there missing value put them into missing list
    missing = [k for k in ("catalog_item_name", "description", "category")
               if not (offering.get(k) or "").strip()]
    if missing:
        offering["missing_fields"] = missing
    else:
        offering.pop("missing_fields", None)

    return offering




def create_structure_json(kb_path="kb/chroma_ivanti", out_dir="structured", k=10, model="gpt-4o-mini"):
    
    assert os.path.exists(kb_path), f"KB not found at {kb_path}. Run ingest first."
    os.makedirs(out_dir , exist_ok=True)

    llm_brain = ChatOpenAI(model=model , temperature=0)

    retriever_data = load_retriever(kb_path, "ivanti_kb", k=k)



    OFFERING_SYS = """You are an ITSM analyst.
    Return ONLY valid JSON matching this schema without extra text:

    {
    "catalog_item_name": "string",
    "description": "string",
    "category": "string",
    "delivery_target_days": 0,
    "user_permissions": { "can_cancel": false, "can_edit": false },
    "publishing_scope": { "mode": "all_users|groups|users", "groups": [], "users": [] }
    }

    Rules:
    - Use ONLY facts explicitly in Context (table rows, labels like "Catalog Item Name", "Description", "Category").
    - These keys are MANDATORY if present anywhere in Context: catalog_item_name, description, category.
    • If a BRD table cell or labeled line exists, extract it verbatim (strip surrounding quotes/colons).
    • Prefer the value in the BRD “Request Offering”/“Overview” section over narrative text if both exist.
    • If truly absent in Context, leave "" (do NOT invent).
    - Normalize "delivery_target_days":
      • If the context says like "1 business days", extract the integer 1.
      • If the unit is "business day(s)" or "working day(s)", still return just the integer count.
      • If absent, set 0.
    - After extraction, these must not be empty when present anywhere in Context: catalog_item_name, description, category.
    - You MUST extract non-empty values for: catalog_item_name, description, category whenever they appear ANYWHERE in Context. Search BOTH label:value rows AND narrative sections like “Overview” or “Request Offering”. If multiple candidates exist, prefer BRD tables/labels over narrative.
    - If the value is found in narrative only, still return it; do NOT leave "".
    - When the BRD or context contains an “Overview” or “Request Offering” section describing the purpose or summary of the request, use that paragraph or sentence as the description.
    - If the “Category” appears under “Self Service Category”, “Category :”, or similar labels, extract its exact value. Do not leave it empty if it exists anywhere in the context.
    - If the Category or Description is missing after extraction, include a `"missing_fields"` array listing any keys that were not found, so they can be validated later.
    - “Description” may come from “Overview”, “Request Offering”, “Purpose”, or “Summary” narrative. Prefer offering-specific narrative over generic catalog narration if both exist.
    - “Category” may appear as “Category”, “Self Service Category”, “Category :”, or inside catalog tables. If any exists, extract the exact value.
    - If after extraction either “description” or “category” is still empty, add a top-level "missing_fields": ["description", ...] listing exactly the missing keys.

    """


    OFFERING_USER = """You will extract OFFERING metadata only as JSON.

    Context:
    {context}

    Instructions:
    - If description/category appear only in “Overview”, “Request Offering”, “Purpose”, or “Summary”, extract those values.
    - Return JSON only, no extra text.
    """




    FIELDS_SYS = """You are an ITSM architect.
    Return ONLY valid JSON matching this schema:

    {
    "fields": [
        {
        "internal_name": "string",
        "display_name": "string",
        "description": "string",
        "field_type": "text|textarea|combo|checkbox|datetime|fileupload|label|list|swfupload",
        "required": true,
        "read_only": false,
        "default_value": null,
        "auto_fill_expression": null,
        "required_expression": null,
        "visibility_expression": null,
        "validation_list_recid": null,
        "validation_constraints": null,
        "sequence_number": 1,
        "options": null,
        "notes": null
        }
    ]
    }

    Authoritative rules (MUST APPLY when the BRD states them):
    1) Identity auto-fills (read-only unless the BRD explicitly says otherwise). Use this exact pattern, controlled by the Submit on behalf flag:
    full_name     -> $( submit_on_behalf ? LookupUserField(employee_id,'FullName')   : CurrentUser('FullName') )
    login_id      -> $( submit_on_behalf ? LookupUserField(employee_id,'LoginID')    : CurrentUser('LoginID') )
    email         -> $( submit_on_behalf ? LookupUserField(employee_id,'Email')      : CurrentUser('Email') )
    line_manager  -> $( submit_on_behalf ? LookupUserField(employee_id,'ManagerName'): CurrentUser('ManagerName') )
    phone_number  -> $( submit_on_behalf ? LookupUserField(employee_id,'Phone')      : CurrentUser('Phone') )
    extension     -> $( submit_on_behalf ? LookupUserField(employee_id,'Extension')  : CurrentUser('Extension') )
    Read-only policy:
        - Set read_only=true for: full_name, login_id, email, line_manager
        - Set read_only=false for: phone_number, extension
        All six remain NOT required unless the BRD explicitly marks them required.


    2) Employee ID gating (from BRD): employee_id is visible and required only when submit_on_behalf == true
    employee_id.required_expression   = $( submit_on_behalf == true )
    employee_id.visibility_expression = $( submit_on_behalf == true )

    3) Domain Name visibility (from BRD wording):
    If the BRD shows Domain Name is only relevant for a specific service type (e.g., “Create in Active Directory”),
    then for this offering set: domain_name.visibility_expression = $(false)
    and add notes explaining it is hidden for non-AD scenarios.

    4) Options for combo fields:
    - If a BRD table lists choices, return them in "options": ["a","b",...], preserving order and not inventing values.

    5) General rules:
    - Use ONLY facts from context; prefer BRD tables/labels exactly as written.
    - Normalize internal_name keys as snake_case where obvious: Submit on behalf -> submit_on_behalf; Employee ID -> employee_id; Full Name -> full_name; Login ID -> login_id; Line Manager -> line_manager; Phone Number -> phone_number.
    - sequence_number must be contiguous starting at 1.
    - If a value is not stated, leave it empty/null/0. Do not invent RecIDs.
    - If a field has required_expression, set "required": false (the expression governs requirement). Do NOT set both required=true and a required_expression for the same field.


    Ensure the above identity/gating/visibility rules are applied when the BRD contains those requirements. If they appear in narrative text (“Auto Filled”, “required if Submit on behalf is checked”), you MUST encode them as the expressions above.
    """


    FIELDS_USER = """Context:
    {context}

    Extract FORM FIELDS now as JSON."""


    WORKFLOW_SYS = """You are an ITSM workflow designer.
    Return ONLY valid JSON matching this schema:

    {
    "blocks": [
        {
        "id": "B1",
        "type": "start|stop|vote0007|update|notification|task|quickaction|if|switch|join",
        "title": "string",
        "properties": {},
        "exits": [ {"title": "ok|approved|denied|cancelled|timedout|noapprovers|failed", "condition": ""} ]
        }
    ],
    "links": [ {"from": "B1", "exit": "ok", "to": "B2"} ],
    "notifications": [ {"event":"on_submission|on_approval|on_rejection","template":"<TEMPLATE_NAME_OR_ID>"} ],
    "status_transitions": [
    {"from":"submitted","on":"approved","to":"Approved"},
    {"from":"submitted","on":"denied","to":"Approval Rejected"}
    ]
    }

    Rules (apply when present in BRD; otherwise use placeholders where IDs are unknown):

    - Exit policy by block type:
    • vote0007 exits MUST be exactly: approved, denied, cancelled, timedout, noapprovers.
    • update/task blocks MAY use: ok and failed (where applicable in Ivanti).
    • start uses ok; stop has no exits; notification uses ok.

    - On submission:
    1) Add an email notification to requester (notifications[] with event=on_submission and a template placeholder).
    2) Add an update block that sets status to "Waiting for Approval" ... (Start → Notify → Update).

    - Approvals (two stages in order):
    1) Line Manager ... related_manager
    2) IT group ... group_recid "<GROUP_REC_ID_IT_KNOWLEDGE>"

    - For the second vote0007 block, add links for exits: denied, cancelled, timedout, noapprovers → Update("Approval Rejected") → Notify(on_rejection) → Stop.

    - After approvals:
    • On final approval path (after second approval approved): update status "Approved" BEFORE sending the approval notification.
    • On any rejection/cancellation/timeout/noapprovers path: update status "Approval Rejected" BEFORE sending the rejection notification.
    • Never send notifications before the corresponding status update.

    - Update blocks MUST include properties: {"status":"<exact target>"} where titles indicate the target:
    • "Waiting for Approval" → {"status":"Waiting for Approval"}
    • "Approved" → {"status":"Approved"}
    • "Approval Rejected" → {"status":"Approval Rejected"}

    - Add explicit notification blocks in the graph:
    • notify_submission AFTER Start (before Waiting for Approval)
    • notify_approval AFTER status "Approved"
    • notify_rejection AFTER status "Approval Rejected"
    Name them clearly and wire them as separate blocks with exit "ok".

    - Line Manager approval block must include:
    "properties": {"approvers":{"mode":"related_manager","relation":"line_manager"}}
    - IT Group approval block must include:
    "properties": {"approvers":{"mode":"group","group_recid":"<GROUP_REC_ID_IT_KNOWLEDGE>"}}


    - Status transitions must cover all workflow exits that lead to “Approved” or “Approval Rejected”.
    Include transitions for: approved, denied, cancelled, timedout, noapprovers.
    Example:
    [   
        {"from":"submitted","on":"approved","to":"Approved"},
        {"from":"submitted","on":"denied","to":"Approval Rejected"},
        {"from":"submitted","on":"cancelled","to":"Approval Rejected"},
        {"from":"submitted","on":"timedout","to":"Approval Rejected"},
        {"from":"submitted","on":"noapprovers","to":"Approval Rejected"}
    ]




    Required order:
    submission → notify(on_submission) → update("Waiting for Approval") → vote0007 LM → vote0007 IT →
    (approved) update("Approved") → notify(on_approval) → stop
    (denied/cancelled/timedout/noapprovers) update("Approval Rejected") → notify(on_rejection) → stop

    - Ensure every path is reachable from start, acyclic, and ends in a stop block.
    - Use ONLY facts from context; do not invent real RecIDs. Keep placeholders for tenant mapping.
    - Match exit spellings exactly: approved, denied, cancelled, timedout, noapprovers.
    """




    WORKFLOW_USER = """Context:
    {context}

    Extract WORKFLOW LOGIC now as JSON."""


    base_offering = [
        'exact:"Catalog Item Name"',
        'exact:"Description"',
        'exact:"Category"',
        'exact:"Self Service Category"', 
        'exact:"Delivery Target"',
        'exact:"User Ability to Cancel"',
        'exact:"User Ability to Edit"',
        'exact:"Publish to"',
        
        "Self Service category",
        "publishing scope visibility",
        "audience scope",
        "SLA business days delivery timeframe",
        
        "Request Offering",
        "Overview", "Purpose", "Summary",
        "Description :", "Category :",
        
        "Requester Details", "Request Details",
        
        "All users specific groups specific users"
    ]



    base_fields = [
        
        'exact:"Field internal name"',
        'exact:"Field display name"',
        'exact:"Field description"',
        'exact:"Field type"',
        'exact:"Required"',
        'exact:"Read-only"',
        'exact:"Default value"',
        'exact:"Auto Fill"',
        'exact:"Required expression"',
        'exact:"Visibility expression"',
        'exact:"Validation list RecID"',
        'exact:"Validation constraints"',
        'exact:"Sequence/Order"',
        
        "Requester Details",
        "Request Details",
        
        'exact:"Submit on behalf"',
        'exact:"Employee ID"',
        'exact:"Full Name"',
        'exact:"Login ID"',
        'exact:"Email"',
        'exact:"Line Manager"',
        'exact:"Phone Number"',
        'exact:"Extension"',
        'exact:"Service Type"',
        'exact:"Domain Name"',
        'exact:"Label Number"',
        'exact:"Location"',
        'exact:"Building Name"',
        'exact:"Office Number"',
        'exact:"Notes"',
        'exact:"Attachments"',
        
        "Drop down list options choices values",
        "Enable Port Disable Port",
        "Riyadh - Digital City",
        "Jeddah Makkah Yanbu Haql Tabuk Arar Jubail Dammam Sulyyil",
        
        "required when",
        "visible when",
        "depends on",
    ]

    
    base_workflow = [
        
        "Workflow",
        "First Approval",
        "Second Approval",
        "Approval Result",
        "IT Team will be assigned",
        "Fulfill",
        
        "Workflow blocks start stop update notification if switch join wait task quick action quickaction",
        "Get Approval vote0007 approval exits approved denied cancelled timedout",
        "Status transitions changes",
        "Email notifications on submission approval rejection",
        
        "approver Line Manager related manager",
        "approver group IT Knowledge group",
        "approval rule all any majority",
        "timeout hours reminder hours",
        
        "Change Status to Waiting for Approval",
        "Approved",
        "Approval Rejected",
        
        "Notify Requester of Submission",
        "ticket number email",
        "Change Status to Waiting for Approval",
        "Update status Approved",
        "Update status Approval Rejected"
    ]



    

    offering_raw, offering_meta = complete_extract_data(
        retriever=retriever_data,
        base_queries=base_offering,
        llm=llm_brain,
        bucket="offering",
        system_prompt=OFFERING_SYS,
        user_prompt=OFFERING_USER,
    )
    

    offering = minimal_normalize_offering(json_only(offering_raw))

    with open(os.path.join(out_dir, "offering_info.json"), "w", encoding="utf-8") as f:
        json.dump(offering, f, ensure_ascii=False, indent=2)




    fields_row, field_meta = complete_extract_data(
        retriever= retriever_data,
        base_queries= base_fields,
        llm= llm_brain,
        bucket="fields",
        system_prompt= FIELDS_SYS,
        user_prompt= FIELDS_USER
    )

    fields = json_only(fields_row)



    if "fields" in fields:
        for i, item in enumerate(fields["fields"], start=1):
            item["sequence_number"] = i
            
            if item.get("required_expression"):
                item["required"] = False
            
            if isinstance(item.get("options"), list):
                seen, dedup = set(), []
                for v in item["options"]:
                    if v not in seen:
                        seen.add(v)
                        dedup.append(v)
                item["options"] = dedup
    
    with open(os.path.join(out_dir , "fields_table.json"), "w" , encoding="utf-8") as f:
        json.dump(fields , f ,  ensure_ascii=False, indent=2)

    

    workflow_row , workflow_meta = complete_extract_data(
        retriever= retriever_data,
        base_queries= base_workflow,
        llm= llm_brain,
        bucket="workflow",
        system_prompt= WORKFLOW_SYS,
        user_prompt= WORKFLOW_USER    
    )
    
    workflow = json_only(workflow_row)

    # validation if the LLM fail to get notification
    workflow.setdefault("notifications", [])
    needed = {
        "on_submission": "<TEMPLATE_ON_SUBMISSION>",
        "on_approval": "<TEMPLATE_ON_APPROVAL>",
        "on_rejection": "<TEMPLATE_ON_REJECTION>"
    }
    have = {n.get("event"): n for n in workflow["notifications"]}
    for evt, tmpl in needed.items():
        if evt not in have:
            workflow["notifications"].append({"event": evt, "template": tmpl})


    # those like end of the book information
    workflow["version"] = "1.0.0"
    workflow["generated_at"] = datetime.now(timezone.utc).isoformat()
    workflow["source_docs"] = ["Request Offering BRD.docx"]


    with open(os.path.join(out_dir, "workflow_logic.json"), "w", encoding="utf-8") as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)



    form = {
    "template": offering,                      
    "fields": fields.get("fields", []),        
    "delivery_items": None,                    
    "version": "1.0.0",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "source_docs": ["Request Offering BRD.docx"]
    }

    with open(os.path.join(out_dir, "form.json"), "w", encoding="utf-8") as f:
        json.dump(form, f, ensure_ascii=False, indent=2)



    # so this debugging file when LLM ask it self if there missing values from query result on function complete_extract_data
    meta = {"offering_followups": offering_meta, "fields_followups": field_meta, "workflow_followups": workflow_meta}
    with open(os.path.join(out_dir, "_followups_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)



    print("Wrote:", os.path.join(out_dir, "offering_info.json"))
    print("Wrote:", os.path.join(out_dir, "fields_table.json"))
    print("Wrote:", os.path.join(out_dir, "workflow_logic.json"))    
    print("Wrote:", os.path.join(out_dir, "form.json"))


if __name__ == "__main__":
    create_structure_json(
        kb_path="kb/chroma_ivanti",
        out_dir="structured",
        k=10,
        model="gpt-4o-mini"
    )
