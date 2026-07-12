# Arrow topology

Use this reference to translate a semantic graph into connector geometry. Arrow
styles are part of the scientific notation, not decoration.

## Contents

- [The critical distinction](#the-critical-distinction)
- [Classification](#classification)
- [Ports and ownership](#ports-and-ownership)
- [Routing](#routing)
- [Arrowheads and multi-edge networks](#arrowheads-and-multi-edge-networks)
- [Edge record](#edge-record)
- [Validation](#validation)

## The critical distinction

**Internal temporal arrows** describe ordered state change within one branch.
**External convergence edges** describe evidence or signals from independent
branches entering an integration operation. A convergence route does not mean
that one branch occurs before another.

Keep the two networks separate in semantics, ports, routing, and appearance:

| Property | Internal temporal | External convergence |
| --- | --- | --- |
| Semantic class | Internal temporal update | External convergence |
| Edge `scope` value | `internal` | `external` |
| Typical endpoints | State output to next state input | Branch output to integration input |
| Boundary rule | Remains inside one branch region | Leaves a branch and travels outside branch regions |
| Direction | Earlier to later, normally left to right | Source branch toward integrator |
| Default line | Solid blue, 3 px | Dashed orange, 3 px |
| Arrowhead | At every state transition | At the integration input, or once after an explicit merge junction |
| Shared junctions | Forbidden | Allowed only when explicitly declared |
| Meaning | Temporal dependency or update | Fusion, aggregation, comparison, or conditioning |

Never connect the final state of Branch A to the first state of Branch B merely
to make the layout flow. That creates a false temporal claim.

## Classification

Classify an edge before routing it:

1. Does it connect successive states of the same entity or branch? Use
   the internal temporal semantic class and set edge `scope` to `internal`.
2. Does it carry a completed branch output into an aggregator? Use
   the external convergence semantic class and set edge `scope` to `external`.
3. Does it distribute one source to several branches? Treat it as external
   distribution: set `scope` to `external` and state distribution in `meaning`.
4. Does it carry the integrated product to a terminal result? Treat it as an
   external result edge: set `scope` to `external` and state the result relation
   in `meaning`.
5. Is it only a grouping bracket or visual guide? Do not encode it as an edge.

When the source material is ambiguous, keep the candidate edge out of the
authoritative graph and record the uncertainty for review.

The hyphenated keys under `default-theme.json` → `role_styles` are semantic
style-preset names, not legal `scope` values. Never copy a role-style key into a
port or edge record.

## Ports and ownership

Every port declares an id, owner, absolute x and y coordinates, and scope. Port
scope is `internal`, `external`, or `junction`; edge scope is only `internal` or
`external`. An edge references port ids in `from` and `to`. Use input and output
ports with distinct ids even when they occupy the same visual location.

For an internal temporal edge (`scope: "internal"`), both port owners must belong
to the same branch and the destination time index must follow the source time
index. For an external convergence edge (`scope: "external"`), the source owner
must be a branch endpoint and the destination owner must be an integration card
or a declared merge junction.

Give an integrator separate named input ports when branch identity matters. Use a
shared merge junction only when branch identity is intentionally discarded.

## Routing

- Use orthogonal point lists. Include the exact source and destination
  coordinates as the first and last points.
- Route internal temporal edges on the repeated-state baseline with zero or two
  bends. Do not leave the containing branch.
- Route convergence edges through the whitespace between branch regions and the
  integrator. Keep at least 24 px clearance from unrelated panels.
- Approach a card perpendicular to its boundary. Avoid arrowheads placed on a
  bend.
- Prefer parallel trunks with consistent spacing over a fan of diagonals.
- Do not route through text, headers, or another card.

If edges cross, a plain crossing means no connection. If they merge, declare a
junction and render a filled junction marker. Do not use a line hop as the only
semantic cue because hops can disappear in raster exports.

## Arrowheads and multi-edge networks

A temporal chain has one arrowhead per transition so each update remains
inspectable. In a direct convergence network, each branch edge ends with an
arrowhead at its named integration port.

For bus-style convergence, branch-to-bus segments have no arrowheads; a single
bus-to-integrator segment carries the arrowhead. This prevents a shared trunk
from appearing to contain several overlapping arrows. Do not mix direct and bus
semantics within one integration operation.

For the opposite case, one declared source port feeds multiple branch input
ports. Encode every distribution segment with `scope: "external"` and an
explicit distribution meaning. A split junction is not a convergence junction
even if its geometry looks similar.

## Edge record

Use the following shape in a figure specification:

    {
      "id": "branch-a-to-fusion",
      "from": "a.final.out",
      "to": "fusion.in.a",
      "scope": "external",
      "meaning": "Branch A evidence enters integration",
      "arrowhead": "end",
      "route": "explicit",
      "points": [{"x": 950, "y": 318}, {"x": 1030, "y": 318},
                 {"x": 1030, "y": 382}, {"x": 1100, "y": 382}],
      "color": "#A65A16",
      "width": 3,
      "dash": "dashed"
    }

Use `dash: "solid"` for solid edges. Use `arrowhead: "none"` for the arrowless
part of a declared bus, never by omission. The v1 schema also accepts `dotted`,
and arrowheads `start` or `both`, but use them only when the scientific meaning
requires them.

## Validation

Reject or flag a graph when any of these conditions holds:

- An edge endpoint is not a declared port or does not match that port coordinate.
- An internal temporal edge crosses a branch boundary or joins different
  branches.
- A convergence edge terminates at an ordinary state card.
- Temporal and convergence edges share the same color and dash pattern.
- A convergence edge is labeled with a time transition.
- Two polylines merge geometrically without a declared junction or distinct
  integration ports.
- A directed cycle exists but recurrence is not explicitly part of the meaning.
- An arrowhead is obscured by a panel, clipped by the canvas, or placed mid-bend.

During visual review, trace the blue temporal chain inside each branch first,
then trace the orange convergence network outside the branches. Each should be
understandable while the other is mentally ignored.
