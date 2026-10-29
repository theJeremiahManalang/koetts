"""Independent service and Firebase user verification for the private HTTP API."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from fastapi import HTTPException, Request

_FIREBASE_APP_LOCK = threading.Lock()
MAX_CREDENTIAL_BYTES = 16 * 1024


def _valid_credential(value: str) -> bool:
    return 0 < len(value) <= MAX_CREDENTIAL_BYTES and all(32 < ord(character) < 127 for character in value)


@dataclass(frozen=True)
class BoundaryConfig:
    project_id: str
    audience: str
    permissions: Mapping[str, frozenset[str]]
    mode: str = "verification"

    def __post_init__(self):
        if (not isinstance(self.project_id, str) or not self.project_id.strip() or self.project_id != self.project_id.strip()
                or not isinstance(self.audience, str) or not self.audience.strip() or self.audience != self.audience.strip()
                or not isinstance(self.mode, str) or self.mode not in {"verification", "local", "cloud"}):
            raise ValueError("Explicit project, audience and valid API mode required")
        if not isinstance(self.permissions, Mapping) or any(
            not isinstance(subject, str) or not subject or not isinstance(actions, frozenset)
            or any(not isinstance(action, str) or not action for action in actions)
            for subject, actions in self.permissions.items()
        ):
            raise ValueError("Invalid service permissions")
        object.__setattr__(self, "permissions", MappingProxyType(dict(self.permissions)))

    @classmethod
    def from_environment(cls):
        permissions = json.loads(os.environ.get("S3_SERVICE_PERMISSIONS", "{}"))
        if not isinstance(permissions, dict) or any(
            not isinstance(subject, str)
            or not subject
            or not isinstance(actions, list)
            or any(not isinstance(action, str) for action in actions)
            for subject, actions in permissions.items()
        ):
            raise ValueError("Invalid service permissions")
        return cls(
            os.environ.get("S3_PROJECT_ID", ""),
            os.environ.get("S3_SERVICE_AUDIENCE", ""),
            {subject: frozenset(actions) for subject, actions in permissions.items()},
            os.environ.get("S3_API_MODE", "verification"),
        )


class CredentialBoundary:
    def __init__(
        self,
        config: BoundaryConfig,
        service_verifier: Callable | None = None,
        user_verifier: Callable | None = None,
    ):
        if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
            raise ValueError("Authentication emulator is unsupported by this boundary")
        self.config = config
        self.service_verifier = service_verifier or self._verify_service
        self.user_verifier = user_verifier or self._verify_user

    def _verify_service(self, token):
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token

        return id_token.verify_oauth2_token(
            token, GoogleRequest(), audience=self.config.audience
        )

    def _verify_user(self, token, session):
        import firebase_admin
        from firebase_admin import auth

        name = f"s3-{self.config.project_id}"
        with _FIREBASE_APP_LOCK:
            try:
                app = firebase_admin.get_app(name)
            except ValueError:
                app = firebase_admin.initialize_app(
                    options={"projectId": self.config.project_id}, name=name
                )
        verifier = auth.verify_session_cookie if session else auth.verify_id_token
        return verifier(token, app=app, check_revoked=True)

    def authorize(self, request: Request, action: str, *, user=True, admin=True):
        authorization = request.headers.getlist("authorization")
        if len(authorization) != 1:
            raise HTTPException(401, "Service credential required")
        scheme, separator, token = authorization[0].partition(" ")
        if not separator or scheme.lower() != "bearer" or not _valid_credential(token):
            raise HTTPException(401, "Service credential required")
        try:
            claims = self.service_verifier(token)
            subject = claims.get("sub")
            if (
                not isinstance(subject, str)
                or not subject
                or claims.get("iss")
                not in {"accounts.google.com", "https://accounts.google.com"}
                or claims.get("aud") != self.config.audience
            ):
                raise ValueError("Invalid service claims")
        except Exception:  # noqa: BLE001 - Credential SDK errors must fail closed without leaking details.
            raise HTTPException(401, "Invalid service credential") from None
        if action not in self.config.permissions.get(subject, frozenset()):
            raise HTTPException(403, "Service action denied")
        if not user:
            return None
        tokens = request.headers.getlist("x-koetts-user-token")
        sessions = request.headers.getlist("x-koetts-session-cookie")
        if len(tokens) + len(sessions) != 1 or not _valid_credential((tokens or sessions)[0]):
            raise HTTPException(401, "Exactly one user credential required")
        try:
            principal = self.user_verifier((tokens or sessions)[0], bool(sessions))
            issuer = (
                "https://session.firebase.google.com/"
                if sessions
                else "https://securetoken.google.com/"
            )
            uid = principal.get("sub")
            if (
                principal.get("aud") != self.config.project_id
                or principal.get("iss") != issuer + self.config.project_id
                or not isinstance(uid, str)
                or not uid
            ):
                raise ValueError("Invalid user claims")
        except Exception:  # noqa: BLE001 - Credential SDK errors must fail closed without leaking details.
            raise HTTPException(401, "Invalid user credential") from None
        if admin and principal.get("admin") is not True:
            raise HTTPException(403, "Administrator required")
        return {"kind": "firebase", "uid": uid, "project_id": self.config.project_id}
