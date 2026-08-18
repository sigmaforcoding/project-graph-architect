"""Small Project Graph PRG 2.7 builder used by the Project Graph Architect skill."""
from __future__ import annotations
from pathlib import Path
import uuid, zipfile
import msgpack


def V(x, y):
    return {"_": "Vector", "x": float(x), "y": float(y)}

def C(r=0, g=0, b=0, a=0):
    return {"_": "Color", "r": int(r), "g": int(g), "b": int(b), "a": float(a)}

def R(x, y, w, h):
    return {"_": "Rectangle", "location": V(x, y), "size": V(w, h)}

def CB(x, y, w, h):
    return {"_": "CollisionBox", "shapes": [R(x, y, w, h)]}

def plate_details(*paragraphs):
    return [{"type": "p", "children": [{"text": str(p)}]} for p in paragraphs if p]

class PRG27:
    def __init__(self):
        self.stage = []
        self.index = {}
        self.tags = []
        self.references = {"sections": {}, "files": []}
        self.attachments = {}
        self.readme = None

    def _add(self, key, obj):
        if key is not None:
            self.index[key] = len(self.stage)
        self.stage.append(obj)
        return obj

    def ref(self, key):
        return {"$": f"/{self.index[key]}"}

    def node(self, key, text, x, y, w=330, h=90, color=(0,0,0,0),
             font_scale=0, weight="", border="solid", details=None,
             size_adjust="manual"):
        return self._add(key, {
            "_": "TextNode", "details": details or [], "uuid": str(uuid.uuid4()),
            "text": text, "collisionBox": CB(x,y,w,h), "color": C(*color),
            "fontScaleLevel": int(font_scale), "sizeAdjust": size_adjust,
            "fontFamily": "", "fontWeight": weight, "borderStyle": border,
        })

    def line(self, source, target, text="", line_type="solid", arrow_type="default",
             color=(0,0,0,0), src_rate=(0.5,0.5), dst_rate=(0.5,0.5)):
        return self._add(None, {
            "_": "LineEdge", "associationList": [self.ref(source), self.ref(target)],
            "targetRectangleRate": V(*dst_rate), "sourceRectangleRate": V(*src_rate),
            "uuid": str(uuid.uuid4()), "text": text, "color": C(*color),
            "lineType": line_type, "arrowType": arrow_type,
        })

    def arc(self, source, target, text="", offset=180, text_position=0.5,
            line_type="solid", arrow_type="default", color=(0,0,0,0),
            src_rate=(0.5,0.5), dst_rate=(0.5,0.5)):
        return self._add(None, {
            "_": "ArcEdge", "associationList": [self.ref(source), self.ref(target)],
            "targetRectangleRate": V(*dst_rate), "sourceRectangleRate": V(*src_rate),
            "uuid": str(uuid.uuid4()), "text": text, "color": C(*color),
            "lineType": line_type, "arrowType": arrow_type,
            "offset": float(offset), "textPosition": float(text_position),
        })

    def hyperedge(self, members, text="", render_type="convex", line_type="dashed",
                  arrow="none", arrow_type="default", padding=24, color=(0,0,0,0)):
        return self._add(None, {
            "_": "MultiTargetUndirectedEdge",
            "associationList": [self.ref(k) for k in members],
            "uuid": str(uuid.uuid4()), "text": text, "color": C(*color),
            "rectRates": [V(0.5,0.5) for _ in members], "centerRate": V(0.5,0.5),
            "arrow": arrow, "arrowType": arrow_type, "renderType": render_type,
            "lineType": line_type, "padding": float(padding),
        })

    def sync(self, members, keys=("text","color","details")):
        return self._add(None, {
            "_": "SyncAssociation", "uuid": str(uuid.uuid4()), "keys": list(keys),
            "associationList": [self.ref(k) for k in members],
        })

    def section(self, key, text, children, color=(0,0,0,0), collapsed=False,
                locked=False, border="solid", details=None):
        return self._add(key, {
            "_": "Section", "details": details or [], "uuid": str(uuid.uuid4()),
            "color": C(*color), "text": text, "children": [self.ref(k) for k in children],
            "isCollapsed": bool(collapsed), "locked": bool(locked), "borderStyle": border,
        })

    def reference_block(self, key, x, y, w, h, file_name, section_name="", scale=1.0,
                        attachment_bytes=None, attachment_ext="png", details=None):
        aid = str(uuid.uuid4()) if attachment_bytes is not None else ""
        if attachment_bytes is not None:
            self.attachments[aid] = (attachment_ext, attachment_bytes)
        return self._add(key, {
            "_": "ReferenceBlockNode", "details": details or [], "uuid": str(uuid.uuid4()),
            "collisionBox": CB(x,y,w,h), "fileName": file_name, "sectionName": section_name,
            "scale": float(scale), "attachmentId": aid,
        })

    def write(self, path, version="2.7.0"):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
            z.writestr("stage.msgpack", msgpack.packb(self.stage, use_bin_type=True))
            z.writestr("tags.msgpack", msgpack.packb(self.tags, use_bin_type=True))
            z.writestr("reference.msgpack", msgpack.packb(self.references, use_bin_type=True))
            z.writestr("metadata.msgpack", msgpack.packb({"version": version}, use_bin_type=True))
            if self.readme:
                z.writestr("README.md", self.readme.encode("utf-8"))
            for aid, (ext, data) in self.attachments.items():
                z.writestr(f"attachments/{aid}.{ext}", data)
        return path
