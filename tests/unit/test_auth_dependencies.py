from typing import List, Tuple

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fakeredis import aioredis as fakeredis
from starlette.applications import Starlette
from starlette.requests import Request

import dependencies.auth_dependencies as auth_deps
from services.redis.sessions import SessionService


class MockResponse:
    def __init__(self, status_code: int = 200, data: dict | None = None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data


class MockAsyncClient:
    def __init__(self, response: MockResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, headers=None):
        return self._response


def _build_request(app: Starlette, headers: List[Tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/test",
        "headers": headers or [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "app": app,
    }

    async def receive():
        return {"type": "http.request"}

    return Request(scope, receive)


@pytest.fixture(autouse=True)
def configure_supabase(monkeypatch):
    """Configure Supabase settings for tests."""
    monkeypatch.setattr(auth_deps, "SUPABASE_URL", "https://supabase.test")
    monkeypatch.setattr(auth_deps, "SUPABASE_KEY", "test_key")


@pytest.fixture
def mock_supabase(monkeypatch):
    """Mock Supabase user fetch to return a static user."""
    response = MockResponse(data={"id": "user_123", "email": "user@example.com"})

    def client_factory(*args, **kwargs):
        return MockAsyncClient(response)

    monkeypatch.setattr(auth_deps.httpx, "AsyncClient", client_factory)
    return response


@pytest.fixture
async def redis_client():
    client = await fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.close()


@pytest.fixture
def credentials():
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="token_abc")


@pytest.mark.asyncio
async def test_get_current_user_id_valid_session(mock_supabase, redis_client, credentials):
    session_service = SessionService(redis_client)
    session_id = await session_service.create_session(
        user_id="user_123",
        device_type="browser",
        ip_address="10.0.0.1",
        user_agent="Mozilla/5.0",
    )

    # Short TTL to verify refresh extends it
    await redis_client.expire("user_sessions:user_123", 300)

    app = Starlette()
    app.state.redis = redis_client
    headers = [(auth_deps.SESSION_HEADER.lower().encode(), session_id.encode())]
    request = _build_request(app, headers=headers)

    user_id = await auth_deps.get_current_user_id(request, credentials)

    assert user_id == "user_123"
    assert getattr(request.state, "session_id") == session_id

    ttl = await redis_client.ttl("user_sessions:user_123")
    assert ttl > 300


@pytest.mark.asyncio
async def test_get_current_user_id_missing_session(mock_supabase, redis_client, credentials):
    session_service = SessionService(redis_client)
    await session_service.create_session(user_id="user_123", device_type="browser")

    app = Starlette()
    app.state.redis = redis_client
    request = _build_request(app)

    with pytest.raises(HTTPException) as exc_info:
        await auth_deps.get_current_user_id(request, credentials)

    assert exc_info.value.status_code == 401
    assert "Session" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_id_invalid_session(mock_supabase, redis_client, credentials):
    app = Starlette()
    app.state.redis = redis_client
    headers = [(auth_deps.SESSION_HEADER.lower().encode(), b"sess_invalid")]
    request = _build_request(app, headers=headers)

    with pytest.raises(HTTPException) as exc_info:
        await auth_deps.get_current_user_id(request, credentials)

    assert exc_info.value.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_current_user_id_redis_unavailable(mock_supabase, credentials):
    app = Starlette()
    app.state.redis = None
    headers: List[Tuple[bytes, bytes]] = []
    request = _build_request(app, headers=headers)

    user_id = await auth_deps.get_current_user_id(request, credentials)
    assert user_id == "user_123"
    assert getattr(request.state, "session_validated", False) is True


@pytest.mark.asyncio
async def test_get_current_user_token_uses_cached_auth(mock_supabase, redis_client, credentials, monkeypatch):
    session_service = SessionService(redis_client)
    session_id = await session_service.create_session(user_id="user_123", device_type="browser")

    app = Starlette()
    app.state.redis = redis_client
    headers = [(auth_deps.SESSION_HEADER.lower().encode(), session_id.encode())]
    request = _build_request(app, headers=headers)

    # First call to cache authentication
    await auth_deps.get_current_user_id(request, credentials)

    calls = {"count": 0}

    class CountingClient(MockAsyncClient):
        async def get(self, url: str, headers=None):
            calls["count"] += 1
            return await super().get(url, headers=headers)

    def counting_factory(*args, **kwargs):
        return CountingClient(MockResponse(data={"id": "user_123"}))

    monkeypatch.setattr(auth_deps.httpx, "AsyncClient", counting_factory)

    token = await auth_deps.get_current_user_token(request, credentials)

    assert token == "token_abc"
    assert calls["count"] == 0  # Cached result prevents extra Supabase calls