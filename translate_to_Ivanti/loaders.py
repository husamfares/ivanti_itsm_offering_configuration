import json
from pathlib import Path
from typing import Dict , Tuple, Any

class LoadError(Exception):
    pass


def read_json(path: Path) -> Dict[str , Any]:
    if not path.exists():
        raise LoadError(f"File not found: {path}")

    try:
        with path.open("r" , encoding="utf-8") as f:
            data = json.load(f)

    except json.JSONDecodeError as e:
        raise LoadError(f"Invalid JSON in {path}: {e}") from e
    
    if not isinstance(data, dict):
        raise LoadError(f"Top-level JSON must be an object in {path}")
    
    return data



def load_input_json(offering_path : str | Path ,
                     form_path : str | Path ,
                       workflow_path: str| Path,
                       fields_path: str | Path | None = None)-> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    
    offering = read_json(Path(offering_path))
    form = read_json(Path(form_path))
    workflow = read_json(Path(workflow_path))

    # Optional: separate fields json (if your pipeline ever splits it)
    if fields_path is not None:
        fields_obj = read_json(Path(fields_path))
        # if present, merge into form safely
        if "fields" in fields_obj and isinstance(fields_obj["fields"], list):
            form["fields"] = fields_obj["fields"]

    # Light shape checks (fail fast, but still simple)
    if "template" not in form or "fields" not in form:
        raise LoadError("form.json must contain 'template' and 'fields' keys.")
    if not isinstance(form["fields"], list):
        raise LoadError("form.fields must be a list.")

    if "blocks" not in workflow or "links" not in workflow:
        raise LoadError("workflow.json must contain 'blocks' and 'links' keys.")
    
    return offering, form, workflow

        

# json file where it is go "they act as bridge between the logic and Ivanti system"

def load_tenant_config(tenant_config_path: str | Path) -> Dict[str , Any]: 
    """
    Load tenant config with IDs/templates used later in mapping.
    Must contain: 'groups' and 'email_templates'.
    """

    config = read_json(Path(tenant_config_path))

    if "groups" not in config or "email_templates" not in config:
        raise LoadError("tenant_config.json must contain 'groups' and 'email_templates' objects.")
    
    return config

