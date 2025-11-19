"""
Authentication Router

Endpoints for user authentication and token management.
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from src.wholesaler.api.auth import (
    authenticate_user,
    create_access_token,
    get_current_active_user,
    fake_users_db,
    Token,
    User,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 compatible token login.

    Args:
        form_data: Username and password from OAuth2 form

    Returns:
        Access token and token type

    Raises:
        HTTPException: If authentication fails
    """
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """
    Get current user information.

    Args:
        current_user: Current authenticated user

    Returns:
        Current user details
    """
    return current_user


@router.get("/users/me/items")
async def read_own_items(current_user: User = Depends(get_current_active_user)):
    """
    Get current user's items (example endpoint).

    Args:
        current_user: Current authenticated user

    Returns:
        User-specific data
    """
    return [{"item_id": "Foo", "owner": current_user.username}]
