# Scientific Figure QA Rubric

Use this rubric for reference reproductions, new pipeline diagrams, architecture figures,
multi-panel results, and figures exported to slides or papers. Review the editable source and
the final rendered artifact; neither view alone is sufficient.

## Contents

- [Required evidence](#required-evidence)
- [Verdict and severity](#verdict-and-severity)
- [Semantics](#1-semantics)
- [Topology](#2-topology)
- [Geometry](#3-geometry)
- [Style](#4-style)
- [Rendering](#5-rendering)
- [Sources and provenance](#6-sources-and-provenance)
- [Final inspection sequence](#final-inspection-sequence)

## Required evidence

Collect these items before scoring:

- The user's brief and, when applicable, the reference figure at its native resolution.
- The editable source and the exact final deliverable (`.svg`, `.pdf`, `.pptx`, or raster image).
- A 1x full-figure render and a 2x render or close-up of dense regions.
- A source manifest for data, renders, icons, fonts, logos, and AI-generated material.
- For a reproduction, an overlay or side-by-side comparison at the same canvas size.

If required evidence is unavailable, mark affected checks `NE` (not evidenced), not `Pass`.

## Verdict and severity

Assign every finding one severity:

- **Critical**: changes scientific meaning, reverses or invents a connection, reports an
  unsupported value, uses an unsafe asset, or violates a license. It blocks delivery.
- **Major**: impairs reading order, hides important content, materially differs from an approved
  reference, or fails in the target renderer. It blocks delivery until fixed.
- **Minor**: visible polish or consistency defect that does not change meaning.

Score each dimension from 0 to 5, then apply its weight. A figure passes only when all hard gates
pass, no Critical or Major findings remain, and the weighted score is at least 90/100.

| Dimension | Weight | Hard gate |
| --- | ---: | :---: |
| Semantics | 25 | Yes |
| Topology | 20 | Yes |
| Geometry | 15 | No |
| Style | 15 | No |
| Rendering | 15 | Yes |
| Sources and provenance | 10 | Yes |

Use `Conditional` only for a score of 80--89 with no hard-gate failure and a written list of
remaining Minor findings. Otherwise use `Fail`.

## 1. Semantics

- State the figure's one-sentence message. Verify that the visual hierarchy supports it.
- Verify every title, label, legend entry, unit, count, equation, acronym, and task name against
  the supplied source. Do not silently infer missing scientific facts.
- Confirm that colors, shapes, line styles, and panel positions have one stable meaning.
- Check reading order at final size without relying on zoom or surrounding prose.
- Confirm that examples and screenshots belong to the panel and condition they claim to show.
- Check that decorative AI-generated elements do not imply nonexistent measurements, hardware,
  capabilities, or causal relationships.
- Make distinctions accessible without color alone when the distinction is scientifically
  important; add labels, shapes, or line styles as needed.

**Hard-gate failures:** wrong scientific claim, wrong number or unit, ambiguous legend that can
invert interpretation, missing required condition, or fabricated evidence.

## 2. Topology

Treat topology as a graph before judging appearance. Inventory nodes, ports, junctions, edges,
and arrow directions in plain text.

- Verify each edge's semantic start, end, and direction against the brief or reference.
- Distinguish true edges from braces, grouping brackets, panel borders, timelines, and internal
  motion indicators.
- Check every branch and merge. A T-junction must be intentional and visually connected; crossing
  edges without a junction must remain visibly separate.
- Put arrowheads only on directed terminal edges. Do not add arrowheads to undirected braces or
  source branches unless the semantics require them.
- Confirm that feedback loops are real, close at the intended ports, and do not accidentally join
  nearby edges.
- Trace every long connector end to end at high zoom. Reject floating ends, hidden segments,
  reversed arrows, doubled lines, and connectors that terminate on whitespace.
- Keep panel-internal arrows separate from inter-panel dataflow.

For reference reproductions, record important ports and junctions as canvas coordinates. Compare
them before and after rendering; a visually similar curve with the wrong endpoint is still a
topology failure.

**Hard-gate failures:** missing, invented, reversed, merged, or split scientific relationships;
an arrow landing on the wrong node; or a grouping brace represented as a directed edge.

## 3. Geometry

- Match the requested canvas size and aspect ratio. Use one coordinate system consistently.
- Check the primary grid, column widths, panel heights, gutters, margins, and visual center.
- Verify repeated components with numeric alignment and distribution, not visual guessing alone.
- Keep padding consistent within component families; align titles, icons, media slots, and labels.
- Check connector tracks, bend radii, line caps, joins, junction positions, and arrowhead landing
  points. Maintain clear routing gutters.
- Inspect all crops. Preserve the robot, end effector, manipulated object, plotted extrema, axes,
  and labels that carry meaning.
- Reject overlaps, clipped text, objects outside the canvas, accidental tangencies, and tiny gaps
  at supposedly joined paths.

For pixel-matched reproduction at native size, target important ports and arrow tips within 2 px,
repeated alignments within 2 px, and major panel bounds within 0.5% of the canvas dimension unless
the user requests a looser match. Judge optical centering separately from numeric centering.

## 4. Style

- Preserve a deliberate hierarchy of title bars, panel titles, annotations, and captions.
- Use the approved palette consistently and verify contrast on both light and dark media.
- Match font family, weight, case, line spacing, and numeric formatting within each component
  family. Avoid unintended fallback fonts.
- Normalize stroke widths, corner radii, dash patterns, arrowhead families, line caps, and joins.
- Keep icon abstraction and detail density consistent. Enclose heterogeneous icons in a shared
  card or badge system when necessary.
- Prefer vector shapes for framework, text, icons, and connectors; use raster images for genuine
  renders, photographs, or dense contact sheets.
- Avoid stylistic cleanup that changes an approved reference's information hierarchy.

## 5. Rendering

- Render through the actual target application or conversion path, not only the authoring preview.
- Re-open the delivered file and render it again to catch round-trip changes.
- Inspect at full-figure final size and at 200% for missing glyphs, font substitution, broken SVGs,
  jagged strokes, transparency halos, clipping, and changed line breaks.
- Confirm SVG paths, masks, gradients, and arrowheads survive import and export. Prefer explicit
  geometry when marker behavior changes across renderers.
- Check z-order: connectors must not disappear behind panels, and annotations must not cover data.
- Verify raster resolution and crop quality; do not upscale low-resolution evidence without
  disclosure.
- Test the required background, including transparent or dark backgrounds when applicable.

**Hard-gate failures:** required content missing or unreadable in the final artifact, corrupted
file, unsafe SVG accepted into the output, or target renderer materially changing meaning.

## 6. Sources and provenance

- Record each non-original asset's creator or repository, direct source, license or permission,
  and any modifications. Preserve attribution where required.
- Record each dataset, benchmark, metric, and quoted number with version/date and a traceable
  source. Prefer primary sources.
- Mark AI-generated icons or illustrations as generated; retain the generator/model, date, prompt
  or design brief, and subsequent manual edits when available. Do not claim a generated element is
  an official logo, measured result, or source-authored asset.
- Record the origin and capture context of simulation renders and screenshots, including relevant
  simulator/project version when known.
- Do not embed unknown fonts, logos, proprietary renders, or third-party figures without a
  documented right to use them.
- Run untrusted SVG files through `scripts/sanitize_svg.py` before insertion. Keep the original
  outside the deliverable and use only the resulting safe copy.

**Hard-gate failures:** untraceable scientific evidence, license conflict, misleading provenance,
or untrusted active/external SVG content.

## Final inspection sequence

1. Read the one-sentence message and verify Semantics without looking at style.
2. Trace the complete node-edge graph and verify Topology.
3. Overlay or measure Geometry.
4. Review Style at normal viewing size.
5. Re-open and inspect the final Rendering at 1x and 2x.
6. Audit Sources and provenance, then assign the verdict.

For an editable PPTX, also run `scripts/audit_pptx_figure.py` and retain its JSON output. Treat
unexpected font-size proliferation, near-total bolding, default roundness across unrelated card
classes, nonzero theme effects, and machine-path hits as review findings. Numeric complexity budgets
are contextual; they never override scientific completeness or readable source text.

When a title or child object is placed near a rounded panel corner, verify containment against the
visible rounded outline. Bounding-box containment alone is insufficient.

Log findings as:

```text
ID | category | severity | page/panel and coordinates | expected | observed | fix | status
```

Do not close a finding based only on the editable source. Close it after inspecting a fresh render
of the delivered artifact.
