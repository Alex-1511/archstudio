"""Dev server:  python3 run_server.py [--port 8765] [--origin http://localhost:3000]
Prints the bearer token on startup (paste it into the web UI). Token may be fixed via ARCH_API_TOKEN."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archcore.api import make_server

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8765)
ap.add_argument("--origin", default="http://localhost:3000")
ap.add_argument("--static", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "apps", "web-lite", "dist"),
                help="directory of built web client to serve at / (skipped if missing)")
a = ap.parse_args()
static = a.static if os.path.isdir(a.static) else None
srv = make_server("127.0.0.1", a.port, os.environ.get("ARCH_API_TOKEN"), a.origin, static_dir=static)
port = srv.server_address[1]
print(json.dumps({"event": "listening", "port": port, "token": srv.token,  # type: ignore[attr-defined]
                  "url": f"http://127.0.0.1:{port}/#token={srv.token}" if static else None}), flush=True)  # type: ignore[attr-defined]
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass
