#!/usr/bin/env python3

import argparse
import os
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upload an agent binary into MongoDB GridFS.")
    parser.add_argument("artifact", type=Path, help="Path to the built agent binary.")
    parser.add_argument("--mongo-uri", default=os.getenv("MONGO_URI", "mongodb://mongodb.xdr-soar.svc.cluster.local:27017/"))
    parser.add_argument("--database", default=os.getenv("MONGO_DATABASE", "xdr_soar"))
    parser.add_argument("--filename", default=os.getenv("GRIDFS_FILENAME", "agent.exe"))
    parser.add_argument("--version", default=os.getenv("AGENT_VERSION", "latest"))
    parser.add_argument("--sha256", default=os.getenv("AGENT_SHA256", ""))
    parser.add_argument("--content-type", default="application/octet-stream")
    parser.add_argument("--download-name", default="")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.artifact.exists():
        parser.error(f"artifact does not exist: {args.artifact}")

    try:
        from gridfs import GridFS
        from pymongo import MongoClient
    except ImportError:
        print("pymongo is required to upload to GridFS. Install pymongo before running this script.", file=sys.stderr)
        return 1

    client = MongoClient(args.mongo_uri)
    database = client[args.database]
    fs = GridFS(database)

    with args.artifact.open("rb") as handle:
        payload = handle.read()

    sha256 = args.sha256 or __import__("hashlib").sha256(payload).hexdigest()
    download_name = args.download_name or f"agent-{args.version}{args.artifact.suffix or '.bin'}"

    fs.put(
        payload,
        filename=args.filename,
        metadata={
            "version": args.version,
            "sha256": sha256,
            "content_type": args.content_type,
            "download_name": download_name,
        },
    )
    print(f"Uploaded {args.artifact} to GridFS as {args.filename} version={args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
