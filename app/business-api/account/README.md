# Account service

Account exposes customer-owned bank and card reads through JWT-authenticated REST
and separately authenticated, agent-only MCP tools. Business ownership checks live
in `services.py`; canonical card types are `Debit Card` and `Credit Card`.

## Masked-suffix card discovery

`discoverCardsBySuffix(suffix)` accepts exactly four ASCII digits, such as `7036`.
The MCP header supplies the verified customer identity, never a caller-selected
customer ID. Existing card listing needs a bank number and supplies only masked
numbers, so this dedicated discovery tool avoids an unnecessary full-number question.
It searches only the customer's persisted canonical cards, returning at most five
candidates with masked display, type, currency and runtime-projected status.

Results explicitly distinguish `MATCH`, `NO_MATCH`, `AMBIGUOUS`,
`TOO_MANY_MATCHES` (with `truncated: true`) and `LOOKUP_UNAVAILABLE`.
An ambiguous result must not be treated as a unique match. Ask a discriminating
masked-display/type/currency question; identical readable candidates remain
unresolved. A truncated result is not a complete catalog.

Each candidate's optional `lookup_product_number` is an **agent-internal** key:
only an exact persisted full card number, verified uniquely owned across all
product types, is supplied. Masked, malformed and duplicate numbers never become
usable keys. No digits are reconstructed. The new models are MCP-only; REST card
responses retain their existing masked contract. Agent output, including tables,
receipts and selection questions, must never reveal the internal full number.

After a unique card selection, Transaction uses the same verified key for both
`product_number` and `card_product_number` in `getCardTransactions`, then filters
persisted movements by the customer's date, amount or merchant clues. This selects
the card itself: discovery does not infer a bank-account association, expose foreign
cards, or establish complete transaction-history coverage.

## Focused checks

From this directory:

```powershell
uv run python -m pytest tests/test_card_discovery.py tests/test_card_masking.py tests/test_authorization.py tests/test_internal_identity.py -q
```

From `app/agent`, with the repository's normal test environment:

```powershell
uv run python -m pytest tests/test_card_discovery_instructions.py -q
```

These synthetic checks verify contracts and isolation, not live-model prose,
hosted identity transport, or real-data end-to-end acceptance.
