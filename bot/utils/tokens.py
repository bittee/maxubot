"""Короткі токени для callback-кнопок (callback_data обмежено 64 байтами)."""
import secrets
from collections import OrderedDict


class TokenStore:
    """In-memory сховище token -> url з обмеженням розміру."""

    def __init__(self, max_size: int = 2000):
        self._data: OrderedDict[str, str] = OrderedDict()
        self._max = max_size

    def put(self, url: str) -> str:
        token = secrets.token_urlsafe(9)
        self._data[token] = url
        while len(self._data) > self._max:
            self._data.popitem(last=False)
        return token

    def get(self, token: str) -> str | None:
        return self._data.get(token)


token_store = TokenStore()
