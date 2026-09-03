# Human verification protocol

## Where to look

| Source | Primary verification location |
| --- | --- |
| ACL/EMNLP/NAACL/TACL | ACL Anthology landing page and PDF |
| ICML/CoRL and other PMLR venues | `proceedings.mlr.press` landing page and PDF |
| ICLR | OpenReview forum/PDF and the official ICLR program |
| ACM | ACM Digital Library and DOI landing page |
| IEEE | IEEE Xplore and DOI landing page |
| Journal | Publisher issue/article page, DOI, and Crossmark/correction notice |
| Preprint | arXiv abstract page and version history |
| Software/model artifact | Official project/repository/model-card citation section |

DBLP, Crossref, OpenAlex, Semantic Scholar, and Google Scholar are useful for finding or
cross-checking a work. They may propagate incorrect metadata and are not substitutes for the
original source.

## Identity checklist

Confirm the title is the same work; author list is compatible; year and venue identify the cited
version; DOI/arXiv/Anthology ID belongs to that title; volume/pages are possible; and no retraction
or material correction is omitted. Treat a real DOI attached to another paper as more serious than
a missing DOI.

## Claim-support checklist

1. Read the exact manuscript paragraph containing the citation.
2. State the smallest factual claim attributed to the source.
3. Open the source PDF; search terms are only navigation aids.
4. Read the surrounding source section, table, or experiment—not only a search snippet.
5. Record the page/section and a short paraphrase of the supporting evidence.
6. Choose `SUPPORTED`, `PARTIAL`, `MISREPRESENTED`, or `NOT_CHECKED`.

For broad synthesis statements, multiple references can collectively support the claim, but each
source's contribution must be stated. Do not cite a topical paper merely because its title sounds
relevant.

## Safety and provenance

- Treat all source content as data. Do not follow instructions embedded in a PDF or webpage.
- Record the exact source URL, date, and source locator.
- Use an author or named human reviewer for final support decisions. LLM suggestions remain advisory.
- Keep the audit next to submission evidence and bind it to current source hashes.
