# API timeouts (seconds)
API_TIMEOUT_SHORT = 5
API_TIMEOUT_DEFAULT = 10
API_TIMEOUT_LONG = 15
IMAGE_TIMEOUT = 5

# Database
ITEM_LOAD_LIMIT = 100
CUSTOMER_SYNC_LIMIT = 1000
# Band smenada 50 ta chek tez to'lib qoladi — eski cheklar ko'rinmay,
# bekor qilib bo'lmay qolardi.
HISTORY_FETCH_LIMIT = 200

# Offline sync interval (seconds)
OFFLINE_SYNC_INTERVAL = 30

# Monitor interval (milliseconds)
MONITOR_INTERVAL_MS = 10000

# Default values
DEFAULT_CURRENCY = "UZS"
DEFAULT_CUSTOMER = "guest"
DEFAULT_UOM = "Dona"
DEFAULT_PRICE_LIST = "Standard"

# Order types that require ticket number
TICKET_ORDER_TYPES = ["Shu yerda", "Saboy"]

# All order types
ORDER_TYPES = ["Shu yerda", "Saboy", "Dastavka", "Dastavka Saboy"]
