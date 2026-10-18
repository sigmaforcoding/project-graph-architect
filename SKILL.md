---
name: project-graph-architect
description: |
  Turn projects, ideas, systems, workflows, comparisons, and knowledge structures into native Project Graph .prg files. Model semantics first, choose Project Graph primitives deliberately, use relationship-aware layout and theme-safe visual design, then validate the archive and audit collisions before delivery.
  Includes a dedicated thinking-chain mode (思考链路图) for two jobs: reviewing and remembering how a user and an AI reasoned through a conversation (对话复盘、思考来路、决策过程), and planning a task path with a branch per situation (路径规划、分情况怎么做、决策树、预案). Writes for people by default and can also produce an AI-readable version.
---

# Project Graph Architect Skill

Use this skill whenever the user asks to **draw, visualize, map, architect, or restructure something in Project Graph**, or asks for a `.prg` file.

## Default deliverable

Unless the user explicitly asks for another format, produce a **native `.prg` file that Project Graph can open**.

Do **not** substitute Mermaid, PNG, SVG, or a conceptual diagram for the `.prg` deliverable unless the user asks for those formats.

If public Project Graph source code is consulted, treat it as **read-only format/reference material**. Do not create issues, comments, pull requests, commits, releases, uploads, or other repository mutations unless the user explicitly asks for a repository write action.

## Choose the mode first

| The user wants… | Mode | Follow |
|---|---|---|
| 复盘：回看 / 记住和 AI 的思考过程、对话历程、决策来路 | **Thinking-chain · review** | `references/thinking_chain_mode.md` |
| 规划：动手前画任务路径、不同情况怎么做、预案、决策树 | **Thinking-chain · plan** | `references/thinking_chain_mode.md` |
| 架构、系统、流程、对比、知识结构等其他图 | **General** | the core workflow below |

Signals for thinking-chain mode: “思考链路”“复盘”“我们是怎么想到这里的”“对话历程做成图”“记住这个思路”“规划路径”“分情况”“如果…就…”“预案”.
If a request is about a conversation's history, it is review mode even if the user says “链路图” or “流程图”.

### Thinking-chain mode in short

1. Write an outline JSON (schema in `references/thinking_chain_mode.md`): one root (需求 / 目标), nodes linked by **cause** (review) or **condition** (plan), statuses on every node, exactly one stop node at the bottom.
   Always write the human fields: an `overview` for the whole graph, and for every node a natural-language `title` plus a 1–3 sentence `summary` that says what happened and why it matters (writing rules: section 3 of the mode reference). Add `short` labels as well whenever the AI version will be built.
2. **Decide the reader yourself — do not ask.** Set `--style` from the request and context:

   | Signal | Style |
   |---|---|
   | Default. The user will look at it: 复盘、记住思路、给我看、发给同学/老师/同事、放进笔记 | `human` |
   | The graph is context for another agent: 交给 Codex / GPT / Claude Code、当上下文、喂给 AI、写进 AGENTS.md 或记忆、压缩一点、省 token | `ai` |
   | Both readers are named or implied: 我看完再交给 Codex、自己复盘也给 AI 接手、存档并交接 | `both` (writes `out.prg` and `out_ai.prg`) |

   When unsure, use `human`: every `.prg` already embeds the full outline JSON, so an AI can always reload it (`thinking_chain.py extract`). State the chosen style in one line when delivering, so the user can ask for the other one.
3. `python scripts/thinking_chain.py tree outline.json` → show the text tree to the user and confirm the structure. Skip the wait only if the user already said to go ahead, and still attach the tree when delivering.
4. `python scripts/thinking_chain.py build outline.json out.prg --style <human|ai|both>` → semantic check + layered tree layout + collision relaxation + `.prg`.
   To **continue an earlier graph**, first run `thinking_chain.py extract old.prg outline.json`, extend the outline (new nodes, move the stop node down), and rebuild. Do not reconstruct it from the canvas.
5. Run `validate_prg.py` and `layout_audit.py` as usual; optionally `preview_prg.py` to look at it.

Rules that matter most:
- Branch by causality, not by topic. Several parallel topic pipelines with no fork means the extraction failed.
- Record only exploration that actually happened; rejected or superseded options need a reason.
- Write for a person re-reading the graph months later: full short sentences, the user as 「你」, AIs by name, no arrows or slashes as logic, no shorthand like 「实现缺口」.
- Unfinished branches end in place with a dashed border; the stop node's Details list them. Do not draw long “pending” lines across the graph to the stop node.
- The layered tree layout (`scripts/tree_layout.py`) is **only** for this mode. Steps 3–5 below (lanes, routing by role) do not apply to it.

## Mental model

Project Graph is not a pixel canvas. Treat it as a semantic graph workspace:

`meaning → entities → relations → graph primitives → spatial layout → visual hierarchy → QA → .prg`

The governing principle is:

> **Semantic operations first; pixel placement second.**

The graph should be understandable from nodes and relations even before visual polish, and the visual design should make the semantics easier to scan rather than merely decorative.

## Core workflow

### 1. Understand the user's actual model

Extract:
- central question / system / project,
- core entities,
- state or lifecycle,
- directed relations,
- undirected group relations,
- feedback loops,
- duplicated views of the same concept,
- modules that deserve subgraphs,
- details that belong in node Details rather than on the canvas.

Prefer a small number of meaningful nodes over turning every sentence into a node.

### 2. Choose native primitives deliberately

Use:
- `TextNode` for entities, concepts, states, decisions, rules, or annotations.
- `LineEdge` for ordinary directed semantic relations.
- `ArcEdge` for return paths, feedback, reverse relations, or any edge that would collide with the main lane.
- `MultiTargetUndirectedEdge` / Hyperedge for a true multi-node group relation or enclosure—not as a decorative frame.
- `Section` for a collapsible semantic module.
- `SyncAssociation` when the **same concept** must appear in multiple views and remain synchronized.
- `ReferenceBlockNode` when a subgraph should be a separately openable `.prg` referenced from the main graph.
- `Details` for deep explanation that would otherwise make the canvas noisy.

See `references/primitive_guide.md`.

### 3. Plan lanes before coordinates

*(General mode only. Thinking-chain mode uses the layered tree layout instead.)*

Before placing nodes, define spatial lanes such as:
- title / global principles,
- main modules,
- main flow lane,
- side-state lane,
- event lane,
- return / feedback lane,
- label lane,
- outer routing corridor,
- subgraph / reference area.

Do not place all nodes first and then hope the edges fit.

### 4. Allocate relationship-aware space

A node occupies more than its visible rectangle. Treat each node as four nested spaces:

1. **Content box** — actual node rectangle.
2. **Visual halo** — breathing room around it.
3. **Routing exclusion zone** — edges and labels should not enter this area unless they terminate at the node.
4. **Traffic context** — extra space determined by local edge density, label length, return paths, and section boundaries.

Dynamic spacing rule:

`required spacing = base spacing + label budget + edge-density budget + return-path budget + section padding`

Do not optimize for compactness. **Readability wins.**

### 5. Route by role

Default geometry:
- main chain: straight and monotonic,
- side branch: leaves the main chain sideways,
- return / feedback: ArcEdge or outer corridor,
- long-distance return: outer perimeter or unused top/bottom corridor,
- projection / mapping relation: separate lane,
- dense fan-out: trunk + fan-out, with selective labels.

Never let two opposite-direction relations share the same straight line.

If a continuous empty corridor exists, use it rather than crossing a busy node cluster.

### 6. Budget edge-label space before drawing

Every labeled edge requires room for:
- label width / line breaks,
- arrowhead,
- visible line before and after the label,
- distance from node borders,
- distance from unrelated edges and section titles.

If the label would dominate the line, shorten it or move explanation into Details.

Repeated semantic labels should be selectively omitted when layout already communicates the pattern.

### 7. Use theme-safe visual design

Color has two jobs and must be split accordingly:

- **Node fill color** encodes semantic module and hierarchy.
- **Edge / label color** encodes relation visibility and must remain readable on both dark and light canvases.

Do not reuse a dark node-fill brown/purple/green directly as an edge-label color on a dark background.

Use medium-light, medium-saturation edge colors with strong alpha. See `references/design_system.md`.

Within one semantic module, prefer one hue family and express hierarchy using:
- fill alpha,
- node size,
- font weight,
- border style,
- whitespace.

Avoid gratuitous new colors.

### 8. Keep semantic grouping labels semantically correct

If a Hyperedge label describes the **whole group**, first try to make room for the native Hyperedge label by:
- moving member nodes,
- increasing padding,
- moving the whole group,
- creating an empty label zone.

Do **not** convert a group-level annotation into a fake standalone semantic node merely to solve layout unless the annotation genuinely should become an entity.

Similarly, Section titles need a clear title band before the first row of child nodes.

### 9. Use progressive detail

Canvas text should communicate:
- identity,
- role,
- relation,
- current decision.

Long rationale, examples, assumptions, or evidence belong in `details`.

### 10. Build `.prg`

Current validated target for this skill:
- Project Graph application generation compatible with PRG metadata version `2.7.0`.
- `.prg` is a ZIP archive containing MsgPack payloads.
- Use ZIP store / compression level 0 for Project Graph payload files.

Use `scripts/prg27.py` rather than reimplementing serialization from memory.
In thinking-chain mode, `scripts/thinking_chain.py build` calls it for you.

### 11. Validate structurally

Run:

```bash
python scripts/validate_prg.py output.prg
```

Shipping must fail if:
- required archive entries are missing,
- metadata version is unexpected,
- stage references point outside the stage,
- unknown / malformed object basics are found.

### 12. Audit layout geometrically

Run:

```bash
python scripts/layout_audit.py output.prg
```

Treat findings as prompts for another layout pass, especially:
- edge passes through a non-endpoint node's protected halo,
- estimated edge-label box intersects a node,
- node-node spacing is below the relationship-aware minimum,
- Section areas crowd adjacent modules.

The audit is approximate—not a replacement for opening Project Graph—but it prevents obvious failures before delivery.

### 13. Perform a relaxation pass

After routing and audit, do not ship immediately. Perform at least one cleanup pass:
- move a node or entire module,
- widen vertical / horizontal spacing,
- change edge attachment side,
- change ArcEdge offset / textPosition,
- move long return paths to an outer corridor,
- increase Section / Hyperedge padding,
- shorten or remove redundant labels.

Then rebuild and rerun validation + audit.

### 14. Deliver

Provide:
- main `.prg`,
- any required same-name subfolder containing referenced `.prg` files,
- optionally a ZIP bundle when ReferenceBlock paths must be preserved.

Keep explanations concise unless the user asks for the design rationale.

## Hard quality rules

A graph is **not finished** merely because Project Graph opens it.

Do not ship when:
- text overlaps text,
- edge labels overlap nodes,
- relation lines visually disappear into the background,
- a return edge crosses a central node when an outer corridor is free,
- different large Sections compete for the same activity space,
- Hyperedge text sits on a central member node,
- arrows and labels leave no visible line segment,
- the diagram is compact at the cost of comprehension.

## Default design philosophy

> **先分区，后摆点；先留白，后连线；先语义，后装饰；先可读，后紧凑。**

And for relationship-aware layout:

> **不是“块之间不重叠”就够了，而是块、线、标签、群组边界都必须拥有安全活动空间。**
