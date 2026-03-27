#!/usr/bin/env python3

import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from gridfs import GridFS
from pymongo import DESCENDING, MongoClient


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8081"))
MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
MONGO_USERNAME = os.getenv("MONGO_USERNAME", "")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "xdr_soar")
GRIDFS_FILENAME = os.getenv("GRIDFS_FILENAME", "agent.exe")
MONGO_URI = os.getenv(
    "MONGO_URI",
    (
        f"mongodb://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/"
        if MONGO_USERNAME and MONGO_PASSWORD
        else f"mongodb://{MONGO_HOST}:{MONGO_PORT}/"
    ),
)

client = MongoClient(MONGO_URI)
database = client[MONGO_DATABASE]
fs = GridFS(database)

METRICS = {
    "firmware_download_requests_total": 0,
    "firmware_download_not_found_total": 0,
}


def render_metrics() -> str:
    return "\n".join(
        [
            "# HELP firmware_download_requests_total Number of firmware download requests.",
            "# TYPE firmware_download_requests_total counter",
            f"firmware_download_requests_total {METRICS['firmware_download_requests_total']}",
            "# HELP firmware_download_not_found_total Number of firmware downloads that failed lookup.",
            "# TYPE firmware_download_not_found_total counter",
            f"firmware_download_not_found_total {METRICS['firmware_download_not_found_total']}",
        ]
    ) + "\n"


def find_firmware(version: str):
    cursor = fs.find(
        {
            "filename": GRIDFS_FILENAME,
            "metadata.version": version,
        }
    ).sort("uploadDate", DESCENDING)
    return next(cursor, None)


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "FirmwareAPI/1.0"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            body = b'{"status":"ok"}'
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/metrics":
            body = render_metrics().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path.startswith("/v1/firmware/"):
            METRICS["firmware_download_requests_total"] += 1
            version = unquote(self.path.rsplit("/", 1)[-1])
            artifact = find_firmware(version)
            if artifact is None:
                METRICS["firmware_download_not_found_total"] += 1
                body = b'{"error":"firmware not found"}'
                self.send_response(HTTPStatus.NOT_FOUND)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            metadata = artifact.metadata or {}
            content = artifact.read()
            filename = metadata.get("download_name", f"agent-{version}.exe")

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", metadata.get("content_type", "application/octet-stream"))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(content)))
            if metadata.get("sha256"):
                self.send_header("X-Artifact-SHA256", metadata["sha256"])
            self.end_headers()
            self.wfile.write(content)
            return

        body = b'{"error":"not found"}'
        self.send_response(HTTPStatus.NOT_FOUND)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print(f"firmware-api listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
