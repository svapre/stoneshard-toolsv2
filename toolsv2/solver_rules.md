# Solver Rules

## 1. Purpose

- This file contains frozen rules only for the grid-based graph layout solver.
- Frozen sections in this file are the source of truth for implemented solver rules and phase boundaries.
- Open questions, missing details, and undecided behavior must not be implemented by assumption.
- If a behavior is not frozen here, it belongs in [7. Open / Not Frozen](#7-open--not-frozen).

## 2. Terminology

- **junction**: the intersection of one logical x rail and one logical y rail on the active grid.
- **node**: a graph element that occupies one junction.
- **logical x rail**: a solver-level rail at a fixed logical x position.
- **logical y rail**: a solver-level rail at a fixed logical y position.
- **tier/authored node**: a node whose y placement is tied to an authored/static tier rail.
- **dynamic/implied node**: a node that is not fixed to an authored/static tier rail and must be placed on allowed y rails from the current active grid.
- **domain**: the explicit set of currently legal junctions for a node before exact routing. `Dom_x` and `Dom_y` may be used internally as construction helpers, but the stored and propagated domain is a junction set.
- **placement seed**: a complete pass-1 node-to-junction assignment on the current grid that satisfies placement-phase legality only and still requires exact routing.
- **screening**: the pre-routing elimination phase that removes candidates only when impossibility is provable from frozen pre-routing checks.
- **exact routing**: the post-placement phase that constructs and commits actual legal routes.
- **refinement**: the post-solve second pass that may move already placed nodes or substructures and reroute affected parts while preserving legality.
- **routing policy**: a configurable ruleset, separate from solver core logic, that constrains legal route movement and route behavior.
- **active grid**: the currently instantiated set of logical x rails and logical y rails available to placement, screening, and exact routing.
- **visual/build profile**: data-only visual/build information kept separate from logical object/schema data.
- **graph content**: explicit production input data for node instances, route requirements, screening-time attachment requirements, and same-row ordering groups.
- **render resolver**: the layer that converts committed runtime truth into render-ready object specs with dynamic visual facts already resolved.
- **render instruction**: a generic renderer-facing primitive or stamp instruction, not a logical graph object.

## 3. Frozen Rules

- **Placement/domain phase**: owns active-grid use, domain construction, and propagation. It may use only pre-routing legality tests.
- **Screening phase**: owns pre-routing candidate elimination by provable contradiction only. It is weaker than exact routing.
- **Exact routing phase**: owns actual route construction and route-state commitment after every node has one legal junction.
- **Post-solve refinement phase**: owns legal-preserving improvement after a fully legal graph exists.

### 3.1 Grid / profile

- Default logical x rails exist as an ordered family.
- Reusable layout presets may define a default x-rail family plus minimum same-row spacing without turning those values into solver-core constants.
- Reusable layout-demand estimators may derive only provable lower-bound initial grid requirements from graph content plus layout/profile data.
- The base y-grid starts with authored/static tier rails only.
- Extra y rails are added only through profile rules.
- A grid is a grid regardless of why a rail was added.
- Band-local dynamic-rail activation/configuration is profile data, not solver-core policy.
- A profile may expose:
  - a midpoint layout for one dynamic rail in a band
  - a split-pair layout for two dynamic rails in a band
  - other explicit in-band layouts later without changing solver-core logic
- If a profile activates a split-pair layout in a band, the midpoint rail for that band may be inactive.
- Static/authored rails do not move.
- A generic midpoint/equal-spacing helper may exist for profiles that choose that rule, but that helper is not itself the frozen global solver policy.
- The solver uses logical rails, not pixel coordinates.
- The current explicit vanilla layout preset preserves:
  - 7 default x rails
  - minimum same-row x-gap = 1
- The current vanilla layout profile also carries:
  - a midpoint band-layout pattern
  - a 4-tier split-pair band-layout pattern
- A stronger profile-owned band pattern may explicitly supersede a weaker one for the same authored band; compatible same-band lower-bound demands must resolve through profile data rather than being treated as automatic contradictions.
- The initial active grid for one solve may be stronger than the bare authored-tier minimum if a reusable estimator can prove profile-owned lower-bound band requirements from the content.
- Such lower-bound estimation is separate from both placement/routing and the multi-grid retry loop.

### 3.2 Node / junction model

- Every node occupies one junction.
- Junctions are grid-intersection location markers and anchor logical objects to the visual grid.
- Current production node kinds are `skill_frame` and `and_knot`.
- Current production node-family registration is external catalog data, not generic-loader branching.
- A node's ports are defined by its node definition.
- Ports always belong to their owner object.
- Node ports attach only across one shared boundary in their facing direction.
- Current production node-family port ids are:
  - skill frame: `top`, `bottom`
  - AND knot: `top`, `left`, `right`, `bottom`
- When a junction is unoccupied, junction-local rules are active at that site.
- When a node occupies a junction, the junction remains the location marker but the junction-local rules are deactivated and the node's local rules become the active rules at that site.
- Nodes do not act as same-object route-through substrates in current v1 unless a future profile explicitly freezes local internal transitions for such an object family.
- Port capacities are defined by the node definition.
- Port capacity means the maximum number of direct built attachments that port may own at one time.
- Port capacity defaults to unbounded unless an explicit finite cap is declared.
- If a port reaches capacity, it remains an active existing endpoint but is unavailable for further direct attachment.
- Current production node-family capacities are:
  - skill frame: `top` unbounded, `bottom` unbounded
  - AND knot: `top` = `1`, `left` = `1`, `right` = `1`, `bottom` unbounded
- Current production graph content must declare source/sink port allowances explicitly for each route requirement rather than inferring them from node family.
- Current schema-view allowance lookup may be requirement-specific; it must not collapse distinct required gate-input ports into one generic per-kind allowance.
- Graph content may also select an external placement-candidate ranking policy by id.
- Only nodes may change junction behavior during screening.
- Non-node junction connection state is ignored during screening.

### 3.3 Graph semantics

- `OR` does not require a separate structural node. All required inputs connect directly to the target.
- `AND` is represented as an implied node, but it does not automatically add a new y rail.
- An implied `AND` node lives on the sink-adjacent inter-tier band, even if some of its inputs originate from higher tiers.
- A dynamic/implied node must first try to fit on the current active grid.
- New rails are added only if the current grid cannot support legal placement or legal routing.

### 3.4 Objective order

Frozen objective order:

1. Hard constraints
2. Minimize active y-grid
3. Minimize total path length
4. Minimize bend count

Clarifications:

- Path length is counted in grid edges only.
- Port offsets do not affect path length.

### 3.5 Placement before routing

- Pass 1 is a placement-seed finder on the current active grid.
- Pass 1 generates provisional placement seeds only.
- Pass 1 does not own the final-output `K`.
- Each pass-1 seed assigns every node to exactly one junction.
- Each pass-1 seed satisfies placement-phase legality only.
- A pass-1 seed is not a legal graph.
- A pass-1 seed is not canonical.
- A pass-1 seed still requires exact routing.
- A pass-1 seed may later be improved or replaced by refinement.
- Exact routing starts only after pass 1 has returned a provisional placement seed with every node assigned to exactly one junction.
- The full solver returns up to `K` distinct final graphs.
- The default `K` is `1`.
- `K` must be configurable, with caller override allowed.
- Distinctness for final outputs is evaluated only after exact routing and refinement.
- The first pass is placement/legality.
- The second pass is refinement.
- The placement phase may use only pre-routing legality tests.
- Exact routing is not allowed during domain construction or propagation.
- Smallest-domain-first is the frozen pass-1 branching rule.
- Pass-1 may use an injected external candidate-ranking policy to order already-legal junction candidates for the current branch node.
- Deterministic tie-breaks in pass 1 exist for reproducibility only.
- Deterministic candidate ordering in pass 1 is traversal only, not a solver objective.
- Current skill-tree content uses a route-graph spring candidate-ranking policy outside solver core to prefer slot assignments closer to the current graph-driven x equilibrium.

### 3.6 Domains

- For every node `n`, the stored domain is an explicit set of legal junctions.
- `Dom_x` and `Dom_y` may be used internally as construction helpers only.
- Tier/authored nodes have fixed `Dom_y`.
- Dynamic nodes use currently active logical y rails that are allowed for them.
- Current ordered same-row raw-domain construction uses row order plus the explicitly supplied minimum same-row spacing hard constraint on the current active x rails.
- If those hard constraints leave no legal current-grid ordered-row assignment, the resulting domains are empty and the current grid is contradictory for that placement attempt.
- Domains are reduced by proof only.

### 3.7 Propagation

Frozen propagation types:

- tier propagation
- row order propagation
- same-row spacing propagation
- occupancy propagation
- port-based pre-routing support filtering
- singleton collapse
- empty-domain contradiction

Clarifications:

- A candidate stays valid unless a hard contradiction proves it impossible.
- No candidate may be removed by intuition or by a "probably bad" judgment.
- Current same-row propagation uses the same frozen row-order plus explicitly supplied minimum same-row spacing hard constraint on the current active x rails.

### 3.8 Screening

- Screening is weaker than routing.
- Screening uses:
  - the active grid
  - the routing policy
  - node occupancy and capabilities
  - candidate port-adjacent sites
- Screening ignores non-node junction connection state.
- Occupancy of an adjacent site alone is not a proof of impossibility, because that adjacent site may be an occupied node whose owner-defined port is the intended attachment.
- Reachability screening is span-based or empty-space-based in principle, not exact routing.
- A candidate is removed in screening only if impossibility is provable.

### 3.9 Routing policy

- Routing policy must be configurable and separate from core solver logic.
- "No upward movement" belongs in routing policy, not in hardcoded solver core behavior.
- Any algebraic shortcut derived from routing policy is optional and must not become the source of truth.

### 3.10 Exact routing

- Exact routing begins only after all nodes are placed.
- Routing starts from the adjacent junction of the chosen source or output port, not from the node center.
- A successful exact route may update:
  - node-port usage
  - non-node junction local connections
  - engaged or locked entries
  - terminal attachments
- A newly committed route may not widen or modify an already engaged entry's exit set.

### 3.11 Refinement phase

- Refinement is a second pass after a fully legal graph exists.
- V1 refinement is post-routing only.
- V1 refinement is x-only. Logical y stays fixed.
- V1 refinement is discrete.
- Row order and minimum same-row spacing remain hard constraints during refinement.
- V1 refinement move neighborhoods include:
  - single-node x moves
  - contiguous same-row block moves
- Refinement may move nodes or substructures and reroute affected parts.
- Every accepted refinement move must preserve full legality after reroute.
- V1 refinement acceptance is based primarily on the actual post-reroute graph:
  - first: lower total routed path length
  - second: lower total bend count
- If still tied, use a secondary local geometric tie-break only:
  - attraction for directly connected pairs
  - repulsion for same-row unrelated pairs
  - repulsion uses a finite local cutoff
  - distance is horizontal x-distance only
- Refinement may only keep moves that preserve legality.
- V1 refinement does not freeze:
  - all-pairs unrelated repulsion
  - pairwise geometry as the sole refinement score
  - continuous force dynamics
  - explicit contact-force propagation
- Refinement is not part of the legality solver.

### 3.12 Visual / render architecture

- Logical object data and visual/build data are separate concerns.
- The renderer is separate from routing, commit, and orchestration.
- Ports are local interface/state only and are not directly renderable by default.
- Empty junctions may exist in runtime state without being rendered.
- The renderer must be a rule follower, not a policy maker.
- Visual/build feasibility may use visual/build profile data as its source of truth for build-geometric constraints without leaking visual semantics into logical solver core.
- Rendering consumes committed runtime truth only, not tentative route plans.
- Rendering must not infer legality or buildability.
- Concrete pixel mapping, canvas size, and default background ownership are render-layout profile data, not renderer-core guesses.
- Local visual/build coordinates are centered on the object anchor by default:
  - `+x` points right
  - `+y` points down
- Rendering uses this layer order boundary:
  - background: order 0
  - shadow: order 1
  - road: order 3
  - object body: order 4
  - object foreground: order 5
- Layer composition is data-driven. Default inter-object composition is upper-over-lower overwrite respecting alpha unless a layer/profile defines another operator.
- `max_light` is one supported composition operator and remains important for object-local composition such as junction-piece assembly, not as a required global road-layer interaction rule.
- Exact composition behavior is provided through an external callable registry; renderer core dispatches to declared rules instead of inferring behavior from asset contents.
- Object-specific pre-render finalization may also be provided through an external callable registry rather than hardcoded in renderer core.
- Derived visual variants such as rotations, mirrors, and local placement offsets are profile data, not renderer guesses.
- Current concrete v1 object-family geometry is:
  - skill frame: `31x31`, top port at `(0, -15)`, bottom port at `(0, 14)`, separate shadow layer
  - AND knot: `5x7`, top `(0, -2)`, left `(-1, 0)`, right `(1, 0)`, bottom `(0, 2)`
  - plain junction: `5x5`, north `(0, -2)`, south `(0, 2)`, west `(-2, 0)`, east `(2, 0)`
- Logical port identity remains schema-owned. Concrete node-family visual profiles may be parameterized by caller-supplied port ids rather than hardcoding a solver-core port-id convention.
- V1 junction rendering uses composition of individual connection pieces only.
- Current v1 source art is grouped by object/family rather than by global asset type.
- Source-art file layout is external catalog data; moving art files must not require edits to generic renderer/profile modules.
- Current production visual-family registration is external catalog data; adding a new production family must not require edits to generic loader or generic profile modules.
- Future T/cross-specific junction overrides must be addable through junction profile data rather than renderer rewrites.
- External edge families are not hardcoded in the renderer.
- V1 external span rendering supports straight repeated primitives only, using the current straight external connection family.
- The current straight external connection family is axis-aligned only and uses repeated `3x1` / `1x3` primitives.
- The current canonical straight primitive source asset is the `top-bottom` form; horizontal straight spans/pieces use the rotated variant.
- In the current implemented v1 primitive expander, an axis-aligned straight connection family may use:
  - one canonical primitive plus a profile-owned transform
  - or explicit oriented templates
- Future diagonal or curved connection families must remain possible without changing logical solver core.
- Boundary-facing junction ports may remain instantiated at edge-of-grid sites even when no outward neighbor exists; outward routing is limited by active-grid adjacency rather than by deleting those ports.
- The render pipeline boundary is:
  1. committed runtime truth
  2. render resolver
  3. primitive expansion
  4. base renderer / compositor
- The renderer/compositor consumes generic render instructions only.
- The render resolver may resolve per-object dynamic render information first, then feed that through primitive expansion before final rendering.
- The current implemented v1 render resolver:
  - emits active node render specs
  - emits unoccupied-junction render specs only when built local junction connections exist
  - omits separate junction specs for occupied sites
  - emits separate external-edge render specs with straight resolved spans only
  - fails loudly rather than guessing on non-axis-aligned external spans
- The current implemented v1 primitive expander:
  - expands object style bindings into generic sprite/pixel-mask stamps
  - expands straight external spans into repeated-span instructions
  - expands local junction/object connection pieces from profile-owned undirected port-pair bindings
  - applies profile-owned local offsets and transforms rather than guessing them in renderer code
- The current implemented v1 base renderer:
  - uses an explicit render-layout preset for canvas size, background, and rail pixel mapping
  - loads templates through a cached template loader
  - dispatches composition only through the external behavior registry
  - runs generic rule-driven object finalization before primitive expansion where a profile declares that need
  - supports the current base output from sprite stamps and repeated straight spans
- The current implemented export/testing helper may:
  - render one committed runtime snapshot to the base image
  - render one successful current-grid solve result to the base image
  - save that base image for smoke testing and manual review
- The current implemented glow export boundary is split into:
  - a generic manifest/schema layer in `toolsv2/glow`
  - a Stoneshard/MSL-specific adapter layer in `toolsv2/adapters/msl_stoneshard`
- The current implemented glow pipeline may:
  - decompose one successful solved graph into reusable glow sections
  - rasterize those sections into cropped red-mask PNGs
  - save a generic glow manifest JSON
  - emit Stoneshard `Other_24`-style GML through the adapter layer
- Glow export dependency groups mirror Stoneshard runtime wiring:
  - point dependency groups are emitted through `addConnectedPoints(...)`
  - line dependency groups are emitted through `addConnectedLines(...)`
- Stoneshard/MSL file/GML generation must not leak into solver, placement, routing, or generic render core.
- The current implemented file runner may:
  - load the current requirement-spec JSON shape
  - compile it into explicit graph content
  - run the current default estimated full solve loop, including the built-in adjacent-authored-flow, single-sink-mediated, and same-band multi-sink split lower-bound estimator rules
  - save the base PNG with default output-path behavior

## 4. Frozen Solve Pipeline

1. Load profile and graph/object definitions.
2. Build the minimum active grid from tier rails.
3. Run pass 1 on the current active grid: build domains, then run propagation and screening during placement-seed search.
4. If pass 1 returns one or more provisional placement seeds, exact routing may be attempted on returned seeds.
5. If placement is impossible because the current grid is insufficient, expand the grid by the next profile rule, then return to domain construction on the expanded active grid.
6. If routing succeeds for a provisional placement seed, produce a legal graph candidate.
7. Run refinement on legal graph candidates.
8. Deduplicate refined graphs and keep up to `K` distinct final outputs.

Current implemented v1 shell boundary:

- The current implemented solve shell consumes explicit graph content plus one fixed active grid.
- It loads current production definitions/content, runs placement on that fixed grid, and then runs routing/commit orchestration across the returned placement seeds on that same fixed grid.
- It may report:
  - placement failure on the current grid
  - routing failure on the current grid after exhausting the returned placement seeds
  - success on the current grid
- The current implemented full multi-grid orchestrator may then:
  - build the minimum active grid from explicit x-rail ids and authored tier rails
  - run the current-grid shell
  - expand by the next explicit profile-rule policy step after either placement-scoped or routing-scoped current-grid failure
  - retry on the expanded grid
  - stop on first success or explicit grid-set exhaustion
- Failure over the tried grid set does not mean global impossibility.
- The current implemented orchestration still does not implement refinement or rendering.
- The current implemented short file runner sits above that stack and uses the current requirement-spec compiler plus base renderer, but it is still limited by whatever graphs the current logical solver can actually solve.

## 5. What Screening May Remove

Only the following screening contradictions may remove a candidate:

- occupancy contradiction
- y-domain contradiction
- row/order/spacing contradiction
- raw port-capacity contradiction
- adjacent required port-site does not exist
- explicit definition contradiction

Guessed geometric heuristics are not allowed screening contradictions.

## 6. What Must NOT Be Assumed

- A dynamic/implied node automatically creates a new rail.
- Symmetry may be used as a hard elimination rule.
- Profile-specific pixel spacing may leak into generic solver logic.
- A candidate can be removed because it "looks bad" or "probably won't route."
- Screening may depend on existing non-node road state.
- Routing policy shortcuts may replace the routing policy itself.
- Port offsets affect path length.
- `OR` does not require a separate structural node in the current requirement compiler; alternate prerequisite groups compile as independent allowed source->sink routes to the same sink.
- Exact routing may not be used during domain construction, propagation, or screening.
- Renderer policy may decide legality or buildability.
- Renderer must infer object placement, span shape, or local connection patterns from raw graph semantics.

## 7. Open / Not Frozen

- Exact router algorithm details.
- Exact route commit and update implementation details.
- Exact multi-branch routing construction.
- Exact secondary geometric tie-break formula.
- Exact secondary geometric tie-break weights and local cutoff values.
- Any refinement model beyond discrete x-only v1 move neighborhoods and acceptance rules.
- Exact row-distribution policy when multiple splits use the same minimum y-grid.
- Exact profile-band enumeration and selection details beyond the midpoint and rebalance rule.
- Exact `Dom_x` construction details beyond hard constraints defined elsewhere.
- Tie-break rules among legal solutions that are equal under the frozen objective order.
- Exact concrete visual/build profiles for any object families beyond the currently frozen v1 skill frame, AND knot, plain junction, and straight external-road family.
- Exact renderer/compositor implementation details.
- Any behavior not frozen in this file.
