# Account service

Account exposes customer-owned bank and card reads through JWT-authenticated REST
and separately authenticated, agent-only MCP tools. Business ownership checks live
in [services/products.py](src/banking_account/services/products.py); canonical card
types are `Debit Card` and `Credit Card`.

## Package layout and local startup

The installed package is [banking_account](src/banking_account/):

- [models](src/banking_account/models/) defines product API DTOs.
- [routers](src/banking_account/routers/) owns browser REST boundaries.
- [services](src/banking_account/services/) owns product reads, errors and authorization.
- [projections](src/banking_account/projections/) maps persisted/runtime values to DTOs.
- [auth](src/banking_account/auth/) keeps browser JWT and agent bearer verification separate.
- [observability](src/banking_account/observability/) owns logging and tracing.
- [mcp_tools.py](src/banking_account/mcp_tools.py) delegates tools to services;
  [main.py](src/banking_account/main.py) composes the application.

From repository root, after configuring this service's own `.env`:

```powershell
rtk proxy uv sync --directory app\business-api\account --frozen --group dev
$env:PROFILE = "dev"
rtk proxy uv run --directory app\business-api\account --env-file .env python -m banking_account.main
```

Local development uses port 8070. The ASGI target is `banking_account.main:app`;
production uses port 8080. Use installed, package-qualified namespaces, not flat
`main`/`services` imports or path injection. See the
[shared setup and packaging guide](../README.md#python-dependency-artifacts).

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
rtk proxy uv run python -m pytest tests\test_card_discovery.py tests\test_card_masking.py tests\test_authorization.py tests\test_internal_identity.py -q
```

From `app/agent`, with the repository's normal test environment:

```powershell
rtk proxy uv run python -m pytest tests\test_card_discovery_instructions.py -q
```

These synthetic checks verify contracts and isolation, not live-model prose,
hosted identity transport, or real-data end-to-end acceptance.
