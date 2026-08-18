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

## Shipping
- [ ] validate_prg passes
- [ ] layout_audit reviewed
- [ ] at least one post-routing cleanup pass completed
