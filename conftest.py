import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import socket
import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Regressionstester får aldrig kontakta nätverkstjänster."""
    def blocked(*args, **kwargs):
        raise AssertionError("Nätverksåtkomst är förbjuden i testsviten")
    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setattr(socket.socket, 'connect_ex', blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
