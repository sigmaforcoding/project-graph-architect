"""Layered top-down layout for thinking-chain graphs.

Scope: ONLY used by thinking-chain mode (see references/thinking_chain_mode.md).
Architecture / flow / comparison graphs keep the lane-based workflow in SKILL.md.

Input is a DAG with one root and (optionally) one forced-bottom sink:
  tree-like expansion  +  occasional merges  +  a single stop node.

Algorithm (Sugiyama-lite):
  1. layer   = longest path from root; sink is forced to the last layer
  2. dummies = edges spanning >1 layer get a dummy slot in every layer they cross,
               so straight lines run through reserved empty corridors
  3. order   = barycenter sweeps (down/up), keep the ordering with fewest crossings
  4. x       = alternate sweeps; each layer is solved by weighted isotonic
               regression (PAVA) so nodes sit as close as possible to the mean of
               their neighbours while respecting per-pair minimum separations
  5. y       = per-layer height + per-gap vertical budget (label height + visible line)
The caller supplies sizes and spacing callbacks; this module knows nothing about PRG.
"""
from __future__ import annotations
from collections import defaultdict


def assign_layers(ids, edges, sink=None):
    children, parents = defaultdict(list), defaultdict(list)
    for s, t in edges:
        children[s].append(t)
        parents[t].append(s)
    indeg = {i: len(parents[i]) for i in ids}
    ready = [i for i in ids if indeg[i] == 0]
    order = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for c in children[n]:
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
    if len(order) != len(ids):
        raise ValueError("graph contains a cycle; thinking-chain graphs must be acyclic")
    layer = {}
    for n in order:
        layer[n] = 0 if not parents[n] else max(layer[p] for p in parents[n]) + 1
    if sink is not None and len(ids) > 1:
        layer[sink] = max(v for k, v in layer.items() if k != sink) + 1
    return layer


def _crossings(upper, lower, down_nb):
    pos_l = {n: i for i, n in enumerate(lower)}
    segs = []
    for i, u in enumerate(upper):
        for v in down_nb.get(u, []):
            if v in pos_l:
                segs.append((i, pos_l[v]))
    c = 0
    for a in range(len(segs)):
        for b in range(a + 1, len(segs)):
            if (segs[a][0] - segs[b][0]) * (segs[a][1] - segs[b][1]) < 0:
                c += 1
    return c


def _pava(values, weights):
    """Weighted isotonic regression (non-decreasing)."""
    blocks = []  # [value, weight, count]
    for v, w in zip(values, weights):
        blocks.append([v, w, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            v2, w2, c2 = blocks.pop()
            v1, w1, c1 = blocks.pop()
            wt = w1 + w2
            blocks.append([(v1 * w1 + v2 * w2) / wt, wt, c1 + c2])
    out = []
    for v, _, c in blocks:
        out.extend([v] * c)
    return out


def layered_layout(ids, edges, size, *, sink=None, rank=None, sep=None,
                   gap_height=None, dummy_width=None, layer_gap=220.0,
                   sweeps=16, x_iters=40):
    """Return (rects, info).

    ids          node ids (outline order = tie-break order)
    edges        list of (src, dst)
    size(id)     -> (w, h)
    sep(a, b, wa, wb) -> min centre distance for neighbours a|b in one layer
                 (a / b may be dummy tuples ('~', src, dst, layer))
    gap_height(k)-> vertical gap below layer k (defaults to layer_gap)
    dummy_width(src, dst, layer) -> width reserved for a long edge in that layer
    rects        id -> (left, top, w, h)
    """
    rank = rank or {n: i for i, n in enumerate(ids)}
    layer = assign_layers(ids, edges, sink)
    nlayers = max(layer.values()) + 1
    up, down = defaultdict(list), defaultdict(list)
    width = {n: size(n)[0] for n in ids}
    height = {n: size(n)[1] for n in ids}
    dummies = []
    for s, t in edges:
        prev = s
        for k in range(layer[s] + 1, layer[t]):
            d = ("~", s, t, k)
            dummies.append(d)
            layer[d] = k
            rank[d] = rank[t] - 0.5
            width[d] = dummy_width(s, t, k) if dummy_width else 40.0
            height[d] = 0.0
            down[prev].append(d)
            up[d].append(prev)
            prev = d
        down[prev].append(t)
        up[t].append(prev)

    layers = [[] for _ in range(nlayers)]
    for n in list(ids) + dummies:
        layers[layer[n]].append(n)

    # initial ordering: down sweep by parent position, tie-break outline order
    pos = {}
    for k, L in enumerate(layers):
        if k == 0:
            L.sort(key=lambda n: rank[n])
        else:
            L.sort(key=lambda n: (sum(pos[p] for p in up[n]) / len(up[n]) if up[n] else 0, rank[n]))
        for i, n in enumerate(L):
            pos[n] = i

    def total_cross(ls):
        return sum(_crossings(ls[k], ls[k + 1], down) for k in range(len(ls) - 1))

    best = [list(L) for L in layers]
    best_c = total_cross(best)
    for it in range(sweeps):
        rng = range(1, nlayers) if it % 2 == 0 else range(nlayers - 2, -1, -1)
        for k in rng:
            nb = up if it % 2 == 0 else down
            L = layers[k]
            L.sort(key=lambda n: (sum(pos[p] for p in nb[n]) / len(nb[n]) if nb[n] else pos[n], pos[n]))
            for i, n in enumerate(L):
                pos[n] = i
        c = total_cross(layers)
        if c < best_c:
            best_c, best = c, [list(L) for L in layers]
    layers = best

    def sep_of(a, b):
        base = (width[a] + width[b]) / 2.0
        return max(base, sep(a, b, width[a], width[b])) if sep else base + 120.0

    # x coordinates
    x = {}
    for L in layers:
        cur = 0.0
        for i, n in enumerate(L):
            if i:
                cur += sep_of(L[i - 1], n)
            x[n] = cur
        for n in L:
            x[n] -= cur / 2.0

    def solve(L, target, weight):
        offs, acc = [], 0.0
        for i, n in enumerate(L):
            if i:
                acc += sep_of(L[i - 1], n)
            offs.append(acc)
        vals = [target[n] - o for n, o in zip(L, offs)]
        ys = _pava(vals, [weight[n] for n in L])
        for n, y, o in zip(L, ys, offs):
            x[n] = y + o

    is_dummy = lambda n: isinstance(n, tuple)

    def interp(d):
        # where the straight source->target line actually crosses this layer
        _, s_, t_, k = d
        r = (k - layer[s_]) / float(layer[t_] - layer[s_])
        return x[s_] * (1 - r) + x[t_] * r

    for it in range(x_iters):
        going_down = it % 2 == 0
        late = it >= x_iters // 2   # second half: dummies follow the real straight line, order may adapt
        rng = range(1, nlayers) if going_down else range(nlayers - 2, -1, -1)
        for k in rng:
            L = layers[k]
            target, weight = {}, {}
            for n in L:
                nb = up[n] if going_down else down[n]
                if is_dummy(n):
                    target[n] = interp(n) if late else sum(x[m] for m in up[n] + down[n]) / 2.0
                    weight[n] = 8.0
                else:
                    target[n] = sum(x[m] for m in nb) / len(nb) if nb else x[n]
                    weight[n] = 1.0 + 0.25 * len(nb)
            if late:
                # only dummies (long-edge corridors) may change slots; real nodes keep the
                # crossing-minimised order chosen above
                reals = [n for n in L if not is_dummy(n)]
                ds = sorted([n for n in L if is_dummy(n)], key=lambda n: target[n])
                merged, j = [], 0
                for n in reals:
                    while j < len(ds) and target[ds[j]] < x[n]:
                        merged.append(ds[j]); j += 1
                    merged.append(n)
                merged += ds[j:]
                L[:] = merged
            solve(L, target, weight)

    # y coordinates
    tops, cur = [], 0.0
    for k, L in enumerate(layers):
        tops.append(cur)
        lh = max([height[n] for n in L if not is_dummy(n)] or [0.0])
        cur += lh + (gap_height(k) if gap_height else layer_gap)
    lheights = [max([height[n] for n in L if not is_dummy(n)] or [0.0]) for L in layers]

    minx = min(x[n] - width[n] / 2 for n in ids)
    rects = {}
    for n in ids:
        k = layer[n]
        cy = tops[k] + lheights[k] / 2.0
        rects[n] = (x[n] - width[n] / 2 - minx, cy - height[n] / 2, width[n], height[n])
    info = {"layer": {n: layer[n] for n in ids}, "layers": nlayers,
            "crossings": best_c, "dummies": len(dummies)}
    return rects, info
