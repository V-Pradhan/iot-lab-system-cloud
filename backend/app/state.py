"""Small in-memory helpers. The server runs as one process, so plain dictionaries are enough."""
armed: dict = {}         # lab_id -> {"mode": "register"|"lookup", "until": unix time}
latest_msg: dict = {}    # lab_id -> newest DeviceMessage id (lets the reader poll without a database query)
device_cache: dict = {}  # device_id -> (expires_at, {"lab_id", "key_hash", "active"})
rate: dict = {}          # key -> list of timestamps (public registration limits)
