# ArchStudio (working name)
Version 0.4.0. Quick start: `python3 services/core/run_server.py`, open the printed URL. Verify everything: `sh tools/check_all.sh` (see `docs/WEB_CLIENT.md` for what is and is not tested). Manual export checks: `docs/EXPORT_VERIFICATION.md`. Run tests: `cd services/core && python3 -m unittest discover -s tests -v` (Python 3.12, no dependencies).
Docs: see `docs/`. Gemini: set `GEMINI_MODEL` and `GEMINI_API_KEY` in the server environment (never in frontend code).
