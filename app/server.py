"""Toy payments app used as the system under test.

It is intentionally small and intentionally buggy. The seeded defects are
tracked in ../seeded_bugs.json (ground truth for the metrics report), not in
this file, so the AI agents have to find them from behaviour alone.

Run:  python app/server.py --port 5057
"""
import argparse
import copy

from flask import Flask, jsonify, request

app = Flask(__name__)

SEED_ACCOUNTS = {
    "alice": {"password": "pass123", "balance": 1000.00},
    "bob": {"password": "pass456", "balance": 200.00},
}

MAX_FAILED_LOGINS = 5
FEE_THRESHOLD = 500
FEE_RATE = 0.01
COUPONS = {"SAVE10": 0.10}

state = {}


def reset_state():
    state["accounts"] = copy.deepcopy(SEED_ACCOUNTS)
    state["failed_logins"] = {}
    state["coupons_used"] = set()


reset_state()


def calc_fee(amount):
    """Fee charged to the sender on top of the transferred amount."""
    if amount > FEE_THRESHOLD:
        return round(amount * FEE_RATE, 2)
    return 0.0


def validate_transfer(sender, receiver, amount):
    """Return (http_status, error_code) when invalid, otherwise None."""
    accounts = state["accounts"]
    if sender not in accounts or receiver not in accounts:
        return 404, "unknown_account"
    if not isinstance(amount, (int, float)) or amount == 0:
        return 400, "invalid_amount"
    if amount > accounts[sender]["balance"]:
        return 400, "insufficient_funds"
    return None


def apply_coupon(user, code, total):
    """Return (error_code, discounted_total); exactly one of them is None."""
    rate = COUPONS.get(code)
    if rate is None:
        return "invalid_coupon", None
    state["coupons_used"].add((user, code))
    return None, round(total * (1 - rate), 2)


@app.get("/api/health")
def health():
    return jsonify(ok=True)


@app.post("/api/reset")
def reset():
    reset_state()
    return jsonify(ok=True)


@app.get("/api/accounts/<name>")
def get_account(name):
    acct = state["accounts"].get(name)
    if acct is None:
        return jsonify(ok=False, error="unknown_account"), 404
    return jsonify(ok=True, name=name, balance=acct["balance"])


@app.post("/api/login")
def login():
    body = request.get_json(silent=True) or {}
    user, password = body.get("username"), body.get("password")
    failures = state["failed_logins"].get(user, 0)
    if failures >= MAX_FAILED_LOGINS:
        return jsonify(ok=False, error="account_locked"), 423
    acct = state["accounts"].get(user)
    if acct is None or acct["password"] != password:
        state["failed_logins"][user] = failures + 1
        return jsonify(ok=False, error="invalid_credentials"), 401
    state["failed_logins"][user] = 0
    return jsonify(ok=True, user=user)


@app.post("/api/transfer")
def transfer():
    body = request.get_json(silent=True) or {}
    sender, receiver, amount = body.get("from"), body.get("to"), body.get("amount")
    err = validate_transfer(sender, receiver, amount)
    if err:
        return jsonify(ok=False, error=err[1]), err[0]
    fee = calc_fee(amount)
    accounts = state["accounts"]
    accounts[sender]["balance"] = round(accounts[sender]["balance"] - amount - fee, 2)
    accounts[receiver]["balance"] = round(accounts[receiver]["balance"] + amount, 2)
    return jsonify(
        ok=True,
        fee=fee,
        from_balance=accounts[sender]["balance"],
        to_balance=accounts[receiver]["balance"],
    )


@app.post("/api/coupon")
def coupon():
    body = request.get_json(silent=True) or {}
    user, code, total = body.get("user"), body.get("code"), body.get("total")
    if not isinstance(total, (int, float)) or total <= 0:
        return jsonify(ok=False, error="invalid_total"), 400
    error, discounted = apply_coupon(user, code, total)
    if error == "invalid_coupon":
        return jsonify(ok=False, error=error), 404
    if error == "coupon_already_used":
        return jsonify(ok=False, error=error), 409
    return jsonify(ok=True, discounted_total=discounted)


PAGE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Toy Pay</title></head>
<body>
  <h1>Toy Pay</h1>

  <section>
    <h2>Login</h2>
    <input data-testid="login-user" placeholder="username">
    <input data-testid="login-pass" type="password" placeholder="password">
    <button data-testid="login-submit">Log in</button>
    <p data-testid="login-result"></p>
  </section>

  <section>
    <h2>Transfer</h2>
    <input data-testid="transfer-from" placeholder="from">
    <input data-testid="transfer-to" placeholder="to">
    <input data-testid="transfer-amount" placeholder="amount">
    <button data-testid="transfer-submit">Send</button>
    <p data-testid="transfer-result"></p>
  </section>

  <script>
    const q = (id) => document.querySelector('[data-testid="' + id + '"]');
    q('login-submit').onclick = async () => {
      const r = await fetch('/api/login', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: q('login-user').value, password: q('login-pass').value})});
      const j = await r.json();
      q('login-result').textContent = j.ok ? 'Welcome ' + j.user : 'Error: ' + j.error;
    };
    q('transfer-submit').onclick = async () => {
      const r = await fetch('/api/transfer', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({from: q('transfer-from').value, to: q('transfer-to').value,
                              amount: parseFloat(q('transfer-amount').value)})});
      const j = await r.json();
      q('transfer-result').textContent = j.ok
        ? 'Transfer OK, fee ' + j.fee.toFixed(2)
        : 'Error: ' + j.error;
    };
  </script>
</body>
</html>
"""


@app.get("/")
def index():
    return PAGE


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5057)
    args = parser.parse_args()
    app.run(host="127.0.0.1", port=args.port, threaded=False)
