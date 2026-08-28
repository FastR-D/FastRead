from __future__ import annotations

from app.services.academic_evidence import assess_academic_identity


IDENTITY_STATES = {
    "confirmed_core",
    "claimed_core_unverified",
    "confirmed_formal_other",
    "preprint",
    "incomplete",
    "retracted_or_withdrawn",
}


class AcademicIdentityService:
    """Own the formal-publication identity state machine independently of relevance search."""

    def assess(self, metadata: dict | None) -> dict:
        gate = assess_academic_identity(metadata)
        if gate.get("integrity_status") in {"retracted", "withdrawn"}:
            status = "retracted_or_withdrawn"
        elif gate.get("publication_status") == "preprint":
            status = "preprint"
        elif gate.get("formal_identity_passed") and gate.get("is_core_venue"):
            status = "confirmed_core"
        elif gate.get("formal_identity_passed"):
            status = "confirmed_formal_other"
        elif gate.get("is_core_venue"):
            status = "claimed_core_unverified"
        else:
            status = "incomplete"
        gate["identity_status"] = status
        gate["gate_passed"] = bool(
            gate.get("formal_identity_passed") and gate.get("is_core_venue")
        )
        return gate
