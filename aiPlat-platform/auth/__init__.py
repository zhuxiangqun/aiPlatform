"""Auth Module - Authentication & Authorization"""

from .authenticator import authenticator, Authenticator, AuthResult

__all__ = ["authenticator", "Authenticator", "AuthResult"]

# Handler registration: platform pushes auth data to CoreFacade
# Direction: platform → core (correct per architecture contract §2.1)
from core.api.core_facade import register_handler
from auth.schemas_policy import ROUTE_PERMISSIONS, METHOD_RESTRICTIONS
register_handler("route_permissions", ROUTE_PERMISSIONS)
register_handler("method_restrictions", METHOD_RESTRICTIONS)