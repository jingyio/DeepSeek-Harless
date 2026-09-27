"""Strong no-model baseline: retrieve all scoped evidence and stop at judgment.

This baseline is deliberately generic across all cases. It has the
same read/aggregation access as the Agent and never invents a conclusion.
"""

from __future__ import annotations

import argparse
import json
import os

from benchmarks.meeting_decision_chain_v1 import mock_apps_server as apps


def run(case: str) -> dict:
    os.environ["SSS_MEETING_CASE"] = case
    event = apps.read_change(f"event:{case}:w39")
    experiment_id = event["experiment_id"]
    pinned = apps.pin_object(experiment_id)
    source = apps.read_pinned_object(pinned["source_id"])
    metric = source["value"]["metric_contract"]
    metrics = apps.aggregate_pinned_experiment(
        source["value"]["dataset_id"], metric["allowed_groups"])
    prior = apps.pin_object(event["previous_experiment_id"])
    if prior["version_sha256"] != event["previous_version_sha256"]:
        raise ValueError("prior experiment version differs from the event")
    prior_source = apps.read_pinned_object(prior["source_id"])
    prior_metrics = apps.aggregate_pinned_experiment(
        prior_source["value"]["dataset_id"], metric["allowed_groups"])
    claims = apps.find_dependent_claims(experiment_id)["claims"]
    related = []
    for claim in claims:
        for key in ("note_id", "annotation_id"):
            other = apps.pin_object(claim[key])
            related.append(apps.read_pinned_object(other["source_id"]))
    return {"case": case, "event_version": event["event_version"],
            "experiment_version": pinned["version_sha256"],
            "metric": metrics, "prior_metric": prior_metrics,
            "related_sources": related,
            "decision": "semantic_review_required", "model_requests": 0,
            "complete_research_decision": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=sorted(apps.CASE_IDS))
    args = parser.parse_args()
    print(json.dumps(run(args.case), ensure_ascii=False, indent=2))
