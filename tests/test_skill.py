"""Regression tests for project-graph-architect.

Run from the skill root:  python -m unittest discover -s tests -v
Only needs msgpack (matplotlib is not required).
"""
import json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EX = ROOT / "examples"
OUTLINES = ["thinking_chain_skill_upgrade.json", "thinking_chain_relay_setup.json", "path_plan_backup_relay.json"]


def run(*args):
    p = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=ROOT)
    return p.returncode, p.stdout + p.stderr


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def outline(self, name, **patch):
        d = json.loads((EX / name).read_text(encoding="utf-8"))
        d.update(patch)
        p = self.tmp / name
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return p, d


class TestExamples(Base):
    def test_minimal_example_validates(self):
        rc, out = run(SCRIPTS / "validate_prg.py", EX / "minimal_project_graph.prg")
        self.assertEqual(rc, 0, out)

    def test_every_example_builds_clean_in_both_styles(self):
        for name in OUTLINES:
            with self.subTest(name=name):
                out = self.tmp / (Path(name).stem + ".prg")
                rc, log = run(SCRIPTS / "thinking_chain.py", "build", EX / name, out, "--style", "both")
                self.assertEqual(rc, 0, log)
                for f in (out, out.with_name(out.stem + "_ai.prg")):
                    rc, log = run(SCRIPTS / "validate_prg.py", f)
                    self.assertEqual(rc, 0, log)
                    rc, log = run(SCRIPTS / "layout_audit.py", f)
                    self.assertEqual(rc, 0, log)

    def test_extract_round_trip(self):
        out = self.tmp / "g.prg"
        run(SCRIPTS / "thinking_chain.py", "build", EX / OUTLINES[1], out)
        back = self.tmp / "back.json"
        rc, log = run(SCRIPTS / "thinking_chain.py", "extract", out, back)
        self.assertEqual(rc, 0, log)
        orig = json.loads((EX / OUTLINES[1]).read_text(encoding="utf-8"))
        self.assertEqual(json.loads(back.read_text(encoding="utf-8"))["nodes"], orig["nodes"])
        rc, log = run(SCRIPTS / "thinking_chain.py", "build", back, self.tmp / "again.prg")
        self.assertEqual(rc, 0, log)

    def test_extract_refuses_foreign_prg(self):
        rc, _ = run(SCRIPTS / "thinking_chain.py", "extract", EX / "minimal_project_graph.prg")
        self.assertEqual(rc, 1)


class TestSemanticGuards(Base):
    def check(self, d):
        p = self.tmp / "x.json"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return run(SCRIPTS / "thinking_chain.py", "check", p, "--style", "ai")

    def test_topic_pipeline_is_rejected(self):
        nodes = [{"id": "R", "kind": "requirement", "title": "x", "quote": ["q"]}]
        prev = "R"
        for i in range(5):
            nodes.append({"id": f"N{i}", "kind": "finding", "status": "confirmed", "title": f"n{i}",
                          "turn": "t", "from": [prev]})
            prev = f"N{i}"
        nodes.append({"id": "S", "kind": "stop", "title": "s", "from": [prev]})
        rc, out = self.check({"nodes": nodes})
        self.assertEqual(rc, 1)
        self.assertIn("pipeline", out)

    def test_dangling_adopted_branch_is_rejected(self):
        d = {"nodes": [
            {"id": "R", "kind": "requirement", "title": "x"},
            {"id": "A", "kind": "option", "status": "adopted", "title": "a", "from": ["R"]},
            {"id": "B", "kind": "option", "status": "adopted", "title": "b", "from": ["R"]},
            {"id": "S", "kind": "stop", "title": "s", "from": ["A"]}]}
        rc, out = self.check(d)
        self.assertEqual(rc, 1)
        self.assertIn("B: branch ends", out)

    def test_two_stop_nodes_rejected(self):
        d = {"nodes": [
            {"id": "R", "kind": "requirement", "title": "x"},
            {"id": "S1", "kind": "stop", "title": "s", "from": ["R"]},
            {"id": "S2", "kind": "stop", "title": "s", "from": ["R"]}]}
        rc, out = self.check(d)
        self.assertEqual(rc, 1)
        self.assertIn("exactly one stop", out)

    def test_plan_branch_needs_two_labelled_cases(self):
        d = {"mode": "plan", "nodes": [
            {"id": "R", "kind": "requirement", "title": "g"},
            {"id": "B", "kind": "branch", "title": "ok?", "from": ["R"]},
            {"id": "A", "kind": "step", "title": "a", "from": [{"id": "B", "why": "yes"}]},
            {"id": "S", "kind": "stop", "title": "s", "from": ["A"], "done_when": ["x"]}]}
        rc, out = self.check(d)
        self.assertEqual(rc, 1)
        self.assertIn("needs ≥2 cases", out)

    def test_cycle_rejected(self):
        d = {"nodes": [
            {"id": "R", "kind": "requirement", "title": "x"},
            {"id": "A", "kind": "option", "status": "adopted", "title": "a", "from": ["R", "B"]},
            {"id": "B", "kind": "option", "status": "adopted", "title": "b", "from": ["A"]},
            {"id": "C", "kind": "option", "status": "rejected", "title": "c", "reason": "r", "from": ["R"]},
            {"id": "S", "kind": "stop", "title": "s", "from": ["B"]}]}
        rc, out = self.check(d)
        self.assertEqual(rc, 1)
        self.assertIn("cycle", out)


class TestHumanStyle(Base):
    def test_missing_summary_is_an_error_but_ai_style_still_builds(self):
        p, d = self.outline(OUTLINES[1])
        for n in d["nodes"]:
            n.pop("summary", None)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        rc, out = run(SCRIPTS / "thinking_chain.py", "check", p)
        self.assertEqual(rc, 1)
        self.assertIn("needs a 'summary'", out)
        rc, out = run(SCRIPTS / "thinking_chain.py", "build", p, self.tmp / "ai.prg", "--style", "ai")
        self.assertEqual(rc, 0, out)

    def test_notation_and_fragments_are_flagged(self):
        p, d = self.outline(OUTLINES[1])
        d["nodes"][1]["summary"] = "跑通→OK"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        _, out = run(SCRIPTS / "thinking_chain.py", "check", p)
        self.assertIn("notation symbols", out)
        self.assertIn("too short", out)
        self.assertIn("complete sentences", out)

    def test_human_canvas_has_no_node_ids_in_details(self):
        import zipfile, msgpack
        out = self.tmp / "h.prg"
        run(SCRIPTS / "thinking_chain.py", "build", EX / OUTLINES[1], out)
        stage = msgpack.unpackb(zipfile.ZipFile(out).read("stage.msgpack"), raw=False)
        ids = {n["id"] for n in json.loads((EX / OUTLINES[1]).read_text(encoding="utf-8"))["nodes"]}
        for o in stage:
            if o.get("_") != "TextNode":
                continue
            text = "\n".join(c["text"] for p in o.get("details", []) for c in p["children"])
            for i in ids - {"R"}:
                self.assertNotIn(f"自 {i}）", text)
                self.assertNotIn(f"[{i}]", text)


if __name__ == "__main__":
    unittest.main()
