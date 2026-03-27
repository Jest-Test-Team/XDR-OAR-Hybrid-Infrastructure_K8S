# Image Pinning Notes

This repo treats `:latest` tags in Kubernetes manifests as invalid. `xdr-soar-infra/8-scripts/validate-config.sh` fails if a manifest introduces a `:latest` image reference.

As of 2026-03-27, every third-party image in the tracked Kubernetes manifests is pinned to an immutable digest. `validate-config.sh` also fails if a third-party image is left tag-only.

Digest pins sourced from primary registries:

- `ghcr.io/supabase/gotrue:v2.183.0@sha256:9e067aef92d24f02ccd4415293cf6cbba23fb1172fc3c2209249ebbbcf3250d0`
  Source: official Supabase GitHub Container Registry package page for `gotrue`
- `ghcr.io/supabase/postgres-meta:v0.93.1@sha256:3b92a6c4e58ce841c79f65201ae3487af84e774e34ecac989684f775eb78f879`
  Source: official Supabase GitHub Container Registry package page for `postgres-meta`
- `ghcr.io/supabase/studio:2025.11.17-sha-6a18e49@sha256:e3afff261e171508e978f182ba53df1f61a3d6e9f6f2ff3c3fb7c42ad99c132f`
  Source: official Supabase GitHub Container Registry package page for `studio`
- `supabase/postgres:15.1.1.78@sha256:881ac26a02870c6784d9fbec67a6a9c5026905216bbd7dfbfa289ecc48073387`
  Source: Docker Hub tag metadata API for `supabase/postgres:15.1.1.78`
- `postgrest/postgrest:v12.0.2@sha256:79369c0cdf9d7112ed4e327bc1b80156be11575dd66fbda245077a2d13b803bc`
  Source: Docker Hub tag metadata API for `postgrest/postgrest:v12.0.2`
- `kong:2.8.1@sha256:1b53405d8680a09d6f44494b7990bf7da2ea43f84a258c59717d4539abf09f6d`
  Source: Docker Hub tag metadata API for `library/kong:2.8.1`
- `mongo:6.0.14@sha256:35a7e5f80601629494216601b06c759b9f89db8876a47f33a14e4c40b5960efa`
  Source: Docker Hub tag metadata API for `library/mongo:6.0.14`
- `influxdb:2.7.5@sha256:766904dcef641fa1491750b7b3e0dd948b30417f7ef0ac4d3f1d6ffed52a1fa2`
  Source: Docker Hub tag metadata API for `library/influxdb:2.7.5`
- `redis:7.2.4-alpine@sha256:c8bb255c3559b3e458766db810aa7b3c7af1235b204cfdb304e79ff388fe1a5a`
  Source: Docker Hub tag metadata API for `library/redis:7.2.4-alpine`
- `confluentinc/cp-kafka:7.6.0@sha256:24cdd3a7fa89d2bed150560ebea81ff1943badfa61e51d66bb541a6b0d7fb047`
  Source: Docker Hub tag metadata API for `confluentinc/cp-kafka:7.6.0`
- `emqx/emqx:5.5.0@sha256:d5703ac4b6cdba024657428661a6334fa4807705286036634ab8ccb73f3e1aef`
  Source: Docker Hub tag metadata API for `emqx/emqx:5.5.0`
- `prom/prometheus:v2.45.0@sha256:9309deb7c981e8a94584d9ed689fd62f7ac4549d816fd3881550311cf056a237`
  Source: Docker Hub tag metadata API for `prom/prometheus:v2.45.0`
- `grafana/loki:2.9.6@sha256:6ca6e2cd3b6f45e0eb298da2920610fde63ecd8ab6c595d9c941c8559d1d9407`
  Source: Docker Hub tag metadata API for `grafana/loki:2.9.6`
- `grafana/grafana:10.4.2@sha256:7d5faae481a4c6f436c99e98af11534f7fd5e8d3e35213552dd1dd02bc393d2e`
  Source: Docker Hub tag metadata API for `grafana/grafana:10.4.2`
- `grafana/promtail:2.9.6@sha256:c0e57ee03512475e982893622544d76da4e3c3671a72425c670ccfc0024a4187`
  Source: Docker Hub tag metadata API for `grafana/promtail:2.9.6`
- `nvcr.io/nvidia/tritonserver:24.01-py3@sha256:3380720761045fc16ba3bcb96cfa54034531fc302df54ecac6b2a4deeab07bbd`
  Source: NVIDIA NGC container catalog tag metadata for `tritonserver:24.01-py3`
