import os
import re
from datetime import datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv

from database import supabase

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET is missing. Please add it to backend/.env")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str):
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"

    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")

    if not re.match(pattern, email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")


def validate_password(password: str):
    if not password:
        raise HTTPException(status_code=400, detail="Password is required.")

    password_bytes = password.encode("utf-8")

    if len(password_bytes) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long."
        )

    if len(password_bytes) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password cannot be longer than 72 characters."
        )


def hash_password(password: str) -> str:
    validate_password(password)
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if len(plain.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password cannot be longer than 72 characters."
        )

    return pwd_context.verify(plain, hashed)


def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)

    payload = {
        "sub": user_id,
        "exp": expire
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        return user_id

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def register_user(username: str, email: str, password: str):
    username = username.strip()
    email = normalize_email(email)

    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")

    validate_email(email)
    validate_password(password)

    try:
        existing = (
            supabase
            .table("users")
            .select("id")
            .eq("email", email)
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=409,
                detail="Email already registered. Please sign in instead."
            )

        hashed = hash_password(password)

        result = (
            supabase
            .table("users")
            .insert({
                "username": username,
                "email": email,
                "password_hash": hashed
            })
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=500,
                detail="Could not create user. Please try again."
            )

        return result.data[0]

    except HTTPException:
        raise

    except Exception as e:
        error_msg = str(e).lower()

        if "duplicate" in error_msg or "already" in error_msg:
            raise HTTPException(
                status_code=409,
                detail="Email already registered. Please sign in instead."
            )

        raise HTTPException(
            status_code=500,
            detail=f"Registration failed: {str(e)}"
        )


def login_user(email: str, password: str):
    email = normalize_email(email)

    validate_email(email)

    if not password:
        raise HTTPException(status_code=400, detail="Password is required.")

    if len(password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=400,
            detail="Password cannot be longer than 72 characters."
        )

    try:
        result = (
            supabase
            .table("users")
            .select("*")
            .eq("email", email)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=401, detail="User not found.")

        user = result.data[0]

        if not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Wrong password.")

        token = create_token(str(user["id"]))

        return {
            "token": token,
            "username": user["username"],
            "user_id": user["id"]
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Login failed: {str(e)}"
        )