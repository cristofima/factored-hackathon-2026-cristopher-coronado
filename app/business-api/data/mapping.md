# Source Mapping

The loader uses `C:\Factored\data` only as a local source supplied through
`--source`. No source records or generated manifests belong in the repository.

## Load Scope

| Target           | Source                 | Selection                                                |
| ---------------- | ---------------------- | -------------------------------------------------------- |
| `branches`       | `branches.csv`         | All rows                                                 |
| `customers`      | `customers.csv`        | All rows                                                 |
| `service_agents` | `service_agents.csv`   | All rows                                                 |
| `products`       | `products.csv`         | All rows                                                 |
| `transactions`   | Daily transaction CSVs | `process_date` from 2025-12-01 through 2026-05-31        |
| `users`          | Prototype-owned seed   | Two or three selected customers; no source password data |

The transaction window contains 182 complete daily partitions. June 2026 is excluded
because the available month ends on June 17.

## Tool Mapping

| Tool field                | Source                                              | Rule                                                               |
| ------------------------- | --------------------------------------------------- | ------------------------------------------------------------------ |
| Account `id`              | `products.product_id`                               | Products of type `Cuenta Ahorro` or `Cuenta Corriente`             |
| Account owner             | `products.customer_id`                              | Mandatory authorization key                                        |
| Account holder            | `customers.first_name`, `customers.last_name`       | Join through `customer_id`                                         |
| Account `currency`        | `products.currency`                                 | Preserve source currency                                           |
| Account `balance`         | `products.current_balance`                          | Preserve decimal precision; serialize at the response boundary     |
| Account activation        | `products.opening_date`                             | ISO 8601 date                                                      |
| Card `id`                 | `products.product_id`                               | Products of type `Tarjeta Crédito` or `Tarjeta Débito`             |
| Card owner                | `products.customer_id`                              | Mandatory authorization key                                        |
| Card type                 | `products.product_type`                             | Map to `credit` or `debit`                                         |
| Card balance and limit    | `current_balance`, `credit_limit`                   | No synthetic values                                                |
| Card dates and status     | `opening_date`, `expiration_date`, `product_status` | ISO 8601 dates and source status                                   |
| Transaction `accountId`   | `transactions.product_id`                           | Product ownership must also match `transactions.customer_id`       |
| Transaction type/category | `transaction_type`, `transaction_category`          | Preserve source vocabulary at rest; adapt only in response mapping |
| Transaction recipient     | `merchant_name`                                     | Nullable; no fabricated recipient                                  |
| Transaction timestamp     | `transaction_date`                                  | Store timezone-aware timestamp                                     |
| Transaction status        | `transaction_status`                                | Preserve source status                                             |

## Known Gaps

- No beneficiary source or beneficiary-to-account relationship exists. Keep
  `getRegisteredBeneficiary` unavailable for real data rather than returning fixtures.
- `product_number` is not treated as a confirmed card PAN and must not be returned as a
  full card number. A masked display value can be added only after its semantics are
  verified.
- Card circuit, CVV, recharge amount, friendly card name, and payment-method subtype do
  not have verified source columns. They remain null or unavailable.
- Service agents are loaded for referential context but are outside the active Account
  and Transaction workflow.
- Payment, campaign, digital-event, complaint, call-center, transcript, and survey data
  are outside this load.
