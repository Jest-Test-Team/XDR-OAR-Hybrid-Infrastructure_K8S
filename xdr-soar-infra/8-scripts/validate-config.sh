#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$ROOT_DIR/1-vmware-esxi"
RENDER_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$RENDER_DIR"
}

trap cleanup EXIT

export XDR_SOAR_REQUIRE_PLATFORM_ENV=0
# shellcheck disable=SC1091
source "$SCRIPT_DIR/load-platform-env.sh"

render_manifest() {
  local source_file="$1"
  local rendered_file="$RENDER_DIR/${source_file#"$ROOT_DIR/"}"

  mkdir -p "$(dirname "$rendered_file")"
  envsubst < "$source_file" > "$rendered_file"
  printf '%s\n' "$rendered_file"
}

echo "[$(date)] Validating Terraform formatting..."
if command -v terraform >/dev/null 2>&1; then
  export TF_DATA_DIR="$RENDER_DIR/.terraform"
  terraform -chdir="$TERRAFORM_DIR" fmt -check
  terraform -chdir="$TERRAFORM_DIR" init -backend=false -input=false >/dev/null
  terraform -chdir="$TERRAFORM_DIR" validate
elif command -v docker >/dev/null 2>&1; then
  mkdir -p "$RENDER_DIR/tfdata"
  docker run --rm -e TF_DATA_DIR=/tfdata \
    -v "$TERRAFORM_DIR:/workspace" -v "$RENDER_DIR/tfdata:/tfdata" -w /workspace \
    hashicorp/terraform:1.8.5@sha256:c2de8d7f1919b8e534c4e7cb92c2b327baafd87010d5a3bba036da05caa12db0 fmt -check
  docker run --rm -e TF_DATA_DIR=/tfdata \
    -v "$TERRAFORM_DIR:/workspace" -v "$RENDER_DIR/tfdata:/tfdata" -w /workspace \
    hashicorp/terraform:1.8.5@sha256:c2de8d7f1919b8e534c4e7cb92c2b327baafd87010d5a3bba036da05caa12db0 init -backend=false -input=false >/dev/null
  docker run --rm -e TF_DATA_DIR=/tfdata \
    -v "$TERRAFORM_DIR:/workspace" -v "$RENDER_DIR/tfdata:/tfdata" -w /workspace \
    hashicorp/terraform:1.8.5@sha256:c2de8d7f1919b8e534c4e7cb92c2b327baafd87010d5a3bba036da05caa12db0 validate
else
  echo "[$(date)] Skipping Terraform checks because terraform is not installed."
fi

echo "[$(date)] Validating Python helper and app sources..."
if command -v python3 >/dev/null 2>&1; then
  python3 -m py_compile \
    "$ROOT_DIR/agent_main.py" \
    "$ROOT_DIR/apps/firmware-api/main.py" \
    "$ROOT_DIR/scripts/upload_to_gridfs.py" \
    "$ROOT_DIR/apps/detection-engine/main.py" \
    "$ROOT_DIR/apps/ml-training/main.py" \
    "$ROOT_DIR/apps/yara-scanner/main.py"
else
  echo "[$(date)] Skipping Python checks because python3 is not installed."
fi

echo "[$(date)] Validating Go app sources..."
if command -v gofmt >/dev/null 2>&1; then
  UNFORMATTED_GO="$(gofmt -l "$ROOT_DIR/apps/ingest-gateway/main.go" "$ROOT_DIR/apps/mq-bridge/main.go" "$ROOT_DIR/apps/stream-processor/main.go" || true)"
  if [ -n "$UNFORMATTED_GO" ]; then
    echo "Found unformatted Go sources." >&2
    printf '%s\n' "$UNFORMATTED_GO" >&2
    exit 1
  fi
else
  echo "[$(date)] Skipping Go formatting checks because gofmt is not installed."
fi

echo "[$(date)] Validating shell script syntax..."
while IFS= read -r shell_script; do
  bash -n "$shell_script"
done < <(
  find \
    "$ROOT_DIR/2-kubernetes-cluster" \
    "$ROOT_DIR/8-scripts" \
    -type f -name '*.sh' | sort
)

echo "[$(date)] Validating Kubernetes manifest YAML syntax..."
if command -v ruby >/dev/null 2>&1; then
  while IFS= read -r source_manifest; do
    manifest="$(render_manifest "$source_manifest")"
    ruby -e 'require "yaml"; YAML.load_stream(File.read(ARGV[0]))' "$manifest" >/dev/null
  done < <(
    find \
      "$ROOT_DIR/2-kubernetes-cluster" \
      "$ROOT_DIR/3-k8s-network-policies" \
      "$ROOT_DIR/4-data-layer" \
      "$ROOT_DIR/5-event-plane" \
      "$ROOT_DIR/5-security-engine" \
      "$ROOT_DIR/6-frontend-ui" \
      "$ROOT_DIR/9-observability" \
      -type f \( -name '*.yaml' -o -name '*.yml' \) ! -name 'cilium-values.yaml' | sort
  )
else
  echo "[$(date)] Skipping manifest syntax checks because ruby is not installed."
fi

echo "[$(date)] Checking for stale placeholder values in active manifests and scripts..."
if rg -n 'change-me|anon-key-placeholder|service-role-key-placeholder|xdr-soar\.local' \
  "$ROOT_DIR/2-kubernetes-cluster" \
  "$ROOT_DIR/4-data-layer" \
  "$ROOT_DIR/6-frontend-ui" \
  "$ROOT_DIR/7-windows-agents" \
  "$ROOT_DIR/apps" \
  "$ROOT_DIR/.gitlab-ci.yml" >/dev/null; then
  echo "Found stale placeholder values in active deployment assets." >&2
  rg -n 'change-me|anon-key-placeholder|service-role-key-placeholder|xdr-soar\.local' \
    "$ROOT_DIR/2-kubernetes-cluster" \
    "$ROOT_DIR/4-data-layer" \
    "$ROOT_DIR/6-frontend-ui" \
    "$ROOT_DIR/7-windows-agents" \
    "$ROOT_DIR/apps" \
    "$ROOT_DIR/.gitlab-ci.yml" >&2
  exit 1
fi

echo "[$(date)] Checking for unpinned :latest container images..."
if rg -n 'image: .*:latest' "$ROOT_DIR" -g '*.yaml' -g '*.yml' >/dev/null; then
  echo "Found forbidden :latest image references in Kubernetes manifests." >&2
  rg -n 'image: .*:latest' "$ROOT_DIR" -g '*.yaml' -g '*.yml' >&2
  exit 1
fi

echo "[$(date)] Checking for third-party images missing digests..."
UNPINNED_THIRD_PARTY_IMAGES="$(rg -n 'image:\s*[^[:space:]@]+:[^[:space:]@]+$' "$ROOT_DIR" -g '*.yaml' -g '*.yml' | rg -v 'image:\s*(custom-engine|ml-training|custom-yara|admin-frontend|soar-frontend|firmware-api|ingest-gateway|mq-bridge|stream-processor):' || true)"
if [ -n "$UNPINNED_THIRD_PARTY_IMAGES" ]; then
  echo "Found third-party Kubernetes images without immutable digests." >&2
  printf '%s\n' "$UNPINNED_THIRD_PARTY_IMAGES" >&2
  exit 1
fi

echo "[$(date)] Validation completed."
