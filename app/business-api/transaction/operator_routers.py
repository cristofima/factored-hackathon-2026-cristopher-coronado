"""Operator-only queue, owned adjudication, restitution and local card protection."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from operator_identity import OperatorPrincipal, get_operator_principal
from adjudication import AdjudicationConflict
from operator_models import AdjudicateRequest, CardProtectionRequest, RetryEffectsRequest, OperatorCaseDetail, OperatorCasePage
from operator_service import (
    OperatorClaimConflict, OperatorPersistenceUnavailable, operator_case_service as service,
)

router = APIRouter()
Principal = Annotated[OperatorPrincipal, Depends(get_operator_principal)]


@router.get("", response_model=OperatorCasePage)
def list_operator_cases(principal: Principal, offset: Annotated[int, Query(ge=0)] = 0,
                        limit: Annotated[int, Query(ge=1, le=100)] = 50,
                        view: Annotated[Literal["available", "assigned"], Query()] = "available") -> OperatorCasePage:
    return service.list_cases(principal, offset, limit, view=view)


@router.get("/{case_id}", response_model=OperatorCaseDetail)
def get_operator_case(case_id: str, principal: Principal) -> OperatorCaseDetail:
    try:
        return service.get_case(case_id, principal)
    except LookupError:
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"}) from None


@router.post("/{case_id}/claim", response_model=OperatorCaseDetail)
def claim_operator_case(case_id: str, principal: Principal) -> OperatorCaseDetail:
    try:
        return service.claim_case(case_id, principal)
    except OperatorClaimConflict:
        raise HTTPException(409, detail={"code": "OPERATOR_CLAIM_CONFLICT"}) from None
    except OperatorPersistenceUnavailable:
        raise HTTPException(503, detail={"code": "SERVICE_UNAVAILABLE"}) from None


@router.post("/{case_id}/adjudicate", response_model=OperatorCaseDetail)
def adjudicate_case(case_id: str, principal: Principal, request: AdjudicateRequest) -> OperatorCaseDetail:
    try:
        return service.adjudicate(case_id, principal, request)
    except LookupError:
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"}) from None
    except AdjudicationConflict as error:
        raise HTTPException(409, detail={"code": error.code}) from None


@router.post("/{case_id}/effects/retry", response_model=OperatorCaseDetail)
def retry_case_effects(case_id: str, principal: Principal, request: RetryEffectsRequest) -> OperatorCaseDetail:
    try:
        return service.retry_effects(case_id, principal, request.expected_case_version, request.destination_product_id)
    except LookupError:
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"}) from None
    except AdjudicationConflict as error:
        raise HTTPException(409, detail={"code": error.code}) from None


@router.post("/{case_id}/card-protection", response_model=OperatorCaseDetail)
def protect_case_card(case_id: str, principal: Principal, request: CardProtectionRequest) -> OperatorCaseDetail:
    try:
        return service.protect_card(case_id, principal, request)
    except LookupError:
        raise HTTPException(404, detail={"code": "CASE_NOT_FOUND"}) from None
    except AdjudicationConflict as error:
        raise HTTPException(409, detail={"code": error.code}) from None
