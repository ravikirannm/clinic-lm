from enum import IntEnum


class Role(IntEnum):
    FREE = 1
    PREMIUM = 2
    ADMIN = 3


ROLE_DEFINITIONS: dict[int, dict] = {
    Role.FREE: {"id": 1, "name": "free", "label": "Free User"},
    Role.PREMIUM: {"id": 2, "name": "premium", "label": "Premium User"},
    Role.ADMIN: {"id": 3, "name": "admin", "label": "Admin User"},
}


def get_all_roles() -> list[dict]:
    return list(ROLE_DEFINITIONS.values())
