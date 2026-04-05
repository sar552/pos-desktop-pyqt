import base64
import os
import re
from urllib.parse import urlparse

import requests

from core.logger import get_logger
from core.paths import BASE_DIR

logger = get_logger(__name__)

_LOGO_FIELD_CANDIDATES = ("picture", "company_logo", "logo", "image")
_LOGO_URL_KEYS = ("company_logo_url", "company_picture_url", "company_logo", "company_picture")
_LOGO_PATH_KEYS = ("company_logo_local_path", "company_picture_local_path")
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

LOGO_CACHE_DIR = os.path.join(BASE_DIR, ".cache", "branding")


def _first_non_empty(data: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_logo_url(logo_url: str) -> str:
    if not isinstance(logo_url, str):
        return ""
    normalized = logo_url.strip()
    if not normalized:
        return ""
    if normalized.startswith(("http://", "https://")):
        return normalized
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def _build_logo_download_url(base_url: str, logo_url: str) -> str:
    if logo_url.startswith(("http://", "https://")):
        return logo_url
    return f"{base_url.rstrip('/')}{logo_url}"


def _safe_company_name(company_name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", (company_name or "").strip()).strip("_")
    return safe or "company"


def extract_company_logo_url(company_payload: dict | None) -> str:
    if not isinstance(company_payload, dict):
        return ""
    return _normalize_logo_url(_first_non_empty(company_payload, _LOGO_FIELD_CANDIDATES))


def fetch_company_logo_url(api, company_name: str, company_payload: dict | None = None) -> str:
    logo_url = extract_company_logo_url(company_payload)
    if logo_url:
        return logo_url

    name = (company_name or "").strip()
    if not name:
        return ""

    success, response = api.call_method(
        "frappe.client.get",
        {"doctype": "Company", "name": name},
    )
    if not success:
        logger.warning("Company ma'lumotini olib bo'lmadi: %s", response)
        return ""
    return extract_company_logo_url(response if isinstance(response, dict) else {})


def download_company_logo(api, logo_url: str, company_name: str = "") -> str:
    normalized_url = _normalize_logo_url(logo_url)
    if not normalized_url:
        return ""

    os.makedirs(LOGO_CACHE_DIR, exist_ok=True)
    parsed_url = urlparse(normalized_url)
    extension = os.path.splitext(parsed_url.path)[1].lower()
    if extension not in _IMAGE_EXTENSIONS:
        extension = ".png"

    local_path = os.path.join(LOGO_CACHE_DIR, f"{_safe_company_name(company_name)}_logo{extension}")
    full_url = _build_logo_download_url(api.url, normalized_url)
    headers = api.get_headers(is_json=False)

    try:
        response = api.session.get(full_url, headers=headers, timeout=20)
        if response.status_code == 403 and api.user and api.password:
            login_ok, _ = api.login(api.url, api.user, api.password, api.site)
            if login_ok:
                response = api.session.get(full_url, headers=headers, timeout=20)

        if response.status_code != 200:
            logger.warning("Company rasmi yuklab bo'lmadi (%s): %s", response.status_code, full_url)
            return ""

        if not response.content:
            logger.warning("Company rasmi bo'sh keldi: %s", full_url)
            return ""

        with open(local_path, "wb") as logo_file:
            logo_file.write(response.content)
        return local_path
    except requests.RequestException as error:
        logger.error("Company rasmini yuklashda tarmoq xatosi: %s", error)
        return ""
    except OSError as error:
        logger.error("Company rasmini saqlashda xatolik: %s", error)
        return ""


def update_company_logo_config(api, config: dict, company_name: str = "", company_payload: dict | None = None) -> tuple[str, str]:
    if not isinstance(config, dict):
        return "", ""

    existing_url = _normalize_logo_url(_first_non_empty(config, _LOGO_URL_KEYS))
    existing_path = _first_non_empty(config, _LOGO_PATH_KEYS)

    selected_company = (company_name or config.get("company", "") or "").strip()
    fetched_url = fetch_company_logo_url(api, selected_company, company_payload)
    logo_url = fetched_url or existing_url

    local_path = ""
    if existing_path and os.path.exists(existing_path):
        local_path = existing_path

    needs_download = bool(logo_url and (not local_path or logo_url != existing_url))
    if needs_download:
        downloaded_path = download_company_logo(api, logo_url, selected_company)
        if downloaded_path:
            local_path = downloaded_path

    config["company_logo_url"] = logo_url
    config["company_logo_local_path"] = local_path
    return logo_url, local_path


def get_cached_company_logo_path(config: dict | None = None) -> str:
    if not isinstance(config, dict):
        return ""
    for key in _LOGO_PATH_KEYS:
        path = config.get(key)
        if isinstance(path, str) and path and os.path.exists(path):
            return path
    return ""


def get_company_logo_data_uri(config: dict | None = None) -> str:
    logo_path = get_cached_company_logo_path(config)
    if not logo_path:
        return ""

    extension = os.path.splitext(logo_path)[1].lower()
    mime = _MIME_BY_EXT.get(extension, "image/png")

    try:
        with open(logo_path, "rb") as logo_file:
            encoded = base64.b64encode(logo_file.read()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except OSError as error:
        logger.error("Company rasmini o'qishda xatolik: %s", error)
        return ""
