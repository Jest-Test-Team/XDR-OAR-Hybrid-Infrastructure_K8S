# Image Pinning Notes

This repo treats `:latest` tags in Kubernetes manifests as invalid. `xdr-soar-infra/8-scripts/validate-config.sh` fails if a manifest introduces a `:latest` image reference.

Verified platform image pins added on 2026-03-27:

- `ghcr.io/supabase/gotrue:v2.183.0@sha256:9e067aef92d24f02ccd4415293cf6cbba23fb1172fc3c2209249ebbbcf3250d0`
  Source: official Supabase GitHub Container Registry package page for `gotrue`
- `ghcr.io/supabase/postgres-meta:v0.93.1@sha256:3b92a6c4e58ce841c79f65201ae3487af84e774e34ecac989684f775eb78f879`
  Source: official Supabase GitHub Container Registry package page for `postgres-meta`
- `ghcr.io/supabase/studio:2025.11.17-sha-6a18e49@sha256:e3afff261e171508e978f182ba53df1f61a3d6e9f6f2ff3c3fb7c42ad99c132f`
  Source: official Supabase GitHub Container Registry package page for `studio`

Remaining versioned third-party images are still tag-pinned rather than digest-pinned. Before production rollout, extend this same verification process to the rest of the stack if you want full registry digest pinning across all vendors.
