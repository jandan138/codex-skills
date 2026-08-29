# EBench reconstruction case study

Use this case study when a user wants to understand or reuse the reference-analysis, arrow-topology,
and editable-PPTX workflow. It is an example, not the default composition for every scientific
figure.

## Included files

| File | Role |
| --- | --- |
| `../assets/examples/ebench/ebench-figure-2-reference.png` | User-supplied screenshot of the EBench paper's Figure 2; inspect only as a visual and topology reference. |
| `../assets/examples/ebench/ebench-reconstructed-template.pptx` | Editable one-slide reconstruction produced during the Skill's development and accepted by the user after arrow-topology corrections. |
| `../assets/examples/ebench/ebench-reconstructed-template-preview.png` | Fresh render of the accepted PPTX for quick inspection and render regression checks. |
| `../assets/examples/ebench/provenance.json` | Machine-readable identity, checksums, source links, and reuse boundaries. |

## Source identity and rights boundary

The reference screenshot corresponds to Figure 2, “EBench end-to-end pipeline,” in:

> Ning Gao et al., “EBench: Elemental Diagnosis of Generalist Mobile Manipulation Policies,”
> arXiv:2606.18239, 2026.

- Paper: <https://arxiv.org/abs/2606.18239>
- Official project repository: <https://github.com/InternRobotics/EBench>
- The repository maintainer explicitly authorized publishing the supplied screenshot in this Skill
  repository as a reference for later users.
- The arXiv record uses the arXiv non-exclusive distribution license, not a Creative Commons
  license. The original reference image therefore remains attributed to the EBench paper authors
  and is not covered by any license applied to this Skill's own code or templates.
- Do not copy the reference screenshot into a paper, product, dataset, or derivative repository
  without establishing an independent legal basis or obtaining permission from the rights holder.

The editable PPTX is an independent reconstruction created to demonstrate a reproducible workflow.
It is not an official EBench asset, and it does not transfer ownership of EBench names, claims,
screenshots, or underlying project content.

## How to use the case study

1. Inspect the reference at native resolution. Inventory panel hierarchy, repeated state frames,
   internal temporal arrows, external data/control arrows, ports, feedback paths, and junctions.
2. Open the PPTX and study how the large frame, small icons, semantic color families, and routed
   connectors are represented as editable slide objects.
3. Replace the schematic render slots with user-owned Isaac Sim frames and replace labels and
   counts with verified project-specific content.
4. Rebuild the semantic graph rather than inheriting the example's scientific claims. The EBench
   numbers, task categories, and client-server semantics are not placeholders for another project.
5. Render the edited PPTX and review it at full size. Recheck connector direction, endpoint landing,
   occlusion, overflow, and text wrapping before delivery.

## What the accepted reconstruction demonstrates

- Separate internal sequence arrows from external system-level flows.
- Route long connectors around panel boundaries and terminate them at meaningful visual ports.
- Use native slide shapes for the editable frame and compact schematic icons.
- Preserve a clear left-to-right story while keeping Server and Client feedback visibly distinct.
- Validate the delivered PPTX by rendering it again; do not approve only from the editing canvas.

The supplied PPTX passed a fresh full-slide render and an overflow check before it was added to the
repository. It contains 176 native shapes, 22 native connectors, and 56 embedded pictures, with no
external or machine-specific file links detected. Its preview is the expected visual baseline for
that exact file.
