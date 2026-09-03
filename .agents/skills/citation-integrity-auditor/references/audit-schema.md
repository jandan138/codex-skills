# Citation audit schemas and CLI contract

## Human support ledger

Use JSON schema version `citation-support-v1`:

```json
{
  "schema_version": "citation-support-v1",
  "entries": [
    {
      "citation_key": "smith-2025-example",
      "context_sha256": "64 lowercase hex characters",
      "identity_status": "VERIFIED_HUMAN_PRIMARY",
      "source_kind": "paper",
      "source_url": "https://publisher.example/paper",
      "support_status": "SUPPORTED",
      "source_locator": "Section 3, pp. 5–6",
      "evidence_summary": "Short paraphrase of the source evidence bearing on the claim.",
      "checked_by": "author",
      "checked_at": "YYYY-MM-DD",
      "retraction_status": "CLEAR"
    }
  ]
}
```

One entry covers one `(citation_key, context_sha256)` pair. A key cited in two different claims
needs two entries. Grouped citations receive one entry per key. Repeated identity fields may be
factored into top-level `defaults` and `sources`; the script merges them in the order
`defaults < sources[citation_key] < entry`.

Allowed identity decisions: `VERIFIED_HUMAN_PRIMARY`, `NOT_CHECKED`.

Allowed support decisions: `SUPPORTED`, `PARTIAL`, `MISREPRESENTED`, `NOT_CHECKED`,
`RETRACTED_UNDISCLOSED`.

Allowed retraction decisions: `CLEAR`, `CORRECTION_REVIEWED`, `RETRACTED`, `NOT_CHECKED`.

## Machine report

`citation-integrity-audit-v1` contains source paths and SHA-256 values; a deterministic TeX source
set hash; cited keys and contexts; BibTeX metadata; resolver attempts; machine, human, and effective
identity states; support records; findings; and the final verdict.

Machine identity states include `VERIFIED_PRIMARY`, `VERIFIED_CROSS_INDEX`, `DOI_MISMATCH`,
`DOI_UNVERIFIED`, `METADATA_MISMATCH`, `RETRACTED`, `UNRESOLVED`, and
`UNVERIFIED_NETWORK`.

## Matching thresholds

- normalized title similarity ≥0.92 plus year/first-author compatibility: machine pass;
- 0.80–0.92: human review;
- DOI lookup with title similarity below 0.80: blocking `DOI_MISMATCH`;
- declared DOI that cannot be resolved: `DOI_UNVERIFIED`, requiring review unless a human
  primary-source identity attestation covers the DOI;
- year may differ by one for online-first/proceedings publication;
- first-author family name must agree when both sides provide authors.

These thresholds narrow the review queue. They cannot establish semantic support.

## Cache behavior

`--refresh` performs network resolution and updates `citation-metadata-cache-v1`. Without
`--refresh`, the script uses cached results if present and otherwise reports `UNVERIFIED_NETWORK`;
a human primary-source identity attestation may still provide the effective identity state. Never
commit API keys, credentials, or a machine-global cache. Network resolution is bounded by
`--workers` (default 8) and the per-request `--timeout`.
