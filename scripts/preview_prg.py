#!/usr/bin/env python3
"""Approximate PNG preview of a .prg (TextNode + LineEdge + ArcEdge-as-dashed-chord).

For the agent's own visual QA before delivery; Project Graph remains authoritative.
Usage: python scripts/preview_prg.py file.prg out.png [--light]
Requires matplotlib and a CJK font (Noto Sans/Serif CJK, PingFang, Microsoft YaHei...).
"""
import sys, zipfile, msgpack, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

CANDIDATES = ["Noto Sans CJK SC", "Noto Serif CJK SC", "PingFang SC", "Microsoft YaHei",
              "Source Han Sans SC", "WenQuanYi Micro Hei", "SimHei"]


FONT_FILES = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
              "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
              "C:/Windows/Fonts/msyh.ttc"]


def font():
    import os, glob
    for p in FONT_FILES + glob.glob("/usr/share/fonts/**/*CJK*.tt[cf]", recursive=True):
        if os.path.exists(p):
            try:
                font_manager.fontManager.addfont(p)
                return font_manager.FontProperties(fname=p).get_name()
            except Exception:
                pass
    have = {f.name for f in font_manager.fontManager.ttflist}
    for c in CANDIDATES:
        if c in have:
            return c
    return None


def rect(o):
    s = o["collisionBox"]["shapes"][0]
    return s["location"]["x"], s["location"]["y"], s["size"]["x"], s["size"]["y"]


def anchor(r, rate):
    l, t, w, h = r
    x, y = rate["x"], rate["y"]
    if y == 0.99: return l + w / 2, t + h
    if y == 0.01: return l + w / 2, t
    if x == 0.99: return l + w, t + h / 2
    if x == 0.01: return l, t + h / 2
    return l + w * x, t + h * y


def main(src, out, light=False):
    with zipfile.ZipFile(src) as z:
        stage = msgpack.unpackb(z.read("stage.msgpack"), raw=False)
    f = font()
    if f: plt.rcParams["font.family"] = f
    bg, fg = ("#f7f5f0", "#222") if light else ("#1e1f22", "#e6e6e6")
    rs = {i: rect(o) for i, o in enumerate(stage) if o.get("_") in ("TextNode", "ReferenceBlockNode")}
    minx = min(r[0] for r in rs.values()) - 100; maxx = max(r[0] + r[2] for r in rs.values()) + 100
    miny = min(r[1] for r in rs.values()) - 100; maxy = max(r[1] + r[3] for r in rs.values()) + 100
    W, H = maxx - minx, maxy - miny
    scale = 1 / 110.0
    fig = plt.figure(figsize=(W * scale, H * scale), dpi=60)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(minx, maxx); ax.set_ylim(maxy, miny); ax.axis("off")
    fig.patch.set_facecolor(bg)
    pt = 72 * scale * 60 / 60  # world px -> points at this figure scale
    for i, o in enumerate(stage):
        if o.get("_") not in ("LineEdge", "ArcEdge"): continue
        a, b = [int(r["$"][1:]) for r in o["associationList"][:2]]
        if a not in rs or b not in rs: continue
        p1 = anchor(rs[a], o["sourceRectangleRate"]); p2 = anchor(rs[b], o["targetRectangleRate"])
        c = o["color"]; col = (c["r"] / 255, c["g"] / 255, c["b"] / 255, c["a"]) if c["a"] else fg
        ls = "--" if o.get("lineType") == "dashed" or o["_"] == "ArcEdge" else "-"
        ax.annotate("", xy=p2, xytext=p1, arrowprops=dict(arrowstyle="-|>", color=col, lw=1.6, ls=ls,
                                                            shrinkA=0, shrinkB=0, mutation_scale=14))
        if o.get("text"):
            m = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
            ax.text(*m, o["text"], ha="center", va="center", color=col, fontsize=32 * pt * 0.9,
                    bbox=dict(boxstyle="square,pad=0.1", fc=bg, ec="none"), linespacing=1.3)
    for i, o in enumerate(stage):
        if o.get("_") != "TextNode": continue
        l, t, w, h = rs[i]; c = o["color"]
        fc = (c["r"] / 255, c["g"] / 255, c["b"] / 255, min(1, c["a"] * 2.2)) if c["a"] else bg
        ax.add_patch(FancyBboxPatch((l, t), w, h, boxstyle="round,pad=0,rounding_size=8", fc=fc, ec=fg,
                                    lw=1.2, ls="--" if o.get("borderStyle") == "dashed" else "-"))
        fs = 32 * 2 ** (o.get("fontScaleLevel", 0) / 2) * pt * 0.9
        ax.text(l + w / 2, t + h / 2, o["text"], ha="center", va="center", color=fg, fontsize=fs,
                linespacing=1.35, fontweight="bold" if o.get("fontWeight") in ("600", "700") else "normal")
    fig.savefig(out, facecolor=bg)
    print(out)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    main(sys.argv[1], sys.argv[2], "--light" in sys.argv)
