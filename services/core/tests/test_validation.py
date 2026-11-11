"""Round-2 review: non-finite/typed input everywhere, hostile imports, fuzzing, independent export checks."""
import copy, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from archcore.bim import Project
from archcore.history import History
from archcore.persist import save_project, load_project, _checksum
from archcore.export import export_obj, export_dxf
from test_core import house, parse_dxf

NAN, INF = float("nan"), float("inf")
BAD_NUMBERS = [NAN, INF, -INF, True, "1", None]


class NonFiniteCreation(unittest.TestCase):
    def setUp(self):
        self.p = Project("v"); self.lv = self.p.add_level("G", 0, 3)
        self.w = self.p.add_wall(self.lv.id, (0, 0), (6, 0), 0.2)

    def all_rejected(self, fn, values=BAD_NUMBERS):
        for v in values:
            with self.subTest(value=v), self.assertRaises(ValueError): fn(v)

    def test_levels(self):
        self.all_rejected(lambda v: self.p.add_level("a", v, 3))
        self.all_rejected(lambda v: self.p.add_level("a", 0, v))
        with self.assertRaises(ValueError): self.p.add_level("a", 0, -1)
        with self.assertRaises(ValueError): self.p.add_level("", 0, 3)
        self.assertEqual(len(self.p.levels), 1)

    def test_walls(self):
        self.all_rejected(lambda v: self.p.add_wall(self.lv.id, (0, 0), (5, 0), v))
        self.all_rejected(lambda v: self.p.add_wall(self.lv.id, (0, 0), (5, 0), 0.2, height=v), [NAN, INF, -INF, True, "1"])
        self.all_rejected(lambda v: self.p.add_wall(self.lv.id, (v, 0), (5, 0), 0.2))
        self.all_rejected(lambda v: self.p.add_wall(self.lv.id, (0, 0), (5, v), 0.2))
        with self.assertRaises(ValueError): self.p.add_wall(self.lv.id, (0, 0), (5, 0), 0.2, properties={"x": NAN})
        with self.assertRaises(ValueError): self.p.add_wall(self.lv.id, (0, 0), (5, 0), 0.2, material="")
        self.assertEqual(len(self.p.walls), 1)

    def test_openings(self):
        self.all_rejected(lambda v: self.p.add_opening(self.w.id, "door", v, 0.9, 2.1))
        self.all_rejected(lambda v: self.p.add_opening(self.w.id, "door", 1, v, 2.1))
        self.all_rejected(lambda v: self.p.add_opening(self.w.id, "door", 1, 0.9, v))
        self.all_rejected(lambda v: self.p.add_opening(self.w.id, "window", 1, 1, 1, sill=v))
        self.assertEqual(self.w.openings, [])

    def test_rooms_and_schedule(self):
        sq = [(0, 0), (4, 0), (4, 4), (0, 4)]
        self.all_rejected(lambda v: self.p.add_room("r", self.lv.id, sq, target_area=v), [NAN, INF, -INF, True, "1", 0, -5])
        self.all_rejected(lambda v: self.p.add_room("r", self.lv.id, [(0, 0), (4, 0), (4, v)]))
        r = self.p.add_room("r", self.lv.id, sq, target_area=20)
        row = self.p.room_schedule()[0]
        self.assertEqual((row["area"], row["target_area"], row["delta"]), (16.0, 20.0, -4.0))

    def test_direct_mutation_inside_command_is_caught_and_rolled_back(self):
        h = History(self.p)
        for field, val in (("thickness", NAN), ("height", INF), ("thickness", -1.0), ("material", 5)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                h.apply("poison", lambda pr: setattr(pr.walls[self.w.id], field, val))
            self.assertEqual((self.w.thickness, self.w.height, self.w.material), (0.2, 3.0, "unspecified"))
        with self.assertRaises(ValueError):
            h.apply("poison", lambda pr: setattr(pr.levels[self.lv.id], "elevation", NAN))
        self.assertEqual(self.lv.elevation, 0.0)

    def test_save_refuses_invalid_model(self):
        self.w.thickness = NAN  # bypasses every API on purpose
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            save_project(self.p, os.path.join(d, "p"))


def signed_file(d, project_dict, name="p"):
    """Write a file with a CORRECT checksum around arbitrary project data (a hostile-but-consistent file)."""
    path = os.path.join(d, name)
    with open(path, "w") as f:
        json.dump({"schema_version": 1, "checksum": _checksum(project_dict), "project": project_dict}, f)
    return path


class HostileImport(unittest.TestCase):
    _GOOD = house()[0].to_dict()  # ids are random per call, so build the fixture once

    def good(self): return copy.deepcopy(self._GOOD)

    def assert_import_rejected(self, mutate, label):
        d = self.good(); mutate(d)
        with tempfile.TemporaryDirectory() as t, self.subTest(label), self.assertRaises(ValueError):
            load_project(signed_file(t, d))

    def test_semantic_corruption_with_valid_checksum(self):
        W, O, R, L = (lambda d: d["walls"][0]), (lambda d: d["walls"][0]["openings"][0]), (lambda d: d["rooms"][0]), (lambda d: d["levels"][0])
        cases = {
            "negative thickness": lambda d: W(d).update(thickness=-1),
            "zero thickness": lambda d: W(d).update(thickness=0),
            "string thickness": lambda d: W(d).update(thickness="0.2"),
            "dangling level": lambda d: W(d).update(level_id="ghost"),
            "zero-length wall": lambda d: W(d).update(end=W(d)["start"]),
            "opening past wall end": lambda d: O(d).update(offset=99),
            "opening too tall": lambda d: O(d).update(height=99),
            "overlapping openings": lambda d: W(d)["openings"].append({**O(d), "id": "dup2"}),
            "duplicate opening id": lambda d: W(d)["openings"].append({**O(d), "offset": 5}),
            "bowtie room": lambda d: R(d).update(boundary=[[0, 0], [4, 4], [4, 0], [0, 4]]),
            "room dangling level": lambda d: R(d).update(level_id="ghost"),
            "room target negative": lambda d: R(d).update(target_area=-3),
            "level height zero": lambda d: L(d).update(height=0),
            "duplicate wall id": lambda d: d["walls"].append(copy.deepcopy(W(d))),
            "bad units": lambda d: d.update(units="furlongs"),
            "unknown extra key": lambda d: W(d).update(hax=1),
            "missing key": lambda d: W(d).pop("material"),
            "walls not a list": lambda d: d.update(walls={}),
            "properties not an object": lambda d: W(d).update(properties=[]),
            "absurd magnitude": lambda d: W(d).update(thickness=1e300),
        }
        for label, m in cases.items():
            self.assert_import_rejected(m, label)

    def test_nan_literal_in_file_rejected_at_parse(self):
        d = self.good()
        with tempfile.TemporaryDirectory() as t:
            path = signed_file(t, d)
            with open(path) as fh: text = fh.read().replace('"thickness": 0.23', '"thickness": NaN', 1)
            with open(path, "w") as fh: fh.write(text)
            with self.assertRaises(ValueError): load_project(path)

    def test_structural_garbage(self):
        with tempfile.TemporaryDirectory() as t:
            for label, content in {"not json": "{{{", "list": "[]", "string": '"x"', "empty obj": "{}",
                                   "project not obj": '{"schema_version":1,"checksum":"x","project":[]}'}.items():
                p = os.path.join(t, "g")
                with open(p, "w") as fh: fh.write(content)
                with self.subTest(label), self.assertRaises(ValueError): load_project(p)
            big = os.path.join(t, "big")
            with open(big, "w") as fh: fh.write("x" * 100)
            with self.assertRaises(ValueError): load_project(big, max_bytes=10)

    def test_valid_project_still_loads(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(load_project(signed_file(t, self.good())).to_dict(), self.good())


def leaves(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items(): yield from leaves(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node): yield from leaves(v, path + (i,))
    else:
        yield path


class FuzzImport(unittest.TestCase):
    def test_every_corrupted_leaf_is_rejected_cleanly_or_remains_valid(self):
        base = HostileImport._GOOD
        n_checked = n_rejected = 0
        for path in leaves(base):
            for bad in (NAN, INF, -INF, -1, 0, True, "x", None, [], {}, 1e308, 1e10):
                d = copy.deepcopy(base); node = d
                for k in path[:-1]: node = node[k]
                node[path[-1]] = bad
                n_checked += 1
                try:
                    p = Project.from_dict(d)
                except ValueError:
                    n_rejected += 1
                    continue
                except Exception as e:  # noqa: BLE001
                    self.fail(f"leaked {type(e).__name__} for {path}={bad!r}: {e}")
                p.validate()  # accepted => must genuinely satisfy every invariant
                for r in p.room_schedule(): self.assertTrue(all(v == v and abs(v) != INF for v in r.values() if isinstance(v, float)))
                for q in p.wall_quantities(): self.assertTrue(all(v == v and abs(v) != INF for v in q.values() if isinstance(v, float)))
        self.assertGreater(n_checked, 500); self.assertGreater(n_rejected, n_checked // 3)


class IndependentExportChecks(unittest.TestCase):
    """Re-parse exported text with separate code. Not a substitute for opening the files in CAD software."""
    def test_obj_reparsed_indices_valid_and_volume_matches_quantities(self):
        p, lv, *_ = house()
        verts, faces = [], []
        for line in export_obj(p, lv.id).splitlines():
            t = line.split()
            if t and t[0] == "v": verts.append(tuple(map(float, t[1:])))
            elif t and t[0] == "f": faces.append(tuple(int(x) for x in t[1:]))
        self.assertTrue(all(len(f) == 3 and all(1 <= i <= len(verts) for i in f) for f in faces))
        vol = 0.0
        for a, b, c in faces:
            (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = verts[a - 1], verts[b - 1], verts[c - 1]
            vol += (x1 * (y2 * z3 - z2 * y3) - y1 * (x2 * z3 - z2 * x3) + z1 * (x2 * y3 - y2 * x3)) / 6
        self.assertAlmostEqual(vol, sum(w.volume() for w in p.walls.values()), places=6)
        self.assertTrue(all(v == v and abs(c) < 1e6 for v in verts for c in v))

    def test_dxf_wall_extents_match_model(self):
        p, lv, *_ = house()
        pairs = parse_dxf(export_dxf(p, lv.id))
        xs, ys, i = [], [], 0
        while i < len(pairs):
            if pairs[i] == (0, "LINE") and ("8", ) and pairs[i + 1] == (8, "A-WALL"):
                vals = {c: float(v) for c, v in pairs[i + 2:i + 8]}
                xs += [vals[10], vals[11]]; ys += [vals[20], vals[21]]
            i += 1
        self.assertAlmostEqual(min(xs), -0.115); self.assertAlmostEqual(max(xs), 10.115)
        self.assertAlmostEqual(min(ys), -0.115); self.assertAlmostEqual(max(ys), 8.115)


if __name__ == "__main__":
    unittest.main()
