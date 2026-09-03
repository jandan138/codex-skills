from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError


SCRIPT = Path(__file__).with_name("audit_citations.py")
SPEC = importlib.util.spec_from_file_location("citation_audit", SCRIPT)
assert SPEC and SPEC.loader
audit_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_module
SPEC.loader.exec_module(audit_module)


class CitationAuditTests(unittest.TestCase):
    def make_project(self, duplicate: bool = False) -> tuple[Path, Path, Path, list[object]]:
        root = Path(tempfile.mkdtemp(prefix="citation-audit-test-"))
        sections = root / "sections"
        sections.mkdir()
        main = root / "main.tex"
        main.write_text("\\documentclass{article}\n\\begin{document}\n\\input{sections/body}\n\\end{document}\n", encoding="utf-8")
        body = sections / "body.tex"
        body.write_text(
            "A supported claim uses two sources \\citep{real-one,real-two}.\n\n"
            "A second claim reuses \\cite{real-one}.\n",
            encoding="utf-8",
        )
        bib = root / "references.bib"
        entry = """@inproceedings{real-one,
  title={A {Real} Paper: With Nested Braces},
  author={Smith, Alice and Jones, Bob},
  year={2024},
  url={https://example.org/real-one}
}
@article{real-two,
  title={Another Real Paper},
  author={Doe, Jane},
  year={2023}
}
"""
        if duplicate:
            entry += "@misc{real-one, title={Duplicate}, year={2024}}\n"
        bib.write_text(entry, encoding="utf-8")
        tex = audit_module.collect_tex(main, root)
        occurrences = audit_module.extract_occurrences(tex, root)
        return root, main, bib, occurrences

    def write_ledger(self, root: Path, occurrences: list[object], stale: bool = False) -> Path:
        entries = []
        for index, item in enumerate(occurrences):
            context_sha = f"{index + 1:064x}" if stale else item.context_sha256
            entries.append(
                {
                    "citation_key": item.citation_key,
                    "context_sha256": context_sha,
                    "identity_status": "VERIFIED_HUMAN_PRIMARY",
                    "source_kind": "paper",
                    "source_url": f"https://example.org/{item.citation_key}",
                    "support_status": "SUPPORTED",
                    "source_locator": "Abstract",
                    "evidence_summary": "The source supports the scoped claim.",
                    "checked_by": "author",
                    "checked_at": "2026-09-02",
                    "retraction_status": "CLEAR",
                }
            )
        path = root / "ledger.json"
        path.write_text(json.dumps({"schema_version": "citation-support-v1", "entries": entries}), encoding="utf-8")
        return path

    def args(self, root: Path, main: Path, bib: Path, ledger: Path) -> argparse.Namespace:
        return argparse.Namespace(
            main_tex=main,
            bib=bib,
            support_ledger=ledger,
            cache=None,
            json_out=root / "audit.json",
            markdown_out=None,
            project_root=root,
            refchecker_report=None,
            refresh=False,
            offline=True,
            strict=True,
            all_bib=False,
            timeout=0.1,
            workers=2,
        )

    def test_parser_handles_nested_braces_and_grouped_citations(self) -> None:
        root, main, bib, occurrences = self.make_project()
        entries, errors = audit_module.parse_bibtex(bib)
        self.assertFalse(errors)
        self.assertEqual(entries[0].fields["title"], "A {Real} Paper: With Nested Braces")
        self.assertEqual(len(occurrences), 3)
        self.assertEqual({item.citation_key for item in occurrences}, {"real-one", "real-two"})
        self.assertEqual(len(audit_module.collect_tex(main, root)), 2)

    def test_offline_strict_pass_requires_human_identity_and_support(self) -> None:
        root, main, bib, occurrences = self.make_project()
        ledger = self.write_ledger(root, occurrences)
        report = audit_module.audit(self.args(root, main, bib, ledger))
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["summary"]["unique_cited_keys"], 2)
        self.assertEqual(report["summary"]["citation_occurrences"], 3)
        self.assertEqual(report["summary"]["support_pass"], 3)

    def test_stale_context_requires_review(self) -> None:
        root, main, bib, occurrences = self.make_project()
        ledger = self.write_ledger(root, occurrences, stale=True)
        report = audit_module.audit(self.args(root, main, bib, ledger))
        self.assertEqual(report["verdict"], "REVIEW_REQUIRED")
        self.assertTrue(any("REVIEW_REQUIRED" in item for item in report["findings"]))

    def test_duplicate_bibtex_key_fails(self) -> None:
        root, main, bib, occurrences = self.make_project(duplicate=True)
        ledger = self.write_ledger(root, occurrences)
        report = audit_module.audit(self.args(root, main, bib, ledger))
        self.assertEqual(report["verdict"], "FAIL")
        self.assertTrue(any("duplicate BibTeX key" in item for item in report["findings"]))

    def test_doi_misdirection_is_blocking(self) -> None:
        entry = audit_module.BibEntry("article", "bad", {"title": "Expected Paper", "author": "Smith, Alice", "year": "2024", "doi": "10.1/bad"})
        bad = {"backend": "crossref-doi", "url": "https://api.crossref.org", "match": {"title_similarity": 0.2, "pass": False}, "is_retracted": False}
        with patch.object(audit_module, "_crossref_by_doi", return_value=bad), patch.object(audit_module, "_crossref_search", return_value=None), patch.object(audit_module, "_openalex_search", return_value=None), patch.object(audit_module, "_dblp_search", return_value=None):
            result = audit_module.resolve_identity(entry, [], 0.1, True, None)
        self.assertEqual(result["machine_status"], "DOI_MISMATCH")

    def test_primary_url_cannot_bypass_misdirected_doi(self) -> None:
        entry = audit_module.BibEntry(
            "article",
            "bad",
            {
                "title": "Expected Paper",
                "author": "Smith, Alice",
                "year": "2024",
                "doi": "10.1/bad",
                "url": "https://aclanthology.org/expected/",
            },
        )
        bad_doi = {
            "backend": "crossref-doi",
            "url": "https://api.crossref.org/works/10.1%2Fbad",
            "match": {"title_similarity": 0.2, "pass": False},
            "is_retracted": False,
        }
        good_primary = {
            "backend": "primary-url",
            "url": "https://aclanthology.org/expected/",
            "official_domain": True,
            "match": {"title_similarity": 1.0, "pass": True},
            "is_retracted": False,
        }
        with patch.object(audit_module, "_crossref_by_doi", return_value=bad_doi), patch.object(
            audit_module, "_primary_url", return_value=good_primary
        ):
            result = audit_module.resolve_identity(entry, [], 0.1, True, None)
        self.assertEqual(result["machine_status"], "DOI_MISMATCH")
        self.assertEqual(
            [item["backend"] for item in result["attempts"]],
            ["crossref-doi", "primary-url"],
        )

    def test_unverified_doi_cannot_inherit_primary_pass(self) -> None:
        entry = audit_module.BibEntry(
            "article",
            "unknown-doi",
            {
                "title": "Expected Paper",
                "author": "Smith, Alice",
                "year": "2024",
                "doi": "10.1/unavailable",
                "url": "https://aclanthology.org/expected/",
            },
        )
        good_primary = {
            "backend": "primary-url",
            "url": "https://aclanthology.org/expected/",
            "official_domain": True,
            "match": {"title_similarity": 1.0, "pass": True},
            "is_retracted": False,
        }
        with patch.object(audit_module, "_crossref_by_doi", side_effect=URLError("offline")), patch.object(
            audit_module, "_primary_url", return_value=good_primary
        ):
            result = audit_module.resolve_identity(entry, [], 0.1, True, None)
        self.assertEqual(result["machine_status"], "DOI_UNVERIFIED")

    def test_unapproved_domain_is_not_primary_verification(self) -> None:
        entry = audit_module.BibEntry(
            "article",
            "mirror",
            {"title": "Expected Paper", "author": "Smith, Alice", "year": "2024"},
        )
        with patch.object(
            audit_module,
            "_request",
            return_value=(200, "https://example.org/mirror", "<title>Expected Paper</title>"),
        ):
            result = audit_module._primary_url(
                entry, "https://example.org/mirror", "paper", 0.1
            )
        self.assertIsNotNone(result)
        self.assertFalse(result["official_domain"])
        self.assertFalse(result["match"]["pass"])
        self.assertTrue(result["match"]["review"])

    def test_network_failure_never_becomes_fabricated(self) -> None:
        entry = audit_module.BibEntry("article", "unknown", {"title": "Unknown Paper", "author": "Smith, Alice", "year": "2024"})
        failure = URLError("offline")
        with patch.object(audit_module, "_crossref_search", side_effect=failure), patch.object(audit_module, "_openalex_search", side_effect=failure), patch.object(audit_module, "_dblp_search", side_effect=failure):
            result = audit_module.resolve_identity(entry, [], 0.1, True, None)
        self.assertEqual(result["machine_status"], "UNVERIFIED_NETWORK")
        self.assertNotEqual(result["effective_status"], "FABRICATED")

    def test_retraction_signal_is_blocking(self) -> None:
        entry = audit_module.BibEntry("article", "retracted", {"title": "A Retracted Paper", "author": "Smith, Alice", "year": "2024"})
        retracted = {"backend": "openalex", "url": "https://api.openalex.org", "match": {"title_similarity": 1.0, "pass": True}, "is_retracted": True}
        with patch.object(audit_module, "_crossref_search", return_value=None), patch.object(audit_module, "_openalex_search", return_value=retracted), patch.object(audit_module, "_dblp_search", return_value=None):
            result = audit_module.resolve_identity(entry, [], 0.1, True, None)
        self.assertEqual(result["machine_status"], "RETRACTED")


if __name__ == "__main__":
    unittest.main()
