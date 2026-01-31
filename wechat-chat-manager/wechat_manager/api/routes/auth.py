"""
Authentication routes for the WeChat Chat Manager API.

Provides endpoints for password management:
- Check if password is set
- Setup initial password
- Login (verify password)
- Change password
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from wechat_manager.core.auth import AuthManager


router = APIRouter()


class PasswordRequest(BaseModel):
    """Request model for password operations"""

    password: str


class ChangePasswordRequest(BaseModel):
    """Request model for changing password"""

    old_password: str
    new_password: str


class AuthStatusResponse(BaseModel):
    """Response model for auth status"""

    is_set: bool


class AuthSuccessResponse(BaseModel):
    """Response model for successful auth operations"""

    success: bool
    message: str


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status():
    """Check if password is set"""
    auth = AuthManager()
    return {"is_set": auth.is_password_set()}


@router.post("/setup", response_model=AuthSuccessResponse)
async def setup_password(req: PasswordRequest):
    """Set initial password (only works if no password is set)"""
    auth = AuthManager()

    if auth.is_password_set():
        raise HTTPException(
            status_code=400,
            detail="Password is already set. Use /change endpoint to update it.",
        )

    if not req.password or len(req.password) < 4:
        raise HTTPException(
            status_code=400, detail="Password must be at least 4 characters long"
        )

    success = auth.set_password(req.password)
    if success:
        return {"success": True, "message": "Password set successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to set password")


@router.post("/login", response_model=AuthSuccessResponse)
async def login(req: PasswordRequest):
    """Verify password for login"""
    auth = AuthManager()

    if not auth.is_password_set():
        raise HTTPException(
            status_code=400, detail="Password not set. Use /setup endpoint first."
        )

    if auth.verify_password(req.password):
        return {"success": True, "message": "Login successful"}
    else:
        raise HTTPException(status_code=401, detail="Invalid password")


@router.post("/change", response_model=AuthSuccessResponse)
async def change_password(req: ChangePasswordRequest):
    """Change password (requires old password verification)"""
    auth = AuthManager()

    if not auth.is_password_set():
        raise HTTPException(
            status_code=400, detail="Password not set. Use /setup endpoint first."
        )

    if not req.new_password or len(req.new_password) < 4:
        raise HTTPException(
            status_code=400, detail="New password must be at least 4 characters long"
        )

    success = auth.change_password(req.old_password, req.new_password)
    if success:
        return {"success": True, "message": "Password changed successfully"}
    else:
        raise HTTPException(status_code=401, detail="Invalid old password")
