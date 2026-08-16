"""REST bootstrap for the Deriv "Options API" generation.

Flow (see docs/postmortem/PROJECT_POSTMORTEM.md items 2-5, verified against
https://github.com/deriv-com/deriv-api-schemas as of 2026-08):

  1. GET  /trading/v1/options/accounts            -> find an existing account
     (POST the same path with {currency, group: "row", account_type} to
     create one if none exists yet for this account_type).
  2. POST /trading/v1/options/accounts/{id}/otp    -> short-lived (120s),
     single-use OTP. The response embeds a ready-to-use WebSocket URL.
  3. Connect to wss://api.derivws.com/trading/v1/options/ws/{demo|real}?otp=...

This is a REST-only handshake done once per session; the resulting WS URL is
handed to DerivClient, which owns the persistent connection.
"""

from __future__ import annotations

import logging

import httpx

from quantum_tick.infrastructure.deriv.exceptions import DerivAuthError

log = logging.getLogger("quantum_tick.deriv.auth")

REST_BASE = "https://api.derivws.com/trading/v1/options"


class AccountBootstrap:
    def __init__(self, app_id: str, api_token: str, account_type: str, currency: str):
        self._app_id = app_id
        self._api_token = api_token
        self._account_type = account_type
        self._currency = currency
        self._headers = {
            "Deriv-App-ID": app_id,
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    async def get_websocket_url(self) -> str:
        async with httpx.AsyncClient(timeout=20.0) as http:
            account_id = await self._find_or_create_account(http)
            return await self._get_otp_ws_url(http, account_id)

    async def _find_or_create_account(self, http: httpx.AsyncClient) -> str:
        resp = await http.get(f"{REST_BASE}/accounts", headers=self._headers)
        if resp.status_code == 200:
            accounts = resp.json().get("data", [])
            for acct in accounts:
                if acct.get("account_type") == self._account_type:
                    log.info(
                        "Using existing %s account %s",
                        self._account_type,
                        _mask(acct.get("account_id", "")),
                    )
                    return acct["account_id"]

        resp = await http.post(
            f"{REST_BASE}/accounts",
            headers=self._headers,
            json={
                "currency": self._currency,
                "group": "row",
                "account_type": self._account_type,
            },
        )
        _raise_for_deriv_error(resp, "account creation")
        data = resp.json()
        account_id = (data.get("data") or data).get("account_id")
        if not account_id:
            raise DerivAuthError(f"Account creation response had no account_id: {data}")
        log.info("Created %s account %s", self._account_type, _mask(account_id))
        return account_id

    async def _get_otp_ws_url(self, http: httpx.AsyncClient, account_id: str) -> str:
        resp = await http.post(
            f"{REST_BASE}/accounts/{account_id}/otp",
            headers=self._headers,
        )
        _raise_for_deriv_error(resp, "OTP retrieval")
        data = resp.json()
        data = data.get("data", data)

        ws_url = data.get("websocket_url") or data.get("ws_url") or data.get("url")
        if ws_url:
            return ws_url

        otp = data.get("otp") or data.get("otp_code") or data.get("code")
        if not otp:
            raise DerivAuthError(f"OTP response had neither a websocket URL nor an OTP code: keys={list(data.keys())}")
        return f"wss://api.derivws.com/trading/v1/options/ws/{self._account_type}?otp={otp}"


def _raise_for_deriv_error(resp: httpx.Response, step: str) -> None:
    if resp.status_code < 400:
        return
    try:
        body = resp.json()
    except ValueError:
        body = resp.text
    raise DerivAuthError(f"Deriv {step} failed: HTTP {resp.status_code} - {body}")


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}...{value[-2:]} (len={len(value)})"
