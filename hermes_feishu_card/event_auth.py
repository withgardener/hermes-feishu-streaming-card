from __future__ import annotations

import hashlib
import hmac
from ipaddress import ip_address
import secrets
import threading
import time
import re
from collections.abc import Mapping
from typing import Callable


EVENT_TIMESTAMP_HEADER = "X-HFC-Event-Timestamp"
EVENT_NONCE_HEADER = "X-HFC-Event-Nonce"
EVENT_SIGNATURE_HEADER = "X-HFC-Event-Signature"
POLICY_TIMESTAMP_HEADER = "X-HFC-Policy-Timestamp"
POLICY_NONCE_HEADER = "X-HFC-Policy-Nonce"
POLICY_SIGNATURE_HEADER = "X-HFC-Policy-Signature"
NATIVE_HANDOFF_ACK_TIMESTAMP_HEADER = "X-HFC-Native-Ack-Timestamp"
NATIVE_HANDOFF_ACK_NONCE_HEADER = "X-HFC-Native-Ack-Nonce"
NATIVE_HANDOFF_ACK_SIGNATURE_HEADER = "X-HFC-Native-Ack-Signature"
NATIVE_HANDOFF_RECOVERY_TIMESTAMP_HEADER = "X-HFC-Native-Recovery-Timestamp"
NATIVE_HANDOFF_RECOVERY_NONCE_HEADER = "X-HFC-Native-Recovery-Nonce"
NATIVE_HANDOFF_RECOVERY_SIGNATURE_HEADER = "X-HFC-Native-Recovery-Signature"
SIDECAR_REQUEST_TIMESTAMP_HEADER = "X-HFC-Sidecar-Timestamp"
SIDECAR_REQUEST_NONCE_HEADER = "X-HFC-Sidecar-Nonce"
SIDECAR_REQUEST_SIGNATURE_HEADER = "X-HFC-Sidecar-Signature"
RUNTIME_INTERACTION_TIMESTAMP_HEADER = "X-HFC-Runtime-Interaction-Timestamp"
RUNTIME_INTERACTION_NONCE_HEADER = "X-HFC-Runtime-Interaction-Nonce"
RUNTIME_INTERACTION_SIGNATURE_HEADER = "X-HFC-Runtime-Interaction-Signature"
RUNTIME_INTERACTION_PATH = "/runtime/interactions/resolve"

_ROOT_SECRET_BYTES = 32
_PROOF_MAX_AGE_SECONDS = 30
_POLICY_PROOF_MAX_AGE_SECONDS = 5
_EVENT_MAX_NONCES = 16_384
_POLICY_MAX_NONCES = 512
_NATIVE_HANDOFF_CONTROL_MAX_NONCES = 512
_SIDECAR_REQUEST_MAX_NONCES = 16_384
_RUNTIME_INTERACTION_MAX_NONCES = 1024
_RUNTIME_INTERACTION_NONCE_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")
_LOWER_HEX_64_RE = re.compile(r"[0-9a-f]{64}")


class EventAuthenticationError(ValueError):
    pass


class PolicyAuthenticationError(ValueError):
    pass


class NativeHandoffAckAuthenticationError(ValueError):
    pass


class NativeHandoffRecoveryAuthenticationError(ValueError):
    pass


class SidecarRequestAuthenticationError(ValueError):
    pass


class RuntimeInteractionAuthenticationError(ValueError):
    pass


def sign_event_request(
    secret: bytes,
    body: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    return _sign_domain_request(
        secret,
        body,
        domain="hfc-event-v1",
        timestamp_header=EVENT_TIMESTAMP_HEADER,
        nonce_header=EVENT_NONCE_HEADER,
        signature_header=EVENT_SIGNATURE_HEADER,
        timestamp=timestamp,
        nonce=nonce,
        label="event",
    )


def sign_policy_request(
    secret: bytes,
    body: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    return _sign_domain_request(
        secret,
        body,
        domain="hfc-policy-v1",
        timestamp_header=POLICY_TIMESTAMP_HEADER,
        nonce_header=POLICY_NONCE_HEADER,
        signature_header=POLICY_SIGNATURE_HEADER,
        timestamp=timestamp,
        nonce=nonce,
        label="policy",
    )


def sign_native_handoff_ack_request(
    secret: bytes,
    body: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    return _sign_domain_request(
        secret,
        body,
        domain="hfc-native-handoff-ack-v1",
        timestamp_header=NATIVE_HANDOFF_ACK_TIMESTAMP_HEADER,
        nonce_header=NATIVE_HANDOFF_ACK_NONCE_HEADER,
        signature_header=NATIVE_HANDOFF_ACK_SIGNATURE_HEADER,
        timestamp=timestamp,
        nonce=nonce,
        label="native handoff ack",
    )


def sign_native_handoff_recovery_request(
    secret: bytes,
    body: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    return _sign_domain_request(
        secret,
        body,
        domain="hfc-native-handoff-recovery-v2",
        timestamp_header=NATIVE_HANDOFF_RECOVERY_TIMESTAMP_HEADER,
        nonce_header=NATIVE_HANDOFF_RECOVERY_NONCE_HEADER,
        signature_header=NATIVE_HANDOFF_RECOVERY_SIGNATURE_HEADER,
        timestamp=timestamp,
        nonce=nonce,
        label="native handoff recovery",
    )


def sign_sidecar_request(
    secret: bytes,
    method: str,
    path: str,
    body: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    return _sign_domain_request(
        secret,
        _sidecar_request_payload(method, path, body),
        domain="hfc-sidecar-request-v1",
        timestamp_header=SIDECAR_REQUEST_TIMESTAMP_HEADER,
        nonce_header=SIDECAR_REQUEST_NONCE_HEADER,
        signature_header=SIDECAR_REQUEST_SIGNATURE_HEADER,
        timestamp=timestamp,
        nonce=nonce,
        label="sidecar request",
    )


def sign_runtime_interaction_request(
    secret: bytes,
    path: str,
    body: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Sign one exact process-local interaction resolution request."""
    if type(path) is not str or path != RUNTIME_INTERACTION_PATH:
        raise ValueError("runtime interaction target is invalid")
    if type(body) is not bytes:
        raise ValueError("runtime interaction request body must be bytes")
    if timestamp is not None and type(timestamp) is not int:
        raise ValueError("runtime interaction proof metadata is invalid")
    if (
        nonce is not None
        and (
            type(nonce) is not str
            or _RUNTIME_INTERACTION_NONCE_RE.fullmatch(nonce) is None
        )
    ):
        raise ValueError("runtime interaction proof metadata is invalid")
    return _sign_domain_request(
        secret,
        _runtime_interaction_payload(path, body),
        domain="hfc-runtime-interaction-callback-v1",
        timestamp_header=RUNTIME_INTERACTION_TIMESTAMP_HEADER,
        nonce_header=RUNTIME_INTERACTION_NONCE_HEADER,
        signature_header=RUNTIME_INTERACTION_SIGNATURE_HEADER,
        timestamp=timestamp,
        nonce=nonce,
        label="runtime interaction",
    )


class EventProofVerifier:
    def __init__(
        self,
        secret: bytes,
        *,
        now: Callable[[], float] = time.time,
        max_nonces: int = _EVENT_MAX_NONCES,
    ):
        self._verifier = _DomainProofVerifier(
            secret,
            domain="hfc-event-v1",
            timestamp_header=EVENT_TIMESTAMP_HEADER,
            nonce_header=EVENT_NONCE_HEADER,
            signature_header=EVENT_SIGNATURE_HEADER,
            max_age_seconds=_PROOF_MAX_AGE_SECONDS,
            error_type=EventAuthenticationError,
            now=now,
            max_nonces=max_nonces,
        )

    def verify(self, headers: Mapping[str, str], body: bytes) -> None:
        self._verifier.verify(headers, body)


class PolicyProofVerifier:
    def __init__(
        self,
        secret: bytes,
        *,
        now: Callable[[], float] = time.time,
        max_nonces: int = _POLICY_MAX_NONCES,
    ):
        self._verifier = _DomainProofVerifier(
            secret,
            domain="hfc-policy-v1",
            timestamp_header=POLICY_TIMESTAMP_HEADER,
            nonce_header=POLICY_NONCE_HEADER,
            signature_header=POLICY_SIGNATURE_HEADER,
            max_age_seconds=_POLICY_PROOF_MAX_AGE_SECONDS,
            error_type=PolicyAuthenticationError,
            now=now,
            max_nonces=max_nonces,
        )

    def verify(self, headers: Mapping[str, str], body: bytes) -> None:
        self._verifier.verify(headers, body)


class NativeHandoffAckProofVerifier:
    def __init__(
        self,
        secret: bytes,
        *,
        now: Callable[[], float] = time.time,
        max_nonces: int = _NATIVE_HANDOFF_CONTROL_MAX_NONCES,
    ):
        self._verifier = _DomainProofVerifier(
            secret,
            domain="hfc-native-handoff-ack-v1",
            timestamp_header=NATIVE_HANDOFF_ACK_TIMESTAMP_HEADER,
            nonce_header=NATIVE_HANDOFF_ACK_NONCE_HEADER,
            signature_header=NATIVE_HANDOFF_ACK_SIGNATURE_HEADER,
            max_age_seconds=_PROOF_MAX_AGE_SECONDS,
            error_type=NativeHandoffAckAuthenticationError,
            now=now,
            max_nonces=max_nonces,
        )

    def verify(self, headers: Mapping[str, str], body: bytes) -> None:
        self._verifier.verify(headers, body)


class NativeHandoffRecoveryProofVerifier:
    def __init__(
        self,
        secret: bytes,
        *,
        now: Callable[[], float] = time.time,
        max_nonces: int = _NATIVE_HANDOFF_CONTROL_MAX_NONCES,
    ):
        self._verifier = _DomainProofVerifier(
            secret,
            domain="hfc-native-handoff-recovery-v2",
            timestamp_header=NATIVE_HANDOFF_RECOVERY_TIMESTAMP_HEADER,
            nonce_header=NATIVE_HANDOFF_RECOVERY_NONCE_HEADER,
            signature_header=NATIVE_HANDOFF_RECOVERY_SIGNATURE_HEADER,
            max_age_seconds=_PROOF_MAX_AGE_SECONDS,
            error_type=NativeHandoffRecoveryAuthenticationError,
            now=now,
            max_nonces=max_nonces,
        )

    def verify(self, headers: Mapping[str, str], body: bytes) -> None:
        self._verifier.verify(headers, body)


class SidecarRequestProofVerifier:
    def __init__(
        self,
        secret: bytes,
        *,
        now: Callable[[], float] = time.time,
        max_nonces: int = _SIDECAR_REQUEST_MAX_NONCES,
    ):
        self._verifier = _DomainProofVerifier(
            secret,
            domain="hfc-sidecar-request-v1",
            timestamp_header=SIDECAR_REQUEST_TIMESTAMP_HEADER,
            nonce_header=SIDECAR_REQUEST_NONCE_HEADER,
            signature_header=SIDECAR_REQUEST_SIGNATURE_HEADER,
            max_age_seconds=_PROOF_MAX_AGE_SECONDS,
            error_type=SidecarRequestAuthenticationError,
            now=now,
            max_nonces=max_nonces,
        )

    def verify(
        self,
        headers: Mapping[str, str],
        method: str,
        path: str,
        body: bytes,
    ) -> None:
        try:
            payload = _sidecar_request_payload(method, path, body)
        except ValueError as exc:
            raise SidecarRequestAuthenticationError(
                "invalid sidecar-request proof"
            ) from exc
        self._verifier.verify(headers, payload)


class RuntimeInteractionProofVerifier:
    def __init__(
        self,
        secret: bytes,
        *,
        now: Callable[[], float] = time.time,
        max_nonces: int = _RUNTIME_INTERACTION_MAX_NONCES,
    ) -> None:
        self._verifier = _DomainProofVerifier(
            secret,
            domain="hfc-runtime-interaction-callback-v1",
            timestamp_header=RUNTIME_INTERACTION_TIMESTAMP_HEADER,
            nonce_header=RUNTIME_INTERACTION_NONCE_HEADER,
            signature_header=RUNTIME_INTERACTION_SIGNATURE_HEADER,
            max_age_seconds=_PROOF_MAX_AGE_SECONDS,
            error_type=RuntimeInteractionAuthenticationError,
            now=now,
            max_nonces=max_nonces,
        )

    def verify(
        self,
        headers: Mapping[str, str],
        path: str,
        body: bytes,
    ) -> None:
        timestamp_text = _header_value(headers, RUNTIME_INTERACTION_TIMESTAMP_HEADER)
        nonce = _header_value(headers, RUNTIME_INTERACTION_NONCE_HEADER)
        signature = _header_value(headers, RUNTIME_INTERACTION_SIGNATURE_HEADER)
        if (
            type(timestamp_text) is not str
            or not timestamp_text.isascii()
            or not timestamp_text.isdecimal()
            or str(int(timestamp_text)) != timestamp_text
            or type(nonce) is not str
            or _RUNTIME_INTERACTION_NONCE_RE.fullmatch(nonce) is None
            or type(signature) is not str
            or _LOWER_HEX_64_RE.fullmatch(signature) is None
        ):
            raise RuntimeInteractionAuthenticationError(
                "invalid runtime interaction proof"
            )
        try:
            payload = _runtime_interaction_payload(path, body)
        except ValueError as exc:
            raise RuntimeInteractionAuthenticationError(
                "invalid runtime interaction proof"
            ) from exc
        self._verifier.verify(headers, payload)


def _sign_domain_request(
    secret: bytes,
    body: bytes,
    *,
    domain: str,
    timestamp_header: str,
    nonce_header: str,
    signature_header: str,
    timestamp: int | None,
    nonce: str | None,
    label: str,
) -> dict[str, str]:
    _validate_secret(secret)
    if not isinstance(body, bytes):
        raise ValueError(f"{label} request body must be bytes")
    signed_at = int(time.time()) if timestamp is None else timestamp
    request_nonce = secrets.token_urlsafe(18) if nonce is None else nonce
    if (
        isinstance(signed_at, bool)
        or not isinstance(signed_at, int)
        or not isinstance(request_nonce, str)
        or not 16 <= len(request_nonce) <= 128
    ):
        raise ValueError(f"{label} proof metadata is invalid")
    signature = hmac.new(
        secret,
        _domain_signing_input(domain, signed_at, request_nonce, _body_hash(body)),
        hashlib.sha256,
    ).hexdigest()
    return {
        timestamp_header: str(signed_at),
        nonce_header: request_nonce,
        signature_header: signature,
    }


class _DomainProofVerifier:
    def __init__(
        self,
        secret: bytes,
        *,
        domain: str,
        timestamp_header: str,
        nonce_header: str,
        signature_header: str,
        max_age_seconds: int,
        error_type: type[ValueError],
        now: Callable[[], float],
        max_nonces: int,
    ) -> None:
        _validate_secret(secret)
        if max_nonces < 1:
            raise ValueError("max_nonces must be positive")
        self._secret = secret
        self._domain = domain
        self._timestamp_header = timestamp_header
        self._nonce_header = nonce_header
        self._signature_header = signature_header
        self._max_age_seconds = max_age_seconds
        self._error_type = error_type
        self._now = now
        self._max_nonces = max_nonces
        self._nonces: dict[str, float] = {}
        self._lock = threading.Lock()

    def verify(self, headers: Mapping[str, str], body: bytes) -> None:
        if not isinstance(body, bytes):
            raise self._error_type(f"invalid {self._proof_label()} proof")
        timestamp_text = _header_value(headers, self._timestamp_header)
        nonce = _header_value(headers, self._nonce_header)
        signature = _header_value(headers, self._signature_header)
        try:
            timestamp = int(timestamp_text) if timestamp_text is not None else None
        except (TypeError, ValueError):
            timestamp = None
        if (
            timestamp is None
            or isinstance(timestamp, bool)
            or not isinstance(nonce, str)
            or not 16 <= len(nonce) <= 128
            or not isinstance(signature, str)
            or len(signature) != 64
        ):
            raise self._error_type(f"invalid {self._proof_label()} proof")
        now = self._now()
        if abs(now - timestamp) > self._max_age_seconds:
            raise self._error_type(f"{self._proof_label()} proof expired")
        expected = hmac.new(
            self._secret,
            _domain_signing_input(
                self._domain,
                timestamp,
                nonce,
                _body_hash(body),
            ),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise self._error_type(f"invalid {self._proof_label()} proof")
        with self._lock:
            self._prune_nonces_locked(now)
            if nonce in self._nonces:
                raise self._error_type(f"{self._proof_label()} proof replayed")
            if len(self._nonces) >= self._max_nonces:
                raise self._error_type(
                    f"{self._proof_label()} proof verifier overloaded"
                )
            self._nonces[nonce] = timestamp + self._max_age_seconds

    def _prune_nonces_locked(self, now: float) -> None:
        for nonce, expires_at in list(self._nonces.items()):
            if expires_at < now:
                self._nonces.pop(nonce, None)

    def _proof_label(self) -> str:
        return self._domain.removeprefix("hfc-").removesuffix("-v1")


def is_loopback_host(host: str) -> bool:
    normalized = str(host or "").strip().lower().strip("[]")
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validate_secret(secret: bytes) -> None:
    if not isinstance(secret, bytes) or len(secret) != _ROOT_SECRET_BYTES:
        raise ValueError("event transport root is invalid")


def _sidecar_request_payload(method: str, path: str, body: bytes) -> bytes:
    normalized_method = str(method or "").strip().upper()
    normalized_path = str(path or "").strip()
    if (
        normalized_method not in {"GET", "POST"}
        or not normalized_path.startswith("/")
        or "?" in normalized_path
        or "#" in normalized_path
        or not isinstance(body, bytes)
    ):
        raise ValueError("sidecar request target is invalid")
    normalized_path = normalized_path.rstrip("/") or "/"
    return (
        normalized_method.encode("ascii")
        + b"\0"
        + normalized_path.encode("utf-8")
        + b"\0"
        + body
    )


def _runtime_interaction_payload(path: str, body: bytes) -> bytes:
    if (
        type(path) is not str
        or path != RUNTIME_INTERACTION_PATH
        or type(body) is not bytes
    ):
        raise ValueError("runtime interaction target is invalid")
    return b"POST\0" + path.encode("ascii") + b"\0" + body


def _body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _event_signing_input(timestamp: int, nonce: str, body_hash: str) -> bytes:
    return _domain_signing_input("hfc-event-v1", timestamp, nonce, body_hash)


def _domain_signing_input(
    domain: str,
    timestamp: int,
    nonce: str,
    body_hash: str,
) -> bytes:
    return f"{domain}\0{timestamp}\0{nonce}\0{body_hash}".encode("utf-8")


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    value = headers.get(name)
    if value is not None:
        return value
    normalized = name.lower()
    for key, candidate in headers.items():
        if str(key).lower() == normalized:
            return candidate
    return None
