"""REST endpoints for the persisted transaction-dispute support-case workflow."""
from fastapi import APIRouter, Depends, HTTPException, status
import logging
from typing import Annotated

from dispute_service import support_case_service_singleton as service
from jwt_identity import get_jwt_customer_id
from models import DisputeApprovalRequest, OpenDisputeRequest, ResolveCaseRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
def list_support_cases(customer_id: Annotated[str, Depends(get_jwt_customer_id)]):
    """List the authenticated customer's support cases."""
    return service.list_cases(customer_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def open_support_case(
    request: OpenDisputeRequest,
    customer_id: Annotated[str, Depends(get_jwt_customer_id)],
):
    """Open a transaction-dispute support case from a direct report action."""
    try:
        return service.open_transaction_dispute(request.transactionId, customer_id, request.reason)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ValueError as ve:
        logger.exception("Validation error while opening a support case")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve)) from ve
    except Exception:
        logger.exception("Unexpected error while opening a support case")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error")


@router.get("/{case_id}")
def get_support_case(
    case_id: str,
    customer_id: Annotated[str, Depends(get_jwt_customer_id)],
):
    """Get a single support case by ID."""
    try:
        return service.get_case(case_id, customer_id)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error


@router.get("/{case_id}/timeline")
def get_support_case_timeline(
    case_id: str,
    customer_id: Annotated[str, Depends(get_jwt_customer_id)],
):
    """Get the event timeline for a support case."""
    try:
        return service.get_case_timeline(case_id, customer_id)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error


@router.post("/{case_id}/approval")
def respond_to_support_case_approval(
    case_id: str,
    request: DisputeApprovalRequest,
    customer_id: Annotated[str, Depends(get_jwt_customer_id)],
):
    """Record the customer's approval or decline for a case awaiting approval."""
    try:
        return service.respond_to_approval(case_id, customer_id, request.approved)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ValueError as ve:
        logger.exception("Validation error while responding to a support case approval")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve)) from ve


@router.post("/{case_id}/resolve")
def resolve_support_case(
    case_id: str,
    request: ResolveCaseRequest,
    customer_id: Annotated[str, Depends(get_jwt_customer_id)],
):
    """Resolve an escalated case under manual review.

    Simulated-reviewer action only; the conversational agent never calls this.
    """
    try:
        return service.resolve_case(
            case_id, customer_id, request.resolutionOutcome, request.resolutionNotes
        )
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ValueError as ve:
        logger.exception("Validation error while resolving a support case")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve)) from ve


@router.post("/{case_id}/recommendation/dismiss")
def dismiss_support_case_recommendation(
    case_id: str,
    customer_id: Annotated[str, Depends(get_jwt_customer_id)],
):
    """Record the customer's explicit opt-out of the post-resolution recommendation."""
    try:
        return service.dismiss_recommendation(case_id, customer_id)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ValueError as ve:
        logger.exception("Validation error while dismissing a support case recommendation")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve)) from ve
