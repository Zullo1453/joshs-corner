"""Small, transactional ordering helper for locally saved Intelligence items."""
from __future__ import annotations

from sqlalchemy import func, select

from .extensions import db


VALID_MOVE_ACTIONS = frozenset({"up", "down", "top", "bottom"})


def active_items(model, *tie_breakers):
    """Return the stable visible order without changing existing records."""
    return db.session.scalars(
        select(model).where(model.active).order_by(model.sort_order, *tie_breakers)
    ).all()


def next_sort_order(model) -> int:
    current_maximum = db.session.scalar(select(func.max(model.sort_order)).where(model.active))
    return 0 if current_maximum is None else current_maximum + 1


def normalize_active_items(model, *tie_breakers) -> None:
    for position, item in enumerate(active_items(model, *tie_breakers)):
        item.sort_order = position


def move_active_item(model, item_id: int, action: str, *tie_breakers) -> bool:
    """Move one active item, normalising positions in the same transaction."""
    if action not in VALID_MOVE_ACTIONS:
        raise ValueError("Unsupported ordering action")
    items = active_items(model, *tie_breakers)
    index = next((position for position, item in enumerate(items) if item.id == item_id), None)
    if index is None:
        raise LookupError("Saved item not found")
    target = {
        "up": index - 1,
        "down": index + 1,
        "top": 0,
        "bottom": len(items) - 1,
    }[action]
    if target < 0 or target >= len(items) or target == index:
        return False
    item = items.pop(index)
    items.insert(target, item)
    for position, item in enumerate(items):
        item.sort_order = position
    db.session.commit()
    return True
