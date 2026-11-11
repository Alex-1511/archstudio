# CAD / Geometry Architecture
**Now:** 2D primitives (area, perimeter, containment, wall footprints, point-along) in `geometry.py`, tested incl. winding independence.
**3D now (`solids.py`):** walls become closed, consistently oriented triangle meshes (segments, sills, heads around openings); total volume equals the wall's quantity. This is a mesh foundation for viewport and checks, not a B-rep kernel.
**Polygon validation:** rooms must be finite, non-degenerate, simple polygons.
**Decision:** do not write a kernel. Use **Open CASCADE** for solids/booleans/sweeps/lofts, mesh libs for tessellation. Our code owns the *architectural object layer* (wall/door/window/roof… with parameters and constraints) that drives the kernel.
**Parametric layer (Phase 4):** a typed node graph (DAG) evaluated deterministically; nodes call the same tools/kernel; graph is saved in the project; recompute on parameter change with dependency tracking.
**Precision:** model units are metres, float64; tolerances explicit (`1e-9` today); drawings preserve supplied dimensions.
