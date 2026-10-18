#!/usr/bin/env python3
"""Approximate collision audit for PRG 2.7 diagrams.

The renderer remains authoritative. This script catches common geometric failures early:
- nodes too close,
- straight edges crossing unrelated node halos,
- estimated edge-label boxes intersecting nodes.
"""
from pathlib import Path
import sys, zipfile, msgpack, math

HALO = 42.0
CHAR_W = 12.0
LINE_H = 28.0
LABEL_PAD = 12.0

def ref_index(ref):
    try: return int(ref['$'][1:].split('/')[0])
    except: return None

def rect_of(obj):
    try:
        s=obj['collisionBox']['shapes'][0]
        loc=s['location']; size=s['size']
        return (loc['x'],loc['y'],loc['x']+size['x'],loc['y']+size['y'])
    except Exception: return None

def expand(r,m): return (r[0]-m,r[1]-m,r[2]+m,r[3]+m)
def overlap(a,b): return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]
def center(r): return ((r[0]+r[2])/2,(r[1]+r[3])/2)

def anchor(r, rate):
    """Project Graph sentinel rates: 0.01/0.99 = exact side centre; otherwise centre-line."""
    if not rate: return None
    x, y = rate.get('x', .5), rate.get('y', .5)
    if y == 0.99: return ((r[0]+r[2])/2, r[3])
    if y == 0.01: return ((r[0]+r[2])/2, r[1])
    if x == 0.99: return (r[2], (r[1]+r[3])/2)
    if x == 0.01: return (r[0], (r[1]+r[3])/2)
    return None

def seg_intersects_rect(p1,p2,r):
    # Liang-Barsky clipping
    x1,y1=p1; x2,y2=p2; dx=x2-x1; dy=y2-y1
    p=[-dx,dx,-dy,dy]; q=[x1-r[0],r[2]-x1,y1-r[1],r[3]-y1]
    u1,u2=0.0,1.0
    for pi,qi in zip(p,q):
        if abs(pi)<1e-9:
            if qi<0: return False
        else:
            t=qi/pi
            if pi<0:
                if t>u2: return False
                u1=max(u1,t)
            else:
                if t<u1: return False
                u2=min(u2,t)
    return True

def label_rect(text, p):
    lines=(text or '').split('\n')
    if not lines or lines==['']: return None
    w=max(len(x) for x in lines)*CHAR_W + LABEL_PAD*2
    h=len(lines)*LINE_H + LABEL_PAD*2
    return (p[0]-w/2,p[1]-h/2,p[0]+w/2,p[1]+h/2)

def main(path):
    with zipfile.ZipFile(path) as z:
        stage=msgpack.unpackb(z.read('stage.msgpack'),raw=False)
    nodes={i:rect_of(o) for i,o in enumerate(stage) if o.get('_') in {'TextNode','ReferenceBlockNode'} and rect_of(o)}
    findings=[]
    # Node halos overlap.
    ids=list(nodes)
    for a_i in range(len(ids)):
        for b_i in range(a_i+1,len(ids)):
            a,b=ids[a_i],ids[b_i]
            if overlap(expand(nodes[a],HALO), expand(nodes[b],HALO)):
                findings.append(('NODE_GAP',a,b,'expanded node halos overlap'))
    # Straight edges. Arc audit is intentionally conservative and skipped for path crossing.
    for ei,e in enumerate(stage):
        if e.get('_') not in {'LineEdge','ArcEdge'}: continue
        al=e.get('associationList',[])
        if len(al)<2: continue
        s,t=ref_index(al[0]),ref_index(al[1])
        if s not in nodes or t not in nodes: continue
        p1=anchor(nodes[s],e.get('sourceRectangleRate')) or center(nodes[s])
        p2=anchor(nodes[t],e.get('targetRectangleRate')) or center(nodes[t])
        if e.get('_')=='LineEdge':
            for ni,r in nodes.items():
                if ni in {s,t}: continue
                if seg_intersects_rect(p1,p2,expand(r,HALO)):
                    findings.append(('EDGE_NODE',ei,ni,'straight edge crosses a non-endpoint node halo'))
        txt=e.get('text','')
        if txt:
            if e.get('_')=='LineEdge':
                lp=((p1[0]+p2[0])/2,(p1[1]+p2[1])/2)
            else:
                # Approximate label at linear interpolation. Renderer geometry is authoritative.
                q=float(e.get('textPosition',0.5)); lp=(p1[0]*(1-q)+p2[0]*q,p1[1]*(1-q)+p2[1]*q)
            lr=label_rect(txt,lp)
            for ni,r in nodes.items():
                if ni in {s,t}: continue
                if overlap(lr,expand(r,10)):
                    findings.append(('LABEL_NODE',ei,ni,'estimated edge-label box overlaps a node'))
    if findings:
        for f in findings: print(*f,sep=' | ')
        print(f'Findings: {len(findings)}')
        return 1
    print('No approximate layout collisions found.')
    return 0

if __name__=='__main__':
    if len(sys.argv)!=2:
        print('usage: layout_audit.py file.prg'); sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
