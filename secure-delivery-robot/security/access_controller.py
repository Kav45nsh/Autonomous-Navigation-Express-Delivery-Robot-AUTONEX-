"""
AccessController - the ONLY thing allowed to open the compartment.

This is the security boundary. Face matching produces evidence; this class
decides. Keeping the decision in one place means there is exactly one function
to audit, one place a reviewer must read, and no path where some other module
reaches for the solenoid directly.

The flow main.py drives:

    camera.set_mode(FACE_AUTH)          # mode switch on arrival
    outcome = authenticator.authenticate(camera)
    controller.handle(outcome, destination)   # unlock or refuse, and log it
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from config import settings
from core.events import Event, bus
from face_auth.face_authentication import AuthOutcome
from security.audit_log import AuditLog
from security.solenoid_lock import SolenoidLock

log = logging.getLogger(__name__)


@dataclass
class AccessDecision:
    granted: bool
    recipient: Optional[str]
    confidence: float
    reason: str
    unlocked: bool = False


class AccessController:
    def __init__(self, lock: SolenoidLock = None, audit: AuditLog = None):
        self.lock = lock or SolenoidLock()
        self.audit = audit or AuditLog()
        self.grants = 0
        self.denials = 0

    # ───────────────────────────────────────────────────────
    def evaluate(self, outcome: AuthOutcome) -> AccessDecision:
        """Pure policy. No side effects, so it is trivially testable."""
        if not outcome.authorised:
            return AccessDecision(False, None, outcome.confidence, outcome.reason)

        if outcome.confidence < settings.UNLOCK_CONFIDENCE_THRESHOLD:
            # Defence in depth: the authenticator should never let this
            # through, but the controller re-checks rather than trusting it.
            return AccessDecision(False, outcome.name, outcome.confidence,
                                  "confidence below threshold at final check")

        if settings.REQUIRE_LIVENESS and not outcome.liveness_passed:
            return AccessDecision(False, outcome.name, outcome.confidence,
                                  "liveness check not satisfied")

        return AccessDecision(True, outcome.name, outcome.confidence,
                              "identity verified")

    def handle(self, outcome: AuthOutcome, destination: str = None) -> AccessDecision:
        """Evaluate, then act: open the lock or refuse. Always audits."""
        decision = self.evaluate(outcome)
        destination = destination or "MARKER 5"

        if decision.granted:
            self.grants += 1
            decision.unlocked = self.lock.unlock(
                reason="face match", recipient=decision.recipient)
            self.audit.delivery_granted(
                recipient=decision.recipient,
                confidence=decision.confidence,
                destination=destination,
                threshold=settings.UNLOCK_CONFIDENCE_THRESHOLD,
                streak_required=settings.AUTH_REQUIRED_STREAK,
                attempt=outcome.attempts,
                elapsed_s=round(outcome.elapsed, 2))
            log.info("ACCESS GRANTED to %s (%.0f%%) at %s",
                     decision.recipient, decision.confidence * 100, destination)
            bus.emit(Event.DELIVERED, recipient=decision.recipient,
                     destination=destination)
        else:
            self.denials += 1
            self.audit.delivery_denied(
                reason=decision.reason,
                confidence=decision.confidence,
                destination=destination,
                attempt=outcome.attempts)
            log.warning("ACCESS DENIED: %s", decision.reason)
            if outcome.attempts >= settings.AUTH_MAX_ATTEMPTS:
                self.audit.lockout(attempts=outcome.attempts)

        return decision

    def emergency_lock(self) -> None:
        self.lock.lock()
        self.audit.record("EMERGENCY_LOCK")

    def cleanup(self) -> None:
        self.lock.cleanup()
