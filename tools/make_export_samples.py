"""Write sample exports for manual verification in real software (see docs/EXPORT_VERIFICATION.md).
Run from repo root:  python3 tools/make_export_samples.py  ->  ./export_samples/"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "core"))
from archcore.bim import Project
from archcore.export import export_dxf, export_obj

p = Project("Export Sample"); lv = p.add_level("Ground", 0.0, 3.0)
pts = [(0, 0), (10, 0), (10, 8), (0, 8)]
ws = [p.add_wall(lv.id, pts[i], pts[(i + 1) % 4], 0.23, material="brick") for i in range(4)]
p.add_opening(ws[0].id, "door", 1.0, 0.9, 2.1)
p.add_opening(ws[1].id, "window", 2.0, 1.5, 1.2, sill=0.9)
p.add_room("Living", lv.id, pts, target_area=80)
os.makedirs("export_samples", exist_ok=True)
open("export_samples/sample.dxf", "w").write(export_dxf(p, lv.id))
open("export_samples/sample.obj", "w").write(export_obj(p, lv.id))
print("wrote export_samples/sample.dxf and sample.obj")
