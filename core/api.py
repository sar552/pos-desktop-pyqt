import json
import threading
import requests
from core.config import load_config
from core.logger import get_logger
from core.constants import API_TIMEOUT_SHORT, API_TIMEOUT_DEFAULT

logger = get_logger(__name__)

class FrappeAPI:
    def __init__(self):
        self.session = requests.Session()
        self._lock = threading.Lock()
        self.reload_config()

    def reload_config(self):
        config = load_config()
        self.url = config.get("serverUrl", "").rstrip("/")
        self.site = config.get("site", "")
        self.api_key = config.get("apiKey", "")
        self.api_secret = config.get("apiSecret", "")
        self.user = config.get("user", "")
        self.password = config.get("password", "")

    def get_headers(self, is_json=True) -> dict:
        headers = {
            "Accept": "application/json",
        }
        
        # Multi-site uchun sayt nomi
        if self.site:
            headers["X-Frappe-Site-Name"] = self.site
            
        if self.api_key and self.api_secret:
            headers["Authorization"] = f"token {self.api_key}:{self.api_secret}"
            
        if is_json:
            headers["Content-Type"] = "application/json"
        return headers

    def is_configured(self) -> bool:
        # Password may be intentionally not persisted; active session cookie can still authorize.
        return bool(self.url and (self.api_key and self.api_secret or self.user))

    def login_with_password(self, url: str, usr: str, pwd: str, site: str = "") -> tuple[bool, str, dict]:
        """Username va Password orqali login qilish"""
        login_url = f"{url.rstrip('/')}/api/method/login"
        payload = {"usr": usr, "pwd": pwd}
        headers = {"Accept": "application/json"}
        
        if site:
            headers["X-Frappe-Site-Name"] = site
            
        try:
            response = self.session.post(login_url, data=payload, headers=headers, timeout=API_TIMEOUT_DEFAULT)
            if response.status_code == 200:
                self.url = url.rstrip("/")
                self.user = usr
                self.password = pwd
                self.site = site
                logger.info("Login muvaffaqiyatli: %s (Site: %s)", usr, site)
                return True, "Success", response.json()
            else:
                logger.warning("Login xatosi: %d - %s", response.status_code, response.text)
                return False, "Login yoki parol noto'g'ri", {}
        except requests.exceptions.RequestException as e:
            logger.error("Login ulanish xatosi: %s", e)
            return False, "Server bilan aloqa o'rnatib bo'lmadi", {}

    def fetch_data(self, doctype: str, fields: str = '["*"]', filters=None, limit: int = 0):
        if not self.is_configured():
            return None
        endpoint = f"{self.url}/api/resource/{doctype}"
        params = {"fields": fields, "limit_page_length": limit}
        if filters:
            if isinstance(filters, dict):
                filter_list = [[doctype, k, "=", v] for k, v in filters.items()]
                params["filters"] = json.dumps(filter_list)
            elif isinstance(filters, str):
                params["filters"] = filters
                
        try:
            with self._lock:
                response = self.session.get(endpoint, headers=self.get_headers(is_json=False), params=params, timeout=API_TIMEOUT_SHORT)
                if response.status_code == 200:
                    return response.json().get("data", [])
                
                # Agar 403 bo'lsa, qayta login qilishga urinish (faqat parol bilan)
                if response.status_code == 403 and self.user and self.password:
                    if self.login_with_password(self.url, self.user, self.password, self.site)[0]:
                        response = self.session.get(endpoint, headers=self.get_headers(is_json=False), params=params, timeout=API_TIMEOUT_SHORT)
                        if response.status_code == 200:
                            return response.json().get("data", [])
                return None
        except Exception as e:
            logger.error("fetch_data %s xatosi: %s", doctype, e)
            return None

    def call_method(self, method: str, data=None) -> tuple[bool, object]:
        if not self.is_configured():
            return False, "API sozlanmagan"
        endpoint = f"{self.url}/api/method/{method}"
        try:
            headers = self.get_headers(is_json=True)
            with self._lock:
                if data is not None:
                    response = self.session.post(endpoint, headers=headers, json=data, timeout=API_TIMEOUT_DEFAULT)
                else:
                    response = self.session.get(endpoint, headers=headers, timeout=API_TIMEOUT_DEFAULT)
            
            # Agar 403 bo'lsa, qayta login qilishga urinish
            if response.status_code == 403 and self.user and self.password:
                if self.login_with_password(self.url, self.user, self.password, self.site)[0]:
                    with self._lock:
                        if data is not None:
                            response = self.session.post(endpoint, headers=headers, json=data, timeout=API_TIMEOUT_DEFAULT)
                        else:
                            response = self.session.get(endpoint, headers=headers, timeout=API_TIMEOUT_DEFAULT)

            if response.status_code == 200:
                try:
                    result = response.json()
                    return True, result.get("message") or result.get("data") or result
                except json.JSONDecodeError:
                    return True, response.text
            else:
                logger.warning("API xatosi %s: %s", method, response.text)
                return False, f"Server xatosi: {response.status_code}"
        except Exception as e:
            logger.error("call_method xatosi %s: %s", method, e)
            return False, str(e)
