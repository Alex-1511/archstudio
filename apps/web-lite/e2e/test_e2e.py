"""End-to-end: real Python server + real bundled client in headless Chromium (Playwright).
Run from the repo root:  python3 -m unittest discover -s apps/web-lite/e2e -v
Needs `playwright` + Chromium and `esbuild`; skips (never fakes a pass) when they are missing."""
import json, os, shutil, subprocess, sys, tempfile, unittest, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
WEB = os.path.join(HERE, "..")
SERVER = os.path.join(ROOT, "services", "core", "run_server.py")
SHOTS = os.environ.get("E2E_SCREENSHOTS", os.path.join(tempfile.gettempdir(), "archstudio-shots"))
TOKEN = "e2e-token"

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


def find_esbuild():
    for c in (shutil.which("esbuild"), os.path.join(WEB, "node_modules", ".bin", "esbuild"), "/opt/npm-tools/node_modules/.bin/esbuild"):
        if c and os.path.exists(c):
            return c


def project(name="E2E House"):
    wall = lambda i, s, e, ops: {"id": f"W{i}", "level_id": "L1", "start": s, "end": e, "thickness": 0.23, "height": 3.0, "material": "brick", "properties": {}, "openings": ops}
    return {"name": name, "units": "m", "levels": [{"id": "L1", "name": "Ground", "elevation": 0.0, "height": 3.0}],
            "walls": [wall(1, [0, 0], [10, 0], [{"id": "D1", "kind": "door", "offset": 1.0, "width": 0.9, "height": 2.1, "sill": 0.0}]),
                      wall(2, [10, 0], [10, 8], [{"id": "N1", "kind": "window", "offset": 2.0, "width": 1.5, "height": 1.2, "sill": 0.9}]),
                      wall(3, [10, 8], [0, 8], []), wall(4, [0, 8], [0, 0], [])],
            "rooms": [{"id": "R1", "name": "Living", "level_id": "L1", "boundary": [[0, 0], [10, 0], [10, 8], [0, 8]], "target_area": 80.0}]}


def api(base, method, path, body=None, token=TOKEN):
    req = urllib.request.Request(base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def setUpModule():
    global PW, BROWSER, PROC, BASE
    if sync_playwright is None:
        raise unittest.SkipTest("playwright not installed")
    esb = find_esbuild()
    if not esb:
        raise unittest.SkipTest("esbuild not found")
    os.makedirs(os.path.join(WEB, "dist"), exist_ok=True)
    r = subprocess.run([esb, "src/main.ts", "--bundle", "--format=esm", "--target=es2022", "--minify", "--outfile=dist/app.js", "--log-level=error"], cwd=WEB, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("client build failed:\n" + r.stderr)
    for f in ("index.html", "styles.css"):
        shutil.copy(os.path.join(WEB, f), os.path.join(WEB, "dist", f))
    PROC = subprocess.Popen([sys.executable, SERVER, "--port", "0"], stdout=subprocess.PIPE, text=True, env={**os.environ, "ARCH_API_TOKEN": TOKEN})
    BASE = f"http://127.0.0.1:{json.loads(PROC.stdout.readline())['port']}"
    PW = sync_playwright().start()
    try:
        BROWSER = PW.chromium.launch()
    except Exception as e:  # pragma: no cover
        PW.stop(); PROC.kill(); raise unittest.SkipTest(f"chromium unavailable: {e}")
    os.makedirs(SHOTS, exist_ok=True)


def tearDownModule():
    BROWSER.close(); PW.stop(); PROC.kill(); PROC.wait(); PROC.stdout.close()


class E2E(unittest.TestCase):
    def setUp(self):
        s, js = api(BASE, "PUT", "/api/v1/project", {"project": project()}); assert s == 200, js
        self.ctx = BROWSER.new_context(viewport={"width": 1280, "height": 760}, accept_downloads=True)
        self.page = self.ctx.new_page(); self.page.set_default_timeout(6000); self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)

    def tearDown(self):
        self.ctx.close()

    def open(self, token=TOKEN):
        self.page.goto(f"{BASE}/?debug#token={token}"); self.page.wait_for_selector("[role=treeitem]"); self.page.wait_for_timeout(250)

    def shot(self, name): self.page.screenshot(path=os.path.join(SHOTS, name + ".png"))
    def server(self): return api(BASE, "GET", "/api/v1/project")[1]
    def wall(self, id_): return next(w for w in self.server()["project"]["walls"] if w["id"] == id_)

    def click_element(self, id_, **kw):
        p = self.page.evaluate(f"window.__archstudio.screenOf('{id_}')"); self.assertIsNotNone(p, id_)
        self.page.mouse.click(p["x"], p["y"], **kw)

    def distinct_colors(self):
        return self.page.evaluate("""() => { const c = document.querySelector('canvas'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
            const s = new Set(); for (let i = 0; i < d.length; i += 4 * 97) s.add(d[i] + ',' + d[i+1] + ',' + d[i+2]); return s.size; }""")

    def canvas_hash(self):
        return self.page.evaluate("""() => { const c = document.querySelector('canvas'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
            let h = 0; for (let i = 0; i < d.length; i += 4 * 13) h = (h * 31 + d[i] + d[i+1] * 3 + d[i+2] * 7) | 0; return h; }""")

    def commit(self, selector, value):
        self.page.fill(selector, value); self.page.press(selector, "Enter"); self.page.wait_for_timeout(350)

    def assert_clean(self, expect_http_errors=False):
        """No JS exceptions / console errors. Tests that deliberately provoke 4xx responses may expect Chromium's network log lines, nothing else."""
        errs = [e for e in self.errors if not (expect_http_errors and e.startswith("Failed to load resource: the server responded with a status of 4"))]
        self.assertEqual(errs, [])

    # ------------------------------------------------------------------
    def test_loads_hides_token_and_renders(self):
        self.open()
        self.assertNotIn("token", self.page.url)
        self.assertEqual(self.page.inner_text("header strong"), "E2E House")
        self.assertEqual(self.page.locator("[role=treeitem]").count(), 8)  # level, 4 walls, door, window, room
        self.assertGreater(self.distinct_colors(), 6, "canvas must not be blank")
        self.assertIn("4 walls", self.page.inner_text("footer")); self.assertIn("2 openings", self.page.inner_text("footer"))
        self.shot("01-loaded"); self.assert_clean()

    def test_canvas_click_selects_and_inspector_edit_hits_engine(self):
        self.open(); r0 = self.server()["revision"]
        self.click_element("W2")
        self.assertEqual(self.page.inner_text(".right h3"), "Wall")
        self.assertEqual(self.page.input_value("#f-thickness"), "0.23")
        self.assertEqual(self.page.get_attribute("[data-id=W2]", "aria-current"), "true")
        self.shot("02-wall-selected")
        before = self.canvas_hash()
        self.commit("#f-thickness", "0.4")
        self.assertEqual(self.wall("W2")["thickness"], 0.4)
        self.assertEqual(self.server()["revision"], r0 + 1)
        self.assertIn(f"Revision {r0 + 1}", self.page.inner_text("footer"))
        self.assertNotEqual(self.canvas_hash(), before, "geometry on screen changed")
        self.assertEqual(self.page.input_value("#f-thickness"), "0.4"); self.assert_clean()

    def test_click_selects_openings_through_the_wall_gap(self):
        self.open(); self.click_element("N1")
        self.assertEqual(self.page.inner_text(".right h3"), "Window")
        self.page.select_option("#f-kind", "door"); self.page.wait_for_timeout(350)
        self.assertEqual(next(o for o in self.wall("W2")["openings"] if o["id"] == "N1")["kind"], "door"); self.assert_clean()

    def test_invalid_edits_are_rejected_with_messages_and_server_untouched(self):
        self.open(); self.click_element("W2"); r0 = self.server()["revision"]
        for bad in ("-1", "abc", "", "NaN"):
            self.commit("#f-thickness", bad)
            self.assertFalse(self.page.locator(".banner").is_hidden(), bad)
            self.assertEqual(self.page.input_value("#f-thickness"), "0.23", "field reverts")
            self.assertEqual(self.page.get_attribute("#f-thickness", "aria-invalid"), "true")
        self.shot("03-invalid-edit")
        self.assertEqual(self.server()["revision"], r0)
        self.click_element("N1")                       # locally valid but geometrically impossible: the engine must refuse
        self.commit("#f-width", "50")
        self.assertIn("exceeds wall length", self.page.inner_text(".banner"))
        self.assertEqual(self.server()["revision"], r0)
        self.page.click("text=Dismiss"); self.assertTrue(self.page.locator(".banner").is_hidden()); self.assert_clean(expect_http_errors=True)

    def test_undo_redo_via_buttons_and_shortcuts(self):
        self.open(); self.click_element("W2"); self.commit("#f-thickness", "0.5")
        self.assertEqual(self.wall("W2")["thickness"], 0.5)
        self.page.click("button:has-text('Undo')"); self.page.wait_for_timeout(350); self.assertEqual(self.wall("W2")["thickness"], 0.23)
        self.page.click("button:has-text('Redo')"); self.page.wait_for_timeout(350); self.assertEqual(self.wall("W2")["thickness"], 0.5)
        self.page.locator("canvas").focus()
        self.page.keyboard.press("Control+z"); self.page.wait_for_timeout(350); self.assertEqual(self.wall("W2")["thickness"], 0.23)
        self.page.keyboard.press("Control+Shift+z"); self.page.wait_for_timeout(350); self.assertEqual(self.wall("W2")["thickness"], 0.5)
        self.assertEqual(self.page.input_value("#f-thickness"), "0.5"); self.assert_clean()

    def test_delete_selection_and_undo(self):
        self.open(); self.page.click("[data-id=D1]"); self.assertEqual(self.page.inner_text(".right h3"), "Door")
        self.page.locator("canvas").focus(); self.page.keyboard.press("Delete"); self.page.wait_for_timeout(350)
        self.assertEqual(self.wall("W1")["openings"], []); self.assertEqual(self.page.locator("[data-id=D1]").count(), 0)
        self.assertIn("Nothing selected", self.page.inner_text(".right"))
        self.page.click("button:has-text('Undo')"); self.page.wait_for_timeout(350)
        self.assertEqual(len(self.wall("W1")["openings"]), 1); self.assertEqual(self.page.locator("[data-id=D1]").count(), 1); self.assert_clean()

    def test_multi_select_and_escape(self):
        self.open(); self.page.click("[data-id=W1]"); self.page.click("[data-id=W2]", modifiers=["Shift"])
        self.assertIn("2 elements selected", self.page.inner_text(".right"))
        self.page.click("[data-id=W2]", modifiers=["Shift"]); self.assertEqual(self.page.inner_text(".right h3"), "Wall")
        self.page.locator("canvas").focus(); self.page.keyboard.press("Escape"); self.assertIn("Nothing selected", self.page.inner_text(".right"))

    def test_orbit_plan_picking_and_dark_theme(self):
        self.open(); h0 = self.canvas_hash(); box = self.page.locator("canvas").bounding_box()
        self.page.mouse.move(box["x"] + 300, box["y"] + 200); self.page.mouse.down(); self.page.mouse.move(box["x"] + 380, box["y"] + 230, steps=5); self.page.mouse.up()
        self.page.wait_for_timeout(200); self.assertNotEqual(self.canvas_hash(), h0, "orbit changes the image")
        self.assertIn("Nothing selected", self.page.inner_text(".right"), "a drag must not select")
        self.page.click("button:has-text('Plan')"); self.page.wait_for_timeout(250)
        self.assertEqual(self.page.get_attribute("button:has-text('Plan')", "aria-pressed"), "true"); self.shot("04-plan")
        self.click_element("W3"); self.assertEqual(self.page.inner_text(".right h3"), "Wall")
        self.page.mouse.move(box["x"] + 300, box["y"] + 200); self.page.mouse.down(); self.page.mouse.move(box["x"] + 340, box["y"] + 215, steps=4); self.page.mouse.up()
        self.assertEqual(self.page.get_attribute("button:has-text('3D')", "aria-pressed"), "true", "dragging leaves plan view")
        dark = BROWSER.new_context(viewport={"width": 1280, "height": 760}, color_scheme="dark"); pg = dark.new_page()
        pg.goto(f"{BASE}/#token={TOKEN}"); pg.wait_for_selector("[role=treeitem]"); pg.wait_for_timeout(250)
        self.assertEqual(pg.evaluate("getComputedStyle(document.body).backgroundColor"), "rgb(21, 21, 20)")
        pg.screenshot(path=os.path.join(SHOTS, "05-dark.png")); dark.close()

    def test_import_valid_hostile_and_garbage(self):
        self.open(); tmp = tempfile.mkdtemp()
        def upload(name, content):
            p = os.path.join(tmp, name)
            with open(p, "w") as f: f.write(content)
            self.page.set_input_files("input[type=file]", p); self.page.wait_for_timeout(450)
        good = project("Imported Villa"); good["walls"] = good["walls"][:2]
        upload("good.json", json.dumps(good))
        self.assertEqual(self.page.inner_text("header strong"), "Imported Villa"); self.assertEqual(self.server()["project"]["name"], "Imported Villa")
        hostile = project("Hostile"); hostile["walls"][0]["thickness"] = -1
        upload("hostile.json", json.dumps(hostile))
        self.assertIn("thickness must be positive", self.page.inner_text(".banner")); self.assertEqual(self.page.inner_text("header strong"), "Imported Villa")
        upload("garbage.json", "{not json")
        self.assertIn("Could not import garbage.json", self.page.inner_text(".banner"))
        upload("wrapped.archproj", json.dumps({"schema_version": 1, "checksum": "x", "project": project("From File")}))
        self.assertEqual(self.page.inner_text("header strong"), "From File"); self.shot("06-imported")

    def test_wrong_token_then_connect_form(self):
        self.page.goto(f"{BASE}/#token=wrong"); self.page.wait_for_selector(".connect"); self.page.wait_for_timeout(200)
        self.assertIn("rejected", self.page.inner_text(".connect"))
        self.page.fill("#token", TOKEN); self.page.click("button:has-text('Connect')"); self.page.wait_for_selector("[role=treeitem]")
        self.assertEqual(self.page.inner_text("header strong"), "E2E House"); self.assertEqual(self.page.locator("#token").count(), 0)

    def test_hostile_text_is_rendered_inert(self):
        evil = project("<img src=x onerror=\"window.__xss=1\">"); evil["levels"][0]["name"] = "<script>window.__xss=2</script>"; evil["walls"][2]["material"] = "\"><svg onload=window.__xss=3>"
        self.assertEqual(api(BASE, "PUT", "/api/v1/project", {"project": evil})[0], 200)
        self.open(); self.click_element("W3"); self.page.wait_for_timeout(200)
        self.assertIsNone(self.page.evaluate("window.__xss")); self.assertEqual(self.page.locator("img, svg, script:not([src])").count(), 0)
        self.assertEqual(self.page.inner_text("header strong"), "<img src=x onerror=\"window.__xss=1\">")
        self.assertEqual(self.page.input_value("#f-material"), "\"><svg onload=window.__xss=3>"); self.assert_clean()

    def test_concurrent_edit_conflict_is_reported_and_view_reloads(self):
        self.open(); self.click_element("W2")
        api(BASE, "POST", "/api/v1/tools/modify_wall", {"args": {"wall_id": "W2", "thickness": 0.6}})   # another client edits
        self.commit("#f-thickness", "0.4")
        self.assertIn("changed elsewhere", self.page.inner_text(".banner"))
        self.assertEqual(self.wall("W2")["thickness"], 0.6); self.assertEqual(self.page.input_value("#f-thickness"), "0.6"); self.assert_clean(expect_http_errors=True)

    def test_exports_download(self):
        self.open()
        with self.page.expect_download() as d: self.page.click("text=Export DXF")
        with open(d.value.path()) as f: dxf = f.read()
        self.assertTrue(dxf.rstrip().endswith("EOF")); self.assertIn("A-WALL", dxf); self.assertTrue(d.value.suggested_filename.endswith(".dxf"))
        with self.page.expect_download() as d: self.page.click("text=Export OBJ")
        with open(d.value.path()) as f: self.assertIn("\nf ", f.read())

    def test_panels_collapse(self):
        self.open(); self.assertTrue(self.page.locator(".left").is_visible())
        self.page.click("button:has-text('Tree')"); self.assertFalse(self.page.locator(".left").is_visible())
        self.page.click("button:has-text('Inspector')"); self.assertFalse(self.page.locator(".right").is_visible())
        self.assertGreater(self.page.locator("canvas").bounding_box()["width"], 1200)


if __name__ == "__main__":
    unittest.main()
