import json
from pathlib import Path
from loaders import load_input_json, load_tenant_config
from validators import validate_all
from transform import transform_bundle  

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
        print("\n🧾 Validation Report:")
        for i in issues:
            print(f"[{i['severity']}] {i['where']}: {i['message']}")
    else:
        print("✅ All files validated successfully!")



    _, offering_form, workflow_only = transform_bundle(form, workflow)

    out_dir = base
    out_dir.mkdir(parents=True, exist_ok=True)



    with (out_dir / "form.json").open("w", encoding="utf-8") as f:
        json.dump(offering_form, f, ensure_ascii=False, indent=2)

    with (out_dir / "workflow.json").open("w", encoding="utf-8") as f:
        json.dump(workflow_only, f, ensure_ascii=False, indent=2)


    print(" Wrote:", out_dir / "form.json")
    print(" Wrote:", out_dir / "workflow.json")

if __name__ == "__main__":
    main()
