# Repository guidance

- Place reusable Codex skills under `.agents/skills/<skill-name>/`.
- Treat each skill's `SKILL.md` as its public workflow contract.
- Keep source specifications and deterministic scripts separate from generated PNG, PDF, PPTX,
  browser-profile, cache, and QA-output directories.
- Do not commit papers, experiment data, credentials, machine-specific absolute paths, or copied
  third-party figures unless the user explicitly authorizes redistribution.
- Preserve Linux portability: Python 3.10+, POSIX-friendly relative paths, UTF-8, open fonts, and no
  Office/COM dependency in a canonical workflow.
- Before committing a skill change, run its structural validation, script syntax checks, strict
  example-spec validation, and a representative forward test.
- When changing an edge schema or topology rule, update the schema, validator, renderer, examples,
  and arrow documentation together.
