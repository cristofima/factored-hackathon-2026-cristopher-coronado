"""Guard the Transaction agent's masked-card discovery contract."""

from app.agents.azure_chat.transaction_agent import TransactionHistoryAgent


def test_suffix_discovery_precedes_full_number_questions() -> None:
    instructions = TransactionHistoryAgent.instructions
    assert "call discoverCardsBySuffix" in instructions
    assert "with those four digits before asking for a full card or bank account number" in instructions
    assert "Filter returned movements by the supplied date/amount/merchant" in instructions
    assert "never reconstruct a full number or submit masked digits" in instructions
    assert "never masked digits or product IDs" in instructions


def test_verified_card_lookup_is_internal_and_has_no_inferred_account() -> None:
    instructions = TransactionHistoryAgent.instructions
    assert "display masked_number" in instructions
    assert "card number in prose, tables, receipts or selection questions" in instructions
    assert "as both product_number and card_product_number" in instructions
    assert "not an inferred bank account" in instructions
    assert "Never infer a card-to-account relationship" in instructions


def test_discovery_keeps_ambiguity_and_unavailable_lookup_explicit() -> None:
    instructions = TransactionHistoryAgent.instructions
    assert "AMBIGUOUS or TOO_MANY_MATCHES requires a discriminating" in instructions
    assert "never select the first candidate" in instructions
    assert "only after the customer uniquely selects" in instructions
    assert "Identical readable candidates remain unresolved" in instructions
    assert "Truncated discovery is not a complete card catalog" in instructions
    assert "NO_MATCH means no matching owned card" in instructions
    assert "LOOKUP_UNAVAILABLE means no usable full key" in instructions
