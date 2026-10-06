from uuid import uuid4

import pytest
from pydantic import ValidationError

from nexus.domain.authorization import (
    AgentPolicy,
    DecisionOutcome,
    DecisionReason,
    OperationRequest,
    evaluate_operation,
)


@pytest.fixture
def policy() -> AgentPolicy:
    return AgentPolicy(
        agent_id=uuid4(),
        company_id=uuid4(),
        active=True,
        allowed_operations=frozenset({"purchase"}),
        automatic_limit_cents=50_000,
        maximum_limit_cents=200_000,
    )


def request(
    operation: str = "purchase", amount_cents: int = 30_000
) -> OperationRequest:
    return OperationRequest(
        request_id=uuid4(), operation=operation, amount_cents=amount_cents
    )


def test_authorizes_allowed_operation_within_automatic_limit(
    policy: AgentPolicy,
) -> None:
    decision = evaluate_operation(policy, request())

    assert decision.outcome is DecisionOutcome.AUTHORIZED
    assert decision.reason is DecisionReason.WITHIN_AUTOMATIC_LIMIT
    assert decision.agent_id == policy.agent_id
    assert decision.company_id == policy.company_id


@pytest.mark.parametrize("amount_cents", [0, 50_000])
def test_authorizes_zero_and_exact_automatic_limit(
    policy: AgentPolicy, amount_cents: int
) -> None:
    decision = evaluate_operation(policy, request(amount_cents=amount_cents))

    assert decision.outcome is DecisionOutcome.AUTHORIZED
    assert decision.reason is DecisionReason.WITHIN_AUTOMATIC_LIMIT


def test_blocks_operation_not_present_in_server_policy(policy: AgentPolicy) -> None:
    decision = evaluate_operation(policy, request(operation="delete_financial_record"))

    assert decision.outcome is DecisionOutcome.BLOCKED
    assert decision.reason is DecisionReason.OPERATION_NOT_ALLOWED


@pytest.mark.parametrize("amount_cents", [50_001, 100_000])
def test_requires_human_approval_above_automatic_limit(
    policy: AgentPolicy, amount_cents: int
) -> None:
    decision = evaluate_operation(policy, request(amount_cents=amount_cents))

    assert decision.outcome is DecisionOutcome.PENDING_APPROVAL
    assert decision.reason is DecisionReason.HUMAN_APPROVAL_REQUIRED


def test_exact_maximum_limit_requires_human_approval(policy: AgentPolicy) -> None:
    decision = evaluate_operation(policy, request(amount_cents=200_000))

    assert decision.outcome is DecisionOutcome.PENDING_APPROVAL
    assert decision.reason is DecisionReason.HUMAN_APPROVAL_REQUIRED


def test_blocks_amount_above_maximum_limit(policy: AgentPolicy) -> None:
    decision = evaluate_operation(policy, request(amount_cents=200_001))

    assert decision.outcome is DecisionOutcome.BLOCKED
    assert decision.reason is DecisionReason.MAXIMUM_LIMIT_EXCEEDED


def test_blocks_inactive_agent_even_for_otherwise_valid_request(
    policy: AgentPolicy,
) -> None:
    inactive_policy = policy.model_copy(update={"active": False})

    decision = evaluate_operation(inactive_policy, request())

    assert decision.outcome is DecisionOutcome.BLOCKED
    assert decision.reason is DecisionReason.AGENT_INACTIVE


def test_rejects_invalid_policy_limit_order() -> None:
    with pytest.raises(
        ValidationError, match="automatic limit cannot exceed maximum limit"
    ):
        AgentPolicy(
            agent_id=uuid4(),
            company_id=uuid4(),
            active=True,
            allowed_operations=frozenset({"purchase"}),
            automatic_limit_cents=201,
            maximum_limit_cents=200,
        )


@pytest.mark.parametrize("invalid_amount", [-1, 1.5, "300"])
def test_rejects_invalid_cent_values(invalid_amount: object) -> None:
    with pytest.raises(ValidationError):
        request(amount_cents=invalid_amount)  # type: ignore[arg-type]
