# Academic 2D illustration components

Use this reference when a scientific figure benefits from small, friendly 2D illustrations rather
than generic boxes or stock SVG icons. The goal is publication clarity with a coherent visual family,
not decorative cartooning.

## Assign each illustration a semantic role

Choose one class before generating an asset:

- **scene-derived exposition**: a simplified physical setup, transition, or outcome that helps the
  reader recognize the real task;
- **abstract semantic component**: evidence binding, grammar, intent, verification, compilation, or
  another nonphysical transformation;
- **control or terminal component**: policy, execute, clarify, reject, merge, or stop.

Use scene-derived images mainly at inputs, outputs, or a scoped execution witness. Do not depict
grammar, intent, verification, or policy as arbitrary beakers merely because the paper contains a
liquid task. Their pictures should encode their computational roles.

Before generating, write a compact brief for each component:

`Actor | object/data | operation | visible relationship | native label | likely misreading | final size (mm)`

A record, the program analyzing it, and the resulting assessment are different roles. Do not give
all three an anonymous document silhouette. A magnifier helps only when it visibly singles out a
field or event being inspected. A gear can represent execution of a script when a code page,
input/output connection, or caption supplies that context; a thinking face alone can imply an
unsupported intelligent evaluator.

Blank slots need a purpose. If they denote fields, reserve room for concise native field names and
show correspondence through position or local guides. If marks add no interpretable content,
remove them rather than filling space with pseudo-writing. Do not invent values, success marks,
or performance charts to make an output page look informative.

## Generate one family, not isolated icons

Write one family brief covering line color, fill palette, viewpoint, stroke character, detail level,
and exclusions. Start with a few genuinely different compositions for the hardest semantic role
(three is a useful option, not a quota). Overlay the intended native labels and choose at final
size before expanding the family with the selected style reference. A jointly generated atlas is
an option when its cells remain separable and clear, not a mandatory workflow.

For small paper components, request:

- flat or lightly hand-drawn 2D academic illustration;
- one dark ink color and two or three restrained fills;
- no generated words, pseudo-text, logos, glossy 3D, drop shadows, or decorative clutter; include
  people or robots only when they carry the intended scientific role;
- generous margins and a background suited to the target panel;
- legibility at the intended physical size and output resolution, not merely at generation size.

For an author-requested gentle hand-drawn style, use thin readable strokes, restrained pale fills,
subtle weight variation, modest natural asymmetry, and white space. Friendly proportions and object
interaction can add warmth. Thick rounded outlines, dense binding rings, scalloped templates,
paper texture, deliberate wobble, and facial detail should not carry the explanation. This is an
optional style direction, not a requirement for every research figure.

Compare candidates by object proportion, meaningful interaction, spacing, and survival at paper
size. Save prompts, candidates, selections, and specific rejection reasons. Generate a targeted
revision when a defect persists; producing a batch is not itself a stopping condition.

Keep the prompt/design brief and generator metadata in internal provenance. Reviewer-facing captions
should describe what the illustration means, not how it was generated.

## Extract and normalize components

Inspect candidates at native resolution. If transparency is requested, verify the actual alpha
channel; a baked checkerboard is not transparency. An opaque white background is acceptable when
it fits the intended surface and is accurately recorded. Check panel-fill composites and grayscale
for halos, lost interior whites, and damaged outlines. Do not automatically remove backgrounds;
follow the applicable image-editing tool and authorization constraints. For atlases, also reject
cross-cell strokes and crop only within reviewed bounds. Never cut through a foreground stroke.

Transparent canvas dimensions are not an alignment metric. Run:

```bash
python scripts/analyze_icon_optics.py icon-a.png icon-b.png icon-c.png --pretty
```

Use each asset's alpha bounding box and alpha-weighted centroid to normalize visible height and
optical baseline. Equalize the apparent area of peer icons, while allowing a primary physical witness
to remain larger. Recheck horizontal gaps using foreground bounds rather than image rectangles.
Alpha-based bounds do not identify foreground inside an opaque white image; use visual inspection
or explicit reviewed content bounds in that case, without silently treating white pixels as alpha.

## Compose deterministically

Keep labels as native text; never rely on generated lettering. Place raster components into PPTX or
SVG with explicit coordinates from configuration, and keep connectors as native vector paths. Use
the same font role, size, and weight for peer labels such as POLICY and COMPILER, and a second shared
role for terminal labels such as EXECUTE, CLARIFY, and REJECT.

Reserve field interiors and label margins before generation. Precise correspondence guides and
system connections belong in native geometry so the generator cannot change scientific relations.
Embed raster assets independently and disclose their replaceable but internally non-editable form.
Keep official brand marks separate from generated art and experimental photos in provenance and QA;
checks for authentic experiment pixels must not be applied indiscriminately to explanatory art.

The bundled case study under `assets/examples/illustration-led-method/` demonstrates this separation:
physical vessel scenes anchor selection/execution, computational cartoons explain the middle, and a
coherent authority family distinguishes policy, compiler, clarification, and rejection. Read its
`provenance.json` before adaptation. It is a visual baseline, not a reusable scientific claim.

## Review at paper scale

Inspect the standalone figure, dense crops, grayscale output, PPTX round trip, and the exact paper
page. Check that the illustrations are visible without dominating labels or connectors, peers share
an optical center, and no component crosses a title rule or card boundary. The claim boundary must
distinguish explanatory illustration from simulation renders and measured evidence.

Briefly hide titles to see whether peer pictures have distinguishable roles, then judge each picture
with its actual text and connections. An abstract concept may need a short label; the test should
expose interchangeable decorations, not prohibit helpful text. If meaning disappears at final size,
reduce detail, enlarge its allotted area, or switch to a native schematic instead of shrinking text.
