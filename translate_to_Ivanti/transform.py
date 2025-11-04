from copy import deepcopy
from typing import Dict, Any, List, Tuple

def _extract_workflow_def(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """Accepts either raw workflow or Ivanti export wrapper; returns the definition subtree."""
    return (workflow.get("WorkflowVersionInformation", {})
                   .get("WorkflowDefinition", {}) or workflow)



def _cleanup_fields(fields: List[Dict[str, Any]]) -> None:
    """Light cleanup to keep output tidy (non-destructive)."""
    for f in fields:
        f.pop("notes", None)
        f.pop("source_docs", None)
        if f.get("validation_constraints") is None:
            f.pop("validation_constraints", None)



def transform_bundle(form: Dict[str, Any],
                     workflow: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Returns:
      - combined_pkg:  Ivanti-style single-file package (CatalogItem + FormFields + Workflow)
      - offering_form: CatalogItem + FormFields only
      - workflow_only: Workflow only
    """
    wf_def   = _extract_workflow_def(workflow)
    template = deepcopy(form.get("template", {}))
    fields   = deepcopy(form.get("fields", []))

    _cleanup_fields(fields)

    combined_pkg = {
        "IvantiPackageVersion": "1.0",
        "CatalogItem": template,
        "FormFields": fields,
        "Workflow": wf_def,
        "Metadata": {
            "exported_by": "Agent B",
            "exported_at": form.get("generated_at"),
            "source": "AI-Automated Generation"
        }
    }

    offering_form = {
        "CatalogItem": template,
        "FormFields": fields
    }

    workflow_only = wf_def  

    return combined_pkg, offering_form, workflow_only
