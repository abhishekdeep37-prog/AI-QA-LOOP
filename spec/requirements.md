# Toy Pay: Requirements

## API overview

Base URL is the app root. All API bodies and responses are JSON. State is in memory and is reset before every scenario.

Seed data: accounts `alice` (password `pass123`, balance 1000.00) and `bob` (password `pass456`, balance 200.00).

Endpoints:
- `POST /api/login` with `{"username", "password"}`. Success: 200 `{"ok": true, "user"}`. Failure: 401 `{"ok": false, "error": "invalid_credentials"}`.
- `GET /api/accounts/<name>` returns 200 `{"ok": true, "name", "balance"}`, or 404 `{"ok": false, "error": "unknown_account"}`.
- `POST /api/transfer` with `{"from", "to", "amount"}`. Success: 200 `{"ok": true, "fee", "from_balance", "to_balance"}`. Failure: 400 or 404 `{"ok": false, "error"}`.
- `POST /api/coupon` with `{"user", "code", "total"}`. Success: 200 `{"ok": true, "discounted_total"}`.

UI at `/` has these elements (use the `data-testid` attribute as the selector, e.g. `[data-testid=login-user]`):
`login-user`, `login-pass`, `login-submit`, `login-result`, `transfer-from`, `transfer-to`, `transfer-amount`, `transfer-submit`, `transfer-result`.

## R1 Login

A user with correct credentials gets HTTP 200 and `ok: true`. Wrong password or unknown user gets HTTP 401 with `error: "invalid_credentials"`.

## R2 Account lockout

After 3 consecutive failed login attempts for a username, every further login attempt for that username, even with the correct password, returns HTTP 423 with `error: "account_locked"`. A successful login before the third failure resets the failure count.

## R3 Transfer amount validation

A transfer amount must be a number greater than zero. Zero, negative and non-numeric amounts return HTTP 400 with `error: "invalid_amount"`, and no balances change.

## R4 Insufficient funds

A transfer is rejected with HTTP 400 and `error: "insufficient_funds"` when the amount plus the fee (see R5) exceeds the sender's balance. Balances do not change on rejection. A transfer that uses exactly the full balance including the fee is allowed.

## R5 Transfer fee

Transfers of 500 or more charge the sender a fee of 1% of the amount, rounded to 2 decimals, on top of the amount. Transfers below 500 have a fee of 0. The response `fee` field shows the fee charged. The sender balance drops by amount plus fee; the receiver balance rises by the amount only.

## R6 Coupons

Coupon code `SAVE10` gives 10% off the given total, rounded to 2 decimals. Each user may use each coupon once: a second attempt by the same user returns HTTP 409 with `error: "coupon_already_used"`. An unknown code returns HTTP 404 with `error: "invalid_coupon"`. A different user can still use `SAVE10` once. A total that is not a positive number returns HTTP 400 with `error: "invalid_total"`.

## R7 UI

The login form shows `Welcome <user>` in `login-result` on success and `Error: <error_code>` on failure. The transfer form shows `Transfer OK, fee <fee with 2 decimals>` in `transfer-result` on success and `Error: <error_code>` on failure.
