"""Admin and user management endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import auth
import database
from settings import get_settings

from .deps import get_current_admin

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================


class AdminCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class PasswordChange(BaseModel):
    password: str = Field(..., min_length=6)


class AdminResponse(BaseModel):
    id: int
    username: str
    created_at: str
    last_login: Optional[str]


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    is_admin: bool = False


class UserUpdate(BaseModel):
    is_admin: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    username: str
    is_admin: bool
    created_at: str
    last_login: Optional[str]


# =============================================================================
# Admin Management API
# =============================================================================


@router.get("/api/admins", response_model=List[AdminResponse])
async def list_admins(admin: dict = Depends(get_current_admin)):
    """List all admin users."""
    admins = database.get_all_admins()
    return [
        AdminResponse(id=a["id"], username=a["username"], created_at=a["created_at"] or "", last_login=a["last_login"])
        for a in admins
    ]


@router.post("/api/admins", response_model=AdminResponse)
async def create_admin(data: AdminCreate, admin: dict = Depends(get_current_admin)):
    """Create a new admin user."""
    # Check if username exists
    existing = database.get_admin_by_username(data.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    password_hash = auth.hash_password(data.password)
    admin_id = database.create_admin(data.username, password_hash)

    new_admin = database.get_admin_by_id(admin_id)
    return AdminResponse(
        id=new_admin["id"],
        username=new_admin["username"],
        created_at=new_admin["created_at"] or "",
        last_login=new_admin["last_login"],
    )


@router.delete("/api/admins/{admin_id}")
async def delete_admin(admin_id: int, admin: dict = Depends(get_current_admin)):
    """Delete an admin user."""
    if admin_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    if database.count_admins() <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last admin")

    if not database.delete_admin(admin_id):
        raise HTTPException(status_code=404, detail="Admin not found")

    return {"success": True}


@router.put("/api/admins/{admin_id}/password")
async def change_password(admin_id: int, data: PasswordChange, admin: dict = Depends(get_current_admin)):
    """Change an admin's password."""
    target_admin = database.get_admin_by_id(admin_id)
    if not target_admin:
        raise HTTPException(status_code=404, detail="Admin not found")

    password_hash = auth.hash_password(data.password)
    database.update_admin_password(admin_id, password_hash)

    return {"success": True}


@router.get("/api/user/me")
async def get_current_user(request: Request):
    """Get current authenticated user info (any user, not just admin)."""
    basic_auth_user = getattr(request.state, "user", None)
    if not basic_auth_user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="Yattee Server"'},
        )
    app_settings = get_settings()
    enabled_sites = database.get_enabled_sites()
    extraction_info = {
        "allow_all_sites": app_settings.allow_all_sites_for_extraction,
        "enabled_sites": [site["name"] for site in enabled_sites],
    }

    return {
        "id": basic_auth_user["id"],
        "username": basic_auth_user["username"],
        "is_admin": basic_auth_user.get("is_admin", False),
        "extraction_info": extraction_info,
    }


# =============================================================================
# User Management API
# =============================================================================


@router.get("/api/users", response_model=List[UserResponse])
async def list_users(admin: dict = Depends(get_current_admin)):
    """List all users."""
    users = database.get_all_users()
    return [
        UserResponse(
            id=u["id"],
            username=u["username"],
            is_admin=bool(u["is_admin"]),
            created_at=u["created_at"] or "",
            last_login=u["last_login"],
        )
        for u in users
    ]


@router.post("/api/users", response_model=UserResponse)
async def create_user(data: UserCreate, admin: dict = Depends(get_current_admin)):
    """Create a new user."""
    # Check if username exists
    existing = database.get_user_by_username(data.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    password_hash = auth.hash_password(data.password)
    user_id = database.create_user(data.username, password_hash, is_admin=data.is_admin)

    new_user = database.get_user_by_id(user_id)
    return UserResponse(
        id=new_user["id"],
        username=new_user["username"],
        is_admin=bool(new_user["is_admin"]),
        created_at=new_user["created_at"] or "",
        last_login=new_user["last_login"],
    )


@router.get("/api/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, admin: dict = Depends(get_current_admin)):
    """Get a user by ID."""
    user = database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=user["id"],
        username=user["username"],
        is_admin=bool(user["is_admin"]),
        created_at=user["created_at"] or "",
        last_login=user["last_login"],
    )


@router.put("/api/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, data: UserUpdate, admin: dict = Depends(get_current_admin)):
    """Update a user's properties."""
    user = database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent removing admin from self
    if user_id == admin["id"] and data.is_admin is False:
        raise HTTPException(status_code=400, detail="Cannot remove admin privileges from yourself")

    # Prevent removing the last admin
    if data.is_admin is False and user["is_admin"]:
        if database.count_admin_users() <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last admin")

    if data.is_admin is not None:
        database.update_user(user_id, is_admin=data.is_admin)

    updated_user = database.get_user_by_id(user_id)
    return UserResponse(
        id=updated_user["id"],
        username=updated_user["username"],
        is_admin=bool(updated_user["is_admin"]),
        created_at=updated_user["created_at"] or "",
        last_login=updated_user["last_login"],
    )


@router.delete("/api/users/{user_id}")
async def delete_user(user_id: int, admin: dict = Depends(get_current_admin)):
    """Delete a user."""
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    user = database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent deleting the last admin
    if user["is_admin"] and database.count_admin_users() <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last admin")

    if not database.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    return {"success": True}


@router.put("/api/users/{user_id}/password")
async def change_user_password(user_id: int, data: PasswordChange, admin: dict = Depends(get_current_admin)):
    """Change a user's password."""
    user = database.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    password_hash = auth.hash_password(data.password)
    database.update_user_password(user_id, password_hash)

    return {"success": True}
