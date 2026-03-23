# Module Contracts

## Purpose

- This file records module responsibilities and forbidden assumptions.
- Frozen rules come from `solver_rules.md`.
- If a responsibility depends on an open item, the module must stop with an explicit TODO or `NotImplementedError` instead of guessing.

## Shared Foundation

### `solver_types.py`

Status:
- Frozen and implementable now.

Responsibilities:
- Define typed ids and immutable data structures for rails, junctions, nodes, ports, domains, routing policy, and active grid state.
- Enforce structural invariants that can be checked without placement, screening, or routing.
- Represent empty domains explicitly.

Forbidden assumptions:
- No placement heuristics.
- No profile-specific pixel spacing.
- No exact routing state.
- No inferred dynamic-rail creation rules.
- No hardcoded routing-policy behavior.

### `profile.py`

Status:
- Frozen for logical grid construction only.

Responsibilities:
- Build the default logical x-rail family from explicit ordered ids.
- Build authored/static tier y rails for the minimum active grid.
- Build bands between adjacent authored y rails.
- Rebalance explicitly supplied dynamic rails within one band using the frozen midpoint/equal-spacing rule.
- Expose logical-to-pixel mapping hooks without implementing unfrozen mapping details.

Forbidden assumptions:
- No automatic choice of which band expands next.
- No automatic creation of dynamic-rail ids.
- No inferred ordering of dynamic-rail identities inside a band.
- No pixel mapping logic in generic solver behavior.
- No placement, screening, routing, or refinement logic.

## Placement / Domain Phase

### `definitions_loader.py`

Status:
- Partly blocked by schema choices outside the frozen solver rules.

Responsibilities:
- Load graph/object/node/junction/routing-policy definitions into `solver_types.py` data.
- Fail loudly on malformed definitions.

Forbidden assumptions:
- No profile behavior in generic node definitions.
- No implied default ports or capacities.
- No hardcoded `OR` or `AND` expansion policy beyond explicit definitions.

### `domain_builder.py`

Status:
- Partly blocked by open `Dom_x` construction details.

Responsibilities:
- Build explicit legal-junction domains from hard constraints only.
- Use `Dom_x` and `Dom_y` only as internal construction helpers where needed.
- Fix authored-tier y placement for tier/authored nodes.
- Use currently active logical y rails for dynamic nodes where allowed.

Forbidden assumptions:
- No exact routing during domain construction.
- No heuristic elimination.
- No dynamic-node rail creation.
- No guessed `Dom_x` policy beyond frozen hard constraints.

### `propagation.py`

Status:
- Implementable only for the frozen propagation types.

Responsibilities:
- Apply tier propagation.
- Apply row order propagation.
- Apply same-row spacing propagation.
- Apply occupancy propagation.
- Apply port-based pre-routing support filtering.
- Apply singleton collapse.
- Detect empty-domain contradiction.

Forbidden assumptions:
- No elimination by symmetry.
- No elimination by "probably bad" routing intuition.
- No exact route construction.
- No use of non-node junction connection state.

### `placement_solver.py`

Status:
- Frozen only for pass-1 placement-seed search on the current active grid.

Responsibilities:
- Build initial domains for the current active grid.
- Run propagation and screening during pass-1 search.
- Generate provisional placement seeds.
- Optionally cap placement-seed generation for local search control only.
- Use smallest-domain-first branching.
- Keep deterministic tie-breaks and candidate ordering as traversal mechanics only.

Frozen pass-1 output meaning:
- A returned seed is pre-routing only.
- A returned seed assigns every node to exactly one junction.
- A returned seed is not a legal graph yet.
- A returned seed is not canonical.
- Exact routing happens afterward.
- Refinement may later improve or replace the seed.

Forbidden assumptions:
- No exact routing.
- No refinement.
- No claim that pass-1 seeds are solved graphs.
- No claim that deterministic traversal is a solver objective.
- No claim that placement-seed count equals final-output `K`.
- No grid-expansion classification guessed from pass-1 search alone.

## Screening Phase

### `screening.py`

Status:
- Broader reachability-based removals are blocked until `solver_rules.md`
  clarifies whether section 3.8 can remove candidates beyond the strict list in
  section 5.

Responsibilities:
- Remove candidates only for frozen screening contradictions.
- Use the active grid, routing policy, node occupancy/capabilities, and candidate port-adjacent sites.
- Stay strictly weaker than exact routing.

Forbidden assumptions:
- No exact routing.
- No guessed geometric heuristics.
- No reachability-based removal beyond the strict section 5 contradiction list unless the spec is clarified.
- No dependence on existing non-node road state.
- No policy shortcuts becoming the source of truth.

## Exact Routing Phase

### `router.py`

Status:
- Blocked by open exact-router algorithm details.

Responsibilities:
- Start routing only after every node has exactly one legal junction.
- Route from the adjacent junction of the chosen source/output port.
- Produce actual legal routes under the configured routing policy.

Forbidden assumptions:
- No routing during placement/domain construction or propagation.
- No routing from node centers.
- No hardcoded policy rules in solver core.

### `route_commit.py`

Status:
- Blocked by open exact commit/update details.

Responsibilities:
- Apply successful route updates to node-port usage, non-node junction local connections, engaged/locked entries, and terminal attachments.
- Enforce the frozen rule that a newly committed route may not widen or modify an already engaged entry's exit set.

Forbidden assumptions:
- No implicit widening of engaged entries.
- No hidden merge behavior.
- No commit-side heuristics that change legal semantics.

### `routing_policy.py`

Status:
- Partly blocked by open policy schema details.

Responsibilities:
- Interpret configurable routing-policy data.
- Provide policy queries to screening and exact routing without becoming solver-core behavior.

Forbidden assumptions:
- No hardcoded "no upward movement" in solver core.
- No algebraic shortcut replacing the policy definition.
- No profile-specific rules leaking into generic policy handling.

## Refinement Phase

### `refinement.py`

Status:
- Partly frozen for v1 refinement.
- Exact secondary geometric tie-break formula, weights, and local cutoff remain open.

Responsibilities:
- Run only after a fully legal graph exists.
- Use discrete x-only refinement for v1 with logical y fixed.
- Keep row order and minimum same-row spacing as hard constraints during refinement.
- Generate v1 legal move neighborhoods using single-node x moves and contiguous same-row block moves.
- Reroute affected parts after each candidate move.
- Keep only moves that preserve full legality after reroute.
- Score accepted moves primarily by lower total routed path length, then lower total bend count.
- Use local pairwise geometry as a secondary tie-break only.

Forbidden assumptions:
- No participation in legality solving.
- No move accepted without reroute legality preservation.
- No all-pairs unrelated repulsion in frozen v1 refinement.
- No pairwise geometry used as the sole refinement score.
- No continuous force dynamics in frozen v1 refinement.
- No explicit contact-force propagation in frozen v1 refinement.

## Orchestration

### `solve_pipeline.py`

Status:
- Implementable only as a thin frozen pipeline shell until blocked modules exist.
- Expansion after placement success but routing failure remains open because
  `solver_rules.md` names routing insufficiency in section 3.3 but only a
  placement-insufficient expansion step in section 4.

Responsibilities:
- Execute the frozen solve order from `solver_rules.md`.
- Run `placement_solver.py` first and receive provisional placement seeds.
- Hand returned provisional seeds to exact routing afterward.
- Run final `K` handling only after routing and refinement.
- Expand the grid only through profile rules when the current grid is insufficient.
- Stop cleanly at blocked or open modules rather than guessing behavior.

Forbidden assumptions:
- No skipping phase boundaries.
- No refinement before legal routing exists.
- No direct band-expansion policy unless that policy is frozen elsewhere.
- No treatment of pass-1 seed order as an optimization objective.
- No treatment of placement-seed count as the final-output `K`.
