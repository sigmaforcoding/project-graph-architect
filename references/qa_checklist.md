# QA / Shipping Checklist

## Structural
- [ ] `.prg` opens as ZIP
- [ ] `stage.msgpack` exists
- [ ] `tags.msgpack` exists
- [ ] `reference.msgpack` exists
- [ ] `metadata.msgpack` exists
- [ ] metadata version is `2.7.0`
- [ ] every `$` stage reference resolves
- [ ] referenced child `.prg` files are bundled when needed

## Semantic
- [ ] every important edge has a meaningful relation or the pattern is obvious enough to omit a duplicate label
- [ ] duplicate view instances use SyncAssociation only when they are genuinely the same concept
- [ ] Hyperedge is a genuine group relation, not merely a decorative rectangle
- [ ] Section boundaries correspond to semantic modules
- [ ] Details hold long explanation instead of canvas clutter

## Layout
- [ ] no node-node overlap
- [ ] no non-endpoint edge enters another node's routing halo
- [ ] no edge label visibly overlaps a node
- [ ] long return paths use outer corridors when available
- [ ] Section title bands are clear
- [ ] large modules have separate activity space
- [ ] Hyperedge label occupies an intentional empty zone
- [ ] arrows remain visible before / after relation text

## Visual
- [ ] edge / label colors are readable on dark canvas
- [ ] edge / label colors remain reasonably visible on light canvas
- [ ] one semantic module uses one hue family
- [ ] hierarchy is visible before reading the text
- [ ] no decorative color competes with the core information

## Thinking-chain mode (review / plan)
- [ ] `thinking_chain.py check` passes with no errors; warnings reviewed
- [ ] the root is the user's requirement / goal, with the user's original words in Details
- [ ] branches follow cause (review) or condition (plan), not topic
- [ ] user-driven turns are marked (`by: "user"`, blue)
- [ ] nothing invented: every review node traces to a conversation turn
- [ ] every branch either reaches the stop node or ends in an allowed terminal status
- [ ] plan: every branch point has ≥2 labelled cases, and a catch-all when there are more than two
- [ ] stop node Details list decision / completion condition, unfinished branches, exits, next steps
- [ ] text tree shown to the user (confirmed, or attached when the user said to go ahead)
- [ ] `build` reported no residual layout findings
- [ ] human style (default): overview and every summary read as plain sentences a person understands without the conversation; no node ids or notation on the canvas
- [ ] ai style only when the reader is an AI, or delivered alongside the human version

## Shipping
- [ ] validate_prg passes
- [ ] layout_audit reviewed
- [ ] at least one post-routing cleanup pass completed
