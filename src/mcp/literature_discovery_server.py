"""Read-only scholarly discovery via public research APIs.

The MCP tools return bounded metadata and provenance. They never download a PDF,
write to Zotero, or treat a search result as evidence for a scientific claim.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import hashlib
import time
import fcntl
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pypdf import PdfReader


server = MCPServer(
    "sss-literature-discovery",
    instructions="Search and inspect scholarly metadata. Results are candidates, not verified paper evidence. "
    "Record query, provider, DOI, and retrieval time. Read the actual paper before making a scientific claim.",
)
OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org"
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
ARXIV = "https://export.arxiv.org/api/query"
SERPAPI = "https://serpapi.com/search.json"
FULLTEXT_CACHE = Path(__file__).resolve().parents[2] / ".local" / "literature-cache" / "europe-pmc"
ARXIV_CACHE = Path(__file__).resolve().parents[2] / ".local" / "literature-cache" / "arxiv"
ARXIV_PDF_CACHE = Path(__file__).resolve().parents[2] / ".local" / "literature-cache" / "arxiv-pdf"
WORK_ID = re.compile(r"^W[0-9]{1,20}$", re.IGNORECASE)
DOI = re.compile(r"^10\.[0-9]{4,9}/\S{1,240}$", re.IGNORECASE)
PMCID = re.compile(r"^PMC[0-9]{1,12}$", re.IGNORECASE)
ARXIV_ID = re.compile(r"^(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d{1,3})?$", re.IGNORECASE)
_last_arxiv_request = 0.0


def _arxiv_feed(params: dict[str, str]) -> tuple[ET.Element, str, bool]:
    """Fetch a bounded Atom feed, cache it for a day, and pace uncached requests."""
    global _last_arxiv_request
    url = ARXIV + "?" + urllib.parse.urlencode(params)
    cache = ARXIV_CACHE / (hashlib.sha256(url.encode()).hexdigest() + ".xml")
    cached = cache.is_file() and time.time() - cache.stat().st_mtime < 24 * 3600
    if cached:
        raw = cache.read_bytes()
    else:
        delay = 3.0 - (time.monotonic() - _last_arxiv_request)
        if delay > 0:
            time.sleep(delay)
        request = urllib.request.Request(url, headers={
            "Accept": "application/atom+xml",
            "User-Agent": "SSS-Research-Agent/0.1 (scholarly discovery)",
        })
        for attempt in range(2):
            try:
                _last_arxiv_request = time.monotonic()
                with urllib.request.urlopen(request, timeout=25) as response:
                    raw = response.read(2_000_001)
                break
            except urllib.error.HTTPError as exc:
                if attempt == 0 and exc.code in {406, 502, 503}:
                    time.sleep(3)
                    continue
                raise RuntimeError(f"arXiv returned HTTP {exc.code}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"arXiv is unavailable: {exc.reason}") from exc
        if len(raw) > 2_000_000:
            raise ValueError("arXiv response exceeds 2 MB")
    if b"<!ENTITY" in raw.upper() or b"<!DOCTYPE" in raw.upper():
        raise ValueError("arXiv response contains XML declarations")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("arXiv returned invalid Atom XML") from exc
    atom = "{http://www.w3.org/2005/Atom}"
    if root.tag != atom + "feed":
        raise ValueError("arXiv did not return an Atom feed")
    if not cached:
        ARXIV_CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
        cache.write_bytes(raw)
        cache.chmod(0o600)
    return root, url, cached


def _arxiv_paper(entry: ET.Element) -> dict[str, Any]:
    atom = "{http://www.w3.org/2005/Atom}"
    ax = "{http://arxiv.org/schemas/atom}"
    def value(name: str) -> str | None:
        node = entry.find(atom + name)
        return re.sub(r"\s+", " ", node.text or "").strip() if node is not None else None
    page = value("id")
    return {
        "arxiv_id": page.rsplit("/", 1)[-1] if page else None,
        "title": value("title"), "abstract": (value("summary") or "")[:3000],
        "authors": [name.text for author in entry.findall(atom + "author")[:20]
                    if (name := author.find(atom + "name")) is not None and name.text],
        "published": value("published"), "updated": value("updated"),
        "categories": [item.get("term") for item in entry.findall(atom + "category")[:15]
                       if item.get("term")],
        "doi": (entry.find(ax + "doi").text if entry.find(ax + "doi") is not None else None),
        "journal_ref": (entry.find(ax + "journal_ref").text
                        if entry.find(ax + "journal_ref") is not None else None),
        "paper_url": page,
        "pdf_url": next((link.get("href") for link in entry.findall(atom + "link")
                         if link.get("title") == "pdf"), None),
    }


def search_arxiv(query: str, field: str = "all", sort: str = "relevance",
                 limit: int = 10) -> dict[str, Any]:
    """Search arXiv preprints by plain topic, title, author, or abstract words; no DOI needed."""
    words = re.findall(r"[\w-]+", query.strip(), re.UNICODE)
    if not 1 <= len(words) <= 20 or not 2 <= len(query.strip()) <= 200:
        raise ValueError("Provide 2–200 characters and at most 20 search words")
    fields = {"all": "all", "title": "ti", "author": "au", "abstract": "abs"}
    sorts = {"relevance": "relevance", "newest": "submittedDate", "updated": "lastUpdatedDate"}
    if field not in fields or sort not in sorts or not 1 <= limit <= 20:
        raise ValueError("Invalid field, sort, or limit (1–20)")
    expression = " AND ".join(f"{fields[field]}:{word}" for word in words)
    params = {"search_query": expression, "start": "0", "max_results": str(limit),
              "sortBy": sorts[sort], "sortOrder": "descending"}
    degraded = False
    try:
        root, url, cached = _arxiv_feed(params)
    except RuntimeError as exc:
        if limit <= 3 or "HTTP 406" not in str(exc):
            return {"provider": "arXiv", "status": "unavailable", "query": query,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "provider_error": str(exc), "total_matches": None, "papers": [],
                    "note": "Provider failure is not a zero-result search. Try OpenAlex or a known arXiv PDF ID."}
        # Some arXiv edge responses reject a larger result window for a query.
        params["max_results"] = "3"
        try:
            root, url, cached = _arxiv_feed(params)
        except RuntimeError as retry_exc:
            return {"provider": "arXiv", "status": "unavailable", "query": query,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "provider_error": str(retry_exc), "total_matches": None, "papers": [],
                    "note": "Provider failure is not a zero-result search. Try OpenAlex or a known arXiv PDF ID."}
        degraded = True
    atom = "{http://www.w3.org/2005/Atom}"
    opensearch = "{http://a9.com/-/spec/opensearch/1.1/}"
    count_node = root.find(opensearch + "totalResults")
    return {"provider": "arXiv", "status": "ok",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "query": query, "query_url": url, "cache_hit": cached,
            "requested_limit": limit, "partial_due_to_provider_error": degraded,
            "total_matches": int(count_node.text) if count_node is not None and count_node.text else None,
            "papers": [_arxiv_paper(item) for item in root.findall(atom + "entry")[:limit]]}


def get_arxiv_paper(arxiv_id: str) -> dict[str, Any]:
    """Inspect one arXiv preprint by its arXiv ID, without requiring a DOI."""
    arxiv_id = arxiv_id.strip().removeprefix("arXiv:")
    if not ARXIV_ID.fullmatch(arxiv_id):
        raise ValueError("Provide an arXiv ID such as 1706.03762")
    try:
        root, url, cached = _arxiv_feed({"id_list": arxiv_id, "max_results": "1"})
    except RuntimeError as exc:
        return {"provider": "arXiv", "status": "unavailable", "arxiv_id": arxiv_id,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "provider_error": str(exc), "paper": None,
                "note": "The metadata endpoint failed; a known ID may still have an accessible PDF."}
    atom = "{http://www.w3.org/2005/Atom}"
    entry = root.find(atom + "entry")
    return {"provider": "arXiv", "status": "ok",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "query_url": url, "cache_hit": cached,
            "paper": _arxiv_paper(entry) if entry is not None else None}


class _ArxivOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in {"arxiv.org", "export.arxiv.org"}:
            raise RuntimeError("arXiv PDF redirected outside the approved provider")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _arxiv_pdf(arxiv_id: str) -> tuple[bytes, dict[str, Any]]:
    arxiv_id = arxiv_id.strip().removeprefix("arXiv:")
    if not ARXIV_ID.fullmatch(arxiv_id):
        raise ValueError("Provide a valid arXiv ID")
    # The Atom endpoint may return 406 even when the versioned PDF is available.
    # The PDF bytes and hash, rather than Atom metadata, define this source.
    url = "https://arxiv.org/pdf/" + urllib.parse.quote(arxiv_id, safe="/.")
    stem = hashlib.sha256(arxiv_id.encode()).hexdigest()
    cache = ARXIV_PDF_CACHE / (stem + ".pdf")
    version_pinned = bool(re.search(r"v\d+$", arxiv_id))
    cache_hit = cache.is_file() and (version_pinned or time.time() - cache.stat().st_mtime < 86400)
    if cache_hit:
        raw = cache.read_bytes()
        retrieved_at = datetime.fromtimestamp(cache.stat().st_mtime, timezone.utc).isoformat()
    else:
        request = urllib.request.Request(url, headers={
            "Accept": "application/pdf",
            "User-Agent": "SSS-Research-Agent/0.1 (scholarly reading)",
        })
        opener = urllib.request.build_opener(_ArxivOnlyRedirect())
        try:
            with opener.open(request, timeout=35) as response:
                raw = response.read(20_000_001)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"arXiv PDF returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"arXiv PDF is unavailable: {exc.reason}") from exc
        if len(raw) > 20_000_000:
            raise ValueError("arXiv PDF exceeds 20 MB")
        if not raw.startswith(b"%PDF-"):
            raise ValueError("arXiv did not return a PDF")
        ARXIV_PDF_CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = ARXIV_PDF_CACHE / (stem + ".tmp")
        temporary.write_bytes(raw)
        temporary.chmod(0o600)
        temporary.replace(cache)
        retrieved_at = datetime.now(timezone.utc).isoformat()
    if len(raw) > 20_000_000 or not raw.startswith(b"%PDF-"):
        raise ValueError("Cached arXiv PDF is invalid")
    return raw, {"provider": "arXiv", "arxiv_id": arxiv_id, "source_url": url,
                 "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                 "version_pinned": version_pinned, "cache_hit": cache_hit,
                 "retrieved_at": retrieved_at}


def read_arxiv_pdf_pages(arxiv_id: str, start_page: int = 1, max_pages: int = 2,
                         max_chars_per_page: int = 5000) -> dict[str, Any]:
    """Read bounded, page-labelled text from an exact arXiv PDF version."""
    if not 1 <= start_page <= 1000 or not 1 <= max_pages <= 3 or not 500 <= max_chars_per_page <= 6000:
        raise ValueError("Page request must be start 1–1000, at most 3 pages and 500–6000 chars each")
    raw, source = _arxiv_pdf(arxiv_id)
    reader = PdfReader(BytesIO(raw))
    if reader.is_encrypted or len(reader.pages) > 1000:
        raise ValueError("arXiv PDF cannot be safely extracted")
    if start_page > len(reader.pages):
        raise ValueError("Start page exceeds PDF page count")
    pages = []
    for number in range(start_page, min(start_page + max_pages, len(reader.pages) + 1)):
        text = (reader.pages[number - 1].extract_text() or "").strip()
        pages.append({"pdf_page": number, "total_chars": len(text),
                      "text": text[:max_chars_per_page],
                      "truncated": len(text) > max_chars_per_page,
                      "low_text": len(text) < 80})
    return {**source, "pdf_page_count": len(reader.pages), "pages": pages,
            "note": "An unversioned arXiv ID may point to a later revision; cite the returned PDF SHA-256 and retrieval time. PDF page positions may differ from printed page labels; verify figures visually."}


def _scholar_budget() -> tuple[str, int]:
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    try:
        budget = int(os.environ.get("SERPAPI_MONTHLY_SEARCH_BUDGET", "0"))
    except ValueError as exc:
        raise ValueError("SERPAPI_MONTHLY_SEARCH_BUDGET must be an integer") from exc
    if not key or not 1 <= budget <= 10000:
        raise RuntimeError("Google Scholar connector needs a SerpAPI key and a monthly search budget")
    return key, budget


def _reserve_scholar_search(budget: int) -> tuple[int, int]:
    """Reserve one request before contacting the provider; ambiguous failures still count."""
    directory = Path(__file__).resolve().parents[2] / ".local" / "literature-cache" / "scholar"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    ledger = directory / "usage.json"
    lock = directory / "usage.lock"
    with lock.open("a+") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        try:
            previous = json.loads(ledger.read_text(encoding="utf-8")) if ledger.exists() else {}
        except (OSError, ValueError):
            raise RuntimeError("Scholar budget ledger is unreadable; refusing the request")
        used = int(previous.get("used", 0)) if previous.get("month") == month else 0
        if used < 0:
            raise RuntimeError("Scholar budget ledger is invalid; refusing the request")
        if used >= budget:
            raise RuntimeError("Google Scholar monthly search budget exhausted")
        tmp = directory / "usage.tmp"
        tmp.write_text(json.dumps({"month": month, "used": used + 1}), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(ledger)
        return used + 1, budget


def search_google_scholar(query: str, from_year: int | None = None,
                          to_year: int | None = None, limit: int = 10) -> dict[str, Any]:
    """Search Google Scholar through an optional, budgeted third-party SerpAPI account."""
    query = query.strip()
    if not 2 <= len(query) <= 200 or not 1 <= limit <= 10:
        raise ValueError("Query must be 2–200 characters; limit must be 1–10")
    if from_year is not None and not 1800 <= from_year <= 2100:
        raise ValueError("Invalid from_year")
    if to_year is not None and not 1800 <= to_year <= 2100:
        raise ValueError("Invalid to_year")
    if from_year and to_year and from_year > to_year:
        raise ValueError("from_year exceeds to_year")
    key, budget = _scholar_budget()
    params = {"engine": "google_scholar", "q": query, "num": str(limit), "api_key": key}
    if from_year: params["as_ylo"] = str(from_year)
    if to_year: params["as_yhi"] = str(to_year)
    used, cap = _reserve_scholar_search(budget)
    request = urllib.request.Request(SERPAPI + "?" + urllib.parse.urlencode(params),
                                     headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(2_000_001)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"SerpAPI returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"SerpAPI is unavailable: {exc.reason}") from exc
    if len(raw) > 2_000_000:
        raise ValueError("Scholar response exceeds 2 MB")
    data = json.loads(raw)
    if data.get("error"):
        raise RuntimeError("SerpAPI rejected the Scholar search; check account status and budget")
    results = []
    for item in data.get("organic_results", [])[:limit]:
        publication = item.get("publication_info") or {}
        results.append({"title": item.get("title"), "link": item.get("link"),
                        "snippet": (item.get("snippet") or "")[:1000],
                        "publication_summary": publication.get("summary"),
                        "cited_by_count": (item.get("inline_links") or {}).get("cited_by", {}).get("total"),
                        "result_id": item.get("result_id")})
    return {"provider": "Google Scholar via SerpAPI (third party)",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "query_url": "https://scholar.google.com/scholar?" + urllib.parse.urlencode({"q": query}),
            "budget_used_this_month": used, "budget_limit_this_month": cap,
            "papers": results}


def _request(base: str, path: str, params: dict[str, str] | None = None) -> tuple[dict[str, Any], str]:
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/json", "User-Agent": "SSS-Research-Agent/0.1 (metadata discovery)"}
    if base == OPENALEX and os.environ.get("OPENALEX_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["OPENALEX_API_KEY"]
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if int(response.headers.get("Content-Length", "0") or 0) > 8_000_000:
                raise ValueError("Metadata response exceeds 8 MB")
            data = response.read(8_000_001)
            if len(data) > 8_000_000:
                raise ValueError("Metadata response exceeds 8 MB")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{base} returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{base} is unavailable: {exc.reason}") from exc
    return json.loads(data), url


def _doi(value: str) -> str:
    value = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
            break
    if not DOI.fullmatch(value):
        raise ValueError("Provide one valid DOI")
    return value


def _work_id(value: str) -> str:
    value = value.rsplit("/", 1)[-1]
    if not WORK_ID.fullmatch(value):
        raise ValueError("Provide an OpenAlex work ID such as W2741809807")
    return value.upper()


def _abstract(index: dict[str, list[int]] | None, limit: int = 1800) -> str | None:
    if not index:
        return None
    positions = [(position, word) for word, offsets in index.items() for position in offsets if isinstance(position, int)]
    positions.sort()
    return " ".join(word for _, word in positions)[:limit]


def _work(record: dict[str, Any], *, detailed: bool = False) -> dict[str, Any]:
    authors = [entry.get("author", {}).get("display_name") for entry in record.get("authorships", [])[:12]]
    primary = record.get("primary_location") or {}
    best_oa = record.get("best_oa_location") or {}
    result = {
        "openalex_id": record.get("id"), "doi": record.get("doi"),
        "title": record.get("title") or record.get("display_name"),
        "authors": [name for name in authors if name],
        "publication_date": record.get("publication_date"), "type": record.get("type"),
        "venue": (primary.get("source") or {}).get("display_name"),
        "cited_by_count": record.get("cited_by_count"),
        "open_access_pdf_url": best_oa.get("pdf_url"),
        "landing_page_url": best_oa.get("landing_page_url") or primary.get("landing_page_url"),
    }
    if detailed:
        result["abstract"] = _abstract(record.get("abstract_inverted_index"))
        result["referenced_work_ids"] = record.get("referenced_works", [])[:30]
        result["related_work_ids"] = record.get("related_works", [])[:20]
        result["source_updated_date"] = record.get("updated_date")
    return result


def search_works(query: str, from_year: int | None = None, to_year: int | None = None,
                 open_access_only: bool = False, limit: int = 10) -> dict[str, Any]:
    """Search scholarly works across OpenAlex, with optional year and open access filters."""
    query = query.strip()
    if not 2 <= len(query) <= 300:
        raise ValueError("Query must contain 2–300 characters")
    if not 1 <= limit <= 25:
        raise ValueError("Limit must be 1–25")
    if from_year is not None and not 1800 <= from_year <= 2100:
        raise ValueError("Invalid from_year")
    if to_year is not None and not 1800 <= to_year <= 2100:
        raise ValueError("Invalid to_year")
    if from_year and to_year and from_year > to_year:
        raise ValueError("from_year exceeds to_year")
    filters = []
    if from_year: filters.append(f"from_publication_date:{from_year}-01-01")
    if to_year: filters.append(f"to_publication_date:{to_year}-12-31")
    if open_access_only: filters.append("is_oa:true")
    params = {"search": query, "per_page": str(limit)}
    if filters: params["filter"] = ",".join(filters)
    data, url = _request(OPENALEX, "/works", params)
    return {"provider": "OpenAlex", "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "query_url": url, "total_matches": data.get("meta", {}).get("count"),
            "api_cost_usd": data.get("meta", {}).get("cost_usd"),
            "works": [_work(item) for item in data.get("results", [])]}


def get_work(identifier: str) -> dict[str, Any]:
    """Inspect one OpenAlex work by work ID or DOI, including abstract and citation IDs."""
    identifier = identifier.strip()
    resource = _work_id(identifier) if WORK_ID.fullmatch(identifier.rsplit("/", 1)[-1]) else "doi:" + _doi(identifier)
    data, url = _request(OPENALEX, "/works/" + urllib.parse.quote(resource, safe=":"))
    return {"provider": "OpenAlex", "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "query_url": url, "work": _work(data, detailed=True)}


def get_citing_works(work_id: str, limit: int = 10) -> dict[str, Any]:
    """Find works that cite an OpenAlex work; citation links may be incomplete."""
    work_id = _work_id(work_id)
    if not 1 <= limit <= 25:
        raise ValueError("Limit must be 1–25")
    data, url = _request(OPENALEX, "/works", {"filter": f"cites:{work_id}", "per_page": str(limit)})
    return {"provider": "OpenAlex", "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "query_url": url, "total_matches": data.get("meta", {}).get("count"),
            "api_cost_usd": data.get("meta", {}).get("cost_usd"),
            "works": [_work(item) for item in data.get("results", [])]}


def verify_doi_metadata(doi: str) -> dict[str, Any]:
    """Fetch Crossref's publisher-deposited metadata for one DOI as an independent metadata check."""
    doi = _doi(doi)
    data, url = _request(CROSSREF, "/works/" + urllib.parse.quote(doi, safe=""))
    message = data.get("message", {})
    return {"provider": "Crossref", "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "query_url": url, "doi": message.get("DOI"), "title": (message.get("title") or [None])[0],
            "type": message.get("type"), "publisher": message.get("publisher"),
            "published": message.get("published"), "container_title": (message.get("container-title") or [None])[0],
            "authors": [" ".join(filter(None, [entry.get("given"), entry.get("family")]))
                        for entry in message.get("author", [])[:12]]}


def find_europe_pmc_fulltext(doi: str) -> dict[str, Any]:
    """Find an Open Access Europe PMC full-text record by exact DOI."""
    doi = _doi(doi)
    data, url = _request(EUROPE_PMC, "/search", {
        "query": "DOI:" + doi, "format": "json", "resultType": "core", "pageSize": "5",
    })
    matches = [item for item in data.get("resultList", {}).get("result", [])
               if str(item.get("doi", "")).lower() == doi.lower()]
    article = next((item for item in matches if item.get("isOpenAccess") == "Y"
                    and PMCID.fullmatch(str(item.get("pmcid", "")))), matches[0] if matches else None)
    pmcid = article.get("pmcid") if article else None
    candidate = bool(article and article.get("isOpenAccess") == "Y"
                     and pmcid and PMCID.fullmatch(pmcid))
    return {"provider": "Europe PMC", "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "query_url": url, "doi": doi, "found": bool(article),
            "fulltext_candidate": candidate, "pmcid": pmcid,
            "next_step": "Call list_europe_pmc_sections to verify full-text access" if candidate else None,
            "title": article.get("title") if article else None,
            "publication_date": article.get("firstPublicationDate") if article else None,
            "license": article.get("license") if article else None,
            "article_url": f"https://europepmc.org/articles/{pmcid}" if pmcid else None}


def _pmcid(value: str) -> str:
    value = value.strip().upper()
    if not PMCID.fullmatch(value):
        raise ValueError("Provide a PMCID such as PMC12460991")
    return value


def _article_xml(pmcid: str, refresh: bool = False) -> tuple[ET.Element, dict[str, Any]]:
    pmcid = _pmcid(pmcid)
    url = f"{EUROPE_PMC}/{pmcid}/fullTextXML"
    file = FULLTEXT_CACHE / f"{pmcid}.xml"
    info_file = FULLTEXT_CACHE / f"{pmcid}.json"
    cached = False
    if not refresh and file.is_file() and info_file.is_file():
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
            age = datetime.now(timezone.utc) - datetime.fromisoformat(info["retrieved_at"])
            if age.total_seconds() < 7 * 24 * 3600:
                raw = file.read_bytes()
                cached = hashlib.sha256(raw).hexdigest() == info["sha256"]
        except (OSError, ValueError, KeyError):
            cached = False
    if not cached:
        request = urllib.request.Request(url, headers={
            "Accept": "application/xml", "User-Agent": "SSS-Research-Agent/0.1 (open full text)",
        })
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if int(response.headers.get("Content-Length", "0") or 0) > 6_000_000:
                    raise ValueError("Full text exceeds 6 MB")
                raw = response.read(6_000_001)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Europe PMC full text returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Europe PMC full text is unavailable: {exc.reason}") from exc
        if len(raw) > 6_000_000:
            raise ValueError("Full text exceeds 6 MB")
        info = {"retrieved_at": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(raw).hexdigest(), "source_url": url}
    if b"<!ENTITY" in raw.upper():
        raise ValueError("Full text contains entity declarations")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("Europe PMC returned invalid article XML") from exc
    if root.tag.rsplit("}", 1)[-1] != "article":
        raise ValueError("Europe PMC did not return an article")
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    if not cached:
        FULLTEXT_CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
        file.write_bytes(raw)
        info_file.write_text(json.dumps(info), encoding="utf-8")
        file.chmod(0o600)
        info_file.chmod(0o600)
    article_meta = root.find("./front/article-meta")
    doi = None
    license_type = None
    if article_meta is not None:
        doi = next((item.text for item in article_meta.findall("article-id")
                    if item.get("pub-id-type") == "doi"), None)
        license_node = article_meta.find("./permissions/license")
        license_type = license_node.get("license-type") if license_node is not None else None
    return root, {**info, "cache_hit": cached, "doi": doi, "license": license_type,
                  "article_url": f"https://europepmc.org/articles/{pmcid}"}


def _clean_text(element: ET.Element) -> str:
    return re.sub(r"\s+", " ", " ".join(element.itertext())).strip()


def _sections(root: ET.Element) -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    meta = root.find("./front/article-meta")
    if meta is not None:
        abstract = meta.find("abstract")
        if abstract is not None:
            result.append(("abstract", "Abstract", _clean_text(abstract)))
    body = root.find("body")
    if body is None:
        return result

    def walk(parent: ET.Element, prefix: str) -> None:
        index = 0
        for section in parent.findall("sec"):
            index += 1
            section_id = f"{prefix}.{index}" if prefix else f"s{index}"
            title_node = section.find("title")
            title = _clean_text(title_node) if title_node is not None else section_id
            text = " ".join(_clean_text(child) for child in section
                            if child.tag not in {"title", "sec"})
            result.append((section_id, title, text.strip()))
            walk(section, section_id)

    walk(body, "")
    return result


def list_europe_pmc_sections(pmcid: str, refresh: bool = False) -> dict[str, Any]:
    """List bounded section IDs and titles for an Open Access full-text article."""
    pmcid = _pmcid(pmcid)
    root, source = _article_xml(pmcid, refresh)
    sections = _sections(root)
    return {"provider": "Europe PMC", "pmcid": pmcid, **source,
            "section_count": len(sections), "sections_truncated": len(sections) > 100,
            "sections": [{"id": key, "title": title[:250], "chars": len(text)}
                         for key, title, text in sections[:100]]}


def read_europe_pmc_section(pmcid: str, section_id: str, offset_chars: int = 0,
                            max_chars: int = 4000, refresh: bool = False) -> dict[str, Any]:
    """Read a bounded text slice from one Open Access article section."""
    pmcid = _pmcid(pmcid)
    if not 0 <= offset_chars <= 1_000_000:
        raise ValueError("offset_chars must be 0–1000000")
    if not 500 <= max_chars <= 8000:
        raise ValueError("max_chars must be 500–8000")
    root, source = _article_xml(pmcid, refresh)
    found = next(((title, text) for key, title, text in _sections(root)
                  if key == section_id), None)
    if found is None:
        raise ValueError("Unknown section ID; call list_europe_pmc_sections first")
    title, text = found
    end = min(offset_chars + max_chars, len(text))
    return {"provider": "Europe PMC", "pmcid": pmcid, **source,
            "section_id": section_id, "section_title": title[:250],
            "offset_chars": offset_chars, "total_chars": len(text),
            "next_offset": end if end < len(text) else None,
            "text": text[offset_chars:end]}


for function in (search_arxiv, get_arxiv_paper, read_arxiv_pdf_pages,
                 search_works, get_work, get_citing_works, verify_doi_metadata,
                 find_europe_pmc_fulltext, list_europe_pmc_sections, read_europe_pmc_section):
    server.add_tool(function, name=function.__name__,
                    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))

try:
    _scholar_limit = int(os.environ.get("SERPAPI_MONTHLY_SEARCH_BUDGET", "0"))
    _scholar_enabled = bool(os.environ.get("SERPAPI_API_KEY")) and 1 <= _scholar_limit <= 10000
except ValueError:
    _scholar_enabled = False
if _scholar_enabled:
    server.add_tool(search_google_scholar, name="search_google_scholar",
                    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True))


if __name__ == "__main__":
    server.run(transport="stdio")
