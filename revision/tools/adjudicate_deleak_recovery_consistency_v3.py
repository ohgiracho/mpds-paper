from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "analysis" / "deleak_recovery_blind_format_adjudication_v2.json"
    output = root / "analysis" / "deleak_recovery_blind_adjudication_v3.json"
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite v3 recovery adjudication: {output}")
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("status") != "PASS" or len(data.get("rows", [])) != 18:
        raise RuntimeError("v2 blinded format adjudication is incomplete")
    corrected = []
    for row in data["rows"]:
        labels = {feature["feature_id"]: feature["label"] for feature in row["features"]}
        if row["case_id"] == 8 and row["rubric_derived_overall_recovery"] == "explicit_target_like":
            # The frozen Case 8 feature-4 definition integrates features 1–3.
            # Thus a final design without an explicitly porous/permeable wall
            # cannot be counted as full target recovery, even if the model
            # called the combined architecture explicit.
            required = (
                "hollow_cube_like_unit",
                "porous_or_permeable_wall",
                "graphene_network_integration",
                "combined_cube_wall_graphene_architecture",
            )
            if any(labels[name] != "explicit_target_like" for name in required):
                row["rubric_derived_overall_recovery"] = "partial_general"
                row["case8_feature_consistency_correction"] = True
                row["overall_was_corrected"] = row["model_overall_recovery"] != "partial_general"
                corrected.append(row["audit_id"])
        row.setdefault("case8_feature_consistency_correction", False)
    data["status"] = "PASS_POST_UNBLIND_KEY_INDEPENDENT_CONSISTENCY_CORRECTION"
    data["source_adjudication"] = str(source.relative_to(root)).replace("\\", "/")
    data["case8_consistency_rule"] = "Full target recovery requires all four frozen Case 8 target features to be explicit, because the combined feature explicitly integrates features 1–3."
    data["case8_consistency_corrected_audit_ids"] = corrected
    data["overall_corrections"] = sum(row["overall_was_corrected"] for row in data["rows"])
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": data["status"], "rows": len(data["rows"]), "case8_consistency_corrections": len(corrected), "overall_corrections": data["overall_corrections"], "feature_labels_changed": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
