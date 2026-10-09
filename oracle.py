"""Mechora MCH — TRON Nile-only CoinGecko/TRX reference-data oracle.

Does NOT set the token's real market price or promise TRX redemption.
Without ENABLE_NILE_WRITES=true, this program is read-only.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=tron&vs_currencies=usd&include_market_cap=true"
    "&include_last_updated_at=true"
)
ALLOWED_FUNCTIONS = {
    "updateTRXMarket": "sourceUpdatedAt",
    "updateTRXReference": "trxSourceUpdatedAt",
    "updateTrxReference": "trxSourceUpdatedAt",
}
MAX_AGE_SECONDS = 20 * 60

@dataclass(frozen=True)
class TrxReference:
    price_e8: int
    market_cap_usd: int
    timestamp: int


def _positive_decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} missing")
    try:
        v = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} not numeric") from exc
    if not v.is_finite() or v <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return v


def parse_market_data(payload: dict, now: int | None = None) -> TrxReference:
    now = int(time.time()) if now is None else int(now)
    tron = payload.get("tron") if isinstance(payload, dict) else None
    if not isinstance(tron, dict):
        raise ValueError("CoinGecko response has no tron object")
    price = _positive_decimal(tron.get("usd"), "TRX price")
    market_cap = _positive_decimal(tron.get("usd_market_cap"), "TRX market cap")
    timestamp = tron.get("last_updated_at")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        raise ValueError("CoinGecko update timestamp unavailable")
    timestamp = int(timestamp)
    if timestamp > now + 60 or now - timestamp > MAX_AGE_SECONDS:
        raise ValueError("CoinGecko data is stale or from the future")
    price_e8 = int((price * Decimal("100000000")).to_integral_value(rounding=ROUND_HALF_UP))
    cap_usd = int(market_cap.to_integral_value(rounding=ROUND_HALF_UP))
    if not 0 < price_e8 < 2**256 or not 0 < cap_usd < 2**256:
        raise ValueError("Encoded market values outside uint256 range")
    return TrxReference(price_e8, cap_usd, timestamp)


def fetch_market_data() -> TrxReference:
    headers = {"Accept": "application/json", "User-Agent": "MechoraNileReferenceOracle/0.1"}
    token = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
    if token:
        headers["x-cg-demo-api-key"] = token
    request = Request(COINGECKO_URL, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"CoinGecko request failed: {exc}") from exc
    return parse_market_data(payload)


def minimal_abi(method: str) -> list[dict]:
    getter = ALLOWED_FUNCTIONS[method]
    return [
        {
            "type": "function", "name": method, "stateMutability": "nonpayable",
            "inputs": [
                {"name": "priceUsdE8", "type": "uint256"},
                {"name": "marketCapUsd", "type": "uint256"},
                {"name": "dataTimestamp", "type": "uint256"},
            ], "outputs": [],
        },
        {
            "type": "function", "name": getter, "stateMutability": "view",
            "inputs": [], "outputs": [{"name": "", "type": "uint256"}],
        },
    ]


def submit_nile_update(data: TrxReference, contract_address: str, method: str, private_key_hex: str) -> str | None:
    from tronpy import Tron
    from tronpy.keys import PrivateKey

    key = PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x")))
    oracle_address = key.public_key.to_base58check_address()
    client = Tron(network="nile")  # hard-coded; NEVER mainnet
    try:
        contract = client.get_contract(contract_address)
        contract.abi = minimal_abi(method)

        try:
            onchain_time = int(getattr(contract.functions, ALLOWED_FUNCTIONS[method])())
        except Exception as exc:
            raise RuntimeError(
                "Cannot read on-chain source timestamp; check contract version and UPDATE_FUNCTION"
            ) from exc
        if onchain_time >= data.timestamp:
            print("No new TRX data; skipped a duplicate or older on-chain update.")
            return None

        transaction = (
            getattr(contract.functions, method)(
                data.price_e8, data.market_cap_usd, data.timestamp
            )
            .with_owner(oracle_address)
            .fee_limit(20_000_000)  # cap of 20 test TRX for Energy (not a fee estimate)
            .build()
            .sign(key)
        )
        receipt = transaction.broadcast().wait()
        result = receipt.get("receipt", {}).get("result", "")
        if result != "SUCCESS":
            raise RuntimeError(f"Nile contract update failed: {result or receipt}")
        txid = receipt.get("id") or transaction.txid
        return str(txid)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def main() -> None:
    data = fetch_market_data()
    print("Source: CoinGecko / TRON (TRX); these are NOT MCH market prices")
    print("TRX reference price USD:", Decimal(data.price_e8) / Decimal(100000000))
    print("TRX reference market cap USD:", data.market_cap_usd)
    print("CoinGecko source timestamp UTC (Unix):", data.timestamp)
    print("Indicative MCH demo quote equals 1 TRX; no real market value asserted.")

    write_enabled = os.getenv("ENABLE_NILE_WRITES", "false").lower() == "true"
    if not write_enabled:
        print("READ-ONLY: ENABLE_NILE_WRITES is not true, no blockchain transaction sent.")
        return

    contract_address = os.getenv("MCH_CONTRACT_ADDRESS", "").strip()
    key_hex = os.getenv("NILE_ORACLE_PRIVATE_KEY", "").strip()
    method = os.getenv("UPDATE_FUNCTION", "updateTRXMarket").strip()
    if method not in ALLOWED_FUNCTIONS:
        raise ValueError("UPDATE_FUNCTION must be updateTRXMarket, updateTRXReference or updateTrxReference")
    if not contract_address.startswith("T") or len(contract_address) != 34:
        raise ValueError("MCH_CONTRACT_ADDRESS must be the deployed Nile contract's T-address")
    if not key_hex or len(key_hex.removeprefix("0x")) != 64:
        raise ValueError("NILE_ORACLE_PRIVATE_KEY secret must be a 32-byte hex test-only key")
    txid = submit_nile_update(data, contract_address, method, key_hex)
    if txid:
        print("Successful Nile transaction ID:", txid)
        print("Explorer: https://nile.tronscan.org/#/transaction/" + txid)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Oracle error: {error}", file=sys.stderr)
        sys.exit(1)
