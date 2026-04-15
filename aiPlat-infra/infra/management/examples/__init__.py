"""
Make infra module importable when running examples from this directory.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

if __name__ == "__main__":
    from usage_example import main
    import asyncio
    asyncio.run(main())