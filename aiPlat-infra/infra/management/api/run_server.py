#!/usr/bin/env python3
"""
Run Infra Management API Server

This script starts the infrastructure layer API server.
"""

import os
import sys
import argparse
import uvicorn

from infra.management.api.auth import infra_api_token, is_loopback_host


def main():
    """Run the infra management API server."""
    name = os.getenv("AIPLAT_INFRA_API_NAME", "infra")
    parser = argparse.ArgumentParser(description=f"{name} Management API Server")
    parser.add_argument(
        "--host",
        default=os.getenv("AIPLAT_INFRA_API_HOST", "127.0.0.1"),
        help="Host to bind to (default 127.0.0.1; non-loopback requires AIPLAT_INFRA_API_TOKEN)",
    )
    parser.add_argument("--port", type=int, default=int(os.getenv("AIPLAT_INFRA_API_PORT", "8001") or "8001"), help="Port to bind to")
    args = parser.parse_args()

    if not is_loopback_host(args.host) and not infra_api_token():
        print(
            "Refusing to bind non-loopback without AIPLAT_INFRA_API_TOKEN "
            f"(host={args.host!r}). Set the token or bind 127.0.0.1.",
            file=sys.stderr,
        )
        sys.exit(2)
    
    print(f"\n{'='*60}")
    print(f"  {name} - Infrastructure Layer API")
    print(f"{'='*60}")
    print(f"  Version: 0.1.0")
    print(f"  Server: http://{args.host}:{args.port}")
    print(f"  API Docs: http://{args.host}:{args.port}/docs")
    print(f"  Auth: {'token required' if infra_api_token() else 'loopback only (no token)'}")
    print(f"{'='*60}\n")
    
    uvicorn.run(
        "infra.management.api.main:create_app",
        host=args.host,
        port=args.port,
        reload=False,
        factory=True,
    )


if __name__ == "__main__":
    main()
