"""
tests/conftest.py — Shared pytest fixtures.
"""
import os
import tempfile
import pytest

# Use an in-memory (temp-file) database for tests
@pytest.fixture(autouse=True, scope="session")
def test_db():
    """Point the config at a temp database for the whole test session."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["DATABASE_PATH"] = tmp.name
    # Re-import config + init db
    import importlib
    import config as cfg
    importlib.reload(cfg)
    from database.db import init_db, close_connection
    init_db()
    yield tmp.name
    # Close thread-local connections before deleting on Windows
    close_connection()
    try:
        os.unlink(tmp.name)
    except PermissionError:
        pass  # Windows: file still held by other threads; will be cleaned by OS


@pytest.fixture()
def app():
    os.environ.setdefault("DATABASE_PATH", "instance/test_jarvis.db")
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()
