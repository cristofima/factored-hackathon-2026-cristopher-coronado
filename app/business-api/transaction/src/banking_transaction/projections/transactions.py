from banking_shared.models import Product, TransactionRecord
from banking_shared.product_types import CARD_PRODUCT_TYPES
from banking_transaction.models.transactions import Transaction


def to_transaction(record: TransactionRecord, product: Product) -> Transaction:
    product_number = product.product_number
    if product.product_type in CARD_PRODUCT_TYPES:
        product_number = (
            f"**** {product_number[-4:]}"
            if product_number and len(product_number) > 4 else None
        )
    return Transaction(
        id=record.transaction_id,
        flowType="income" if record.source_kind == "runtime" else None,
        originalTransactionId=record.original_transaction_id,
        supportCaseId=record.support_case_id,
        sourceKind=record.source_kind,
        type=record.transaction_type,
        recipientName=record.merchant_name,
        product_number=product_number,
        paymentType=record.channel,
        amount=float(record.amount),
        currency=record.currency,
        timestamp=record.transaction_date.isoformat(),
        country=record.transaction_country,
        city=record.transaction_city,
        category=record.transaction_category,
        status=record.transaction_status,
    )
