#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
./scripts/build.sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover -s tests -v
mkdir -p build
/usr/bin/xcrun swiftc src/SendJob.swift tests/main.swift -o build/model-tests
./build/model-tests
