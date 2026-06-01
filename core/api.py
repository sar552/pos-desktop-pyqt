"""Thin HTTP client for the Frappe / POSAwesome backend.

Design notes
------------
* `requests.Session` is internally thread-safe for independent calls; we no
  longer hold a process-wide lock across the entire HTTP round-trip — that
  was forcing every background worker (sync, offline_sync, connectivity) to
  serialise behind each other.
* Credentials are still mutated atomically under a short-lived `RLock`.
* `call_method` returns `(success, payload, status_code)` so callers can
  classify errors by HTTP code instead of fragile localised strings.  A
  legacy 2-tuple unpack still works via `tuple()` slicing.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import requests

from core.config import load_config
from core.constants import API_TIMEOUT_DEFAULT, API_TIMEOUT_SHORT
from core.logger import get_logger

logger = get_logger(__name__)


class ApiResponse(tuple):
    """`(success, payload, status_code)` — but unpacks as the old 2-tuple too."""

    __slots__ = ()

    def __new__(cls, success: bool, payload: Any, status_code: int = 0):
        return super().__new__(cls, (success, payload, status_code))

    # Backward compatibility: code in the codebase does
    # `success, payload = api.call_method(...)`.  Allow that by returning the
    # 2-tuple from iter when unpacking with 2 names.
    def __iter__(self):
        # Default unpack iterates all 3.  Sub-class trick: if called with
        # exactly 2 names Python tries star-unpacking; instead we keep the
        # default 3-element iter and rely on `status_code` being optional in
        # most call-sites.  Existing 2-name unpacks already exist throughout
        # the codebase — for those we expose only (success, payload).
        yield self[0]
        yield self[1]

    @property
    def status_code(self) -> int:
        return self[2]


class FrappeAPI:
    def __init__(self):
        self.session = requests.Session()
        self._cred_lock = threading.RLock()
        self.url = ""
        self.site = ""
        self.api_key = ""
        self.api_secret = ""
        self.user = ""
        self.password = ""
        self.reload_config()

    # ── credentials ────────────────────────────────────────────────────────
    def reload_config(self):
        with self._cred_lock:
            cfg = load_config()
            self.url = (cfg.get("url") or "").rstrip("/")
            self.site = cfg.get("site") or ""
            self.api_key = cfg.get("api_key") or ""
            self.api_secret = cfg.get("api_secret") or ""
            self.user = cfg.get("user") or ""
            self.password = cfg.get("password") or ""

    def _snapshot(self) -> dict:
        """Return a thread-safe copy of credentials for a single request."""
        with self._cred_lock:
            return {
                "url": self.url,
                "site": self.site,
                "api_key": self.api_key,
                "api_secret": self.api_secret,
                "user": self.user,
                "password": self.password,
            }

    def get_headers(self, is_json: bool = True, snap: dict | None = None) -> dict:
        snap = snap or self._snapshot()
        headers = {"Accept": "application/json"}
        if snap["site"]:
            headers["X-Frappe-Site-Name"] = snap["site"]
        if snap["api_key"] and snap["api_secret"]:
            headers["Authorization"] = f"token {snap['api_key']}:{snap['api_secret']}"
        if is_json:
            headers["Content-Type"] = "application/json"
        return headers

    def is_configured(self) -> bool:
        snap = self._snapshot()
        return bool(
            snap["url"]
            and ((snap["api_key"] and snap["api_secret"]) or (snap["user"] and snap["password"]))
        )

    # ── auth ───────────────────────────────────────────────────────────────
    def login(self, url: str, usr: str, pwd: str, site: str = "") -> tuple[bool, str]:
        login_url = f"{url.rstrip('/')}/api/method/login"
        payload = {"usr": usr, "pwd": pwd}
        headers = {"Accept": "application/json"}
        if site:
            headers["X-Frappe-Site-Name"] = site

        try:
            resp = self.session.post(
                login_url, data=payload, headers=headers, timeout=API_TIMEOUT_DEFAULT
            )
        except requests.exceptions.RequestException as e:
            logger.error("Login ulanish xatosi: %s", e)
            return False, "Server bilan aloqa o'rnatib bo'lmadi"

        if resp.status_code == 200:
            logger.info("Login muvaffaqiyatli: %s (User: %s)", url, usr)
            with self._cred_lock:
                self.url = url.rstrip("/")
                self.user = usr
                self.password = pwd
                self.site = site
            return True, "Success"

        try:
            error_data = resp.json()
            if error_data.get("message") == "Logged In":
                return True, "Success"
        except (json.JSONDecodeError, ValueError):
            pass
        logger.warning("Login xatosi: %d - %s", resp.status_code, resp.text[:200])
        return False, "Login yoki parol noto'g'ri"

    def ping(self, url: str, api_key: str, api_secret: str, site: str = "") -> tuple[bool, str]:
        test_url = f"{url.rstrip('/')}/api/method/frappe.auth.get_logged_user"
        headers = {
            "Authorization": f"token {api_key}:{api_secret}",
            "Accept": "application/json",
        }
        if site:
            headers["X-Frappe-Site-Name"] = site
        try:
            resp = requests.get(test_url, headers=headers, timeout=API_TIMEOUT_DEFAULT)
        except Exception as e:
            logger.error("Ping xatosi: %s", e)
            return False, str(e)
        if resp.status_code == 200:
            return True, "Success"
        return False, f"Error: {resp.status_code}"

    # ── resource fetch ─────────────────────────────────────────────────────
    def fetch_data(
        self,
        doctype: str,
        fields: str = '["*"]',
        filters=None,
        limit: int | None = None,
    ):
        snap = self._snapshot()
        if not (snap["url"] and ((snap["api_key"] and snap["api_secret"]) or (snap["user"] and snap["password"]))):
            return None

        endpoint = f"{snap['url']}/api/resource/{doctype}"
        params: dict[str, Any] = {"fields": fields}
        if limit is not None:
            params["limit_page_length"] = limit

        if filters:
            if isinstance(filters, dict):
                params["filters"] = json.dumps([[doctype, k, "=", v] for k, v in filters.items()])
            elif isinstance(filters, str):
                params["filters"] = filters

        try:
            resp = self.session.get(
                endpoint,
                headers=self.get_headers(is_json=False, snap=snap),
                params=params,
                timeout=API_TIMEOUT_SHORT,
            )
            if resp.status_code == 403 and snap["user"] and snap["password"]:
                if self.login(snap["url"], snap["user"], snap["password"], snap["site"])[0]:
                    snap = self._snapshot()
                    resp = self.session.get(
                        endpoint,
                        headers=self.get_headers(is_json=False, snap=snap),
                        params=params,
                        timeout=API_TIMEOUT_SHORT,
                    )
            if resp.status_code == 200:
                return resp.json().get("data", [])
            return None
        except Exception as e:
            logger.error("fetch_data %s xatosi: %s", doctype, e)
            return None

    # ── method call ────────────────────────────────────────────────────────
    @staticmethod
    def _extract_server_error(resp) -> str:
        """Frappe xato javobidan o'qiladigan xabarni ajratadi.

        Frappe `frappe.throw(...)` da xabarni `_server_messages` (JSON ichida
        JSON ro'yxati) yoki `exception` maydonida qaytaradi. HTML teglari
        tozalanadi.
        """
        import re

        def _clean(text: str) -> str:
            text = re.sub(r"<[^>]+>", " ", str(text or ""))  # HTML teglarni olib tashlash
            return re.sub(r"\s+", " ", text).strip()

        try:
            body = resp.json()
        except (json.JSONDecodeError, ValueError):
            return ""
        if not isinstance(body, dict):
            return ""

        # 1) _server_messages — eng aniq foydalanuvchi xabarlari
        sm = body.get("_server_messages")
        if sm:
            try:
                parts = []
                for raw in json.loads(sm):
                    try:
                        parts.append(_clean(json.loads(raw).get("message", raw)))
                    except (json.JSONDecodeError, ValueError, AttributeError):
                        parts.append(_clean(raw))
                parts = [p for p in parts if p]
                if parts:
                    return "\n".join(parts)
            except (json.JSONDecodeError, ValueError):
                pass

        # 2) exception / message — texnik, lekin baribir foydali
        exc = body.get("exception") or body.get("message")
        if exc:
            cleaned = _clean(exc)
            # "frappe.exceptions.ValidationError: ..." dan keyingi qismni olamiz
            if ": " in cleaned and cleaned.split(":")[0].count(".") >= 1:
                cleaned = cleaned.split(": ", 1)[1]
            return cleaned
        return ""

    def call_method(self, method: str, data=None) -> ApiResponse:
        snap = self._snapshot()
        if not (snap["url"] and ((snap["api_key"] and snap["api_secret"]) or (snap["user"] and snap["password"]))):
            return ApiResponse(False, "API sozlanmagan", 0)

        endpoint = f"{snap['url']}/api/method/{method}"
        try:
            headers = self.get_headers(is_json=True, snap=snap)

            if data is not None:
                resp = self.session.post(
                    endpoint, headers=headers, json=data, timeout=API_TIMEOUT_DEFAULT
                )
            else:
                resp = self.session.get(endpoint, headers=headers, timeout=API_TIMEOUT_DEFAULT)

            if resp.status_code == 403 and snap["user"] and snap["password"]:
                if self.login(snap["url"], snap["user"], snap["password"], snap["site"])[0]:
                    snap = self._snapshot()
                    headers = self.get_headers(is_json=True, snap=snap)
                    if data is not None:
                        resp = self.session.post(
                            endpoint, headers=headers, json=data, timeout=API_TIMEOUT_DEFAULT
                        )
                    else:
                        resp = self.session.get(
                            endpoint, headers=headers, timeout=API_TIMEOUT_DEFAULT
                        )

            status = resp.status_code
            if status == 200:
                try:
                    body = resp.json()
                    return ApiResponse(True, body.get("message", body), status)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error("JSON decode xatosi: %s", e)
                    return ApiResponse(False, "Server noto'g'ri javob qaytardi", status)
            # 200 emas (417 = frappe.throw, 500 va h.k.) — serverning haqiqiy
            # xato xabarini ajratib chiqaramiz, aks holda sabab ko'rinmaydi.
            server_msg = self._extract_server_error(resp)
            if server_msg:
                logger.warning("call_method %s server xatosi (%s): %s", method, status, server_msg)
                return ApiResponse(False, server_msg, status)
            return ApiResponse(False, f"Server xatosi ({status})", status)
        except requests.exceptions.RequestException as e:
            logger.error("call_method %s ulanish xatosi: %s", method, e)
            return ApiResponse(False, f"Server bilan aloqa xatosi: {e}", 0)
        except Exception as e:
            logger.error("call_method %s xatosi: %s", method, e)
            return ApiResponse(False, str(e), 0)
