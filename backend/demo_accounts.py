"""Local-only demo accounts. Never enable this feature on a public deployment."""

DEMO_USERS = [
    {
        "email": "demo1@foodcal.test",
        "display_name": "FoodCal Demo 1",
        "password": "FoodCalDemo1!",
    },
    {
        "email": "demo2@foodcal.test",
        "display_name": "FoodCal Demo 2",
        "password": "FoodCalDemo2!",
    },
    {
        "email": "demo3@foodcal.test",
        "display_name": "FoodCal Demo 3",
        "password": "FoodCalDemo3!",
    },
]


def demo_login_enabled() -> bool:
    import os

    return os.getenv("DEMO_LOGIN_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"}
