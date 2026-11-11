import json, os, sys, threading, unittest, urllib.error, urllib.request, http.client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from archcore.api import make_server, Session
from archcore.bim import Project
from archcore.history import History
from schema_check import check
from test_core import house

TOKEN = "test-token"


class Api(unittest.TestCase):
    def setUp(self):
        self.session = Session(house()[0])
        self.srv = make_server(token=TOKEN, session=self.session, allowed_origin="http://localhost:3000")
        threading.Thread(target=lambda: self.srv.serve_forever(poll_interval=0.01), daemon=True).start()
        self.port = self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()

    def call(self, method, path, body=None, token=TOKEN, headers=None, raw=None, ctype="application/json"):
        h = {"Content-Type": ctype, **(headers or {})}
        if token: h["Authorization"] = f"Bearer {token}"
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse(); txt = r.read().decode(); conn.close()
        try: js = json.loads(txt)
        except ValueError: js = None
        return r.status, js, txt, r

    def ok(self, method, path, schema, body=None):
        s, js, txt, _ = self.call(method, path, body)
        self.assertEqual(s, 200, txt)
        self.assertEqual(check(js, {"$ref": "#/$defs/" + schema}), [])
        return js

    # ---------------------------------------------------------------- contract
    def test_responses_conform_to_contract(self):
        st = self.ok("GET", "/api/v1/project", "State")
        self.ok("GET", "/api/v1/mesh", "Mesh"); self.ok("GET", "/api/v1/tools", "Tools")
        lv = st["project"]["levels"][0]["id"]; wid = st["project"]["walls"][0]["id"]
        js = self.ok("POST", "/api/v1/tools/modify_wall", "State", {"args": {"wall_id": wid, "thickness": 0.3}})
        self.assertEqual(js["result"], {"id": wid})
        self.ok("POST", "/api/v1/undo", "State", {}); self.ok("POST", "/api/v1/redo", "State", {})
        self.ok("GET", f"/api/v1/mesh?level={lv}", "Mesh")

    def test_error_shape_conforms(self):
        for method, path, body in (("GET", "/api/v1/nope", None), ("POST", "/api/v1/tools/create_wall", {"args": {}}),
                                   ("POST", "/api/v1/tools/zzz", {"args": {}}), ("GET", "/api/v1/mesh?level=ghost", None)):
            s, js, txt, _ = self.call(method, path, body)
            self.assertIn(s, (400, 404), txt); self.assertEqual(check(js, {"$ref": "#/$defs/Error"}), [], txt)

    # ---------------------------------------------------------------- security
    def test_auth_required_everywhere(self):
        for tok in (None, "wrong", ""):
            self.assertEqual(self.call("GET", "/api/v1/health", token=tok)[0], 401)
            self.assertEqual(self.call("PUT", "/api/v1/project", {"project": {}}, token=tok)[0], 401)
        self.assertEqual(self.call("GET", "/api/v1/health")[0], 200)

    def test_host_header_must_be_loopback(self):
        s, *_ = self.call("GET", "/api/v1/health", headers={"Host": "evil.example.com"})
        self.assertEqual(s, 403)

    def test_cors_preflight_and_origin(self):
        s, _, _, r = self.call("OPTIONS", "/api/v1/project", token=None)
        self.assertEqual(s, 204); self.assertEqual(r.getheader("Access-Control-Allow-Origin"), "http://localhost:3000")
        self.assertIn("Authorization", r.getheader("Access-Control-Allow-Headers"))

    def test_body_rules(self):
        self.assertEqual(self.call("PUT", "/api/v1/project", raw=b"{}", ctype="text/plain")[0], 415)
        self.assertEqual(self.call("PUT", "/api/v1/project", raw=b"{nope")[0], 400)
        self.assertEqual(self.call("PUT", "/api/v1/project", raw=b"[]")[0], 400)
        self.assertEqual(self.call("PUT", "/api/v1/project", raw=b'{"project": NaN}')[0], 400)
        self.assertEqual(self.call("POST", "/api/v1/tools/inspect_project", raw=b'{"args":{},"evil":1}')[0], 400)
        # declare an oversize body without sending it: the server must refuse BEFORE reading
        s, js, *_ = self.call("PUT", "/api/v1/project", raw=b"{}", headers={"Content-Length": str(5 * 1024 * 1024 + 1)})
        self.assertEqual((s, js["error"]["code"]), (413, "too_large"))

    def test_internal_errors_do_not_leak(self):
        self.session.history = None  # force an unexpected exception inside a route
        s, js, txt, _ = self.call("GET", "/api/v1/project")
        self.assertEqual(s, 500); self.assertEqual(js["error"]["message"], "internal error"); self.assertNotIn("Traceback", txt)

    # ---------------------------------------------------------------- behaviour
    def test_tool_edit_undo_redo_and_revisions(self):
        st = self.call("GET", "/api/v1/project")[1]; r0, wid = st["revision"], st["project"]["walls"][0]["id"]
        _, js, *_ = self.call("POST", "/api/v1/tools/modify_wall", {"args": {"wall_id": wid, "thickness": 0.4}, "expected_revision": r0})
        self.assertEqual(js["revision"], r0 + 1); self.assertEqual(js["project"]["walls"][0]["thickness"], 0.4)
        s, js2, *_ = self.call("POST", "/api/v1/tools/modify_wall", {"args": {"wall_id": wid, "thickness": 0.5}, "expected_revision": r0})
        self.assertEqual((s, js2["error"]["code"]), (409, "revision_conflict"))
        self.assertEqual(self.call("GET", "/api/v1/project")[1]["project"]["walls"][0]["thickness"], 0.4, "conflict must not apply")
        js = self.call("POST", "/api/v1/undo", {})[1]
        self.assertEqual(js["project"]["walls"][0]["thickness"], 0.23); self.assertEqual(js["revision"], r0 + 2)
        self.assertEqual(self.call("POST", "/api/v1/redo", {})[1]["project"]["walls"][0]["thickness"], 0.4)

    def test_invalid_edits_rejected_and_state_unchanged(self):
        st = self.call("GET", "/api/v1/project")[1]; wid = st["project"]["walls"][1]["id"]; oid = st["project"]["walls"][1]["openings"][0]["id"]
        before = self.call("GET", "/api/v1/project")[1]
        for tool, args in (("modify_wall", {"wall_id": wid, "thickness": -1}), ("modify_wall", {"wall_id": wid, "height": 1.0}),
                           ("modify_opening", {"opening_id": oid, "width": 50}), ("modify_opening", {"opening_id": oid, "sill": 2.9}),
                           ("modify_level", {"level_id": st["project"]["levels"][0]["id"], "height": 0}),
                           ("modify_wall", {"wall_id": "ghost", "thickness": 1}), ("modify_wall", {"wall_id": wid, "thickness": "0.3"})):
            s, js, txt, _ = self.call("POST", f"/api/v1/tools/{tool}", {"args": args})
            self.assertEqual(s, 400, (tool, args, txt))
        self.assertEqual(self.call("GET", "/api/v1/project")[1], before)

    def test_delete_then_undo_restores_same_object(self):
        w0 = next(iter(self.session.history.project.walls.values())); wid = w0.id
        self.call("POST", "/api/v1/tools/delete_wall", {"args": {"wall_id": wid}})
        self.assertNotIn(wid, self.session.history.project.walls)
        self.call("POST", "/api/v1/undo", {})
        self.assertIs(self.session.history.project.walls[wid], w0)
        op = w0.openings[0]
        self.call("POST", "/api/v1/tools/delete_opening", {"args": {"opening_id": op.id}}); self.assertEqual(w0.openings, [])
        self.call("POST", "/api/v1/undo", {}); self.assertIs(w0.openings[0], op)

    def test_import_replaces_project_strictly(self):
        good = Project("Imported"); lv = good.add_level("L1", 0, 3); good.add_wall(lv.id, (0, 0), (4, 0), 0.2)
        r0 = self.call("GET", "/api/v1/project")[1]["revision"]
        js = self.call("PUT", "/api/v1/project", {"project": good.to_dict()})[1]
        self.assertEqual((js["project"]["name"], js["revision"] > r0), ("Imported", True))
        for label, mut in (("negative", lambda d: d["walls"][0].update(thickness=-1)), ("ghost level", lambda d: d["walls"][0].update(level_id="x")),
                           ("extra key", lambda d: d.update(evil=1))):
            d = good.to_dict(); mut(d)
            s, js, txt, _ = self.call("PUT", "/api/v1/project", {"project": d}); self.assertEqual(s, 400, label)
        self.assertEqual(self.call("GET", "/api/v1/project")[1]["project"]["name"], "Imported")

    def test_mesh_is_engine_geometry_and_consistent_with_quantities(self):
        p = self.session.history.project
        js = self.call("GET", "/api/v1/mesh")[1]
        vol = 0.0
        for el in js["elements"]:
            if el["type"] != "wall": continue
            pos, idx = el["positions"], el["indices"]
            for i in range(0, len(idx), 3):
                a, b, c = (tuple(pos[3 * k:3 * k + 3]) for k in idx[i:i + 3])
                vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
        self.assertAlmostEqual(vol, sum(w.volume() for w in p.walls.values()), places=6)
        ids = {e["id"]: e for e in js["elements"]}
        self.assertEqual(sum(1 for e in js["elements"] if e["type"] == "opening"), 2)
        for w in p.walls.values():
            self.assertIn(w.id, ids)
            for o in w.openings: self.assertEqual((ids[o.id]["wall_id"], ids[o.id]["kind"]), (w.id, o.kind))
        for e in js["elements"]:
            self.assertTrue(all(0 <= i < len(e["positions"]) // 3 for i in e["indices"]))

    def test_mesh_changes_with_edit(self):
        p = self.session.history.project; wid = next(iter(p.walls))
        v = lambda: sum(len(e["positions"]) for e in self.call("GET", "/api/v1/mesh")[1]["elements"])
        n0 = v()
        self.call("POST", "/api/v1/tools/delete_opening", {"args": {"opening_id": p.walls[wid].openings[0].id}})
        self.assertNotEqual(v(), n0)

    def test_exports_and_capabilities(self):
        lv = next(iter(self.session.history.project.levels))
        s, _, txt, r = self.call("GET", f"/api/v1/export/dxf?level={lv}")
        self.assertEqual(s, 200); self.assertTrue(txt.rstrip().endswith("EOF")); self.assertIn("attachment", r.getheader("Content-Disposition"))
        self.assertEqual(self.call("GET", f"/api/v1/export/obj?level={lv}")[0], 200)
        self.assertEqual(self.call("GET", "/api/v1/export/ifc?level=" + lv)[0], 404, "unimplemented formats must not be served")
        self.assertEqual(self.call("GET", "/api/v1/capabilities")[1]["exports"]["ifc"]["status"], "not_implemented")


if __name__ == "__main__":
    unittest.main()


class StaticServing(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        root = os.path.join(self.tmp.name, "dist"); os.mkdir(root)
        with open(os.path.join(root, "index.html"), "w") as f: f.write("<h1>app</h1>")
        with open(os.path.join(root, "app.js"), "w") as f: f.write("console.log(1)")
        with open(os.path.join(root, "notes.py"), "w") as f: f.write("print('no')")
        with open(os.path.join(self.tmp.name, "secret.html"), "w") as f: f.write("TOP-SECRET")
        os.symlink(os.path.join(self.tmp.name, "secret.html"), os.path.join(root, "link.html"))
        self.srv = make_server(token=TOKEN, session=Session(house()[0]), static_dir=root)
        threading.Thread(target=lambda: self.srv.serve_forever(poll_interval=0.01), daemon=True).start()
        self.port = self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.tmp.cleanup()

    def get(self, path, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.putrequest("GET", path, skip_host=host is not None)
        if host: c.putheader("Host", host)
        c.endheaders(); r = c.getresponse(); body = r.read().decode(); c.close(); return r.status, body, r

    def test_serves_index_and_assets_without_token_with_strict_headers(self):
        s, body, r = self.get("/"); self.assertEqual((s, body), (200, "<h1>app</h1>"))
        csp = r.getheader("Content-Security-Policy"); self.assertIn("script-src 'self'", csp); self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn("unsafe-inline", csp); self.assertNotIn("unsafe-eval", csp)
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        s, _, r = self.get("/app.js"); self.assertEqual((s, r.getheader("Content-Type").split(";")[0]), (200, "text/javascript"))

    def test_path_traversal_and_escape_attempts_are_refused(self):
        for p in ("/../secret.html", "/%2e%2e/secret.html", "/..%2fsecret.html", "/%2e%2e%2fsecret.html", "//etc/passwd", "/index.html/../../secret.html",
                  "/..\\secret.html", "/link.html", "/notes.py", "/%00index.html", "/app.js/", "/nope.js"):
            s, body, _ = self.get(p); self.assertEqual(s, 404, p); self.assertNotIn("TOP-SECRET", body, p)

    def test_host_check_and_api_auth_still_apply(self):
        self.assertEqual(self.get("/", host="evil.example.com")[0], 403)
        self.assertEqual(self.get("/api/v1/project")[0], 401)

    def test_static_disabled_without_directory(self):
        srv = make_server(token=TOKEN); threading.Thread(target=lambda: srv.serve_forever(poll_interval=0.01), daemon=True).start()
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1]); c.request("GET", "/"); r = c.getresponse()
        self.assertEqual(r.status, 401); c.close(); srv.shutdown(); srv.server_close()
