# Story-first paper hero figures

Use this reference when creating or simplifying a paper's opening figure, visual abstract, hero
pipeline, or Figure 1. Read `paper-to-figure.md` and `arrow-topology.md` as well when the figure
contains scientific routes.

## Choose one communication job

Before drawing, classify the requested figure as one primary role:

- **story hero**: the paper's central contrast and memorable evidence;
- **method architecture**: ownership, modules, and interfaces;
- **evidence plate**: source renders, observations, or measured outputs;
- **audit ledger**: cases, decisions, provenance, or failure accounting.

Do not silently combine all four. A story hero may contain one bounded evidence witness, but move
complete registries, audit tables, runtime inventories, and long qualifications into a method
figure, caption, or appendix.

Write the communication job as one sentence. If an object does not help a reader understand that
sentence within a few seconds, remove it or move it.

## Model the contrast before styling

For two paths that produce an identical final configuration:

1. keep the distinct sources, policies, decisions, and provenance visible before the merge;
2. use one explicit junction or named integration ports;
3. render the shared physical execution once;
4. terminate blocked or clarification paths before the junction and simulator edge.

Duplicating the same execution sequence for each authority source makes the reader see repetition
before provenance. A single shared witness makes outcome equivalence visible while the incoming
paths preserve why the result is authorized.

## Establish visual hierarchy

- Give the paper's distinctive real render or measured plot the largest continuous visual region.
- Use at most two containment levels in a story hero unless the semantic graph requires more.
- Avoid making every state, policy, result, and note the same rounded card.
- Use short labels in the graphic and move prose to the caption.
- Use saturated color on paths, junctions, and terminal states rather than every card surface.
- Mix regular, medium, and bold roles deliberately. If almost every run is bold, hierarchy has
  collapsed.
- Vary geometry by semantic class. A request, parser, terminal decision, and evidence frame should
  not all share the same corner radius and border weight.

The bundled reference gallery is under
`assets/examples/story-first-hero/reference-gallery/`. Read
`assets/examples/story-first-hero/provenance.json` before use. The
gallery demonstrates visual grammar only; it does not authorize copying another paper's graph,
labels, icons, or layout into a new publication.

## Complexity budgets

Complexity counts are diagnostic, not universal submission rules. For a wide, full-page-width hero
similar to the bundled case study, these are useful starting gates:

- roughly 100 or fewer native shapes;
- roughly 35 or fewer text objects;
- roughly 100 or fewer words inside the graphic;
- no more than four deliberate font sizes;
- a minimum source font that remains legible after scaling to the paper width;
- one clear primary reading route.

If the figure contains real prompt text, annotated examples, or a necessary matrix, higher counts
may be correct. Explain the exception and inspect the actual paper-scale render. Never shrink text
merely to pass a budget.

Run the native PPTX audit:

```bash
python scripts/audit_pptx_figure.py figure.pptx --pretty \
  --single-slide --no-external --require-flat --no-machine-paths \
  --max-shapes 110 --max-text-shapes 35 --max-words 100 \
  --max-font-sizes 4 --min-font-pt 13
```

Adjust the optional numeric limits to the target canvas and paper width. Keep the structural and
portability gates.

## Iteration order

When the author says a figure is still unattractive, iterate in this order:

1. **scientific story**: remove duplicate outcomes and competing figure roles;
2. **reading order**: place inputs, decision, and outcome in causal order;
3. **containment**: remove unnecessary outer panels and nested card families;
4. **typography**: reduce word count, font-size count, and uniform bolding;
5. **routing**: replace diagonal fans with named orthogonal paths;
6. **asset style**: make small icons one coherent family while retaining real evidence as real;
7. **surface polish**: tune fills, radii, border weights, and whitespace;
8. **paper-scale QA**: re-render the exact delivered PPTX and the manuscript page.

Do not spend early rounds polishing a graph that still tells the wrong story.

## Bundled case study and template

`assets/examples/story-first-hero/authority-paths-case-study.pptx` is a project-owned example of
two authorized branches and one blocked branch converging on a shared four-state witness. It is not
a neutral scientific claim template.

`assets/examples/story-first-hero/story-first-hero-template.pptx` replaces project values,
provenance, and render frames with neutral labels and placeholders. Copy it only when its branch,
merge, and execution topology fits the new paper. Reset semantic approval and replace every label,
placeholder, and provenance record.

Use `scripts/create_story_first_template.py` to regenerate the neutral PPTX from the case study.

## Lessons encoded by the case study

- A policy or control input must not enter a component described as policy-blind.
- `CLARIFY` or another non-execution terminal needs an explicit absence label such as `NOT ISSUED`;
  a blank cell looks like missing data.
- Generated component art that is glossy, three-dimensional, or too detailed fails at 48--96 px.
  Prefer one flat academic 2D family and keep labels authoritative.
- Real simulator frames may establish a visible endpoint without establishing physics quality or
  constitutive validity. Put the scientific boundary in the caption.
- A stronger hero often results from moving the full evidence panel and audit matrix to later
  figures, not compressing them inside Figure 1.
