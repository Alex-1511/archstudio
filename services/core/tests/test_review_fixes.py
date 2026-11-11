"""Regression tests for the five review findings. Written to FAIL against v0.1.0 first."""
import json, os, sys, tempfile, math, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from archcore.bim import Project
from archcore.history import History
from archcore.persist import save_project, load_project
from archcore.tools import apply_tool_call, apply_batch, ToolError
from archcore.ai.provider import FakeProvider, plan_tool_calls, converse
from archcore.solids import wall_solids, mesh_volume, is_closed_oriented
from archcore.export import export_obj, export_capabilities
from test_core import house

RW = frozenset({"read", "write"})


class RoomValidation(unittest.TestCase):
    def setUp(self):
        self.p = Project("r"); self.lv = self.p.add_level("G", 0, 3)

    def bad(self, pts):
        with self.assertRaises(ValueError): self.p.add_room("x", self.lv.id, pts)
        self.assertEqual(len(self.p.rooms), 0)

    def test_bowtie_rejected(self): self.bad([(0, 0), (4, 4), (4, 0), (0, 4)])
    def test_collinear_zero_area_rejected(self): self.bad([(0, 0), (1, 0), (2, 0)])
    def test_duplicate_points_rejected(self): self.bad([(0, 0), (0, 0), (4, 0), (4, 4)])
    def test_spike_rejected(self): self.bad([(0, 0), (4, 0), (6, 0), (4, 0), (4, 4)])
    def test_nan_inf_rejected(self):
        self.bad([(0, 0), (4, 0), (float("nan"), 4)]); self.bad([(0, 0), (4, 0), (math.inf, 4)])
    def test_touching_nonadjacent_edges_rejected(self): self.bad([(0, 0), (4, 0), (4, 4), (2, 0), (0, 4)])
    def test_valid_concave_L_accepted(self):
        r = self.p.add_room("L", self.lv.id, [(0, 0), (6, 0), (6, 2), (2, 2), (2, 5), (0, 5)])
        self.assertAlmostEqual(r.area, 18.0)  # 6x2 bar + 2x3 leg
    def test_wall_nonfinite_rejected(self):
        with self.assertRaises(ValueError): self.p.add_wall(self.lv.id, (0, 0), (float("nan"), 1), 0.2)


class ReferenceStability(unittest.TestCase):
    def test_held_references_survive_undo_redo_and_rollback(self):
        p, lv, ws, _, door = house(); h = History(p)
        w, op = p.walls[ws[0].id], p.walls[ws[0].id].openings[0]
        h.apply("t", lambda pr: setattr(pr.walls[w.id], "thickness", 0.5))
        h.undo()
        self.assertIs(p.walls[w.id], w); self.assertEqual(w.thickness, 0.23)
        self.assertIs(w.openings[0], op)
        h.redo(); self.assertIs(p.walls[w.id], w); self.assertEqual(w.thickness, 0.5)
        def bad(pr):
            pr.walls[w.id].thickness = 9.0; raise ValueError("boom")
        with self.assertRaises(ValueError): h.apply("bad", bad)
        self.assertIs(p.walls[w.id], w); self.assertEqual(w.thickness, 0.5)

    def test_deleted_then_redone_object_is_the_same_object(self):
        p = Project("t"); h = History(p); lv = h.apply("l", lambda pr: pr.add_level("G", 0, 3))
        w = h.apply("w", lambda pr: pr.add_wall(lv.id, (0, 0), (3, 0), 0.2))
        h.undo(); self.assertNotIn(w.id, p.walls)
        h.redo(); self.assertIs(p.walls[w.id], w)
        self.assertIs(p.levels[lv.id], lv)


class Integrity(unittest.TestCase):
    KEY = b"k" * 32

    def _tamper_and_recompute(self, path):
        import hashlib
        with open(path) as fh: d = json.load(fh)
        d["project"]["walls"][0]["thickness"] = 0.9
        d["checksum"] = hashlib.sha256(json.dumps(d["project"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with open(path, "w") as f: json.dump(d, f)

    def test_plain_checksum_does_not_stop_deliberate_tampering_documented(self):
        p, *_ = house()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p"); save_project(p, path); self._tamper_and_recompute(path)
            self.assertEqual(load_project(path).walls[next(iter(p.walls))].thickness, 0.9)  # known limitation

    def test_hmac_detects_recomputed_checksum_tampering(self):
        p, *_ = house()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p"); save_project(p, path, key=self.KEY)
            self.assertEqual(load_project(path, key=self.KEY).to_dict(), p.to_dict())
            with self.assertRaises(ValueError): load_project(path, key=b"wrong" * 8)
            self._tamper_and_recompute(path)
            with self.assertRaises(ValueError): load_project(path, key=self.KEY)

    def test_stripping_signature_rejected_when_key_given(self):
        p, *_ = house()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p"); save_project(p, path)
            with self.assertRaises(ValueError): load_project(path, key=self.KEY)


class ToolSchemas(unittest.TestCase):
    def setUp(self):
        self.p = Project("t"); self.h = History(self.p)
        self.lv = apply_tool_call(self.h, "create_level", {"name": "G", "elevation": 0, "height": 3}, RW)

    def rejects(self, tool, args):
        with self.assertRaises(ToolError): apply_tool_call(self.h, tool, args, RW)

    def test_arg_validation(self):
        base = {"level_id": self.lv["id"], "start": [0, 0], "end": [4, 0], "thickness": 0.2}
        self.rejects("create_wall", {**base, "thickness": "thick"})
        self.rejects("create_wall", {**base, "thickness": True})
        self.rejects("create_wall", {**base, "start": [0]})
        self.rejects("create_wall", {**base, "colour": "red"})            # unknown key
        self.rejects("create_wall", {k: v for k, v in base.items() if k != "end"})  # missing
        self.rejects("create_wall", {**base, "thickness": float("nan")})
        self.rejects("add_opening", {"wall_id": "w", "kind": "hatch", "offset": 0, "width": 1, "height": 1})
        self.assertEqual(len(self.p.walls), 0)

    def test_batch_is_atomic_and_supports_references(self):
        calls = [{"tool": "create_wall", "args": {"level_id": self.lv["id"], "start": [0, 0], "end": [5, 0], "thickness": 0.2}},
                 {"tool": "add_opening", "args": {"wall_id": "$0.id", "kind": "door", "offset": 1, "width": 0.9, "height": 2.1}}]
        res = apply_batch(self.h, calls, RW)
        self.assertEqual(len(list(self.p.walls.values())[0].openings), 1)
        bad = [{"tool": "create_wall", "args": {"level_id": self.lv["id"], "start": [0, 0], "end": [0, 5], "thickness": 0.2}},
               {"tool": "add_opening", "args": {"wall_id": "$0.id", "kind": "door", "offset": 4.9, "width": 0.9, "height": 2.1}}]
        with self.assertRaises(ToolError): apply_batch(self.h, bad, RW)
        self.assertEqual(len(self.p.walls), 1, "first call of failed batch must be rolled back")

    def test_clarification_loop_asks_instead_of_guessing(self):
        lvl = self.lv["id"]
        asked = []
        provider = FakeProvider(
            '[{"tool":"ask_user","args":{"question":"How thick should the wall be?"}}]',
            json.dumps([{"tool": "create_wall", "args": {"level_id": lvl, "start": [0, 0], "end": [4, 0], "thickness": 0.3}}]))
        out = converse(provider, self.h, "add a 4 m wall", ask=lambda q: (asked.append(q), "300 mm")[1], permissions=RW)
        self.assertEqual(asked, ["How thick should the wall be?"]); self.assertEqual(out["status"], "done")
        self.assertIn("300 mm", provider.prompts[1]); self.assertIn(lvl, provider.prompts[0])  # context incl. ids
        out2 = converse(FakeProvider('[{"tool":"ask_user","args":{"question":"?"}}]'), self.h, "x", ask=None, permissions=RW)
        self.assertEqual(out2["status"], "needs_clarification")
        self.assertEqual(len(self.p.walls), 1)

    def test_planner_rejects_bad_args_before_execution(self):
        with self.assertRaises(ValueError):
            plan_tool_calls(FakeProvider('[{"tool":"create_wall","args":{"level_id":"x","thickness":-1}}]'), "x")


class Solids(unittest.TestCase):
    def test_wall_mesh_volume_matches_quantities_and_is_closed(self):
        p, lv, ws, _, _ = house()
        for w in p.walls.values():
            boxes = wall_solids(w, p.levels[w.level_id])
            self.assertAlmostEqual(sum(mesh_volume(v, t) for v, t in boxes), w.volume(), places=9)
            for v, t in boxes:
                self.assertTrue(is_closed_oriented(t)); self.assertGreater(mesh_volume(v, t), 0)

    def test_window_leaves_sill_and_head_pieces(self):
        p, lv, ws, _, _ = house()
        boxes = wall_solids(p.walls[ws[1].id], lv)  # 8 m wall, window at 2.0..3.5, sill .9, h 1.2
        self.assertEqual(len(boxes), 4)             # left, sill, head, right
        zs = sorted((min(z for _, _, z in v), max(z for _, _, z in v)) for v, _ in boxes)
        self.assertIn((0.0, 0.9), zs); self.assertIn((2.1, 3.0), zs)

    def test_obj_export_and_capability(self):
        p, lv, *_ = house(); obj = export_obj(p, lv.id)
        self.assertTrue(obj.startswith("# ArchStudio")); self.assertGreater(obj.count("\nf "), 40)
        c = export_capabilities()["obj"]
        self.assertEqual(c["status"], "implemented"); self.assertIn("mesh-only", c["fidelity"].lower())


if __name__ == "__main__":
    unittest.main()
