"""
Re-export from auth.deps for backward compatibility.
All builder router endpoints use require_builder_access / require_admin_access.
"""
from auth.deps import require_auth as require_builder_access
from auth.deps import require_admin as require_admin_access

__all__ = ["require_builder_access", "require_admin_access"]
