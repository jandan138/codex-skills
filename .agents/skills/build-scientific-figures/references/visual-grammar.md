# Visual grammar

Use this reference when designing a figure, selecting a theme, or reviewing a
render. The grammar is intentionally neutral: it provides hierarchy and
scientific clarity without imitating the composition, iconography, or decoration
of any paper.

## Contents

- [Non-negotiable invariants](#non-negotiable-invariants)
- [Composition](#composition)
- [Semantic primitives](#semantic-primitives)
- [Typography](#typography)
- [Color and contrast](#color-and-contrast)
- [Panels and hierarchy](#panels-and-hierarchy)
- [Connectors](#connectors)
- [Assets and originality](#assets-and-originality)
- [Render acceptance](#render-acceptance)

## Non-negotiable invariants

- Treat the figure specification and SVG as authoritative sources. PNG and PDF
  are render products.
- Design on Linux first. Use UTF-8, forward-slash relative asset paths, explicit
  canvas dimensions, and fonts with common Linux substitutes.
- Keep the default template original. A bundled third-party reference figure is allowed only when
  the repository maintainer explicitly authorizes that exact file and its provenance, copyright
  status, and reuse boundary are documented. Keep it separate from original templates and never
  imply that the Skill's license covers it.
- Encode meaning redundantly. Important distinctions need at least two of label,
  geometry, color, line style, and position.
- Prefer stable vector primitives over platform-dependent glyphs, emoji, or
  application-specific effects.
- Make every connector terminate at a declared port. Never use a decorative line
  where a semantic edge is intended.

## Composition

Start with a left-to-right reading order unless the scientific process is
intrinsically cyclic or hierarchical.

1. Reserve 5% of the canvas on every side as a safe margin.
2. Use an 8 px base grid at 1600 x 900; scale it proportionally for other sizes.
3. Allocate one visual region per semantic branch, not per sentence in the
   source material.
4. Keep repeated states equal in size and align them to a shared baseline.
5. Place aggregation after branch outputs and outside branch containers.
6. Put the main result at the terminal reading edge and give it more whitespace,
   not gratuitous decoration.

At 1600 x 900, use gaps of 24-40 px within a group, 64-112 px between major
groups, and at least 56 px between a connector and unrelated text.

## Semantic primitives

| Primitive | Meaning | Default treatment |
| --- | --- | --- |
| Region | A branch, subsystem, or conceptual boundary | Light tint, restrained header, thin stroke |
| State card | A time point, observation, or processing state | White or near-white fill, equal repeated geometry |
| Process card | A transformation | Verb-led title and one short qualifying subtitle |
| Integration card | Evidence aggregation | Warm neutral tint, multiple named input ports |
| Result card | Output, decision, or measured endpoint | Quiet green tint, strong label, no oversized icon |
| Annotation | Assumption, unit, or caveat | Muted text adjacent to the affected element |

Use rounded rectangles for processes and states. Reserve circles for explicit
junctions or stochastic variables; do not use them as generic decoration.

## Typography

- Prefer Noto Sans. Fall back to Liberation Sans, DejaVu Sans, Arial, then the
  generic sans-serif family.
- At 1600 x 900, start with 32 px for the figure title, 18 px for the subtitle,
  18-20 px for panel titles, 14-16 px for card text, and 13-14 px for notes.
- Use only regular, medium, and bold weights. Do not use italics as the sole
  signal for a scientific distinction.
- Keep titles in sentence case. Use nouns for states and results, verbs for
  transformations, and explicit time labels such as t-2, t-1, and t.
- Wrap text deliberately. Never shrink body text below 13 px merely to make a
  sentence fit.

## Color and contrast

Use the semantic palette in assets/default-theme.json. Keep the canvas and most
cards neutral; spend saturated color on relationships and focal states.

- Use blue solid connectors for internal temporal order.
- Use orange dashed connectors for external convergence.
- Use green for terminal results, not for arbitrary emphasis.
- Keep text-to-background contrast at least 4.5:1 for normal text and 3:1 for
  large text.
- Check the figure in grayscale. Labels and line styles must preserve the
  topology when hue disappears.
- Limit a figure to three semantic accents unless the data itself requires more.

Do not use red and green as the only opposing pair. Avoid gradients, glow,
transparency-dependent meaning, and heavy drop shadows in the default style.

## Panels and hierarchy

Use fill and spacing to establish containment; use stroke weight only as a
secondary cue. A containing region must be drawn before its child cards. Keep
corner radii consistent within a semantic class.

Panel subtitles answer one of three questions: what enters, what changes, or what
leaves. If a subtitle does none of these, remove it. Avoid placing prose inside
the flow; move explanations to a caption or numbered callout.

## Connectors

Read references/arrow-topology.md whenever a figure contains a time sequence,
parallel branches, recurrence, or fusion. In particular, never reuse the same
edge style for an internal temporal arrow and an external convergence route.

Prefer orthogonal routes with the fewest bends. A crossing without a junction
does not imply connection; a merge must use an explicit junction or separate
named input ports. Keep arrowheads consistent in size and align endpoints exactly
to ports.

## Assets and originality

Create generic vector schematics from first principles. Use simple geometric
symbols for sensors, models, samples, and outputs. Any external image must have a
documented source and license in provenance and must remain replaceable.

Reference papers may inform facts, labels, and topology. They must not silently
become packaged visual assets. For an inspired figure, change the composition,
visual hierarchy, geometry, palette, and icon vocabulary rather than applying a
new color layer to the source layout.

The EBench case study is a deliberate, documented exception for teaching the reconstruction
workflow. Read [ebench-case-study.md](ebench-case-study.md) before using its reference image or
editable PPTX. Treat the reference image as third-party material and the PPTX as an editable
learning artifact, not as an official EBench template.

## Render acceptance

Before delivery, verify all of the following:

- SVG, PNG, and PDF show the same node and edge topology.
- No text is clipped, substituted with missing-glyph boxes, or smaller than the
  declared minimum.
- Every edge has a declared meaning, scope, source port, and destination port.
- Temporal order remains local to a branch; convergence remains outside it.
- The figure is legible at 50% display scale and in grayscale.
- The provenance list distinguishes original geometry from supplied assets.
- No absolute Windows path, backslash-only path, linked office object, or
  proprietary font is required to reproduce the render.
