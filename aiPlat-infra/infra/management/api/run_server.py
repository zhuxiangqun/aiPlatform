#!/usr/bin/env python3
"""
Run aiPlat-infra API Server

This script starts the infrastructure layer API server.
"""

import argparse
import uvicorn


def main():
    """Run the aiPlat-infra API server."""
    parser = argparse.ArgumentParser(description="aiPlat-infra API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print("  aiPlat-infra - Infrastructure Layer API")
    print(f"{'='*60}")
    print(f"  Version: 0.1.0")
    print(f"  Server: http://{args.host}:{args.port}")
    print(f"  API Docs: http://{args.host}:{args.port}/docs")
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