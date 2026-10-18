#!/usr/bin/env python3
"""Thinking-chain mode: outline JSON -> semantic check -> tree preview -> layered .prg

Two sub-modes, chosen by the outline's top-level "mode":
  "review" (default)  复盘：record how the user and the AI actually reasoned
                      requirement -> questions / options / checks / findings -> decisions -> stop
  "plan"              规划：plan a task path before doing it, one branch per situation
                      goal -> steps / branch points (edge = condition) -> exits / fallbacks -> goal reached

Writing styles, chosen by "style" in the outline or --style on the command line:
  "human" (default)   给人读：自然语言标题 + 画布上 1–3 句摘要 + 散文式详情，三个月后不看对话也能读懂
  "ai"                给 AI 读：短标题、节点编号、结构化详情，适合交给另一个 AI 当上下文
  "both"              两张都出：out.prg（给人读）和 out_ai.prg（给 AI 读）
Every .prg also embeds the full outline JSON in its README, so any AI can reload it.

Usage:
  python scripts/thinking_chain.py check   outline.json [--style human|ai|both]
  python scripts/thinking_chain.py tree    outline.json [--style human|ai]
  python scripts/thinking_chain.py build   outline.json out.prg [--style human|ai|both]
  python scripts/thinking_chain.py extract graph.prg [outline.json]   # get the outline back to continue a graph

See references/thinking_chain_mode.md for the outline schema and modelling rules.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import json, sys, unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prg27 import PRG27, plate_details  # noqa: E402
from tree_layout import layered_layout   # noqa: E402

# ---------------------------------------------------------------- vocabulary
REVIEW_KINDS = {
    "requirement": "需求", "subgoal": "子需求", "question": "问题", "option": "方案",
    "hypothesis": "假设", "check": "验证", "finding": "发现", "decision": "决定", "stop": "终点",
}
PLAN_KINDS = {
    "requirement": "目标", "subgoal": "子目标", "branch": "判断", "step": "步骤",
    "check": "检查点", "decision": "决定", "stop": "终点",
}
REVIEW_STATUSES = {
    "adopted": "采用", "confirmed": "已证实", "resolved": "已解决",
    "rejected": "否定", "superseded": "被取代",
    "pending": "待验证", "open": "未解决", "parked": "搁置",
}
PLAN_STATUSES = {
    "planned": "计划", "optional": "可选", "fallback": "备选", "done": "已完成",
    "unknown": "未定", "blocked": "受阻",
    "abort": "中止", "handoff": "交给你",
}
MODES = {
    # TERMINAL   = statuses allowed to end a branch without reaching the stop node
    # UNFINISHED = listed as 未完成/未定 at the stop node
    # EXCLUDED   = listed as 已排除 (review) / 出口 (plan) at the stop node; need a reason
    "review": dict(kinds=REVIEW_KINDS, statuses=REVIEW_STATUSES,
                   terminal={"rejected", "superseded", "pending", "open", "parked"},
                   unfinished={"pending", "open", "parked"}, excluded={"rejected", "superseded"},
                   default_status=None, header="思考链路图", stop_label="终点 · 停止思考",
                   unf_word="未完成", exc_word="已排除"),
    "plan": dict(kinds=PLAN_KINDS, statuses=PLAN_STATUSES,
                 terminal={"unknown", "blocked", "abort", "handoff"},
                 unfinished={"unknown", "blocked"}, excluded={"abort", "handoff"},
                 default_status="planned", header="路径规划图", stop_label="终点 · 目标达成",
                 unf_word="未定", exc_word="出口"),
}
M = MODES["review"]   # active mode; set by set_mode()
KINDS, STATUSES = M["kinds"], M["statuses"]
TERMINAL, UNFINISHED, EXCLUDED = M["terminal"], M["unfinished"], M["excluded"]


def set_mode(data):
    global M, KINDS, STATUSES, TERMINAL, UNFINISHED, EXCLUDED
    mode = data.get("mode", "review")
    if mode not in MODES:
        raise SystemExit(f"ERROR: mode must be one of {list(MODES)} (got {mode!r})")
    M = MODES[mode]
    KINDS, STATUSES = M["kinds"], M["statuses"]
    TERMINAL, UNFINISHED, EXCLUDED = M["terminal"], M["unfinished"], M["excluded"]
    if M["default_status"]:
        for n in data.get("nodes", []):
            if n.get("kind") not in ("requirement", "stop"):
                n.setdefault("status", M["default_status"])
    return mode


DRIVERS = {"reasoning", "user", "evidence"}

# fill colours: one hue family per kind; alpha encodes status strength
KIND_FILL = {
    "requirement": (40, 90, 150), "subgoal": (55, 105, 160), "question": (110, 80, 145),
    "option": (150, 105, 55), "hypothesis": (150, 105, 55), "check": (40, 120, 110),
    "finding": (50, 120, 80), "decision": (70, 100, 130), "stop": (95, 95, 95),
    "branch": (110, 80, 145), "step": (150, 105, 55),
}
STATUS_ALPHA = {"adopted": .30, "confirmed": .26, "resolved": .26, "pending": .14,
                "open": .14, "parked": .09, "rejected": .07, "superseded": .07,
                "planned": .26, "done": .30, "optional": .14, "fallback": .14,
                "unknown": .10, "blocked": .10, "abort": .07, "handoff": .10}
EDGE_COLOR = {
    "reasoning": (165, 165, 165, .96), "user": (89, 140, 205, .96), "evidence": (71, 172, 150, .96),
    "stop": (92, 169, 130, .96), "excluded": (196, 141, 84, .96),
}

STYLES = {
    # wrap widths are display units (1 CJK char = 1 unit)
    "ai":    dict(title_wrap=14, label_wrap=6, summary_wrap=0),
    "human": dict(title_wrap=16, label_wrap=7, summary_wrap=17),
}
STYLE = "human"
AI_MARKS = "→←⇒≠≈↪|/+=&<>[]{}#`*_~"   # symbols that read as notation, not prose

FONT = 32.0          # Project Graph Renderer.FONT_SIZE
PAD = 14.0           # Renderer.NODE_PADDING
LINE_H = 1.5         # text node line height factor
LABEL_FONT = 32.0    # edge label font (conservative)
HALO = 42.0   # same protected halo as layout_audit.py


# ---------------------------------------------------------------- text utils
def cw(ch):
    return 1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.56


def units(s):
    return sum(cw(c) for c in s)


def wrap(text, limit):
    """Wrap by display units; CJK may break anywhere, ASCII words/numbers stay whole."""
    import re
    out = []
    for para in str(text).split("\n"):
        line, u = "", 0.0
        for tok in re.findall(r"[A-Za-z0-9_.\-/+%]+|\s+|.", para):
            tu = units(tok)
            if u + tu > limit and line.strip():
                out.append(line.rstrip()); line, u = "", 0.0
                if tok.isspace():
                    continue
            line += tok; u += tu
        out.append(line.rstrip())
    return "\n".join(out)


def text_box(text, font, pad=PAD):
    lines = text.split("\n")
    w = max(units(l) for l in lines) * font + pad * 2 + 24
    h = len(lines) * font * LINE_H + pad * 2 + 6
    return max(w, 220.0), h


def label_box(text):
    if not text:
        return 0.0, 0.0
    lines = text.split("\n")
    return max(units(l) for l in lines) * LABEL_FONT + 20, len(lines) * LABEL_FONT * 1.5 + 12


def join_lines(t):
    """Undo hand-made line breaks: no space between CJK, one space between ASCII words."""
    out = ""
    for part in str(t).split("\n"):
        if out and part and (out[-1].isascii() and out[-1].isalnum()) and (part[0].isascii() and part[0].isalnum()):
            out += " "
        out += part.strip()
    return out


def title_of(n):
    if STYLE == "ai":
        return n.get("short") or n.get("title", "")
    return join_lines(n.get("title", ""))


def flat(t):
    return join_lines(t)


def writing_findings(text, where, min_units=12, max_units=130, sentence=True):
    """Prose checks for human style."""
    w = []
    t = flat(text)
    marks = sorted({c for c in t if c in AI_MARKS})
    if marks:
        w.append(f"{where}: notation symbols {''.join(marks)} read as shorthand; say it in words")
    u = units(t)
    if u < min_units:
        w.append(f"{where}: too short to stand alone ({u:.0f} units); say what happened and why it matters")
    if u > max_units:
        w.append(f"{where}: too long for the canvas ({u:.0f} units); keep 1–3 sentences, move the rest to details")
    if sentence and t and t[-1] not in "。！？…」）":
        w.append(f"{where}: write complete sentences ending with 。？！")
    return w


# ---------------------------------------------------------------- model
def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["_mode"] = set_mode(data)
    data.setdefault("style", "human")
    nodes = data.get("nodes", [])
    edges = []   # dicts: src, dst, why, by
    for n in nodes:
        for f in n.get("from", []) or []:
            if isinstance(f, str):
                f = {"id": f}
            edges.append({"src": f.get("id"), "dst": n.get("id"), "why": f.get("why", ""),
                          "short": f.get("short", ""), "by": f.get("by", "reasoning")})
    return data, nodes, edges


def check(data, nodes, edges):
    errors, warns = [], []
    ids = [n.get("id") for n in nodes]
    byid = {}
    for n in nodes:
        i = n.get("id")
        if not i:
            errors.append("node without id"); continue
        if i in byid:
            errors.append(f"duplicate id {i}")
        byid[i] = n
    children = defaultdict(list)
    for e in edges:
        if e["src"] not in byid:
            errors.append(f"{e['dst']}: from references unknown id {e['src']!r}")
        elif e["src"] == e["dst"]:
            errors.append(f"{e['dst']}: self loop")
        else:
            children[e["src"]].append(e["dst"])
        if e["by"] not in DRIVERS:
            errors.append(f"{e['src']}->{e['dst']}: by must be one of {sorted(DRIVERS)}")
    roots = [n for n in nodes if n.get("kind") == "requirement"]
    stops = [n for n in nodes if n.get("kind") == "stop"]
    if len(roots) != 1:
        errors.append(f"need exactly one requirement (root: {KINDS['requirement']}) node, found {len(roots)}")
    if len(stops) != 1:
        errors.append(f"need exactly one stop node, found {len(stops)}")
    for n in nodes:
        i, k = n.get("id"), n.get("kind")
        if k not in KINDS:
            errors.append(f"{i}: unknown kind {k!r}"); continue
        has_from = bool(n.get("from"))
        if k == "requirement":
            if has_from: errors.append(f"{i}: requirement must not have parents")
            if not n.get("quote"): warns.append(f"{i}: requirement has no quote (user's original words)")
            continue
        if not has_from:
            errors.append(f"{i}: only the requirement may lack 'from' (orphan node)")
        if k == "stop":
            if children.get(i): errors.append(f"{i}: stop node must not have children")
            if data["_mode"] == "review" and not n.get("reason"):
                warns.append(f"{i}: stop has no 'reason' (why thinking stopped)")
            if data["_mode"] == "plan" and not n.get("done_when"):
                warns.append(f"{i}: plan stop has no 'done_when' (completion condition)")
            if not n.get("next"): warns.append(f"{i}: stop has no 'next' steps")
            continue
        st = n.get("status")
        if st not in STATUSES:
            errors.append(f"{i}: status must be one of {list(STATUSES)} (got {st!r})")
        elif not children.get(i) and st not in TERMINAL:
            errors.append(f"{i}: branch ends at status '{st}'. Either connect it onward "
                          f"(to a later node or the stop) or mark it {sorted(TERMINAL)}")
        if st in EXCLUDED and not n.get("reason"):
            errors.append(f"{i}: {st} node needs a 'reason'")
        if data["_mode"] == "review" and not n.get("turn"):
            warns.append(f"{i}: no 'turn' (source in the conversation) — traceability")
        if k == "branch":
            outs = [e for e in edges if e["src"] == i]
            if len(outs) < 2:
                errors.append(f"{i}: branch point needs ≥2 cases (outgoing edges), found {len(outs)}")
            for e in outs:
                if not e["why"]:
                    errors.append(f"{i}->{e['dst']}: every case leaving a branch point needs a condition in 'why'")
            conds = {flat(e["why"]).split("，")[0] for e in outs}
            if len(conds) > 2 and not any(w in e["why"] for e in outs for w in ("否则", "其他", "其它", "都不", "else", "otherwise")):
                warns.append(f"{i}: no catch-all case (否则/其他). Are the cases exhaustive?")
        t = wrap(title_of(n), STYLES[STYLE]["title_wrap"])
        if t.count("\n") >= 2:
            warns.append(f"{i}: title wraps to >2 lines on canvas; shorten and move text to details")
    if STYLE == "human":
        hint = " (or render with --style ai)"
        if not data.get("overview"):
            errors.append("human style needs a graph-level 'overview': 2–4 sentences telling the whole story" + hint)
        else:
            warns += writing_findings(data["overview"], "overview", 40, 260)
        for n in nodes:
            i = n.get("id")
            if not n.get("summary"):
                errors.append(f"{i}: human style needs a 'summary' (1–3 sentences shown on the canvas){hint}")
            else:
                warns += writing_findings(n["summary"], f"{i}.summary")
            tt = flat(n.get("title", ""))
            tm = sorted({c for c in tt if c in AI_MARKS})
            if tm:
                warns.append(f"{i}.title: notation symbols {''.join(tm)}; write it as a phrase")
        for e in edges:
            src_kind = byid.get(e["src"], {}).get("kind")
            w_ = flat(e["why"])
            marks = sorted({c for c in w_ if c in AI_MARKS and not (src_kind == "branch" and c == "/")})
            if marks:
                warns.append(f"{e['src']}->{e['dst']}: label uses {''.join(marks)}; say it in words")
    for e in edges:
        dst = byid.get(e["dst"], {})
        n_in = sum(1 for x in edges if x["dst"] == e["dst"])
        if dst.get("kind") != "stop" and not e["why"] and n_in < 2:
            warns.append(f"{e['src']}->{e['dst']}: edge has no 'why'")
        lw_ = STYLES[STYLE]["label_wrap"]
        lab = flat(e["why"]) if STYLE == "human" else (e["short"] or e["why"])
        if lab and wrap(lab, lw_).count("\n") >= 2:
            warns.append(f"{e['src']}->{e['dst']}: label >2 lines ({flat(e['why'])!r}); keep it ≤{2 * lw_} CJK chars")
    if errors:
        return errors, warns
    # cycles + reachability
    try:
        from tree_layout import assign_layers
        layer = assign_layers(ids, [(e["src"], e["dst"]) for e in edges], stops[0]["id"])
    except ValueError as ex:
        errors.append(str(ex)); return errors, warns
    branching = [i for i in ids if len(children.get(i, [])) >= 2]
    merges = [i for i in ids if sum(1 for e in edges if e["dst"] == i) >= 2 and byid[i]["kind"] != "stop"]
    if data["_mode"] == "plan" and len(nodes) >= 6 and not any(n["kind"] == "branch" for n in nodes):
        warns.append("plan has no branch point: it only covers the happy path. Add 判断 nodes for "
                     "situations that change what to do.")
    if len(nodes) >= 6 and not branching:
        errors.append("no node has ≥2 children: this is a pipeline, not a thinking tree. "
                      "Model where one question opened several options/checks.")
    depth = max(layer.values())
    if len(nodes) >= 10 and depth <= 2:
        warns.append(f"only {depth + 1} layers for {len(nodes)} nodes: graph is flat; check causal order")
    data["_stats"] = {"nodes": len(nodes), "edges": len(edges), "branch_nodes": len(branching),
                      "merge_nodes": len(merges), "layers": depth + 1,
                      "unfinished": len(unfinished_nodes(nodes, edges))}
    return errors, warns


def tree_text(data, nodes, edges):
    byid = {n["id"]: n for n in nodes}
    kids = defaultdict(list)
    for e in edges:
        kids[e["src"]].append(e)
    root = next(n for n in nodes if n["kind"] == "requirement")
    seen, out = set(), [f"# {M['header']}：{data.get('title', '')}"]

    def tag(n):
        st = STATUSES.get(n.get("status"), "")
        return f"[{KINDS[n['kind']]}{'·' + st if st else ''}] {flat(title_of(n))}"

    n_par = defaultdict(int)
    for e in edges:
        n_par[e["dst"]] += 1
    arrived = defaultdict(int)

    def walk(nid, depth, why="", by="", _branch_edge=False):
        n = byid[nid]
        pre = "  " * depth + ("└ " if depth else "")
        if data.get("_mode") == "plan":
            reason = (f"   ← {'若：' if _branch_edge else ''}{why.replace(chr(10), '')}" if why else "") + ("  [由你决定]" if by == "user" else "")
        else:
            reason = (f"   ← {why.replace(chr(10), '')}" if why else "") + ("  [你推动]" if by == "user" else "")
        arrived[nid] += 1
        if nid in seen or arrived[nid] < max(1, n_par[nid]):
            # expand a merge node only under its last parent; earlier parents show a pointer
            out.append(f"{pre}↪ 合流到 {nid} {flat(title_of(n))}{reason}")
            return
        seen.add(nid)
        out.append(f"{pre}{nid} {tag(n)}{reason}")
        if STYLE == "human" and n.get("summary"):
            out.append("  " * depth + ("  " if depth else "") + "    " + flat(n["summary"]))
        for e in kids[nid]:
            walk(e["dst"], depth + 1, e["why"], e["by"], n.get("kind") == "branch")

    walk(root["id"], 0)
    unf = unfinished_nodes(nodes, edges)
    exc = [n for n in nodes if n.get("status") in EXCLUDED]
    if data.get("_mode") == "plan" and exc:
        out.append("\n出口（不走到目标的情况）：")
        out += [f"  - {n['id']} [{STATUSES[n['status']]}] {flat(title_of(n))}" for n in exc]
    if unf:
        out.append(f"\n{M['unf_word']}分支（终点处列出）：")
        out += [f"  - {n['id']} [{STATUSES[n['status']]}] {flat(title_of(n))}" for n in unf]
    return "\n".join(out)


# ---------------------------------------------------------------- build
def unfinished_nodes(nodes, edges):
    """Unfinished nodes that are the deepest unfinished point of their branch
    (a pending parent whose descendant is also pending is not listed twice)."""
    st = {n["id"]: n.get("status") for n in nodes}
    kids = defaultdict(list)
    for e in edges:
        kids[e["src"]].append(e["dst"])

    def has_unfinished_below(i, seen=None):
        seen = seen or set()
        for c in kids[i]:
            if c in seen: continue
            seen.add(c)
            if st.get(c) in UNFINISHED or has_unfinished_below(c, seen):
                return True
        return False
    return [n for n in nodes if n.get("status") in UNFINISHED and not has_unfinished_below(n["id"])]


def node_text(n, unfinished_count):
    k = n["kind"]
    sw = STYLES[STYLE]
    title = wrap(title_of(n), sw["title_wrap"])
    if k == "requirement":
        head = KINDS["requirement"]
    elif k == "stop":
        head = M["stop_label"]
    elif n["status"] == M["default_status"]:
        head = KINDS[k]
    else:
        head = f"{KINDS[k]} · {STATUSES[n['status']]}"
    if STYLE == "ai":
        if k == "stop":
            w = M["unf_word"]
            tail = f"\n{w} {unfinished_count} 条" if unfinished_count else f"\n无{w}分支"
            return f"{head}\n{title}{tail}"
        return f"{head}\n{title}"
    # human: tag line, title, blank line, summary paragraph
    body = wrap(flat(n.get("summary", "")), sw["summary_wrap"]) if n.get("summary") else ""
    if k == "stop":
        w = M["unf_word"]
        body += (f"\n还有 {unfinished_count} 条{w}分支，见详情。" if unfinished_count else f"\n没有{w}的分支。")
    return f"【{head}】\n{title}" + (f"\n\n{body.strip()}" if body.strip() else "")


def node_details(n, nodes, edges):
    return (node_details_human if STYLE == "human" else node_details_ai)(n, nodes, edges)


def node_details_ai(n, nodes, edges):
    byid = {m["id"]: m for m in nodes}
    T = lambda m: flat(title_of(m))
    paras = [f"[{n['id']}] {KINDS[n['kind']]}" + (f" · {STATUSES[n['status']]}" if n.get("status") else "")]
    if n.get("turn"): paras.append(f"出处：{n['turn']}")
    for q in n.get("quote", []) or []: paras.append(f"原话：「{q}」")
    if n.get("summary"): paras.append(f"摘要：{flat(n['summary'])}")
    if n.get("goal"): paras.append(f"目标：{n['goal']}")
    for c in n.get("constraints", []) or []: paras.append(f"约束：{c}")
    for a in n.get("acceptance", []) or []: paras.append(f"验收：{a}")
    if n["kind"] != "stop":
        for e in edges:
            if e["dst"] == n["id"] and e["why"]:
                if M is MODES["plan"]:
                    who = "由你决定" if e["by"] == "user" else "条件"
                    paras.append(f"进入条件（{who}，自 {e['src']}）：{flat(e['why'])}")
                else:
                    who = {"user": "用户推动", "evidence": "证据驱动"}.get(e["by"], "推理")
                    paras.append(f"来由（{who}，自 {e['src']}）：{flat(e['why'])}")
    if n.get("reason"): paras.append(f"理由：{n['reason']}")
    for d in n.get("details", []) or []: paras.append(d)
    for ev in n.get("evidence", []) or []: paras.append(f"证据：{ev}")
    if n["kind"] == "stop":
        par = [byid[e["src"]] for e in edges if e["dst"] == n["id"]]
        for d in n.get("decision", []) or []: paras.append(f"当前决定：{d}")
        for d in n.get("done_when", []) or []: paras.append(f"完成条件：{d}")
        if par: paras.append("收束自：" + "；".join(f"{p['id']} {T(p)}" for p in par))
        unf = unfinished_nodes(nodes, edges)
        exc = [m for m in nodes if m.get("status") in EXCLUDED]
        paras.append(f"{M['unf_word']}分支：" + ("；".join(f"{m['id']}【{STATUSES[m['status']]}】{T(m)}" for m in unf) if unf else "无"))
        if exc: paras.append(f"{M['exc_word']}：" + "；".join(f"{m['id']}【{STATUSES[m['status']]}】{T(m)}" for m in exc))
        for x in n.get("next", []) or []: paras.append(f"下一步：{x}")
    return plate_details(*paras)


def _join_cn(items):
    items = [x for x in items if x]
    if len(items) <= 1: return "".join(items)
    return "、".join(items[:-1]) + "和" + items[-1]


def _end(t):
    t = str(t).strip()
    return t if not t or t[-1] in "。！？…」）：" else t + "。"


def node_details_human(n, nodes, edges):
    """Prose for a person re-reading the graph months later: no ids, no notation."""
    byid = {m["id"]: m for m in nodes}
    plan = M is MODES["plan"]
    T = lambda m: f"「{flat(m.get('title', ''))}」"
    paras = []
    k = n["kind"]
    if n.get("summary"): paras.append(flat(n["summary"]))
    if k == "requirement":
        if n.get("quote"):
            paras.append("你当时的原话：")
            paras += [f"「{q}」" for q in n["quote"]]
        if n.get("goal"): paras.append(f"想达到的效果：{n['goal']}")
        if n.get("constraints"): paras.append("前提条件：" + "；".join(n["constraints"]) + "。")
        if n.get("acceptance"): paras.append("怎样算做成：" + "；".join(n["acceptance"]) + "。")
    elif k != "stop":
        ins = [e for e in edges if e["dst"] == n["id"]]
        lines = []
        bare = [byid[e["src"]] for e in ins if not flat(e["why"])]
        if len(bare) >= 2:
            # several unlabeled parents: one sentence instead of a list of "由…引出"
            lines.append(("这一步要等" if plan else "这个结论综合了") + _join_cn([T(p) for p in bare])
                         + ("都完成。" if plan else "。"))
            ins = [e for e in ins if flat(e["why"])]
        for e in ins:
            p = byid[e["src"]]
            why = flat(e["why"])
            if plan and p["kind"] == "branch":
                lines.append(f"在{T(p)}这一步，如果{why}，就走到这里。" if why else f"从{T(p)}这一步分出来。")
            elif plan:
                lines.append(f"接在{T(p)}之后" + (f"（{why}）。" if why else "。"))
            elif e["by"] == "user":
                lines.append(f"由你推动：{why}。这一步接在{T(p)}之后。" if why else f"由你推动，接在{T(p)}之后。")
            elif e["by"] == "evidence":
                lines.append(f"从{T(p)}出发{why}，查到了这一点。" if why else f"从{T(p)}出发查证得到。")
            else:
                lines.append(f"由{T(p)}引出：{why}。" if why else f"由{T(p)}引出。")
        paras += lines
        st = n.get("status")
        if st in TERMINAL or st in ("optional", "fallback"):
            paras.append(f"目前状态：{STATUSES[st]}。" + (_end(f"原因是{n['reason']}") if n.get("reason") else ""))
        elif n.get("reason"):
            paras.append(_end(f"原因是{n['reason']}"))
        kids = [byid[e["dst"]] for e in edges if e["src"] == n["id"]]
        if kids:
            paras.append("后来引出了" + _join_cn([T(c) for c in kids]) + "。")
    for d in n.get("details", []) or []: paras.append(d)
    for ev in n.get("evidence", []) or []: paras.append(f"依据：{ev}")
    if k == "stop":
        if n.get("reason"): paras.append(("停在这里的原因：" if not plan else "说明：") + _end(n["reason"]))
        if n.get("decision"):
            paras.append("已经定下来的：")
            paras += [f"· {_end(d)}" for d in n["decision"]]
        for d in n.get("done_when", []) or []: paras.append(f"怎样算完成：{_end(d)}")
        unf = unfinished_nodes(nodes, edges)
        exc = [m for m in nodes if m.get("status") in EXCLUDED]
        if unf:
            paras.append(f"还没解决的（{len(unf)} 条）：")
            paras += [f"· {flat(m['title'])}（{STATUSES[m['status']]}）" + (f"：{flat(m['summary'])}" if m.get("summary") else "") for m in unf]
        else:
            paras.append("没有遗留的未完成分支。")
        if exc:
            paras.append("不会走到目标的情况：" if plan else "放弃了的方向：")
            paras += [f"· {flat(m['title'])}" + (f"：{_end(m['reason'])}" if m.get("reason") else "") for m in exc]
        if n.get("next"):
            paras.append("接下来：")
            paras += [f"· {_end(x)}" for x in n["next"]]
    if n.get("turn"): paras.append(f"出自：{n['turn']}")
    return plate_details(*paras)


def geometry_findings(rects, segs):
    """segs: list of (src, dst, p1, p2, label_rect or None)."""
    def ov(a, b): return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]
    def ex(r, m): return (r[0] - m, r[1] - m, r[2] + m, r[3] + m)
    box = {k: (l, t, l + w, t + h) for k, (l, t, w, h) in rects.items()}
    f = []
    ks = list(box)
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            if ov(ex(box[ks[i]], HALO), ex(box[ks[j]], HALO)):
                f.append(("NODE_GAP", ks[i], ks[j]))
    from layout_audit import seg_intersects_rect
    for s, d, p1, p2, lr in segs:
        for k, r in box.items():
            if k in (s, d): continue
            if seg_intersects_rect(p1, p2, ex(r, HALO)):
                f.append(("EDGE_NODE", f"{s}->{d}", k))
            if lr and ov(lr, ex(r, 8)):
                f.append(("LABEL_NODE", f"{s}->{d}", k))
    labs = [(f"{s}->{d}", lr) for s, d, _, _, lr in segs if lr]
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            if ov(ex(labs[i][1], 6), labs[j][1]):
                f.append(("LABEL_LABEL", labs[i][0], labs[j][0]))
    return f


def make_segs(rects, elist, lsize):
    segs = []
    for (s, d) in elist:
        l, t, w, h = rects[s]; p1 = (l + w / 2, t + h)
        l2, t2, w2, h2 = rects[d]; p2 = (l2 + w2 / 2, t2)
        lw, lh = lsize[(s, d)]
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        lr = (mid[0] - lw / 2, mid[1] - lh / 2, mid[0] + lw / 2, mid[1] + lh / 2) if lw else None
        segs.append((s, d, p1, p2, lr))
    return segs


def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])


def edge_crossings(segs):
    """Number of proper crossings between edge segments that share no endpoint."""
    n = 0
    for i in range(len(segs)):
        s1, d1, a, b, _ = segs[i]
        for j in range(i + 1, len(segs)):
            s2, d2, c, d, _ = segs[j]
            if {s1, d1} & {s2, d2}: continue
            if _ccw(a, b, c) * _ccw(a, b, d) < 0 and _ccw(c, d, a) * _ccw(c, d, b) < 0:
                n += 1
    return n


def corridor_repair(rects, layer, elist, lsize, indeg, rounds=80):
    """Greedy local relaxation. For each collision, try opening a corridor by shifting the
    blocking node (and everything beyond it in the same layer) left or right, or shifting the
    edge's endpoints; keep the move only if the total number of findings drops. Labels of
    merge edges are hidden (their "why" stays in Details) only when no move helps.
    Row order is never changed, so the causal tree stays readable."""
    rects = dict(rects)
    hidden = set()
    FIX = ("EDGE_NODE", "LABEL_NODE", "LABEL_LABEL")

    def score(rs):
        return [x for x in geometry_findings(rs, make_segs(rs, elist, lsize)) if x[0] in FIX]

    def shifted(rs, k, pivot_x, side, amount):
        out = dict(rs)
        for n, (l, t, w, h) in rs.items():
            if layer[n] != k: continue
            c = l + w / 2
            if (side > 0 and c >= pivot_x) or (side < 0 and c <= pivot_x):
                out[n] = (l + side * amount, t, w, h)
        return out

    def node_moves(rs, n, lo, hi):
        l, t, w, h = rs[n]; c = l + w / 2
        return [shifted(rs, layer[n], c - 1e-6, +1, max(1.0, hi - l)),
                shifted(rs, layer[n], c + 1e-6, -1, max(1.0, l + w - lo))]

    cur = score(rects)
    for _ in range(rounds):
        if not cur: break
        improved = False
        segs = {f"{a}->{b}": (a, b, p1, p2, lr) for a, b, p1, p2, lr in make_segs(rects, elist, lsize)}
        for kind, a, b in cur:
            cands = []
            if kind in ("EDGE_NODE", "LABEL_NODE"):
                s_, d_, p1, p2, lr = segs[a]
                l, t, w, h = rects[b]
                if kind == "EDGE_NODE":
                    def xat(y):
                        r = 0 if p2[1] == p1[1] else (y - p1[1]) / (p2[1] - p1[1])
                        return p1[0] + (p2[0] - p1[0]) * min(1, max(0, r))
                    xs = (xat(t - HALO), xat(t + h + HALO))
                    lo, hi = min(xs) - HALO - 24, max(xs) + HALO + 24
                else:
                    lo, hi = lr[0] - 24, lr[2] + 24
                cands += node_moves(rects, b, lo, hi)
                for end in (s_, d_):          # or bend the line by moving one endpoint
                    el, et, ew, eh = rects[end]
                    for step in (-1, 1):
                        cands.append(shifted(rects, layer[end], el + ew / 2 - 1e-6 if step > 0 else el + ew / 2 + 1e-6,
                                             step, (w + 2 * HALO)))
            else:
                (s1, d1, _, _, l1), (s2, d2, _, _, l2) = segs[a], segs[b]
                ov = min(l1[2], l2[2]) - max(l1[0], l2[0]) + 16
                for d in (d1, d2):
                    dl, dt, dw, dh = rects[d]
                    for step in (-1, 1):
                        cands.append(shifted(rects, layer[d], dl + dw / 2 - step * 1e-6, step, 2 * ov))
            best = None
            for rs in cands:
                sc = score(rs)
                if len(sc) < len(cur) and (best is None or len(sc) < len(best[1])):
                    best = (rs, sc)
            if best:
                rects, cur = best
                improved = True
                break
        if improved:
            continue
        # nothing helps: hide one merge-edge label involved in a label collision, else stop
        lab = [x for x in cur if x[0] == "LABEL_LABEL"]
        if not lab: break
        e1, e2 = segs[lab[0][1]][:2], segs[lab[0][2]][:2]
        e = max((e1, e2), key=lambda e: indeg.get(e[1], 1))
        lsize[e] = (0.0, 0.0); hidden.add(e)
        cur = score(rects)
    # leaf alignment pass: try to put each leaf straight under its parent (shifting its side
    # of the row); keep a move only if collisions do not grow and line crossings drop
    parent, has_kid = {}, set()
    for a, b in elist:
        parent.setdefault(b, a); has_kid.add(a)
    def total(rs):
        sg = make_segs(rs, elist, lsize)
        return (len([x for x in geometry_findings(rs, sg) if x[0] in FIX]), edge_crossings(sg))
    cur_t = total(rects)
    for _ in range(2):
        for n in sorted(rects, key=lambda n: layer[n]):
            if n not in parent or n in has_kid: continue   # leaves only: moving them cannot distort the tree
            pl, pt, pw, ph = rects[parent[n]]
            l, t, w, h = rects[n]
            base = (pl + pw / 2) - (l + w / 2)
            c = l + w / 2
            best_mv = None
            for dx in (base, base + w + 2 * HALO + 60, base - w - 2 * HALO - 60):
                if abs(dx) < 1: continue
                rs = shifted(rects, layer[n], c - 1e-6 if dx > 0 else c + 1e-6, 1 if dx > 0 else -1, abs(dx))
                tt = total(rs)
                if tt[0] <= cur_t[0] and tt[1] < cur_t[1] and (best_mv is None or tt < best_mv[1]):
                    best_mv = (rs, tt)
            if best_mv:
                rects, cur_t = best_mv
    minx = min(l for l, t, w, h in rects.values())
    return {n: (l - minx, t, w, h) for n, (l, t, w, h) in rects.items()}, hidden


def build(data, nodes, edges, out_path, max_rounds=5):
    byid = {n["id"]: n for n in nodes}
    stop = next(n for n in nodes if n["kind"] == "stop")
    unfinished = len(unfinished_nodes(nodes, edges))
    texts = {n["id"]: node_text(n, unfinished) for n in nodes}
    scale = {n["id"]: (1 if n["kind"] in ("requirement", "stop") else 0) for n in nodes}
    sizes = {i: text_box(t, FONT * 2 ** (scale[i] / 2), PAD * 2 ** (scale[i] / 2)) for i, t in texts.items()}
    lw_ = STYLES[STYLE]["label_wrap"]
    labels = {(e["src"], e["dst"]): wrap(flat(e["why"]) if STYLE == "human" else (e["short"] or e["why"]), lw_)
              for e in edges}
    lsize = {k: label_box(v) for k, v in labels.items()}
    ids = [n["id"] for n in nodes]
    elist = [(e["src"], e["dst"]) for e in edges]
    indeg = defaultdict(int)
    for s_, d_ in elist:
        indeg[d_] += 1
    in_label_w = defaultdict(float)
    for (s, d), (w, _) in lsize.items():
        in_label_w[d] = max(in_label_w[d], w)

    hgap, vgap = 110.0, 150.0
    best = None
    for rnd in range(max_rounds):
        def sep(a, b, wa, wb, hgap=hgap):
            dummy = isinstance(a, tuple) or isinstance(b, tuple)
            base = (wa + wb) / 2 + (hgap * 0.6 if dummy else hgap)
            la = 0 if isinstance(a, tuple) else in_label_w[a]
            lb = 0 if isinstance(b, tuple) else in_label_w[b]
            # sibling labels sit at edge midpoints, i.e. roughly half the child distance apart
            return max(base, la + lb + 60 if la and lb else 0)

        def gap_height(k, vgap=vgap):
            return vgap + max([h for (_, _), (_, h) in lsize.items()] or [0])

        def dummy_width(s, d, k):
            return max(48.0, lsize[(s, d)][0] * 0.9) + 2 * HALO

        rects, info = layered_layout(ids, elist, lambda i: sizes[i], sink=stop["id"], sep=sep,
                                     gap_height=gap_height, dummy_width=dummy_width)
        lsize_r = dict(lsize)
        rects, hidden = corridor_repair(rects, info["layer"], elist, lsize_r, indeg)
        lsize_used = lsize_r
        segs = make_segs(rects, elist, lsize_used)
        findings = geometry_findings(rects, segs)
        if best is None or len(findings) < len(best[0]):
            best = (findings, rects, info, rnd, hidden)
        if not findings:
            break
        kinds = {f[0] for f in findings}
        if kinds & {"LABEL_LABEL", "EDGE_NODE", "NODE_GAP"}: hgap += 60
        if kinds & {"LABEL_NODE", "EDGE_NODE"}: vgap += 40
    findings, rects, info, rnd, hidden = best
    for k in hidden:
        labels[k] = ""

    g = PRG27()
    g.tags = ["thinking-chain", data["_mode"]]
    ox, oy = 200.0, 420.0
    for n in nodes:
        i, k = n["id"], n["kind"]
        l, t, w, h = rects[i]
        st = n.get("status")
        alpha = .34 if k in ("requirement", "stop") else (.30 if k == "decision" else STATUS_ALPHA.get(st, .2))
        border = "dashed" if st in TERMINAL or st in ("optional", "fallback") else "solid"
        weight = "700" if k in ("requirement", "stop", "decision") else ""
        g.node(i, texts[i], ox + l, oy + t, w, h, color=(*KIND_FILL[k], alpha), font_scale=scale[i],
               weight=weight, border=border, details=node_details(n, nodes, edges))
    for e in edges:
        s, d = e["src"], e["dst"]
        dn = byid[d]
        if dn["kind"] == "stop":
            col, lt = EDGE_COLOR["stop"], "solid"
        elif dn.get("status") in EXCLUDED or dn.get("status") == "fallback":
            col, lt = EDGE_COLOR["excluded"], "dashed"
        else:
            col = EDGE_COLOR[e["by"]]
            lt = "dashed" if dn.get("status") in UNFINISHED or dn.get("status") == "optional" else "solid"
        g.line(s, d, labels[(s, d)], line_type=lt, color=col, src_rate=(0.5, 0.99), dst_rate=(0.5, 0.01))

    # header + legend, outside the tree's activity space
    right = max(l + w for l, t, w, h in rects.values())
    root = next(n for n in nodes if n["kind"] == "requirement")
    rl, rt, rw, rh = rects[root["id"]]
    plan = M is MODES["plan"]
    if STYLE == "human":
        head = wrap(f"{M['header']}：{data.get('title', '')}", 24)
        if data.get("overview"):
            head += "\n\n" + wrap(flat(data["overview"]), 26)
        reading = ("怎么读：从上往下是做事的先后顺序。紫色的判断框下面，每条线代表一种情况，线上写着在什么条件下走这条路。"
                   "虚线框是备选、可选、还没定下来，或者需要中途停下交给你的地方。所有顺利的路最后都汇到底部的终点。") if plan else \
                  ("怎么读：从上往下是思考推进的顺序，越往下分支越多，说明问题被拆得越细。几条线汇到一起，表示这些线索共同促成了一个决定。"
                   "实线框是已经定下来的结论，虚线框是还没解决、被搁置或被放弃的方向。最底部是这轮思考停下来的地方。")
    else:
        head = wrap(f"{M['header']}：{data.get('title', '')}", 22)
        reading = ("读法：自上而下 = 执行顺序；判断点下的每条线 = 一种情况（线上写条件）；"
                   "虚线 = 备选 / 可选 / 未定 / 出口；所有正常路径收束到底部唯一终点 = 目标达成。") if plan else \
                  ("读法：自上而下 = 思考推进；一层比一层宽 = 分支展开；合流 = 收束；底部唯一终点 = 停止思考。")
    hw, hh = text_box(head, FONT)
    g.node("_head", head, ox + rl + rw / 2 - hw / 2, oy + rt - hh - 160, hw, hh,
           color=(95, 95, 95, .10), weight="700", border="dashed",
           details=plate_details(f"来源：{data.get('source', '')}", reading))
    if STYLE == "human" and plan:
        legend = ("怎么看颜色和线\n紫色框：要做判断的地方\n橙色框：具体要做的步骤\n青色框：检查结果的地方\n"
                  "实线框：计划要做或已完成\n虚线框：备选、可选、没定，\n　　　　或者要停下交给你\n"
                  "橙色虚线：走向备选或出口\n蓝色线：需要你来决定\n绿色线：汇到最终目标")
    elif STYLE == "human":
        legend = ("怎么看颜色和线\n实线框：已经定下来的结论\n虚线框：没解决、搁置或放弃\n"
                  "灰色线：顺着推理往下想\n蓝色线：你提出的转向\n青色线：查证后得到的结论\n"
                  "橙色虚线：后来放弃的方向\n绿色线：汇到最后的停止点")
    elif plan:
        legend = ("图例\n紫框 = 判断点（线上写条件）\n橙框 = 步骤　青框 = 检查点\n"
                  "实线框 = 计划 / 已完成\n虚线框 = 可选 / 备选 / 未定 /\n            受阻 / 中止 / 交给你\n"
                  "橙虚线 = 走向备选或出口\n蓝线 = 由你决定\n绿线 = 收束到目标")
    else:
        legend = ("图例\n实线框 = 采用 / 证实 / 解决\n虚线框 = 待验证 / 未解决 /\n"
                  "            搁置 / 否定 / 被取代\n蓝线 = 你推动的转向\n青线 = 证据驱动\n"
                  "橙虚线 = 走向被排除的分支\n绿线 = 收束到终点")
    lw_, lh_ = text_box(legend, FONT * 2 ** (-1 / 2))
    g.node("_legend", legend, ox + right + 260, oy, lw_, lh_, color=(95, 95, 95, .06),
           font_scale=-1, border="dashed")
    clean = {k: v for k, v in data.items() if not k.startswith("_")}
    g.readme = (f"# Thinking-chain graph ({data['_mode']}, style={STYLE}): {data.get('title', '')}\n\n"
                "Generated by project-graph-architect thinking_chain.py. The full outline is embedded below so an AI\n"
                "can reload the reasoning without parsing the canvas.\n\n```json\n"
                + json.dumps(clean, ensure_ascii=False, indent=1) + "\n```\n")
    g.write(out_path)
    info.update(data.get("_stats", {}))
    info["style"] = STYLE
    info["layout_rounds"] = rnd + 1
    info["edge_crossings"] = edge_crossings(make_segs(rects, elist, {k: (0.0, 0.0) for k in lsize}))
    info["labels_moved_to_details"] = sorted(f"{a}->{b}" for a, b in hidden)
    info["residual_findings"] = findings
    return info


def extract(prg_path, out_path=None):
    """Recover the outline embedded by build(), so an earlier graph can be extended."""
    import zipfile
    with zipfile.ZipFile(prg_path) as z:
        if "README.md" not in z.namelist():
            print("ERROR: this .prg has no README.md, so it was not built by thinking_chain.py"); return 1
        text = z.read("README.md").decode("utf-8")
    if "```json\n" not in text:
        print("ERROR: no embedded outline found (built before v1.2?)"); return 1
    raw = text.split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    data = json.loads(raw)
    out = json.dumps(data, ensure_ascii=False, indent=1)
    if out_path:
        Path(out_path).write_text(out + "\n", encoding="utf-8")
        print(f"Outline written: {out_path} ({len(data.get('nodes', []))} nodes, mode={data.get('mode', 'review')})")
    else:
        print(out)
    return 0


def _run(cmd, path, out, style):
    global STYLE
    data, nodes, edges = load(path)
    STYLE = style
    errors, warns = check(data, nodes, edges)
    for w in warns: print("WARN:", w)
    for e in errors: print("ERROR:", e)
    if errors:
        print(f"Semantic check FAILED ({len(errors)} errors, style={style})"); return 1
    print(f"Semantic check OK (style={style}):", data.get("_stats"))
    if cmd == "tree":
        print(); print(tree_text(data, nodes, edges))
    if cmd == "build":
        info = build(data, nodes, edges, out)
        res = info.pop("residual_findings")
        info.pop("layer", None)
        print("Built:", out, info)
        for f in res: print("LAYOUT:", *f)
        if res:
            print("Residual layout findings remain: shorten labels/titles or split a branch, then rebuild.")
            return 3
    return 0


def main(argv):
    style_cli = None
    if "--style" in argv:
        i = argv.index("--style")
        style_cli = argv[i + 1] if i + 1 < len(argv) else None
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 3 or argv[1] not in ("check", "tree", "build", "extract"):
        print(__doc__); return 2
    if argv[1] == "extract":
        return extract(argv[2], argv[3] if len(argv) > 3 else None)
    if argv[1] == "build" and len(argv) < 4:
        print("build needs an output path"); return 2
    raw = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    style = style_cli or raw.get("style", "human")
    if style not in list(STYLES) + ["both"]:
        print(f"ERROR: style must be one of {list(STYLES) + ['both']} (got {style!r})"); return 2
    out = argv[3] if len(argv) > 3 else None
    if style != "both":
        return _run(argv[1], argv[2], out, style)
    if argv[1] == "tree":
        return _run("tree", argv[2], None, "human")
    rc = _run(argv[1], argv[2], out, "human")
    if rc:
        return rc
    out_ai = None
    if out:
        p = Path(out)
        out_ai = str(p.with_name(p.stem + "_ai" + p.suffix))
    return _run(argv[1], argv[2], out_ai, "ai")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
