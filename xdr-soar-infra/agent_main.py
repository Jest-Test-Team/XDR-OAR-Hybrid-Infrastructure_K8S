#!/usr/bin/env python3

import json
import platform
import socket
from datetime import datetime, timezone


def main() -> None:
    payload = {
        "service": "watchdog-agent",
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "reported_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
