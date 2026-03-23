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

## 3. Frozen Rules

- **Placement/domain phase**: owns active-grid use, domain construction, and propagation. It may use only pre-routing legality tests.
- **Screening phase**: owns pre-routing candidate elimination by provable contradiction only. It is weaker than exact routing.
- **Exact routing phase**: owns actual route construction and route-state commitment after every node has one legal junction.
- **Post-solve refinement phase**: owns legal-preserving improvement after a fully legal graph exists.

### 3.1 Grid / profile

- Default logical x rails exist as an ordered family.
- The base y-grid starts with authored/static tier rails only.
- Extra y rails are added only through profile rules.
- A grid is a grid regardless of why a rail was added.
- Generic profile rule:
  - The first extra rail in a band goes to the midpoint.
  - If more rails are later added in the same band, dynamic rails in that band are rebalanced to equal spacing.
  - Static/authored rails do not move.
- The solver uses logical rails, not pixel coordinates.

### 3.2 Node / junction model

- Every node occupies one junction.
- A node's ports are defined by its node definition.
- Ports connect only to the adjacent junction in their orientation.
- Port capacities are defined by the node definition.
- If a port reaches capacity, it is unavailable for further attachment.
- Only nodes may change junction behavior during screening.
- Non-node junction connection state is ignored during screening.

### 3.3 Graph semantics

- `OR` does not require a separate structural node. All required inputs connect directly to the target.
- `AND` is represented as an implied node, but it does not automatically add a new y rail.
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
- Deterministic tie-breaks in pass 1 exist for reproducibility only.
- Deterministic candidate ordering in pass 1 is traversal only, not a solver objective.

### 3.6 Domains

- For every node `n`, the stored domain is an explicit set of legal junctions.
- `Dom_x` and `Dom_y` may be used internally as construction helpers only.
- Tier/authored nodes have fixed `Dom_y`.
- Dynamic nodes use currently active logical y rails that are allowed for them.
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

### 3.8 Screening

- Screening is weaker than routing.
- Screening uses:
  - the active grid
  - the routing policy
  - node occupancy and capabilities
  - candidate port-adjacent sites
- Screening ignores non-node junction connection state.
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

## 4. Frozen Solve Pipeline

1. Load profile and graph/object definitions.
2. Build the minimum active grid from tier rails.
3. Run pass 1 on the current active grid: build domains, then run propagation and screening during placement-seed search.
4. If pass 1 returns one or more provisional placement seeds, exact routing may be attempted on returned seeds.
5. If placement is impossible because the current grid is insufficient, expand the grid by the next profile rule, then return to domain construction on the expanded active grid.
6. If routing succeeds for a provisional placement seed, produce a legal graph candidate.
7. Run refinement on legal graph candidates.
8. Deduplicate refined graphs and keep up to `K` distinct final outputs.

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
- `OR` requires a separate structural node.
- Exact routing may be used during domain construction, propagation, or screening.

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
- Any behavior not frozen in this file.
