"""Operator-only queue, owned detail and exclusive claim. No verdict surface."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from operator_identity import OperatorPrincipal, get_operator_principal
from operator_models import OperatorCaseDetail, OperatorCasePage
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
