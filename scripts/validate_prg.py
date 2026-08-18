#!/usr/bin/env python3
from pathlib import Path
import sys, zipfile, msgpack

REQUIRED = {"stage.msgpack","tags.msgpack","reference.msgpack","metadata.msgpack"}
KNOWN = {"TextNode","LineEdge","ArcEdge","MultiTargetUndirectedEdge","Section","SyncAssociation","ReferenceBlockNode"}

def walk_refs(v, out):
    if isinstance(v, dict):
        if set(v.keys()) == {"$"} and isinstance(v["$"], str):
            out.append(v["$"])
        else:
            for x in v.values(): walk_refs(x,out)
    elif isinstance(v, list):
        for x in v: walk_refs(x,out)

def validate(path):
    errors=[]; warnings=[]
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist())
        missing=REQUIRED-names
        if missing: errors.append(f"missing entries: {sorted(missing)}")
        if errors: return errors,warnings
        stage=msgpack.unpackb(z.read('stage.msgpack'),raw=False)
        meta=msgpack.unpackb(z.read('metadata.msgpack'),raw=False)
        if meta.get('version')!='2.7.0': warnings.append(f"metadata version is {meta.get('version')!r}, expected '2.7.0'")
        if not isinstance(stage,list): errors.append('stage.msgpack must decode to a list'); return errors,warnings
        for i,obj in enumerate(stage):
            if not isinstance(obj,dict): errors.append(f'stage[{i}] is not a map'); continue
            typ=obj.get('_')
            if not typ: errors.append(f'stage[{i}] missing class marker _')
            elif typ not in KNOWN: warnings.append(f'stage[{i}] unknown top-level type {typ}')
            refs=[]; walk_refs(obj,refs)
            for ref in refs:
                try:
                    if not ref.startswith('/'): raise ValueError
                    idx=int(ref[1:].split('/')[0])
                    if idx<0 or idx>=len(stage): errors.append(f'stage[{i}] reference {ref} is out of range')
                except Exception:
                    errors.append(f'stage[{i}] malformed reference {ref!r}')
    return errors,warnings

if __name__=='__main__':
    if len(sys.argv)!=2:
        print('usage: validate_prg.py file.prg'); sys.exit(2)
    p=Path(sys.argv[1]); errors,warnings=validate(p)
    for w in warnings: print('WARN:',w)
    for e in errors: print('ERROR:',e)
    if errors: sys.exit(1)
    print('OK:',p)
