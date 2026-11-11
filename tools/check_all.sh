#!/bin/sh
# Runs every verification layer that can run on this machine and prints a summary.
# Optional env: TSC (default: tsc), TSC_FLAGS (e.g. "--typeRoots /path/to/@types"), ESBUILD (path to esbuild).
cd "$(dirname "$0")/.." || exit 1
TSC="${TSC:-tsc}"; FAIL=0
step() { printf '\n== %s ==\n' "$1"; shift; if "$@"; then echo "PASS"; else echo "FAIL"; FAIL=1; fi; }

step "Python engine + API tests"        sh -c 'cd services/core && python3 -W error::ResourceWarning -m unittest discover -s tests 2>&1 | tail -4 && python3 -m unittest discover -s tests >/dev/null 2>&1'
step "app-core strict type-check"       sh -c "cd packages/app-core && $TSC -p tsconfig.json $TSC_FLAGS"
step "web-lite strict type-check"       sh -c "cd apps/web-lite && $TSC -p tsconfig.json"
step "app-core unit + cross-language integration tests" sh -c 'cd packages/app-core && node --test test/*.test.ts 2>&1 | grep -E "^# (tests|pass|fail)" && node --test test/*.test.ts >/dev/null 2>&1'
step "browser end-to-end (Playwright)"  sh -c 'python3 -m unittest discover -s apps/web-lite/e2e 2>&1 | tail -4 && python3 -m unittest discover -s apps/web-lite/e2e >/dev/null 2>&1'
echo; echo "NOT checked here: apps/web (Next.js + Three.js) needs 'npm install' and has never been built or run."
[ "$FAIL" = 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"; exit "$FAIL"
