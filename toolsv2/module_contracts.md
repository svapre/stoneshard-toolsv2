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
- Apply explicitly supplied dynamic-rail layouts within one band.
- Expose a generic equal-spacing helper for profiles that choose that rule.
- Expose logical-to-pixel mapping hooks without implementing unfrozen mapping details.

Forbidden assumptions:
- No automatic choice of which band expands next.
- No automatic creation of dynamic-rail ids.
- No inferred ordering of dynamic-rail identities inside a band.
- No inferred profile-specific band-layout heuristics.
- No pixel mapping logic in generic solver behavior.
- No placement, screening, routing, or refinement logic.

### `layout_profiles.py`

Status:
- Implemented as the data-only layout-preset layer above generic grid rules.

Responsibilities:
- Define reusable named layout presets without embedding them into solver-core logic.
- Preserve the current vanilla skill-tree x-rail family and its minimum same-row spacing as explicit data.
- Keep profile-local band-layout patterns so vanilla-specific dynamic-rail heuristics do not leak into generic grid code.
- Provide the current vanilla midpoint and 4-tier split-pair band-layout patterns as explicit data.
- Provide a thin helper for building a minimum active grid from one explicit layout profile.

Forbidden assumptions:
- No placement, screening, routing, or refinement behavior.
- No automatic grid-expansion policy.
- No pixel mapping or renderer behavior.
- No requirement that every solve path must use the vanilla preset.

### `layout_estimation.py`

Status:
- Implemented as the reusable content-to-layout lower-bound estimation layer.

Responsibilities:
- Read explicit graph content plus one explicit layout profile and one explicit authored-tier ordering.
- Derive only provable lower-bound initial grid demands from content.
- Support reusable demand rules for current content-side implied-band nodes without pushing those node-family rules into solver core.
- Keep content-driven initial band-layout requirements separate from the full solve loop.
- Apply profile-owned band-layout patterns to build the initial active grid without leaking profile heuristics into solver core.
- Allow reusable injected estimation rules so other layout families can tailor lower-bound logic without rewriting the full orchestrator.

Forbidden assumptions:
- No placement, routing, commit, refinement, or renderer behavior.
- No automatic authored-tier ordering inference.
- No hidden grid-expansion policy.
- No guessing when content does not prove a layout demand.

### `grid_expansion_policy.py`

Status:
- Implemented as the explicit pure grid-expansion policy contract layer.

Responsibilities:
- Define the pure current-grid -> next-grid policy surface used by the full multi-grid solve loop.
- Provide explicit profile-rule-based expansion steps without inventing hidden heuristics.
- Allow one expansion step to use exact profile-owned in-band rail positions when the layout profile supplies them.
- Keep band-selection and dynamic-rail-id ordering explicit and policy-owned rather than solver-core-owned.

Forbidden assumptions:
- No placement, routing, commit, refinement, or renderer behavior.
- No automatic band-selection heuristics in solver core.
- No implicit dynamic-rail-id generation.
- No mutation of active-grid state in place.

### `visual_profiles.py`

Status:
- Implemented as the current data-only visual/build profile contract layer.

Responsibilities:
- Keep logical object data separate from visual/build data.
- Define data-only build geometry profiles, render style profiles, shared render layers, and connection-family profiles.
- Supply the visual/build catalog consumed by geometry/build-feasibility and later render-resolution layers.
- Freeze the centered local coordinate convention and the shared absolute render-layer catalog.
- Define data-only per-binding local placement offsets and per-binding render transforms so derived visual variants stay profile-owned rather than renderer-guessed.
- Define data-only local-connection template bindings for junction/object-local port pairs.
- Provide reusable current v1 profile builders for the plain junction substrate, skill frame, AND knot, and straight external-road family without hardcoding logical node port ids into solver core.
- Keep future junction pattern overrides data-driven rather than engine-hardcoded.

Forbidden assumptions:
- No routing or legality logic.
- No renderer-side policy decisions.
- No object-type-specific engine behavior embedded in the catalog itself.
- No requirement that every runtime object must already have a fully locked visual profile.

### `source_art_catalog.py`

Status:
- Implemented as the data-only source-art lookup/catalog layer.

Responsibilities:
- Map render template keys to grouped source-art asset locations.
- Build sprite-ref render-template specs from that external mapping.
- Isolate source-art folder layout from generic profile and renderer modules.

Forbidden assumptions:
- No placement, routing, commit, or renderer behavior.
- No object-family logic beyond template ownership.
- No hardcoded asset-path edits in generic core modules when art files move.

### `production_family_catalog.py`

Status:
- Implemented as the external production node-family registration layer.

Responsibilities:
- Register the current production node kinds, canonical owner-local port ids, and schema-side port capacities as data.
- Build canonical `NodeDefinition` records for registered families without requiring generic loader edits.
- Isolate production-family registration from generic loading and routing modules.

Forbidden assumptions:
- No placement, routing, commit, or renderer behavior.
- No asset-path ownership.
- No generic loader branching on concrete family kinds.

### `production_visual_catalog.py`

Status:
- Implemented as the external production visual-family registration layer.

Responsibilities:
- Register family-specific build-geometry and render-style profiles outside the generic profile contract module.
- Assemble the current production visual/build catalog from:
  - plain junction substrate data
  - registered production visual families
  - external source-art template data
- Let new object families extend production visual registration without requiring edits to generic renderer/profile modules.

Forbidden assumptions:
- No placement, routing, commit, or compositor behavior.
- No asset-path ownership beyond consuming the external source-art catalog.
- No generic core branching on concrete production family kinds.

### `graph_content.py`

Status:
- Implemented as the explicit minimal graph-content input schema for the current solver path.

Responsibilities:
- Define explicit input records for production node instances, route requirements, screening-time port attachment requirements, and same-row ordering groups.
- Keep content input separate from solver-internal placement metadata and routing/runtime structures.
- Require explicit source/sink port allowances in content rather than inferring them from node family.

Forbidden assumptions:
- No implicit route allowance inference from node kind alone.
- No file parsing or external I/O.
- No placement, routing, commit, or renderer behavior.

### `skill_tree_requirements.py`

Status:
- Implemented as the current requirement-spec JSON loader/compiler for the file runner.

Responsibilities:
- Load the current higher-level skill-tree requirement JSON shape.
- Validate requirement-spec structure and dependency legality.
- Compile that higher-level requirement spec into explicit current `GraphContentModel`.
- Insert current implied `AND` nodes as explicit graph content where multi-input requirement groups require them.
- Constrain implied `AND` nodes to the inter-tier band they mediate by emitting band-local `allowed_y_rail_ids`.
- Keep requirement-json parsing and graph-content compilation separate from generic solver/runtime layers.

Forbidden assumptions:
- No placement, routing, commit, or renderer behavior.
- No generic solver-core knowledge of file formats.
- No hidden activation logic beyond explicit graph-shape compilation.

### `production_node_definitions.py`

Status:
- Implemented as the stable compatibility wrapper over the external production family and visual catalogs.

Responsibilities:
- Preserve stable helper functions and constants already used by the rest of the stack.
- Delegate current production family data to `production_family_catalog.py`.
- Delegate current production visual catalog assembly to `production_visual_catalog.py`.

Forbidden assumptions:
- No placement, routing, commit, or renderer behavior.
- No game activation logic.
- No dynamic object-family inference from render data.

## Current-Grid Solve Shell

### `solve_pipeline.py`

Status:
- Implemented as the thin current-grid solve shell over the current logical stack.

Responsibilities:
- Consume explicit graph content plus one fixed active grid.
- Load canonical production definitions, placement metadata, route requirements, schema allowances, screening port requirements, and the shared visual/build catalog from explicit graph content.
- Run pass-1 placement on the current active grid only.
- Consume the explicitly supplied minimum same-row x-gap for the current-grid placement shell, or bind it from an explicit layout profile helper.
- If placement succeeds, run current placement-seed routing orchestration over the returned seeds on that same active grid.
- Return a structured result that distinguishes:
  - placement failure on the current grid
  - routing failure on the current grid after trying the returned seeds
  - full success on the current grid

Forbidden assumptions:
- No automatic grid expansion.
- No refinement.
- No renderer behavior.
- No new placement or routing policy beyond the already-frozen lower layers.

## Placement / Domain Phase

### `definitions_loader.py`

Status:
- Implemented as a thin explicit loader for the current frozen v1 node-family catalog.

Responsibilities:
- Convert explicit graph-content input into canonical `NodeDefinition` records, placement metadata, route requirements, schema-view allowances, screening port requirements, and the shared production visual/build catalog.
- Resolve concrete production node kinds only through the external production family catalog.
- Preserve per-requirement source/sink port allowances in the schema view rather than collapsing them to one allowance per object and requirement kind.
- Fail loudly on unknown or malformed explicit production inputs.

Forbidden assumptions:
- No profile behavior in generic node definitions.
- No implied family inference from render data.
- No hardcoded `OR` or `AND` expansion policy beyond explicit definitions.
- No hardcoded branching on concrete production family kinds in the generic loader.
- No broader graph/junction/routing-policy loading behavior beyond the current frozen v1 content surface.

### `domain_builder.py`

Status:
- Implemented for the current frozen hard-constraint domain-construction subset.

Responsibilities:
- Build explicit legal-junction domains from hard constraints only.
- Use `Dom_x` and `Dom_y` only as internal construction helpers where needed.
- Fix authored-tier y placement for tier/authored nodes.
- Use currently active logical y rails for dynamic nodes where allowed.
- Apply ordered same-row x-domain construction using frozen row order plus the explicitly supplied minimum same-row gap on the current active x rails.
- Return empty domains when those hard constraints leave no legal current-grid assignment.

Forbidden assumptions:
- No exact routing during domain construction.
- No heuristic elimination.
- No dynamic-node rail creation.
- No guessed `Dom_x` policy beyond frozen hard constraints.

### `propagation.py`

Status:
- Implemented for the current frozen structural propagation subset.

Responsibilities:
- Apply tier propagation.
- Apply row order propagation.
- Apply same-row spacing propagation.
- Apply occupancy propagation.
- Apply singleton collapse.
- Detect empty-domain contradiction.
- Apply the frozen ordered same-row support rule over the current active x rails using the explicitly supplied minimum same-row gap, without special-casing only one rail-count subset.

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
- Consume the explicitly supplied minimum same-row x-gap for current-grid placement legality.
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
- Stay conservative around occupied adjacent sites: adjacent node occupancy alone is not a proof that a required terminal attachment is impossible.

Forbidden assumptions:
- No exact routing.
- No guessed geometric heuristics.
- No reachability-based removal beyond the strict section 5 contradiction list unless the spec is clarified.
- No dependence on existing non-node road state.
- No policy shortcuts becoming the source of truth.

## Exact Routing Phase

### `router.py`

Status:
- Implemented as a minimal exact router for one fixed runtime snapshot only.

Responsibilities:
- Run pure exact-routing search inside one fixed placement/runtime snapshot.
- Start from schema-allowed source ports and succeed on reaching schema-allowed sink ports.
- Respect occupied-site semantics:
  - unoccupied junction sites use junction-local rules
  - occupied junction sites keep the junction only as the location marker while active local routing behavior comes from the occupant
- Allow node ports to attach across one shared boundary into the active neighboring site through the existing adjacency / geometry / eligibility layers when visual/build profiles define that attachment.
- Traverse committed built edges via entry-conditioned reachability queries.
- Use adjacency, geometry/build-feasibility, and candidate eligibility for tentative local expansions.
- Return a pure tentative route plan/trace only.

Forbidden assumptions:
- No routing during placement/domain construction or propagation.
- No commit/update mutation during search.
- No placement backtracking.
- No global route-preservation validation in the router itself.
- No hardcoded policy rules in solver core.

### `route_commit.py`

Status:
- Implemented as the first validate-and-apply layer on one fixed snapshot.

Responsibilities:
- Re-check a tentative route plan against the current snapshot.
- Materialize new built `PortEdge` objects from tentative route steps.
- Enforce local direct-attachment capacity constraints when materializing new edges.
- Return a new runtime snapshot on success without mutating the input snapshot in place.
- Keep validation local to the current tentative plan and current snapshot.

Forbidden assumptions:
- No in-place mutation.
- No alternate-route search.
- No placement backtracking or refinement.
- No source-owned multi-requirement correctness policy.

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
- Not implemented yet.
- This section records the frozen future module boundary only.
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

### `runtime_snapshot_builder.py`

Status:
- Implemented as the production bridge from one placement seed to one initial runtime snapshot.

Responsibilities:
- Materialize runtime junctions for the active grid.
- Materialize runtime nodes for placed assignments.
- Apply occupancy links and active/inactive junction state.
- Build the initial `PortGraphState` with no prebuilt route edges.
- Keep boundary-facing junction ports present even where no outward neighbor exists; routing limits come from active-grid adjacency rather than port deletion.

Forbidden assumptions:
- No routing or commit behavior.
- No placement mutation or placement search.
- No inferred route edges from mere possibility.

### `route_orchestrator.py`

Status:
- Implemented as the thin source-grouped routing orchestrator on one fixed runtime snapshot.

Responsibilities:
- Group requirements by `source_object_ref`, preserving first source appearance and original in-source order.
- Route and commit one source-owned directed flow DAG at a time on immutable snapshots.
- Keep physical edge traversal capability separate from source-owned flow semantics.
- Allow additive fanout and suffix reuse inside the current source-owned flow DAG when the result remains acyclic.
- Reject current-source reachability to undeclared foreign node ports.
- Thread immutable snapshots forward after each successful commit.
- Stop on first failure and return snapshot-scoped failure with completed prefix information.

Forbidden assumptions:
- No alternate-route retries.
- No backtracking across committed requirements.
- No placement mutation or refinement.

### `placement_orchestrator.py`

Status:
- Implemented as a thin placement-level orchestrator over an explicit ordered set of placement seeds.

Responsibilities:
- Use the runtime snapshot builder to construct one initial runtime state per placement seed.
- Invoke the one-snapshot route orchestrator on each seed in order.
- Stop on first success or return failure scoped only to the tried seed set.

Forbidden assumptions:
- No placement generation.
- No placement mutation or search policy beyond the explicit ordered set.
- No route retries, requirement reordering, refinement, or grid expansion.

### `full_solve_orchestrator.py`

Status:
- Implemented as the thin explicit multi-grid solve loop above the current-grid shell.

Responsibilities:
- Build the minimum active grid from explicit x-rail ids and authored tier rails, or consume a reusable content-driven initial-grid estimate.
- Run the current-grid solve shell on each tried grid in order.
- Expand the grid only through the injected explicit grid-expansion policy.
- Retry after both placement-scoped and routing-scoped current-grid failure.
- Allow the current-grid shell to be bound either from explicit x rails plus minimum same-row gap or from an explicit reusable layout profile preset.
- Keep content-to-layout lower-bound estimation outside the retry loop itself.
- Stop on first success or return failure scoped only to the tried grid set.

Forbidden assumptions:
- No hidden grid-expansion heuristics.
- No profile-specific lower-bound inference in the retry loop itself.
- No placement, routing, or commit logic embedded in the orchestrator.
- No refinement.
- No renderer behavior.
- No claim that exhaustion of the tried grid set is global impossibility.

### `run_branch.py`

Status:
- Implemented as the current short file runner for requirement JSON -> solve -> base render.

Responsibilities:
- Load the current requirement-spec JSON through `skill_tree_requirements.py`.
- Compile it into explicit current graph content.
- Run the current estimated full solve loop with built-in default layout/expansion settings.
- Keep the built-in default expansion policy targeted to already-demanded bands instead of globally widening unrelated bands.
- Render and save the base PNG with short default command-line usage.

Forbidden assumptions:
- No legacy-prototype rendering path.
- No hidden solver-core policy beyond the explicitly bound default layout/expansion helpers.
- No claim that every requirement JSON is already solvable by the current logical stack.

### `render_contracts.py`

Status:
- Implemented as contract-only renderer-boundary data and protocol definitions.

Responsibilities:
- Define resolved render-ready object specs, neutral render instructions, and the render-resolver / primitive-expander boundary.
- Keep committed runtime truth separate from render-ready derived data.
- Keep the renderer itself object-agnostic by requiring generic instructions only.
- Allow a two-step render-preparation flow:
  - resolve per-object dynamic visual state first
  - expand resolved objects into generic renderer instructions afterward

Forbidden assumptions:
- No routing, legality, or commit logic.
- No raw graph interpretation in the renderer.
- No object-specific rendering policy embedded in the final renderer/compositor contract.

### `render_layout_profiles.py`

Status:
- Implemented as the data-only render-layout preset layer.

Responsibilities:
- Define concrete canvas size, default background ownership, default x-rail pixel positions, and authored-tier pixel rows as explicit preset data.
- Keep default dynamic-band pixel offsets local to render-layout profile data rather than embedding them into mapper or compositor core logic.

Forbidden assumptions:
- No runtime interpretation, routing, commit, or placement behavior.
- No asset-path ownership for object-family art.
- No renderer-core hardcoding of vanilla/default pixel rails.

### `render_mapper.py`

Status:
- Implemented as the first concrete logical-to-render mapper layer.

Responsibilities:
- Convert one active logical grid into explicit x/y rail pixel mappings using one explicit render-layout profile.
- Fail loudly when the current render-layout profile does not support the active authored-tier count or dynamic-band shape.
- Keep pixel mapping separate from render resolution and separate from generic grid/profile construction.

Forbidden assumptions:
- No asset loading or compositing.
- No routing, commit, or legality behavior.
- No hidden profile inference beyond the supplied render-layout preset.

### `render_template_loader.py`

Status:
- Implemented as the cached template-loading and transform layer.

Responsibilities:
- Load sprite-ref assets from repo-relative paths.
- Apply declared template transforms with caching.
- Keep art-file I/O and transform caching out of the compositor core.

Forbidden assumptions:
- No routing, placement, or commit behavior.
- No object-specific render logic.
- No asset-path ownership beyond consuming explicit template specs and repo-relative asset refs.

### `render_behavior_registry.py`

Status:
- Implemented as the external callable registry for object finalization and composition behavior.

Responsibilities:
- Register exact callable composition behavior by declared composition operator.
- Register optional per-profile object finalizers without changing renderer core.
- Keep "weird" object/family render behavior external to the core renderer.

Forbidden assumptions:
- No hardcoded object-family behavior in the renderer core.
- No asset-color interpretation guessed by the renderer core.
- No placement, routing, or commit behavior.

### `render_resolver.py`

Status:
- Implemented as the first concrete committed-runtime -> resolved-render-spec layer.

Responsibilities:
- Read committed runtime truth from `PortGraphState.objects` as the rendering source of truth.
- Resolve active node anchors and active node port pixel positions through the injected logical-to-render mapper plus build-geometry profiles.
- Resolve unoccupied-junction local built connections into render-ready junction specs only when those junctions actually own built local connection edges.
- Omit separate junction render specs for occupied sites because node-local rules are active there.
- Resolve active external built edges into separate edge render specs with resolved straight spans only.
- Fail loudly on unfrozen render-geometry cases rather than guessing, including unsupported non-axis-aligned external spans.

Forbidden assumptions:
- No renderer-side inference of legality, buildability, or route alternatives.
- No special casing of occupied junctions as active render substrates under a node.
- No implicit support for non-zero logical-anchor offsets until that meaning is frozen.
- No T/cross-specific junction rendering policy in engine code for v1.

### `primitive_expander.py`

Status:
- Implemented as the first concrete resolved-spec -> generic-instruction layer.

Responsibilities:
- Expand resolved object style bindings into generic sprite or pixel-mask stamp instructions.
- Expand current straight external spans into generic repeated-span instructions.
- Read layer ordering/composition and connection-family template data from the visual profile catalog.
- Read local-connection template bindings, per-binding offsets, and transforms from the visual profile catalog.

Forbidden assumptions:
- No direct reading of runtime truth or graph semantics.
- No legality, routing, or commit behavior.
- No invented transform or offset rules in renderer code.
- No hidden object-type logic in the renderer-facing instruction set.

### `base_renderer.py`

Status:
- Implemented as the first concrete base-render pipeline.

Responsibilities:
- Read committed runtime truth through the render resolver and primitive expander.
- Use the explicit render-layout profile for default background and canvas size.
- Sort generic render instructions by declared layer order.
- Dispatch all composition through the external render-behavior registry.
- Render the current base output from sprite stamps and repeated spans without embedding object-family-specific code.

Forbidden assumptions:
- No routing, placement, or commit behavior.
- No hidden composition behavior beyond declared operator callables.
- No asset-color interpretation in renderer core.
- No object-specific render finalization hardcoded in renderer core.

### `render_export.py`

Status:
- Implemented as the thin base-render export/testing helper layer.

Responsibilities:
- Render one committed runtime snapshot to the current base image through the concrete mapper and base renderer.
- Render one successful current-grid solve result to the current base image.
- Save the current base image to disk for smoke testing and manual review.

Forbidden assumptions:
- No solver behavior, routing, placement, or commit logic.
- No extra renderer policy beyond the already-frozen base renderer path.
- No format-specific export policy beyond simple image saving.
