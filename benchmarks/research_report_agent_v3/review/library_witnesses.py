"""Independent witnessed-edge audit, adapted from our v2.2 reviewer.

Reads actual adjacent tool calls and frozen receipts; never imports the compiler.
"""
from pathlib import Path
from evidence_io import read, digest, file_sha, PREFIX

def audit_library(path, objects, formal_names):
    issues, witness_rows = [], []
    if not Path(path).is_file():
        return {"passed": False, "issues": ["Library file missing"], "path": str(path)}
    library = read(path)
    by_run_id = {obj.manifest.get("run_id"): obj for obj in objects.values() if hasattr(obj, "manifest")}
    if digest({k: v for k, v in library.items() if k != "library_digest"}) != library.get("library_digest"):
        issues.append("Library content digest mismatch")
    for field in ("contracts", "tool_schemas"):
        if digest(library.get(field)) != library.get(field + "_digest"):
            issues.append(field + " digest mismatch")
    for edge in library.get("artifacts", []):
        row = {"motif_id": edge["motif_id"], "from_tool": edge["from_tool"], "to_tool": edge["to_tool"], "witnesses": []}
        certified = digest({k: v for k, v in edge.items() if k not in {"certified_digest", "motif_id"}})
        if certified != edge.get("certified_digest") or edge.get("motif_id") != "receipt-" + certified[:16]:
            issues.append("Certified edge content digest mismatch: " + edge["motif_id"])
        target_contract = library.get("contracts", {}).get(edge["to_tool"], {})
        if target_contract.get("execution") != "workspace_idempotent" or target_contract.get("required_params") != [edge["to_param"]]:
            issues.append("Learned target is not an eligible deterministic single-receipt tool: " + edge["motif_id"])
        if edge["to_tool"].removeprefix(PREFIX) in {"approve_analysis", "approve_presentation", "submit_report_text"}:
            issues.append("Learned edge must not cross a semantic barrier: " + edge["motif_id"])
        train_csv, cert_csv = set(), set()
        for phase, evidence in [("training", e) for e in edge["training_evidence"]] + [("certification", edge["certification_evidence"])]:
            obj = by_run_id.get(evidence["run_id"])
            valid = obj is not None and obj.path.name not in formal_names
            if obj:
                valid &= obj.result.get("business_delivered") is True and obj.manifest.get("mode") == "baseline"
                valid &= obj.group == "training" and obj.manifest.get("experiment_role") == ("train" if phase == "training" else "certification")
                valid &= obj.manifest.get("contracts_digest") == library.get("contracts_digest")
                valid &= bool(evidence.get("witnesses")) and evidence.get("case_id") == obj.manifest.get("case_id")
                valid &= evidence["events_sha256"] == file_sha(obj.path / "agent-events.jsonl")
                (train_csv if phase == "training" else cert_csv).add(obj.source_hashes.get("data.csv"))
                by_call = {r["call_id"]: r for r in obj.rows}
                for witness in evidence.get("witnesses", []):
                    a, b = by_call.get(witness["from_call_id"]), by_call.get(witness["to_call_id"])
                    valid &= bool(a and b and a["success"] and b["success"] and a["origin"] == b["origin"] == "llm")
                    if a and b:
                        valid &= (a["tool"] == edge["from_tool"] and b["tool"] == edge["to_tool"] and b["step"] == a["step"] + 1
                                  and digest(a["output"]) == witness["from_output_sha256"] and digest(b["arguments"]) == witness["to_arguments_sha256"]
                                  and b["arguments"] == {edge["to_param"]: a["output"].get(edge["from_field"])}
                                  and edge["to_tool"].removeprefix(PREFIX) in a["output"].get("_provenance", {}).get("authorized_tools", []))
            row["witnesses"].append({"phase": phase, "run_id": evidence["run_id"], "valid": bool(valid)})
            if not valid:
                issues.append(f"Invalid/missing {phase} witness: {edge['motif_id']} {evidence['run_id']}")
        if len(train_csv) < 2 or len(cert_csv) != 1 or train_csv & cert_csv or None in train_csv | cert_csv:
            issues.append("Need two independent training CSVs and independent confirmation: " + edge["motif_id"])
        witness_rows.append(row)
    used_csv = set(library.get("training_csv_sha256", [])) | {library.get("certification_csv_sha256")}
    motif_by_id = {edge["motif_id"]: edge for edge in library.get("artifacts", [])}
    for name in formal_names:
        obj = objects.get(name)
        if not obj or not hasattr(obj, "source_hashes"):
            continue
        if obj.source_hashes.get("data.csv") in used_csv:
            issues.append("Formal input reused training/cert CSV: " + name)
        if obj.manifest.get("mode") == "execute":
            if obj.manifest.get("library_digest") != library.get("library_digest"):
                issues.append("Formal execute library differs: " + name)
            by_call = {r["call_id"]: r for r in obj.rows}
            for attempt in getattr(obj, "audit_rows", []):
                if attempt.get("kind") != "motif_bypass_attempt":
                    continue
                edge, before = motif_by_id.get(attempt.get("motif_id")), by_call.get(attempt.get("after_call_id"))
                if not edge or not before or (attempt.get("certified_digest") != edge["certified_digest"]
                    or before["tool"] != edge["from_tool"] or attempt["tool"] != edge["to_tool"]
                    or attempt["arguments"] != {edge["to_param"]: (before["output"] or {}).get(edge["from_field"])}):
                    issues.append("Actual bypass is not a learned witnessed edge: " + name + "/" + attempt.get("call_id", "?"))
    return {"path": str(path), "file_sha256": file_sha(path), "library_digest": library.get("library_digest"),
            "passed": not issues, "issues": issues, "edge_count": len(witness_rows), "edges": witness_rows,
            "meaning": "Tools and authorized successors are manually designed; the compiler records independently witnessed receipt transfers, not autonomous workflow discovery or formal proof."}
