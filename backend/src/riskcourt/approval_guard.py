"""Bind approvals to immutable inputs and reserve idempotent submissions."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from threading import Lock

from riskcourt.domain import ApprovalArtifact, EvidenceItem, EvidenceType, TradeIntent

MAXIMUM_APPROVAL_LIFETIME = timedelta(seconds=30)


class SubmissionAction(StrEnum):
    SUBMIT = "submit"
    REPLAY = "replay"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ApprovalBinding:
    approval: ApprovalArtifact
    client_order_id: str
    intent_sha256: str
    evidence_sha256: str
    request_sha256: str


@dataclass(frozen=True, slots=True)
class ApprovalCheck:
    action: SubmissionAction
    reason: str


class IdempotencyRegistry:
    def __init__(self) -> None:
        self._requests: dict[str, str] = {}
        self._lock = Lock()

    def reserve(self, client_order_id: str, request_sha256: str) -> SubmissionAction:
        with self._lock:
            existing = self._requests.get(client_order_id)
            if existing is None:
                self._requests[client_order_id] = request_sha256
                return SubmissionAction.SUBMIT
            if existing == request_sha256:
                return SubmissionAction.REPLAY
            return SubmissionAction.REJECT


def create_approval_binding(
    approval: ApprovalArtifact,
    intent: TradeIntent,
    evidence: tuple[EvidenceItem, ...],
    client_order_id: str,
) -> ApprovalBinding:
    if approval.intent_id != intent.intent_id or approval.case_id != intent.case_id:
        raise ValueError("approval must reference the bound trade intent")
    if approval.expires_at - approval.approved_at > MAXIMUM_APPROVAL_LIFETIME:
        raise ValueError("approval lifetime cannot exceed 30 seconds")
    if not client_order_id or len(client_order_id) > 48:
        raise ValueError("client_order_id must contain 1 to 48 characters")

    evidence_by_id = {item.evidence_id: item for item in evidence}
    if len(evidence_by_id) != len(evidence):
        raise ValueError("approval evidence IDs must be unique")
    bound_evidence = tuple(evidence_by_id.get(item_id) for item_id in approval.evidence_ids)
    if any(item is None for item in bound_evidence):
        raise ValueError("every approval evidence ID must resolve")
    evidence_types = {item.evidence_type for item in bound_evidence if item is not None}
    required_types = {
        EvidenceType.OPTION_QUOTE,
        EvidenceType.UNDERLYING_QUOTE,
        EvidenceType.ACCOUNT,
    }
    if not required_types.issubset(evidence_types):
        raise ValueError("approval must bind option, underlying, and account evidence")

    intent_sha256 = _sha256(intent.model_dump_json())
    evidence_sha256 = _evidence_fingerprint(evidence, approval.evidence_ids)
    request_sha256 = _sha256(
        "|".join(
            (
                approval.approval_id,
                approval.policy_version,
                client_order_id,
                intent_sha256,
                evidence_sha256,
            )
        )
    )
    return ApprovalBinding(
        approval=approval,
        client_order_id=client_order_id,
        intent_sha256=intent_sha256,
        evidence_sha256=evidence_sha256,
        request_sha256=request_sha256,
    )


def validate_approval_for_execution(
    binding: ApprovalBinding,
    current_intent: TradeIntent,
    current_evidence: tuple[EvidenceItem, ...],
    current_policy_version: str,
    client_order_id: str,
    now: datetime,
    registry: IdempotencyRegistry,
) -> ApprovalCheck:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if now >= binding.approval.expires_at:
        return ApprovalCheck(SubmissionAction.REJECT, "approval_expired")
    if current_policy_version != binding.approval.policy_version:
        return ApprovalCheck(SubmissionAction.REJECT, "policy_version_changed")
    if client_order_id != binding.client_order_id:
        return ApprovalCheck(SubmissionAction.REJECT, "client_order_id_changed")
    if _sha256(current_intent.model_dump_json()) != binding.intent_sha256:
        return ApprovalCheck(SubmissionAction.REJECT, "intent_changed")
    try:
        current_evidence_sha256 = _evidence_fingerprint(
            current_evidence,
            binding.approval.evidence_ids,
        )
    except ValueError:
        return ApprovalCheck(SubmissionAction.REJECT, "evidence_changed")
    if current_evidence_sha256 != binding.evidence_sha256:
        return ApprovalCheck(SubmissionAction.REJECT, "evidence_changed")

    action = registry.reserve(client_order_id, binding.request_sha256)
    reason = {
        SubmissionAction.SUBMIT: "approval_valid_and_reserved",
        SubmissionAction.REPLAY: "idempotent_replay",
        SubmissionAction.REJECT: "idempotency_conflict",
    }[action]
    return ApprovalCheck(action, reason)


def _evidence_fingerprint(
    evidence: tuple[EvidenceItem, ...],
    evidence_ids: tuple[str, ...],
) -> str:
    evidence_by_id = {item.evidence_id: item for item in evidence}
    try:
        fingerprints = sorted(
            (item_id, evidence_by_id[item_id].payload_sha256) for item_id in evidence_ids
        )
    except KeyError as error:
        raise ValueError("bound evidence is missing") from error
    return _sha256(json.dumps(fingerprints, separators=(",", ":")))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
