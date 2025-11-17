import json
from pathlib import Path
from loaders import load_input_json, load_tenant_config
from validators import validate_all

def main():
    base = Path("structured")  

    
    offering, form, workflow = load_input_json(
        base / "offering_info.json",    
        base / "form.json",              
        base / "workflow_logic.json"     
    )

    tenant_cfg = load_tenant_config(base / "tenant_config.json")


    issues = validate_all(offering, form, workflow, tenant_cfg)
    if issues:
        print("\n Validation Report:")
        for i in issues:
            print(f"[{i['severity']}] {i['where']}: {i['message']}")
    else:
        print(" All files validated successfully!")


if __name__ == "__main__":
    main()
