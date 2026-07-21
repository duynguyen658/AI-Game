import pytest
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.constants import UserRole
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.service.auth_service import AuthService, AuthenticatedActor
import app.service.auth_service as auth_module


def test_system_and_agent_cannot_self_approve_actions() -> None:
    service = AuthService()
    with pytest.raises(AuthorizationError):
        service.require_action_approval(
            AuthenticatedActor(actor_id="system", role=UserRole.SYSTEM),
            UserRole.REVIEWER.value,
            "CONTENT_REVIEWER",
        )
    with pytest.raises(AuthorizationError):
        service.require_action_approval(
            AuthenticatedActor(actor_id="agent:CONTENT_REVIEWER", role=UserRole.ADMIN),
            UserRole.REVIEWER.value,
            "CONTENT_REVIEWER",
        )


def test_action_approval_role_hierarchy() -> None:
    service = AuthService()
    service.require_action_approval(
        AuthenticatedActor(actor_id="manager", role=UserRole.MANAGER),
        UserRole.REVIEWER.value,
        "CONTENT_REVIEWER",
    )
    with pytest.raises(AuthorizationError):
        service.require_action_approval(
            AuthenticatedActor(actor_id="reviewer", role=UserRole.REVIEWER),
            UserRole.MANAGER.value,
            "CONTENT_REVIEWER",
        )


def test_jwt_issuer_and_audience_are_verified() -> None:
    service = AuthService()
    service.settings = service.settings.model_copy(
        update={"jwt_issuer": "cyber-legends", "jwt_audience": "operators"}
    )
    token = jwt.encode(
        {
            "sub": "manager-1",
            "role": UserRole.MANAGER.value,
            "iss": "cyber-legends",
            "aud": "operators",
        },
        service.settings.jwt_secret_key.get_secret_value(),
        algorithm=service.settings.jwt_algorithm,
    )
    actor = service.decode_bearer_token(token)
    assert actor == AuthenticatedActor("manager-1", UserRole.MANAGER)

    invalid = jwt.encode(
        {
            "sub": "manager-1",
            "role": UserRole.MANAGER.value,
            "iss": "cyber-legends",
            "aud": "wrong-audience",
        },
        service.settings.jwt_secret_key.get_secret_value(),
        algorithm=service.settings.jwt_algorithm,
    )
    with pytest.raises(AuthenticationError):
        service.decode_bearer_token(invalid)


def test_oidc_jwks_key_and_configured_role_claim_are_used(monkeypatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    class SigningKey:
        key = public_key

    class JwksClient:
        def get_signing_key_from_jwt(self, _: str) -> SigningKey:
            return SigningKey()

    monkeypatch.setattr(auth_module, "_jwks_client", lambda _: JwksClient())
    service = AuthService()
    service.settings = service.settings.model_copy(
        update={
            "jwt_algorithm": "RS256",
            "jwt_issuer": "https://issuer.example",
            "jwt_audience": "cyber-legends-api",
            "jwt_jwks_url": "https://issuer.example/jwks",
            "jwt_role_claim": "app_role",
        }
    )
    token = jwt.encode(
        {
            "sub": "oidc-manager",
            "app_role": UserRole.MANAGER.value,
            "iss": "https://issuer.example",
            "aud": "cyber-legends-api",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    assert service.decode_bearer_token(token) == AuthenticatedActor(
        "oidc-manager", UserRole.MANAGER
    )
