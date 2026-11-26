"""Auth pipeline events and triggers for the Actions runtime.

An Auth0 Action runs at a fixed point ("trigger") in the login / token
pipeline: before a user is registered, after login, before a token is
issued, and so on. Each trigger carries a typed event object; the action
may read it, add claims, deny the flow, or redirect the user.
"""

from dataclasses import dataclass, field
from enum import Enum


class Trigger(str, Enum):
    PRE_USER_REGISTRATION = "pre-user-registration"
    POST_LOGIN = "post-login"
    PRE_TOKEN_ISSUANCE = "pre-token-issuance"
    POST_CHANGE_PASSWORD = "post-change-password"
    SEND_PHONE_MESSAGE = "send-phone-message"


# Triggers where an action error must fail the flow closed (deny) rather
# than let the login/token proceed without the action having run.
FAIL_CLOSED_TRIGGERS = frozenset(
    {Trigger.PRE_USER_REGISTRATION, Trigger.PRE_TOKEN_ISSUANCE}
)

# Maximum size of a single claim value, in characters. Keeps one tenant's
# action from bloating tokens for every other tenant on the platform.
MAX_CLAIM_VALUE_CHARS = 512


@dataclass
class AuthEvent:
    """One invocation of the auth pipeline for one tenant's user."""

    tenant_id: str
    user_id: str
    connection: str  # e.g. "Username-Password-Authentication", "google-oauth2"
    trigger: Trigger
    claims: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)

    def clone(self) -> "AuthEvent":
        return AuthEvent(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            connection=self.connection,
            trigger=self.trigger,
            claims=dict(self.claims),
            context=dict(self.context),
        )
