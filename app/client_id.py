import re
from typing import Optional

CLIENT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_client_id(raw: Optional[str]) -> str:
    if raw is None:
        return ""
    value = raw.strip()
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r"[_\s]+", "-", value)
    value = re.sub(r"[^a-z0-9-]", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value


def is_canonical_client_id(value: Optional[str]) -> bool:
    if not value:
        return False
    return bool(CLIENT_ID_PATTERN.fullmatch(value))
