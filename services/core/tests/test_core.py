import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from archcore.bim import Project
from archcore.geometry import polygon_area, perimeter, point_in_polygon
from archcore.history import History
from archcore.persist import save_project, load_project
from archcore.export import export_dxf, export_capabilities
from archcore.tools import apply_tool_call, ToolError
from archcore.ai.provider import FakeProvider, plan_tool_calls

RW = frozenset({"read", "write"})


def house():
    """10 m x 8 m room, 230 mm brick walls, one door, one window."""
    p = Project("Test House")
    lv = p.add_level("Ground", 0.0, 3.0)
    pts = [(0, 0), (10, 0), (10, 8), (0, 8)]
    ws = [p.add_wall(lv.id, pts[i], pts[(i + 1) % 4], 0.23, material="brick") for i in range(4)]
    door = p.add_opening(ws[0].id, "door", 1.0, 0.9, 2.1)
    p.add_opening(ws[1].id, "window", 2.0, 1.5, 1.2, sill=0.9)
    r = p.add_room("Living", lv.id, pts, target_area=80)
    return p, lv, ws, r, door


def parse_dxf(text):
    lines = text.split("\n")
    assert lines[-1] == ""
    lines = lines[:-1]
    assert len(lines) % 2 == 0, "DXF must be group-code/value pairs"
    pairs = [(int(lines[i]), lines[i + 1]) for i in range(0, len(lines), 2)]
    return pairs


class GeometryTests(unittest.TestCase):
    def test_area_perimeter_containment(self):
        sq = [(0, 0), (4, 0), (4, 3), (0, 3)]
        self.assertAlmostEqual(polygon_area(sq), 12)
        self.assertAlmostEqual(perimeter(sq), 14)
        self.assertTrue(point_in_polygon((1, 1), sq))
        self.assertFalse(point_in_polygon((5, 1), sq))

    def test_area_independent_of_winding(self):
        self.assertAlmostEqual(polygon_area([(0, 0), (0, 3), (4, 3), (4, 0)]), 12)


class FloorPlanTest(unittest.TestCase):
    def test_supplied_dimensions_preserved_exactly(self):
        p, lv, ws, r, _ = house()
        self.assertEqual(ws[0].length, 10.0)
        self.assertEqual(ws[1].length, 8.0)
        self.assertEqual(ws[0].thickness, 0.23)
        self.assertAlmostEqual(r.area, 80.0)
        self.assertEqual(p.room_schedule()[0]["delta"], 0.0)

    def test_quantities(self):
        p, _, ws, _, _ = house()
        q = {w["id"]: w for w in p.wall_quantities()}[ws[0].id]
        self.assertAlmostEqual(q["gross_area"], 30.0)
        self.assertAlmostEqual(q["net_area"], 30.0 - 0.9 * 2.1)
        self.assertAlmostEqual(q["volume"], q["net_area"] * 0.23)

    def test_invalid_input_rejected(self):
        p, lv, ws, _, _ = house()
        with self.assertRaises(ValueError): p.add_wall(lv.id, (0, 0), (0, 0), 0.2)
        with self.assertRaises(ValueError): p.add_opening(ws[0].id, "door", 9.5, 0.9, 2.1)   # past end
        with self.assertRaises(ValueError): p.add_opening(ws[0].id, "window", 3, 1, 3.5)      # past top
        with self.assertRaises(ValueError): p.add_opening(ws[0].id, "door", 1.5, 0.9, 2.1)   # overlaps door
        with self.assertRaises(ValueError): p.add_room("x", lv.id, [(0, 0), (1, 1)])


class BimPersistenceTest(unittest.TestCase):
    def test_wall_metadata_survives_save_reopen(self):
        p, lv, ws, _, door = house()
        p.walls[ws[0].id].properties["fire_rating"] = "2h"
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.archproj")
            save_project(p, path)
            q = load_project(path)
        w = q.walls[ws[0].id]
        self.assertEqual((w.thickness, w.height, w.material), (0.23, 3.0, "brick"))
        self.assertEqual(w.properties["fire_rating"], "2h")
        self.assertEqual(w.openings[0].id, door.id)
        self.assertEqual(q.to_dict(), p.to_dict())

    def test_tamper_detected(self):
        p, *_ = house()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.archproj")
            save_project(p, path)
            with open(path) as fh: data = json.load(fh)
            data["project"]["walls"][0]["thickness"] = 0.5
            with open(path, "w") as fh: json.dump(data, fh)
            with self.assertRaises(ValueError): load_project(path)


class HistoryTests(unittest.TestCase):
    def test_undo_redo_and_atomic_rollback(self):
        p = Project("h"); h = History(p)
        lv = h.apply("level", lambda pr: pr.add_level("G", 0, 3))
        h.apply("wall", lambda pr: pr.add_wall(lv.id, (0, 0), (5, 0), 0.2))
        self.assertEqual(len(p.walls), 1)
        h.undo(); self.assertEqual(len(p.walls), 0)
        h.redo(); self.assertEqual(len(p.walls), 1)

        def bad(pr):
            pr.add_wall(lv.id, (0, 0), (0, 5), 0.2)   # succeeds...
            pr.add_wall("nope", (0, 0), (1, 1), 0.2)  # ...then fails
        with self.assertRaises(ValueError): h.apply("bad", bad)
        self.assertEqual(len(p.walls), 1, "partial change must be rolled back")

    def test_version_diff(self):
        p, lv, ws, _, _ = house(); h = History(p)
        h.save_version("v1")
        h.apply("thicken", lambda pr: setattr(pr.walls[ws[0].id], "thickness", 0.3))
        extra = h.apply("add", lambda pr: pr.add_wall(lv.id, (0, 0), (3, 3), 0.1))
        h.save_version("v2")
        d = h.diff("v1", "v2")["walls"]
        self.assertEqual(d["changed"], [ws[0].id]); self.assertEqual(d["added"], [extra.id])
        with self.assertRaises(ValueError): h.save_version("v1")


class ExportTests(unittest.TestCase):
    def test_dxf_structure_and_content(self):
        p, lv, *_ = house()
        pairs = parse_dxf(export_dxf(p, lv.id))
        self.assertEqual(pairs[-1], (0, "EOF"))
        sections = [v for c, v in pairs if c == 0 and v == "SECTION"]
        ends = [v for c, v in pairs if c == 0 and v == "ENDSEC"]
        self.assertEqual(len(sections), len(ends))
        lines = [i for i, (c, v) in enumerate(pairs) if (c, v) == (0, "LINE")]
        self.assertEqual(len(lines), 4 * 4 + 2 + 4)  # wall outlines + 2 openings + room outline
        layers = {v for c, v in pairs if c == 8}
        self.assertEqual(layers, {"A-WALL", "A-DOOR", "A-GLAZ", "A-ROOM", "A-ANNO"})
        self.assertIn("Living 80.00 sqm", [v for c, v in pairs if c == 1])

    def test_capabilities_are_honest(self):
        c = export_capabilities()
        self.assertEqual(c["dxf"]["status"], "implemented")
        self.assertFalse(c["dxf"]["validated_in_cad_app"])
        for k in ("ifc", "dwg", "rvt", "3dm", "gltf"):
            self.assertEqual(c[k]["status"], "not_implemented")


class ToolAndAiTests(unittest.TestCase):
    def test_permissions_and_undo(self):
        p = Project("t"); h = History(p)
        with self.assertRaises(ToolError):
            apply_tool_call(h, "create_level", {"name": "G", "elevation": 0, "height": 3})  # read-only default
        lv = apply_tool_call(h, "create_level", {"name": "G", "elevation": 0, "height": 3}, RW)
        w = apply_tool_call(h, "create_wall", {"level_id": lv["id"], "start": [0, 0], "end": [6, 0], "thickness": 0.2}, RW)
        self.assertEqual(w["length"], 6.0)
        h.undo(); self.assertEqual(len(p.walls), 0)

    def test_bad_args_become_tool_errors_without_changes(self):
        p = Project("t"); h = History(p)
        with self.assertRaises(ToolError): apply_tool_call(h, "create_wall", {"level_id": "x"}, RW)
        with self.assertRaises(ToolError): apply_tool_call(h, "format_disk", {}, RW)
        self.assertEqual(len(p.walls), 0)

    def test_modify_wall_cannot_cut_opening(self):
        p, lv, ws, _, _ = house(); h = History(p)
        with self.assertRaises(ToolError):
            apply_tool_call(h, "modify_wall", {"wall_id": ws[1].id, "height": 1.5}, RW)  # window top at 2.1
        self.assertEqual(p.walls[ws[1].id].height, 3.0)
        apply_tool_call(h, "modify_wall", {"wall_id": ws[1].id, "height": 3.6, "material": "concrete"}, RW)
        self.assertEqual(p.walls[ws[1].id].material, "concrete")

    def test_planner_to_geometry_pipeline_with_fake_model(self):
        p = Project("t"); h = History(p)
        lv = h.apply("lvl", lambda pr: pr.add_level("G", 0, 3))
        reply = "```json\n" + json.dumps([{"tool": "create_wall", "args": {
            "level_id": lv.id, "start": [0, 0], "end": [4, 0], "thickness": 0.2}}]) + "\n```"
        calls = plan_tool_calls(FakeProvider(reply), "add a 4 m wall along the south edge")
        for c in calls: apply_tool_call(h, c["tool"], c["args"], RW)
        self.assertEqual(list(p.walls.values())[0].length, 4.0)

    def test_planner_rejects_hallucinated_tools_and_junk(self):
        with self.assertRaises(ValueError): plan_tool_calls(FakeProvider('[{"tool":"rm_rf","args":{}}]'), "x")
        with self.assertRaises(ValueError): plan_tool_calls(FakeProvider('{"tool":"create_wall"}'), "x")
        self.assertEqual(plan_tool_calls(FakeProvider('[{"tool":"ask_user","args":{"question":"Plot size?"}}]'), "x")[0]["tool"], "ask_user")


if __name__ == "__main__":
    unittest.main()
