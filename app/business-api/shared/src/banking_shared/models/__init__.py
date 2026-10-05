"""Canonical table families; importing this package eagerly registers all metadata."""

from __future__ import annotations

from sqlmodel import SQLModel

from banking_shared.identity_models import (
    CustomerUser, IdentityAudit, Operator, Role, User, UserRole,
)

BRANCH_ID_FOREIGN_KEY = "branches.branch_id"
CUSTOMER_ID_FOREIGN_KEY = "customers.customer_id"
PRODUCT_ID_FOREIGN_KEY = "products.product_id"
TRANSACTION_ID_FOREIGN_KEY = "transactions.transaction_id"


from banking_shared.models.catalog import Branch, Customer
from banking_shared.models.legacy import LegacyServiceAgent, LegacyOperatorServiceAgent
from banking_shared.models.products import Product, ProductMonthlySnapshot
from banking_shared.models.transactions import TransactionRecord
from banking_shared.models.effects import RuntimePosting, CardProtection
from banking_shared.models.cases import SUPPORT_CASE_STATUSES, SupportCase, SupportCaseEvent
