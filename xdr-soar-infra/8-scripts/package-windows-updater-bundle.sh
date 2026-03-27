#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
BUNDLE_DIR="${1:-$ROOT_DIR/.generated/windows-updater-bundle}"
ZIP_PATH="${2:-$ROOT_DIR/.generated/windows-updater-bundle.zip}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to package the Windows updater bundle." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$SCRIPT_DIR/load-platform-env.sh"
"$SCRIPT_DIR/generate-updater-config.sh" "$ROOT_DIR/.generated/updater-config.json" >/dev/null
"$SCRIPT_DIR/generate-tls-assets.sh" >/dev/null

rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"

cp "$ROOT_DIR/7-windows-agents/mqtt-pull-updater.ps1" "$BUNDLE_DIR/"
cp "$ROOT_DIR/7-windows-agents/install-updater-bundle.ps1" "$BUNDLE_DIR/"
cp "$ROOT_DIR/.generated/updater-config.json" "$BUNDLE_DIR/updater-config.json"
cp "$ROOT_DIR/.generated/tls/ca.crt" "$BUNDLE_DIR/ca.crt"

cat > "$BUNDLE_DIR/README.txt" <<EOF
XDR/SOAR Windows updater bundle

Files:
- mqtt-pull-updater.ps1: persistent MQTT listener and binary updater
- install-updater-bundle.ps1: installs the updater, config, root CA, and scheduled task
- updater-config.json: generated broker/API/settings payload for this environment
- ca.crt: bootstrap CA certificate used to validate the MQTT TLS endpoint

Run install-updater-bundle.ps1 from an elevated PowerShell session on the Windows agent host.
EOF

ZIP_PATH="$ZIP_PATH" BUNDLE_DIR="$BUNDLE_DIR" python3 - <<'PY'
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

bundle_dir = Path(os.environ["BUNDLE_DIR"])
zip_path = Path(os.environ["ZIP_PATH"])
zip_path.parent.mkdir(parents=True, exist_ok=True)

with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
    for path in sorted(bundle_dir.rglob("*")):
        if path.is_file():
            zf.write(path, path.relative_to(bundle_dir))
PY

echo "[$(date)] Packaged Windows updater bundle at $ZIP_PATH"
