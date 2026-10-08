"""
PriceSense database package.

Exposes the connection/session helpers and ORM models so the rest of the
application can do `from database import init_db, get_session` etc. without
reaching into submodules directly. Repository functions (CRUD operations)
live in `database.repositories` and are imported explicitly where needed.
"""

from database.db import get_engine, get_session, init_db
from database.models import Alert, Base, PriceObservation, Product, Tracking

__all__ = [
    "init_db",
    "get_engine",
    "get_session",
    "Base",
    "Product",
    "PriceObservation",
    "Tracking",
    "Alert",
]
