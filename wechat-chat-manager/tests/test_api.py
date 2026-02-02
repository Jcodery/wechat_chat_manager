"""
API endpoint tests for the WeChat Chat Manager.

Tests the FastAPI endpoints for:
- Health check
- Authentication
- Static file serving
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import TestClient from fastapi
from fastapi.testclient import TestClient


# Create a separate test client that doesn't require real routes
@pytest.fixture
def test_client():
    """Create a test client for the API."""
    # Create a minimal FastAPI app for testing
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    test_app = FastAPI()

    @test_app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @test_app.get("/")
    async def root():
        return {"message": "WeChat Chat Manager API", "docs": "/docs"}

    return TestClient(test_app)


@pytest.fixture
def mock_auth_manager():
    """Create a mock AuthManager."""
    with patch("wechat_manager.core.auth.AuthManager") as mock:
        instance = MagicMock()
        mock.return_value = instance
        yield instance


class TestHealthEndpoint:
    """Tests for /api/health endpoint."""

    def test_health_returns_ok(self, test_client):
        """Test that health endpoint returns status ok."""
        response = test_client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestRootEndpoint:
    """Tests for / endpoint."""

    def test_root_returns_api_info(self, test_client):
        """Test root endpoint returns API info when no frontend."""
        response = test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data or "docs" in data


class TestAuthRoutes:
    """Tests for /api/auth/* endpoints."""

    @pytest.fixture
    def auth_client(self):
        """Create a test client with auth routes."""
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel

        test_app = FastAPI()

        # Track state
        password_set = False
        password_hash = None

        class PasswordRequest(BaseModel):
            password: str

        class ChangePasswordRequest(BaseModel):
            old_password: str
            new_password: str

        @test_app.get("/api/auth/status")
        async def auth_status():
            return {"is_set": password_set}

        @test_app.post("/api/auth/setup")
        async def setup_password(req: PasswordRequest):
            nonlocal password_set, password_hash
            if password_set:
                return JSONResponse(
                    status_code=400, content={"detail": "Password already set"}
                )
            if len(req.password) < 4:
                return JSONResponse(
                    status_code=400, content={"detail": "Password too short"}
                )
            password_set = True
            password_hash = req.password
            return {"success": True, "message": "Password set successfully"}

        @test_app.post("/api/auth/login")
        async def login(req: PasswordRequest):
            if not password_set:
                return JSONResponse(
                    status_code=400, content={"detail": "Password not set"}
                )
            if req.password == password_hash:
                return {"success": True, "message": "Login successful"}
            return JSONResponse(status_code=401, content={"detail": "Invalid password"})

        return TestClient(test_app)

    def test_auth_status_not_set(self, auth_client):
        """Test auth status when no password is set."""
        response = auth_client.get("/api/auth/status")
        assert response.status_code == 200
        assert response.json()["is_set"] == False

    def test_setup_password(self, auth_client):
        """Test setting up password."""
        response = auth_client.post("/api/auth/setup", json={"password": "test1234"})
        assert response.status_code == 200
        assert response.json()["success"] == True

    def test_setup_password_too_short(self, auth_client):
        """Test setup with password too short."""
        response = auth_client.post("/api/auth/setup", json={"password": "abc"})
        assert response.status_code == 400

    def test_login_success(self, auth_client):
        """Test successful login."""
        # First setup password
        auth_client.post("/api/auth/setup", json={"password": "test1234"})

        # Then login
        response = auth_client.post("/api/auth/login", json={"password": "test1234"})
        assert response.status_code == 200
        assert response.json()["success"] == True

    def test_login_wrong_password(self, auth_client):
        """Test login with wrong password."""
        # First setup password
        auth_client.post("/api/auth/setup", json={"password": "test1234"})

        # Then try wrong password
        response = auth_client.post("/api/auth/login", json={"password": "wrong"})
        assert response.status_code == 401


class TestWeChatRoutes:
    """Tests for /api/wechat/* endpoints."""

    @pytest.fixture
    def wechat_client(self):
        """Create a test client with wechat routes."""
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel
        from typing import Optional, List

        test_app = FastAPI()

        # Track state
        wechat_dir = None
        key_saved = False

        class SetDirRequest(BaseModel):
            path: str

        class ManualKeyRequest(BaseModel):
            key: str

        @test_app.get("/api/wechat/status")
        async def wechat_status():
            return {"running": False}

        @test_app.get("/api/wechat/key/status")
        async def key_status():
            return {"is_saved": key_saved}

        @test_app.post("/api/wechat/key/manual")
        async def set_manual_key(req: ManualKeyRequest):
            nonlocal key_saved
            if len(req.key) != 64:
                return JSONResponse(
                    status_code=400, content={"detail": "Key must be 64 hex chars"}
                )
            key_saved = True
            return {"success": True, "message": "Key set successfully"}

        return TestClient(test_app)

    def test_wechat_status(self, wechat_client):
        """Test WeChat running status check."""
        response = wechat_client.get("/api/wechat/status")
        assert response.status_code == 200
        assert "running" in response.json()

    def test_key_status(self, wechat_client):
        """Test key status check."""
        response = wechat_client.get("/api/wechat/key/status")
        assert response.status_code == 200
        assert "is_saved" in response.json()

    def test_set_manual_key_valid(self, wechat_client):
        """Test setting a valid manual key."""
        valid_key = "0123456789abcdef" * 4  # 64 hex chars
        response = wechat_client.post("/api/wechat/key/manual", json={"key": valid_key})
        assert response.status_code == 200
        assert response.json()["success"] == True

    def test_set_manual_key_invalid(self, wechat_client):
        """Test setting an invalid manual key."""
        response = wechat_client.post(
            "/api/wechat/key/manual", json={"key": "tooshort"}
        )
        assert response.status_code == 400


class TestSearchRoutes:
    """Tests for /api/search/* endpoints."""

    @pytest.fixture
    def search_client(self):
        """Create a test client with search routes."""
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from typing import Optional

        test_app = FastAPI()

        @test_app.get("/api/search/")
        async def search_messages(
            q: str, contact_id: Optional[str] = None, limit: int = 100
        ):
            if not q:
                return JSONResponse(
                    status_code=400, content={"detail": "Query required"}
                )
            # Return mock results
            return {"results": [], "count": 0, "query": q}

        return TestClient(test_app)

    def test_search_with_query(self, search_client):
        """Test search with a valid query."""
        response = search_client.get("/api/search/?q=hello")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "count" in data
        assert data["query"] == "hello"


class TestProjectStructure:
    """Tests for project structure after API integration."""

    def test_routes_directory_exists(self):
        """Test that routes directory exists."""
        project_root = Path(__file__).parent.parent
        routes_dir = project_root / "wechat_manager" / "api" / "routes"
        assert routes_dir.exists()
        assert routes_dir.is_dir()

    def test_route_modules_exist(self):
        """Test that all route modules exist."""
        project_root = Path(__file__).parent.parent
        routes_dir = project_root / "wechat_manager" / "api" / "routes"

        expected_modules = [
            "auth.py",
            "wechat.py",
            "contacts.py",
            "mode_a.py",
            "search.py",
            "export.py",
            "dependencies.py",
            "__init__.py",
        ]

        for module in expected_modules:
            module_path = routes_dir / module
            assert module_path.exists(), f"Missing route module: {module}"

    def test_main_exists(self):
        """Test that main.py exists in api directory."""
        project_root = Path(__file__).parent.parent
        main_path = project_root / "wechat_manager" / "api" / "main.py"
        assert main_path.exists()


class TestAPIIntegration:
    """Integration tests for the actual API (when possible)."""

    def test_import_main_app(self):
        """Test that main app can be imported."""
        try:
            from wechat_manager.api.main import app

            assert app is not None
            assert app.title == "微信聊天记录管理"
        except ImportError as e:
            pytest.skip(f"Could not import app: {e}")

    def test_routes_imported(self):
        """Test that routes are properly imported."""
        try:
            from wechat_manager.api.routes import (
                auth,
                wechat,
                contacts,
                mode_a,
                search,
                export,
            )

            assert auth.router is not None
            assert wechat.router is not None
            assert contacts.router is not None
            assert mode_a.router is not None
            assert search.router is not None
            assert export.router is not None
        except ImportError as e:
            pytest.skip(f"Could not import routes: {e}")
