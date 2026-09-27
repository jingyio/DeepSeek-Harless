"""Evidence-ledger motif for a bounded, locally sourced research question.

Retrieval and citation checks are structural operations. Synthesis is an
explicit semantic gap; the runtime does not manufacture conclusions.
"""

from __future__ import annotations

import re
from math import log1p
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from src.graph.runtime import Evidence, Motif, Node, SemanticGap


def _collect(state: Mapping[str, Evidence]) -> dict[str, Any]:
    from pypdf import PdfReader

    root = Path(state["source_dir"].value).resolve(strict=True)
    if not root.is_dir():
        raise SemanticGap("invalid_source", "Source path must be a directory")
    records: list[dict[str, Any]] = []
    sources = sorted(path for path in root.iterdir() if path.suffix.lower() in {".pdf", ".md", ".txt"})
    if len(sources) > 20:
        raise SemanticGap("scope_limit", "Select at most 20 sources for this first prototype")
    for path in sources:
        if path.is_symlink() or path.stat().st_size > 10_000_000:
            raise SemanticGap("unsafe_source", f"Source requires review: {path.name}")
        raw_digest = sha256(path.read_bytes()).hexdigest()
        if path.suffix.lower() == ".pdf":
            pages = PdfReader(path).pages
            for number, page in enumerate(pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    records.append({"source": path.name, "page": number, "text": text, "source_sha256": raw_digest})
        else:
            text = path.read_text(encoding="utf-8")
            if text.strip():
                records.append({"source": path.name, "page": 1, "text": text, "source_sha256": raw_digest})
    if not records:
        raise SemanticGap("empty_sources", "No readable source text was found")
    return {"pages": records}


def _dedupe(state: Mapping[str, Evidence]) -> dict[str, Any]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in state["pages"].value:
        normalized = re.sub(r"\s+", " ", page["text"]).strip()
        digest = sha256(normalized.encode("utf-8")).hexdigest()
        if digest not in seen:
            seen.add(digest)
            unique.append({**page, "page_sha256": digest})
    return {"unique_pages": unique}


def _select(state: Mapping[str, Evidence]) -> dict[str, Any]:
    terms = [term.casefold().strip() for term in state["terms"].value if term.strip()]
    if not terms:
        raise SemanticGap("missing_query_terms", "Provide searchable terms, including English terms for English references")
    per_source_limit = state.get("per_source_limit", Evidence(4, "default_limit")).value
    if not isinstance(per_source_limit, int) or not 1 <= per_source_limit <= 12:
        raise SemanticGap("invalid_retrieval_limit", "Per-source evidence limit must be 1 to 12")
    pages = state["unique_pages"].value
    allowed = state.get("source_allowlist", Evidence(None, "default_scope")).value
    if allowed is not None:
        known = {page["source"] for page in pages}
        if not isinstance(allowed, list) or not allowed or any(source not in known for source in allowed):
            raise SemanticGap("invalid_source_scope", "Source allowlist must name existing sources")
        pages = [page for page in pages if page["source"] in allowed]
    normalized_pages = [re.sub(r"\s+", " ", page["text"]) for page in pages]
    frequency = {term: sum(term in text.casefold() for text in normalized_pages) for term in terms}
    weight = {term: log1p((len(pages) + 1) / (frequency[term] + 1)) for term in terms}
    scored: list[dict[str, Any]] = []
    for page, normalized in zip(pages, normalized_pages):
        lower = normalized.casefold()
        if not any(term in lower for term in terms):
            continue
        # The downstream synthesis budget keeps at most 750 characters per page.
        # Score exactly that size here so a winning passage is never truncated
        # after verification, and overlap windows enough to retain conditions
        # that cross the former 900/750-character boundary.
        windows = [normalized[start : start + 750] for start in range(0, len(normalized), 250)]
        def rank(chunk: str) -> tuple[float, int, float]:
            folded = chunk.casefold()
            distinct = sum(term in folded for term in terms)
            weighted_hits = sum(weight[term] * min(folded.count(term), 2) for term in terms)
            letters = sum(char.isalpha() for char in chunk)
            return weighted_hits, distinct, letters / max(len(chunk), 1)
        snippet = max(windows, key=rank)
        weighted_hits, distinct, prose_ratio = rank(snippet)
        score = round(weighted_hits * 10 + distinct * 2 + prose_ratio * 5, 2)
        scored.append({
            "source": page["source"], "page": page["page"],
            "source_sha256": page["source_sha256"], "page_sha256": page["page_sha256"],
            "score": score, "snippet": snippet,
            "evidence_kind": page.get("evidence_kind", "source_passage"),
            **({"derived_from_pages": page["derived_from_pages"]}
               if "derived_from_pages" in page else {}),
        })
    scored.sort(key=lambda item: (-item["score"], item["source"], item["page"]))
    if not scored:
        raise SemanticGap("no_matching_evidence", "No source page matched the query terms; broaden or revise them")
    # Numeric summaries are exact, source-bound structural results. Reserve one
    # matching summary per JSON source before raw records fill the retrieval
    # budget, so repeated high-scoring records cannot hide the aggregate.
    derived_by_source: dict[str, dict[str, Any]] = {}
    for item in scored:
        if item.get("evidence_kind") == "derived_numeric_summary":
            derived_by_source.setdefault(item["source"], item)
    priority = sorted(derived_by_source.values(),
                      key=lambda item: (-item["score"], item["source"], item["page"]))[:4]
    ordered = priority + [item for item in scored if item not in priority]
    selected: list[dict[str, Any]] = []
    per_source: dict[str, int] = {}
    for item in ordered:
        if per_source.get(item["source"], 0) >= per_source_limit:
            continue
        selected.append(item)
        per_source[item["source"]] = per_source.get(item["source"], 0) + 1
        if len(selected) == 12:
            break
    return {"evidence_candidates": selected}


def _verify(state: Mapping[str, Evidence]) -> dict[str, Any]:
    root = Path(state["source_dir"].value).resolve(strict=True)
    lookup = {(page["source"], page["page"]): page for page in state["unique_pages"].value}
    verified: list[dict[str, Any]] = []
    for candidate in state["evidence_candidates"].value:
        live = root / candidate["source"]
        if live.is_symlink() or not live.is_file() or sha256(live.read_bytes()).hexdigest() != candidate["source_sha256"]:
            raise SemanticGap("stale_source", f"Source changed during verification: {candidate['source']}")
        page = lookup[(candidate["source"], candidate["page"])]
        normalized = re.sub(r"\s+", " ", page["text"])
        if candidate["snippet"] not in normalized or candidate["page_sha256"] != page["page_sha256"]:
            raise SemanticGap("citation_mismatch", f"Evidence no longer matches {candidate['source']} p.{candidate['page']}")
        verified.append(candidate)
    return {"verified_evidence": verified}


def _synthesize(state: Mapping[str, Evidence]) -> dict[str, Any]:
    raise SemanticGap(
        "semantic_synthesis",
        f"Answer the scoped question using the {len(state['verified_evidence'].value)} verified evidence records; cite source and page for each supported claim, and mark unsupported claims as unknown: {state['question'].value}",
        allowed_answers=("cited_answer", "need_more_evidence", "stop"),
        evidence_keys=("question", "verified_evidence"),
    )


RESEARCH_MOTIF = Motif(
    id="bounded-reference-research-v1",
    nodes=(
        Node("collect", (), ("source_dir",), ("pages",), _collect),
        Node("dedupe", ("collect",), ("pages",), ("unique_pages",), _dedupe),
        Node("select", ("dedupe",), ("unique_pages", "terms"), ("evidence_candidates",), _select),
        Node("verify", ("select",), ("source_dir", "unique_pages", "evidence_candidates"), ("verified_evidence",), _verify),
        Node("synthesize", ("verify",), ("question", "verified_evidence"), (), _synthesize),
    ),
)


SOURCE_MOTIF = Motif(
    id="bounded-reference-source-cache-v1",
    nodes=(
        Node("collect", (), ("source_dir",), ("pages",), _collect),
        Node("dedupe", ("collect",), ("pages",), ("unique_pages",), _dedupe),
    ),
)


RETRIEVE_MOTIF = Motif(
    id="bounded-reference-subquestion-v1",
    nodes=(
        Node("select", (), ("unique_pages", "terms"), ("evidence_candidates",), _select),
        Node("verify", ("select",), ("source_dir", "unique_pages", "evidence_candidates"),
             ("verified_evidence",), _verify),
        Node("synthesize", ("verify",), ("question", "verified_evidence"), (), _synthesize),
    ),
)


def _validate_selected_point_pages(state: Mapping[str, Evidence]) -> dict[str, Any]:
    """Recheck semantic page choices against the source snapshot and live files."""
    points = state["validated_answer_points"].value
    selected = state["selected_evidence_by_point"].value
    if not isinstance(selected, dict) or set(selected) != {point["id"] for point in points}:
        raise SemanticGap("invalid_point_selection", "Each required point needs exactly one selected passage")
    lookup = {(page["source"], page["page"]): page for page in state["unique_pages"].value}
    root = Path(state["source_dir"].value).resolve(strict=True)
    checked: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        point_id = point["id"]
        rows = selected[point_id]
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 4 or any(not isinstance(row, dict) for row in rows):
            raise SemanticGap("invalid_point_selection", f"Invalid selected passages for {point_id}")
        if len({row.get("source") for row in rows}) < point.get("min_sources", 1):
            raise SemanticGap("invalid_point_selection", f"Independent sources required for {point_id}")
        if len({(row.get("source"), row.get("page")) for row in rows}) != len(rows):
            raise SemanticGap("invalid_point_selection", f"Duplicate selected page for {point_id}")
        for row in rows:
            key = (row.get("source"), row.get("page"))
            page = lookup.get(key)
            if page is None or any(row.get(field) != page[field] for field in ("source_sha256", "page_sha256")):
                raise SemanticGap("citation_mismatch", f"Selected source page is unavailable or changed: {point_id}")
            live = root / page["source"]
            if live.is_symlink() or not live.is_file() or sha256(live.read_bytes()).hexdigest() != page["source_sha256"]:
                raise SemanticGap("stale_source", f"Source changed after page selection: {page['source']}")
            normalized = re.sub(r"\s+", " ", page["text"])
            if not isinstance(row.get("snippet"), str) or row["snippet"] not in normalized:
                raise SemanticGap("citation_mismatch", f"Selected passage cannot be found: {point_id}")
        checked[point_id] = rows
    return {"rechecked_point_pages": checked}


def _package_point_passages(state: Mapping[str, Evidence]) -> dict[str, Any]:
    """Reuse page-local passages across points under a fixed source-text budget."""
    checked = state["rechecked_point_pages"].value
    lookup = {(page["source"], page["page"]): page for page in state["unique_pages"].value}
    by_page: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for rows in checked.values():
        for row in rows:
            by_page.setdefault((row["source"], row["page"]), []).append(row)
    normalized = {
        key: (lookup[key]["text"] if lookup[key].get("evidence_kind") == "derived_numeric_summary"
              else re.sub(r"\s+", " ", lookup[key]["text"]))
        for key in by_page
    }
    full_length = sum(len(text) for text in normalized.values())
    mode = "full_selected_pages" if full_length <= 10_000 else "selected_page_neighborhoods"
    max_source_characters = 10_000
    margin = 300 if mode == "selected_page_neighborhoods" else 0

    def ranges_for(margin_size: int) -> dict[tuple[str, int], list[tuple[int, int]]]:
        result = {}
        for key, rows in by_page.items():
            text = normalized[key]
            full_page = (mode == "full_selected_pages"
                         or lookup[key].get("evidence_kind") == "derived_numeric_summary")
            spans = ([(0, len(text))] if full_page else [
                (max(0, text.index(row["snippet"]) - margin_size),
                 min(len(text), text.index(row["snippet"]) + len(row["snippet"]) + margin_size))
                for row in rows
            ])
            merged: list[tuple[int, int]] = []
            for start, end in sorted(spans):
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            result[key] = merged
        return result

    page_ranges = ranges_for(margin)
    if sum(end - start for spans in page_ranges.values() for start, end in spans) > max_source_characters:
        margin = 0
        page_ranges = ranges_for(margin)
    if sum(end - start for spans in page_ranges.values() for start, end in spans) > max_source_characters:
        raise SemanticGap("evidence_budget_exceeded", "Selected source passages exceed the 10,000-character budget")

    passages_by_page: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for key, spans in sorted(page_ranges.items()):
        page = lookup[key]
        text = normalized[key]
        passages = []
        for start, end in spans:
            cursor = start
            while cursor < end:
                stop = min(cursor + 750, end)
                if (page.get("evidence_kind") == "derived_numeric_summary"
                        and stop < end):
                    boundary = text.rfind("\n", cursor + 1, stop + 1)
                    if boundary > cursor:
                        stop = boundary + 1
                passage = text[cursor:stop]
                if passage:
                    passages.append({"source": page["source"], "page": page["page"],
                                     "source_sha256": page["source_sha256"],
                                     "page_sha256": page["page_sha256"],
                                     "evidence_kind": page.get("evidence_kind", "source_passage"),
                                     **({"derived_from_pages": page["derived_from_pages"]}
                                        if "derived_from_pages" in page else {}),
                                     "snippet": passage, "span": [cursor, stop]})
                cursor = stop
        passages_by_page[key] = passages
    return {
        "point_passages": {
            point_id: [passage for row in rows
                       for passage in passages_by_page[(row["source"], row["page"])]]
            for point_id, rows in checked.items()
        },
        "passage_packaging": {"mode": mode, "margin": margin,
                              "source_characters": sum(end - start for spans in page_ranges.values()
                                                       for start, end in spans),
                              "unique_pages": len(page_ranges)},
    }


POINT_PAGE_PASSAGES_MOTIF = Motif(
    id="verified-point-page-passages-v1",
    nodes=(
        Node("recheck", (), ("validated_answer_points", "selected_evidence_by_point", "unique_pages", "source_dir"),
             ("rechecked_point_pages",), _validate_selected_point_pages),
        Node("package", ("recheck",), ("rechecked_point_pages", "unique_pages"),
             ("point_passages", "passage_packaging"), _package_point_passages),
    ),
)


def _enforce_evidence_contract(state: Mapping[str, Evidence]) -> dict[str, Any]:
    """Keep predeclared source anchors in the exact passage sent for synthesis."""
    contract = state["contract"].value
    selected = state["selected_evidence"].value
    pages = state["unique_pages"].value
    if not isinstance(contract, list) or len(contract) > 12:
        raise SemanticGap("invalid_evidence_contract", "Contract must contain at most 12 answer points")
    lookup = {(page["source"], page["page"]): page for page in pages}
    by_page: dict[tuple[str, int], list[dict[str, Any]]] = {}
    seen_ids: set[str] = set()
    for item in contract:
        if not isinstance(item, dict) or set(item) != {"id", "source", "page", "anchors"}:
            raise SemanticGap("invalid_evidence_contract", "Each point needs id, source, page, and anchors")
        label, source, number, anchors = (item[key] for key in ("id", "source", "page", "anchors"))
        if (not isinstance(label, str) or not label.strip() or label in seen_ids
                or not isinstance(source, str) or not source
                or not isinstance(number, int) or isinstance(number, bool) or number < 1
                or not isinstance(anchors, list) or not 1 <= len(anchors) <= 3
                or any(not isinstance(anchor, str) or not 8 <= len(anchor.strip()) <= 120 for anchor in anchors)):
            raise SemanticGap("invalid_evidence_contract", "Invalid answer point or duplicate ID")
        seen_ids.add(label)
        key = (source, number)
        if key not in lookup:
            raise SemanticGap("missing_required_source", f"Required source page is unavailable: {source} p.{number}")
        by_page.setdefault(key, []).append(item)
    selected_keys = {(row["source"], row["page"]) for row in selected}
    missing = set(by_page) - selected_keys
    if missing:
        source, number = sorted(missing)[0]
        raise SemanticGap("missing_required_evidence", f"Selected evidence omitted {source} p.{number}",
                          evidence_keys=("selected_evidence", "contract"))
    replacements: dict[tuple[str, int], dict[str, Any]] = {}
    checks: list[dict[str, Any]] = []
    for key, entries in by_page.items():
        page = lookup[key]
        normalized = re.sub(r"\s+", " ", page["text"]).strip()
        positions: list[tuple[int, int]] = []
        for item in entries:
            for anchor in item["anchors"]:
                needle = re.sub(r"\s+", " ", anchor).strip()
                position = normalized.casefold().find(needle.casefold())
                if position < 0:
                    raise SemanticGap("missing_required_evidence",
                                      f"Anchor {item['id']} not found in {key[0]} p.{key[1]}",
                                      evidence_keys=("unique_pages", "contract"))
                positions.append((position, position + len(needle)))
        passages: list[str] = []
        snippet = ""
        for margin in (100, 50, 20, 0):
            intervals: list[list[int]] = []
            for first, last in sorted(positions):
                begin, finish = max(0, first - margin), min(len(normalized), last + margin)
                if intervals and begin <= intervals[-1][1]:
                    intervals[-1][1] = max(intervals[-1][1], finish)
                else:
                    intervals.append([begin, finish])
            passages = [normalized[begin:finish] for begin, finish in intervals]
            snippet = " [... omitted ...] ".join(passages)
            if len(snippet) <= 750:
                break
        if len(snippet) > 750 or any(
            not any(re.sub(r"\s+", " ", anchor).strip().casefold() in passage.casefold()
                    for passage in passages)
            for item in entries for anchor in item["anchors"]
        ):
            raise SemanticGap("evidence_budget_exceeded",
                              f"Required passages exceed 750 characters: {key[0]} p.{key[1]}",
                              evidence_keys=("unique_pages", "contract"))
        replacements[key] = {"snippet": snippet, "passages": passages}
        checks.extend({"id": item["id"], "source": key[0], "page": key[1],
                       "page_sha256": page["page_sha256"], "status": "included_in_excerpt",
                       "passages": len(passages)}
                      for item in entries)
    grounded = [{**row, **replacements.get((row["source"], row["page"]), {})} for row in selected]
    return {"grounded_evidence": grounded, "coverage_checks": checks}


EVIDENCE_CONTRACT_MOTIF = Motif(
    id="required-evidence-excerpt-v1",
    nodes=(Node("enforce", (), ("unique_pages", "selected_evidence", "contract"),
                ("grounded_evidence", "coverage_checks"), _enforce_evidence_contract),),
)


def _assess_answer_coverage(state: Mapping[str, Evidence]) -> dict[str, Any]:
    contract = state["contract"].value
    citations = state["citations"].value
    claims = state["claims"].value
    checks: list[dict[str, Any]] = []
    for item in contract:
        evidence_ids = {key for key, row in citations.items()
                        if row["source"] == item["source"] and row["page"] == item["page"]}
        covered_anchors: list[str] = []
        for anchor in item["anchors"]:
            canonical_anchor = "".join(char for char in anchor.casefold() if char.isalnum())
            found = False
            for claim in claims:
                for support in claim["supports"]:
                    if support["evidence_id"] not in evidence_ids:
                        continue
                    canonical_quote = "".join(char for char in support["quote"].casefold() if char.isalnum())
                    if len(canonical_quote) >= 12 and (
                        canonical_quote in canonical_anchor or canonical_anchor in canonical_quote
                    ):
                        found = True
                        break
                if found:
                    break
            if found:
                covered_anchors.append(anchor)
        checks.append({"id": item["id"], "source": item["source"], "page": item["page"],
                       "status": "cited_in_claim" if len(covered_anchors) == len(item["anchors"])
                       else "missing_claim_quote", "anchors_cited": len(covered_anchors),
                       "anchors_required": len(item["anchors"])})
    return {"answer_coverage": checks}


def _gate_answer_coverage(state: Mapping[str, Evidence]) -> dict[str, Any]:
    missing = [item["id"] for item in state["answer_coverage"].value
               if item["status"] != "cited_in_claim"]
    if missing:
        raise SemanticGap("incomplete_answer", f"Required answer points lack cited claims: {', '.join(missing)}",
                          evidence_keys=("answer_coverage",))
    return {"answer_coverage_ready": True}


ANSWER_COVERAGE_MOTIF = Motif(
    id="required-answer-coverage-v1",
    nodes=(
        Node("assess", (), ("contract", "citations", "claims"), ("answer_coverage",), _assess_answer_coverage),
        Node("gate", ("assess",), ("answer_coverage",), ("answer_coverage_ready",), _gate_answer_coverage),
    ),
)


def _validate_answer_points(state: Mapping[str, Evidence]) -> dict[str, Any]:
    """Freeze question obligations before evidence selection or model synthesis."""
    points = state["answer_points"].value
    if not isinstance(points, list) or not 1 <= len(points) <= 8:
        raise SemanticGap("invalid_answer_points", "Provide 1 to 8 answer points")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for point in points:
        if (not isinstance(point, dict) or not {"id", "requirement"} <= set(point)
                or not set(point) <= {"id", "requirement", "min_sources", "allow_abstention"}):
            raise SemanticGap("invalid_answer_points", "Each point needs id and requirement")
        label, requirement = point["id"], point["requirement"]
        if (not isinstance(label, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,29}", label)
                or label in seen or not isinstance(requirement, str)
                or not 8 <= len(requirement.strip()) <= 240
                or type(point.get("min_sources", 1)) is not int
                or not 1 <= point.get("min_sources", 1) <= 4
                or type(point.get("allow_abstention", False)) is not bool):
            raise SemanticGap("invalid_answer_points", "Invalid or duplicate answer point")
        seen.add(label)
        normalized.append({**point, "id": label, "requirement": requirement.strip()})
    return {"validated_answer_points": normalized}


ANSWER_POINT_PREFLIGHT_MOTIF = Motif(
    id="question-obligation-preflight-v1",
    nodes=(Node("validate", (), ("answer_points",), ("validated_answer_points",), _validate_answer_points),),
)


def _assess_point_coverage(state: Mapping[str, Evidence]) -> dict[str, Any]:
    points = state["validated_answer_points"].value
    claims = state["claims"].value
    citations = state["citations"].value
    uncertainties = state["uncertainties"].value
    checks: list[dict[str, Any]] = []
    for point in points:
        matches: list[str] = []
        supported_sources: set[str] = set()
        for claim in claims:
            if claim.get("point_id") != point["id"]:
                continue
            for support in claim.get("supports", []):
                row = citations.get(support.get("evidence_id"))
                if not row:
                    continue
                quote = "".join(char for char in support.get("quote", "").casefold() if char.isalnum())
                passages = row.get("passages") or [row["snippet"]]
                if len(quote) >= 12 and any(
                    quote in "".join(char for char in passage.casefold() if char.isalnum())
                    for passage in passages
                ):
                    matches.append(claim["text"])
                    supported_sources.add(row["source"])
        explicit_gap = any(item.get("point_id") == point["id"] and item.get("blocks_requirement") is True
                           for item in uncertainties if isinstance(item, dict))
        checks.append({"id": point["id"], "requirement": point["requirement"],
                       "status": "abstention_pending_review" if explicit_gap and point.get("allow_abstention") else
                                 "explicit_uncertainty" if explicit_gap else
                                 "missing_cited_claim" if not matches else
                                 "insufficient_sources" if len(supported_sources) < point.get("min_sources", 1)
                                 else "cited_claim",
                       "matching_claims": list(dict.fromkeys(matches)),
                       "cited_sources": sorted(supported_sources),
                       "required_sources": point.get("min_sources", 1)})
    return {"point_coverage": checks}


def _gate_point_coverage(state: Mapping[str, Evidence]) -> dict[str, Any]:
    missing = [item["id"] for item in state["point_coverage"].value
               if item["status"] not in {"cited_claim", "abstention_pending_review"}]
    if missing:
        raise SemanticGap("incomplete_answer", f"Question obligations lack cited claims: {', '.join(missing)}",
                          evidence_keys=("point_coverage",))
    return {"point_coverage_ready": True}


QUESTION_COVERAGE_MOTIF = Motif(
    id="question-obligation-coverage-v1",
    nodes=(
        Node("assess", (), ("validated_answer_points", "claims", "citations", "uncertainties"),
             ("point_coverage",), _assess_point_coverage),
        Node("gate", ("assess",), ("point_coverage",), ("point_coverage_ready",), _gate_point_coverage),
    ),
)


def _merge_repair(state: Mapping[str, Evidence]) -> dict[str, Any]:
    """Replace only unresolved point claims after a verified local repair."""
    points = {row["id"] for row in state["validated_answer_points"].value}
    missing = set(state["missing_ids"].value)
    if not missing or not missing <= points:
        raise SemanticGap("invalid_repair_scope", "Repair points must be a nonempty subset of task obligations")
    original_citations = state["original_citations"].value
    repair_citations = state["repair_citations"].value
    if set(original_citations) & set(repair_citations):
        raise SemanticGap("invalid_repair_citations", "Repair citation IDs overlap original IDs")
    repaired = state["repair_claims"].value
    if any(claim.get("point_id") not in missing or any(
        support.get("evidence_id") not in repair_citations for support in claim.get("supports", [])
    ) for claim in repaired):
        raise SemanticGap("invalid_repair_scope", "Repair claim escaped its missing point or evidence scope")
    old = [claim for claim in state["original_claims"].value if claim.get("point_id") not in missing]
    uncertainties = [item for item in state["repair_uncertainties"].value
                     if isinstance(item, dict) and item.get("point_id") in missing]
    return {"merged_claims": old + repaired,
            "merged_citations": {**original_citations, **repair_citations},
            "merged_uncertainties": uncertainties}


RESEARCH_REPAIR_MERGE_MOTIF = Motif(
    id="bounded-research-repair-merge-v1",
    nodes=(Node("merge", (), (
        "validated_answer_points", "missing_ids", "original_claims", "original_citations",
        "repair_claims", "repair_citations", "repair_uncertainties",
    ), ("merged_claims", "merged_citations", "merged_uncertainties"), _merge_repair),),
)


def ground_query_terms(terms: list[str], pages: list[dict[str, Any]], allowed_sources: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Keep literal phrases, or reduce an absent phrase to a verified source term."""
    corpus = [re.sub(r"\s+", " ", page["text"]).casefold()
              for page in pages if page["source"] in allowed_sources]
    if not corpus:
        raise SemanticGap("invalid_source_scope", "No pages in the requested source scope")
    grounded: list[str] = []
    changes: list[dict[str, str]] = []
    for term in terms:
        folded = term.casefold().strip()
        if any(folded in text for text in corpus):
            choice = term.strip()
        else:
            tokens = [token for token in re.findall(r"[a-z][a-z0-9-]+", folded)
                      if len(token) >= 4 and token not in {"with", "from", "into", "that", "this"}]
            ranked = [(sum(token in text for text in corpus), -len(token), token)
                      for token in tokens]
            ranked = [item for item in ranked if item[0] > 0]
            choice = min(ranked)[2] if ranked else ""
        if choice and choice.casefold() not in {item.casefold() for item in grounded}:
            grounded.append(choice)
        if choice != term.strip():
            changes.append({"suggested": term, "grounded": choice})
    if len(grounded) < 2:
        raise SemanticGap("insufficient_grounded_terms", "Fewer than two planned terms occur in the scoped sources")
    return grounded, changes


def ground_repair_terms(phrases: list[str], pages: list[dict[str, Any]],
                        allowed_sources: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Retain short exact source phrases before searching a missing answer point."""
    grounded, changes = ground_query_terms(phrases, pages, allowed_sources)
    corpus = [re.sub(r"\s+", " ", page["text"]).casefold()
              for page in pages if page["source"] in allowed_sources]
    for phrase in phrases:
        tokens = re.findall(r"[a-z][a-z0-9_-]*", phrase.casefold())
        found = None
        for width in (3, 2):
            for index in range(len(tokens) - width + 1):
                candidate = " ".join(tokens[index:index + width])
                if any(candidate in text for text in corpus):
                    found = candidate
                    break
            if found:
                break
        if found and found not in {term.casefold() for term in grounded}:
            grounded.append(found)
            changes.append({"suggested": phrase, "grounded": found})
        if len(grounded) >= 8:
            break
    return grounded[:8], changes
