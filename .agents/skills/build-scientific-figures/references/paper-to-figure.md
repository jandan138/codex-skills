# Paper to figure

Use this reference when the task includes a paper PDF, manuscript, supplement, or research notes.

## 1. Extract traceable evidence

Run `scripts/ingest_paper.py` to create page-addressable text and, when useful, page previews. Keep
the emitted SHA-256 manifest with the figure. Cite page and section in every provenance entry rather
than relying on memory. `source_path` is POSIX-style and relative to the manifest directory; keep
the source PDF at that relative location when transferring the evidence bundle.

Read the abstract, introduction claim, method overview, experimental setup, limitations, and the
caption or surrounding text of relevant source figures. Use supplemental material when it changes
the system graph or definitions.

## 2. State the communication job

Write one sentence:

> By the end, **[audience]** should understand **[scientific message]** because the figure shows
> **[minimum required evidence or process]**.

Do not force every method detail into one figure. Choose a primary job such as method overview,
training/data pipeline, inference flow, experimental comparison, ablation result, or deployment
architecture.

## 3. Build a semantic inventory

List before drawing:

- entities or modules;
- inputs and outputs;
- transformations;
- states or time steps;
- branch, merge, feedback, and recurrence relationships;
- observations, actions, datasets, metrics, and results;
- claims, quantities, and units that must appear;
- relationships that remain uncertain.

Name modules using paper terminology. Shorten labels only when the shorter form is unambiguous and
defined in the caption or legend.

## 4. Build the graph before geometry

Create ports and edges independently of layout. Every edge must state `from`, `to`, `scope`,
`meaning`, and `arrowhead`. Read `arrow-topology.md` for sequences, fusion, distribution, feedback,
or long external connectors.

Separate three concepts that are often visually confused:

- containment: a module belongs inside a subsystem;
- ordering: one state or transformation follows another;
- data or control flow: information crosses module boundaries.

A border, bracket, alignment, or nearby arrow does not establish a scientific relationship.

## 5. Map evidence to figure objects

For each panel, text block, asset, and non-obvious edge, add a provenance entry with:

- source file;
- page and section;
- the supported claim;
- affected object ids;
- status: `verified`, `user-provided`, `inferred`, or `unverified`.

Never convert a hypothesis, limitation, or proposed future step into an achieved capability. Never
turn a qualitative statement into a number.

## 6. Design and review

Select `exact`, `inspired`, or `original` using `input-and-modes.md`. Translate the approved graph
into panels, ports, routed edges, assets, and text. Use named placeholders for missing renders.

Before final artwork, present a compact review table:

```text
object/edge | paper evidence | interpretation | status
```

Resolve Critical semantic ambiguity before setting `semantic_graph_approved=true`. After approval,
changes to scientific relationships require a new review; coordinate and style adjustments do not.

## 7. Caption and limitations

Draft a caption from the final graph, not from the reference figure. Define abbreviations, reading
order, line-style semantics, and any generated illustrative elements. Keep caveats that affect
interpretation visible in the caption or figure note.
