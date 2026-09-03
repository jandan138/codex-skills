#!/usr/bin/env python3
"""Audit cited BibTeX identities and human claim-support attestations."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


AUDIT_SCHEMA = "citation-integrity-audit-v1"
LEDGER_SCHEMA = "citation-support-v1"
CACHE_SCHEMA = "citation-metadata-cache-v1"
SCRIPT_VERSION = "1.0.1"
OFFICIAL_DOMAINS = {
    "aclanthology.org",
    "academic.oup.com",
    "arxiv.org",
    "dl.acm.org",
    "doi.org",
    "github.com",
    "ieeexplore.ieee.org",
    "iclr.cc",
    "jmlr.org",
    "openreview.net",
    "proceedings.mlr.press",
    "www.microsoft.com",
}
MACHINE_PASS = {"VERIFIED_PRIMARY", "VERIFIED_CROSS_INDEX"}
HUMAN_IDENTITY_PASS = {"VERIFIED_HUMAN_PRIMARY"}
SUPPORT_PASS = {"SUPPORTED"}
FAIL_IDENTITY = {"FABRICATED", "DOI_MISMATCH", "METADATA_MISMATCH", "RETRACTED"}
FAIL_SUPPORT = {"MISREPRESENTED", "RETRACTED_UNDISCLOSED"}


@dataclass(frozen=True)
class BibEntry:
    entry_type: str
    key: str
    fields: dict[str, str]


@dataclass(frozen=True)
class CitationOccurrence:
    citation_key: str
    source_path: str
    paragraph_index: int
    context: str
    context_sha256: str
    occurrence_id: str


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def strip_tex_comments(value: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", value)


def normalize_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("---", "-").replace("--", "-")
    value = re.sub(r"\\(?:texttt|textit|emph|url|href|mbox|mathrm|mathbf)\s*\{([^{}]*)\}", r"\1", value)
    value = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?", " ", value)
    value = value.replace("{", "").replace("}", "").replace("~", " ")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def normalize_context(value: str) -> str:
    value = re.sub(r"\\cite\w*\s*(?:\[[^\]]*\]\s*)*\{[^}]+\}", " ", value)
    value = re.sub(r"\\(?:label|ref|pageref)\{[^}]+\}", " ", value)
    return normalize_text(value)


def title_similarity(left: str, right: str) -> float:
    a, b = normalize_text(left), normalize_text(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def family_name(author: str) -> str:
    author = re.sub(r"[{}]", "", author).strip()
    if "," in author:
        value = author.split(",", 1)[0]
    else:
        value = author.split()[-1] if author.split() else ""
    return normalize_text(value)


def bib_authors(entry: BibEntry) -> list[str]:
    return [family_name(item) for item in re.split(r"\s+and\s+", entry.fields.get("author", "")) if family_name(item)]


def _consume_braced(text: str, index: int) -> tuple[str, int]:
    if index >= len(text) or text[index] != "{":
        raise ValueError("expected braced BibTeX value")
    depth, cursor = 1, index + 1
    while cursor < len(text) and depth:
        if text[cursor] == "{" and (cursor == 0 or text[cursor - 1] != "\\"):
            depth += 1
        elif text[cursor] == "}" and (cursor == 0 or text[cursor - 1] != "\\"):
            depth -= 1
        cursor += 1
    if depth:
        raise ValueError("unterminated braced BibTeX value")
    return text[index + 1 : cursor - 1], cursor


def _consume_quoted(text: str, index: int) -> tuple[str, int]:
    cursor = index + 1
    output: list[str] = []
    while cursor < len(text):
        if text[cursor] == '"' and text[cursor - 1] != "\\":
            return "".join(output), cursor + 1
        output.append(text[cursor])
        cursor += 1
    raise ValueError("unterminated quoted BibTeX value")


def parse_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    cursor = 0
    while cursor < len(body):
        while cursor < len(body) and (body[cursor].isspace() or body[cursor] == ","):
            cursor += 1
        if cursor >= len(body):
            break
        match = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body[cursor:])
        if not match:
            next_comma = body.find(",", cursor)
            cursor = len(body) if next_comma < 0 else next_comma + 1
            continue
        name = match.group(1).casefold()
        cursor += match.end()
        if cursor < len(body) and body[cursor] == "{":
            value, cursor = _consume_braced(body, cursor)
        elif cursor < len(body) and body[cursor] == '"':
            value, cursor = _consume_quoted(body, cursor)
        else:
            end = body.find(",", cursor)
            end = len(body) if end < 0 else end
            value, cursor = body[cursor:end].strip(), end
        fields[name] = value.strip()
    return fields


def parse_bibtex(path: Path) -> tuple[list[BibEntry], list[str]]:
    text = path.read_text(encoding="utf-8")
    entries: list[BibEntry] = []
    errors: list[str] = []
    cursor = 0
    while True:
        match = re.search(r"@([A-Za-z]+)\s*\{", text[cursor:])
        if not match:
            break
        entry_type = match.group(1).casefold()
        start = cursor + match.end() - 1
        try:
            payload, end = _consume_braced(text, start)
        except ValueError as exc:
            errors.append(f"BibTeX entry near byte {start}: {exc}")
            break
        comma = payload.find(",")
        if comma < 0:
            errors.append(f"BibTeX entry near byte {start} has no key separator")
        else:
            key = payload[:comma].strip()
            entries.append(BibEntry(entry_type=entry_type, key=key, fields=parse_fields(payload[comma + 1 :])))
        cursor = end
    return entries, errors


def _resolve_input(current: Path, target: str) -> Path:
    candidate = current.parent / target
    if candidate.suffix == "":
        candidate = candidate.with_suffix(".tex")
    return candidate.resolve()


def collect_tex(main_tex: Path, project_root: Path) -> dict[Path, str]:
    collected: dict[Path, str] = {}

    def visit(path: Path) -> None:
        path = path.resolve()
        if path in collected:
            return
        text = path.read_text(encoding="utf-8")
        collected[path] = text
        clean = strip_tex_comments(text)
        for target in re.findall(r"\\(?:input|include)\{([^}]+)\}", clean):
            child = _resolve_input(path, target)
            if child.is_file():
                visit(child)

    visit(main_tex.resolve())
    return collected


def relative_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def extract_occurrences(tex_files: Mapping[Path, str], project_root: Path) -> list[CitationOccurrence]:
    occurrences: list[CitationOccurrence] = []
    for path in sorted(tex_files, key=lambda item: item.as_posix()):
        clean = strip_tex_comments(tex_files[path])
        paragraphs = re.split(r"\n\s*\n", clean)
        for paragraph_index, paragraph in enumerate(paragraphs, start=1):
            context = " ".join(paragraph.split())
            context_normalized = normalize_context(context)
            context_sha = sha256_bytes(context_normalized.encode("utf-8"))
            for match in re.finditer(r"\\cite\w*\s*(?:\[[^\]]*\]\s*)*\{([^}]+)\}", paragraph):
                for key in (item.strip() for item in match.group(1).split(",")):
                    if not key:
                        continue
                    occurrence_id = f"{key}:{context_sha[:16]}"
                    occurrences.append(
                        CitationOccurrence(
                            citation_key=key,
                            source_path=relative_path(path, project_root),
                            paragraph_index=paragraph_index,
                            context=context,
                            context_sha256=context_sha,
                            occurrence_id=occurrence_id,
                        )
                    )
    return occurrences


def _request(url: str, timeout: float) -> tuple[int, str, str]:
    request = Request(url, headers={"User-Agent": "citation-integrity-auditor/1.0 (research verification)"})
    with urlopen(request, timeout=timeout) as response:
        body = response.read(2_000_000).decode("utf-8", errors="replace")
        return int(response.status), response.geturl(), body


def _json_request(url: str, timeout: float) -> Any:
    _status, _final_url, body = _request(url, timeout)
    return json.loads(body)


def _html_title(body: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.I | re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", match.group(1))).strip() if match else ""


def _metadata_match(entry: BibEntry, title: str, authors: Sequence[str], year: int | None) -> dict[str, Any]:
    similarity = title_similarity(entry.fields.get("title", ""), title)
    cited_year = int(entry.fields["year"]) if entry.fields.get("year", "").isdigit() else None
    year_ok = cited_year is None or year is None or abs(cited_year - year) <= 1
    cited_authors = bib_authors(entry)
    returned_authors = [normalize_text(item) for item in authors if normalize_text(item)]
    first_author_ok = not cited_authors or not returned_authors or cited_authors[0] == returned_authors[0]
    return {
        "title": title,
        "title_similarity": round(similarity, 6),
        "year": year,
        "year_ok": year_ok,
        "authors": list(authors),
        "first_author_ok": first_author_ok,
        "pass": similarity >= 0.92 and year_ok and first_author_ok,
        "review": 0.80 <= similarity < 0.92 and year_ok,
    }


def _crossref_by_doi(entry: BibEntry, timeout: float) -> dict[str, Any] | None:
    doi = entry.fields.get("doi", "").strip()
    if not doi:
        return None
    url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    payload = _json_request(url, timeout)["message"]
    title = (payload.get("title") or [""])[0]
    authors = [item.get("family", "") for item in payload.get("author", [])]
    parts = (payload.get("published-print") or payload.get("published-online") or {}).get("date-parts", [])
    year = int(parts[0][0]) if parts and parts[0] else None
    return {"backend": "crossref-doi", "url": url, "match": _metadata_match(entry, title, authors, year), "is_retracted": False}


def _crossref_search(entry: BibEntry, timeout: float) -> dict[str, Any] | None:
    params = urlencode({"query.title": entry.fields.get("title", ""), "rows": 3})
    url = f"https://api.crossref.org/works?{params}"
    items = _json_request(url, timeout)["message"].get("items", [])
    matches = []
    for item in items:
        title = (item.get("title") or [""])[0]
        authors = [author.get("family", "") for author in item.get("author", [])]
        parts = (item.get("published-print") or item.get("published-online") or {}).get("date-parts", [])
        year = int(parts[0][0]) if parts and parts[0] else None
        matches.append(_metadata_match(entry, title, authors, year))
    best = max(matches, key=lambda item: item["title_similarity"], default=None)
    return {"backend": "crossref-search", "url": url, "match": best, "is_retracted": False} if best else None


def _openalex_search(entry: BibEntry, timeout: float) -> dict[str, Any] | None:
    params = urlencode({"search": entry.fields.get("title", ""), "per-page": 3})
    url = f"https://api.openalex.org/works?{params}"
    matches = []
    retracted = False
    for item in _json_request(url, timeout).get("results", []):
        authors = [auth.get("author", {}).get("display_name", "").split()[-1] for auth in item.get("authorships", []) if auth.get("author", {}).get("display_name")]
        matches.append(_metadata_match(entry, item.get("title", ""), authors, item.get("publication_year")))
        retracted = retracted or bool(item.get("is_retracted"))
    best = max(matches, key=lambda item: item["title_similarity"], default=None)
    return {"backend": "openalex", "url": url, "match": best, "is_retracted": retracted} if best else None


def _dblp_search(entry: BibEntry, timeout: float) -> dict[str, Any] | None:
    params = urlencode({"q": entry.fields.get("title", ""), "h": 3, "format": "json"})
    url = f"https://dblp.org/search/publ/api?{params}"
    hits = _json_request(url, timeout).get("result", {}).get("hits", {}).get("hit", [])
    matches = []
    for hit in hits:
        info = hit.get("info", {})
        authors_raw = info.get("authors", {}).get("author", [])
        if isinstance(authors_raw, Mapping):
            authors_raw = [authors_raw]
        authors = []
        for author in authors_raw:
            value = author.get("text", "") if isinstance(author, Mapping) else str(author)
            authors.append(value.split()[-1] if value else "")
        year = int(info["year"]) if str(info.get("year", "")).isdigit() else None
        matches.append(_metadata_match(entry, info.get("title", ""), authors, year))
    best = max(matches, key=lambda item: item["title_similarity"], default=None)
    return {"backend": "dblp", "url": url, "match": best, "is_retracted": False} if best else None


def _primary_url(entry: BibEntry, source_url: str, source_kind: str, timeout: float) -> dict[str, Any] | None:
    if not source_url:
        return None
    status, final_url, body = _request(source_url, timeout)
    domain = urlparse(final_url).netloc.casefold().removeprefix("www.")
    page_title = _html_title(body)
    similarity = max(title_similarity(entry.fields.get("title", ""), page_title), title_similarity(entry.fields.get("title", ""), body[:200_000]))
    official_domain = domain in OFFICIAL_DOMAINS
    software_ok = source_kind == "software" and official_domain and status == 200
    title_ok = official_domain and similarity >= 0.92
    return {
        "backend": "primary-url",
        "url": final_url,
        "official_domain": official_domain,
        "http_status": status,
        "match": {
            "title": page_title,
            "title_similarity": round(similarity, 6),
            "pass": title_ok or software_ok,
            "review": similarity >= 0.80 and not (title_ok or software_ok),
        },
        "is_retracted": False,
    }


def resolve_identity(entry: BibEntry, ledger_records: Sequence[Mapping[str, Any]], timeout: float, refresh: bool, cached: Mapping[str, Any] | None) -> dict[str, Any]:
    if not refresh and cached:
        return dict(cached)
    record = ledger_records[0] if ledger_records else {}
    if not refresh:
        human_identity = str(record.get("identity_status") or "NOT_CHECKED")
        return {
            "machine_status": "UNVERIFIED_NETWORK",
            "human_identity_status": human_identity,
            "effective_status": human_identity,
            "checked_at": utc_now(),
            "attempts": [],
            "errors": ["network refresh not requested and no cached result is available"],
        }
    attempts: list[dict[str, Any]] = []
    errors: list[str] = []
    source_url = str(record.get("source_url") or entry.fields.get("url") or "")
    source_kind = str(record.get("source_kind") or "paper")
    resolvers = []
    doi_declared = bool(entry.fields.get("doi"))
    # A declared DOI is an identity constraint, not merely another discovery hint.
    # Resolve it before any landing-page success can terminate the cascade.
    if doi_declared:
        resolvers.append(lambda: _crossref_by_doi(entry, timeout))
    if source_url:
        resolvers.append(lambda: _primary_url(entry, source_url, source_kind, timeout))
    resolvers.extend((lambda: _crossref_search(entry, timeout), lambda: _openalex_search(entry, timeout), lambda: _dblp_search(entry, timeout)))
    for resolver in resolvers:
        try:
            result = resolver()
            if result:
                attempts.append(result)
                if result.get("is_retracted"):
                    break
                if result.get("backend") == "crossref-doi" and result.get("match", {}).get("pass") and not source_url:
                    break
                if result.get("backend") == "primary-url" and result.get("match", {}).get("pass"):
                    break
        except (HTTPError, URLError, TimeoutError, OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    if any(item.get("is_retracted") for item in attempts):
        machine_status = "RETRACTED"
    else:
        doi_attempt = next((item for item in attempts if item.get("backend") == "crossref-doi"), None)
        if doi_attempt and not doi_attempt.get("match", {}).get("pass"):
            machine_status = "DOI_MISMATCH" if doi_attempt.get("match", {}).get("title_similarity", 0.0) < 0.80 else "METADATA_MISMATCH"
        elif doi_declared and doi_attempt is None:
            machine_status = "DOI_UNVERIFIED"
        elif any(item.get("backend") == "primary-url" and item.get("match", {}).get("pass") for item in attempts):
            machine_status = "VERIFIED_PRIMARY"
        elif any(item.get("backend") == "crossref-doi" and item.get("match", {}).get("pass") for item in attempts):
            machine_status = "VERIFIED_PRIMARY"
        elif sum(bool(item.get("match", {}).get("pass")) for item in attempts) >= 2:
            machine_status = "VERIFIED_CROSS_INDEX"
        elif attempts:
            machine_status = "UNRESOLVED"
        else:
            machine_status = "UNVERIFIED_NETWORK"
    human_identity = str(record.get("identity_status") or "NOT_CHECKED")
    effective = machine_status if machine_status in MACHINE_PASS | FAIL_IDENTITY else human_identity
    return {
        "machine_status": machine_status,
        "human_identity_status": human_identity,
        "effective_status": effective,
        "checked_at": utc_now(),
        "attempts": attempts,
        "errors": errors,
    }


def load_json(path: Path | None, expected_schema: str | None = None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    if expected_schema and payload.get("schema_version") != expected_schema:
        raise ValueError(f"expected {expected_schema} in {path}")
    return payload


def _ledger_index(payload: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    output: dict[tuple[str, str], Mapping[str, Any]] = {}
    defaults = payload.get("defaults", {}) if isinstance(payload.get("defaults", {}), Mapping) else {}
    sources = payload.get("sources", {}) if isinstance(payload.get("sources", {}), Mapping) else {}
    for item in payload.get("entries", []):
        if not isinstance(item, Mapping):
            continue
        citation_key = str(item.get("citation_key", ""))
        source = sources.get(citation_key, {}) if isinstance(sources.get(citation_key, {}), Mapping) else {}
        merged = {**defaults, **source, **item}
        key = (citation_key, str(item.get("context_sha256", "")))
        if key in output:
            raise ValueError(f"duplicate support-ledger entry: {key}")
        output[key] = merged
    return output


def build_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Citation Integrity Audit",
        "",
        f"Verdict: **{report['verdict']}**",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Unique cited keys | {summary['unique_cited_keys']} |",
        f"| Citation occurrences | {summary['citation_occurrences']} |",
        f"| Identity pass | {summary['identity_pass']} |",
        f"| Support pass | {summary['support_pass']} |",
        f"| Review required | {summary['review_required']} |",
        f"| Failures | {summary['failures']} |",
        "",
        "## References",
        "",
        "| Key | Identity | Machine | Support occurrences |",
        "| --- | --- | --- | ---: |",
    ]
    for item in report["references"]:
        lines.append(f"| `{item['citation_key']}` | {item['identity']['effective_status']} | {item['identity']['machine_status']} | {item['support_pass_count']}/{item['occurrence_count']} |")
    if report["findings"]:
        lines.extend(("", "## Findings", ""))
        lines.extend(f"- {item}" for item in report["findings"])
    lines.extend(("", "Machine resolution narrows the review surface; it does not replace author verification of each cited claim.", ""))
    return "\n".join(lines)


def audit(args: argparse.Namespace) -> dict[str, Any]:
    main_tex = args.main_tex.resolve()
    bib_path = args.bib.resolve()
    project_root = args.project_root.resolve() if args.project_root else Path.cwd().resolve()
    tex_files = collect_tex(main_tex, project_root)
    occurrences = extract_occurrences(tex_files, project_root)
    cited_keys = sorted({item.citation_key for item in occurrences})
    entries, bib_errors = parse_bibtex(bib_path)
    key_map: dict[str, BibEntry] = {}
    duplicate_keys: list[str] = []
    for entry in entries:
        if entry.key in key_map:
            duplicate_keys.append(entry.key)
        else:
            key_map[entry.key] = entry
    missing_keys = sorted(set(cited_keys) - set(key_map))
    selected_keys = sorted(key_map) if args.all_bib else cited_keys

    ledger_payload = load_json(args.support_ledger, LEDGER_SCHEMA) if args.support_ledger else {}
    ledger_index = _ledger_index(ledger_payload)
    records_by_key: dict[str, list[Mapping[str, Any]]] = {}
    for (key, _context), record in ledger_index.items():
        records_by_key.setdefault(key, []).append(record)
    cache_payload = load_json(args.cache, CACHE_SCHEMA) if args.cache and args.cache.is_file() else {"schema_version": CACHE_SCHEMA, "entries": {}}
    cache_entries = cache_payload.setdefault("entries", {})

    identity_by_key: dict[str, dict[str, Any]] = {}
    resolvable_keys = [key for key in selected_keys if key in key_map]
    with ThreadPoolExecutor(max_workers=max(1, args.workers), thread_name_prefix="citation-resolver") as executor:
        futures = {
            executor.submit(
                resolve_identity,
                key_map[key],
                records_by_key.get(key, []),
                args.timeout,
                args.refresh,
                cache_entries.get(key),
            ): key
            for key in resolvable_keys
        }
        for future in as_completed(futures):
            key = futures[future]
            identity_by_key[key] = future.result()
            cache_entries[key] = identity_by_key[key]

    references: list[dict[str, Any]] = []
    findings: list[str] = []
    failure_count = 0
    review_count = 0
    identity_pass_count = 0
    support_pass_count = 0
    for key in selected_keys:
        entry = key_map.get(key)
        if entry is None:
            continue
        identity = identity_by_key[key]
        key_occurrences = [item for item in occurrences if item.citation_key == key]
        support_records = []
        for occurrence in key_occurrences:
            record = ledger_index.get((key, occurrence.context_sha256))
            status = str(record.get("support_status")) if record else "NOT_CHECKED"
            support_records.append({"occurrence": asdict(occurrence), "status": status, "ledger": dict(record) if record else None})
        effective_identity = identity["effective_status"]
        identity_pass = effective_identity in MACHINE_PASS | HUMAN_IDENTITY_PASS
        support_ok = bool(support_records) and all(item["status"] in SUPPORT_PASS for item in support_records)
        if identity_pass:
            identity_pass_count += 1
        if support_ok:
            support_pass_count += len(support_records)
        if effective_identity in FAIL_IDENTITY or any(item["status"] in FAIL_SUPPORT for item in support_records):
            failure_count += 1
            findings.append(f"FAIL `{key}`: identity={effective_identity}; support={[item['status'] for item in support_records]}")
        elif not identity_pass or not support_ok:
            review_count += 1
            findings.append(f"REVIEW_REQUIRED `{key}`: identity={effective_identity}; support={[item['status'] for item in support_records]}")
        references.append(
            {
                "citation_key": key,
                "bib_entry_type": entry.entry_type,
                "bib_metadata": entry.fields,
                "identity": identity,
                "occurrence_count": len(key_occurrences),
                "support_pass_count": sum(item["status"] in SUPPORT_PASS for item in support_records),
                "support": support_records,
            }
        )

    for key in missing_keys:
        findings.append(f"FAIL missing BibTeX entry for cited key `{key}`")
    for key in sorted(set(duplicate_keys)):
        findings.append(f"FAIL duplicate BibTeX key `{key}`")
    findings.extend(f"FAIL {item}" for item in bib_errors)
    failure_count += len(missing_keys) + len(set(duplicate_keys)) + len(bib_errors)

    if failure_count:
        verdict = "FAIL"
    elif review_count:
        verdict = "REVIEW_REQUIRED"
    else:
        verdict = "PASS"

    source_files = [
        {"path": relative_path(path, project_root), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in sorted(tex_files, key=lambda item: item.as_posix())
    ]
    combined_digest = hashlib.sha256()
    for item in source_files:
        combined_digest.update(item["path"].encode("utf-8") + b"\0" + item["sha256"].encode("ascii") + b"\n")
    report: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA,
        "script_version": SCRIPT_VERSION,
        "generated_at": utc_now(),
        "mode": "refresh" if args.refresh else "offline-cache",
        "verdict": verdict,
        "inputs": {
            "main_tex": relative_path(main_tex, project_root),
            "bib": {"path": relative_path(bib_path, project_root), "sha256": sha256_file(bib_path)},
            "support_ledger": {"path": relative_path(args.support_ledger.resolve(), project_root), "sha256": sha256_file(args.support_ledger)} if args.support_ledger else None,
            "tex_sources": source_files,
            "manuscript_source_set_sha256": combined_digest.hexdigest(),
            "script_sha256": sha256_file(Path(__file__).resolve()),
        },
        "summary": {
            "cite_commands": sum(len(re.findall(r"\\cite\w*\s*(?:\[[^\]]*\]\s*)*\{[^}]+\}", strip_tex_comments(value))) for value in tex_files.values()),
            "citation_occurrences": len(occurrences),
            "unique_cited_keys": len(cited_keys),
            "identity_pass": identity_pass_count,
            "support_pass": support_pass_count,
            "review_required": review_count,
            "failures": failure_count,
            "unused_bib_entries": len(set(key_map) - set(cited_keys)),
        },
        "cited_keys": cited_keys,
        "occurrences": [asdict(item) for item in occurrences],
        "references": references,
        "findings": findings,
        "refchecker_report": {"path": relative_path(args.refchecker_report.resolve(), project_root), "sha256": sha256_file(args.refchecker_report)} if args.refchecker_report else None,
    }
    if args.cache:
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        args.cache.write_text(json.dumps(cache_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-tex", type=Path, required=True)
    parser.add_argument("--bib", type=Path, required=True)
    parser.add_argument("--support-ledger", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--refchecker-report", type=Path)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--all-bib", action="store_true")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--workers", type=int, default=8)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.refresh and args.offline:
        parser.error("--refresh and --offline are mutually exclusive")
    try:
        report = audit(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"citation audit error: {exc}", file=sys.stderr)
        return 2
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(build_markdown(report), encoding="utf-8")
    print(f"{report['verdict']}: {report['summary']['unique_cited_keys']} keys, {report['summary']['citation_occurrences']} occurrences")
    if report["verdict"] == "FAIL":
        return 2
    if report["verdict"] == "REVIEW_REQUIRED" and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
