import logging
import random
import string
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from db.postgres import get_conn
from models.roles import Role
from utils.email import send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")

_SESSION_DAYS = 30
_OTP_MINUTES = 10


class RequestOTPBody(BaseModel):
    email: str


class RegisterBody(BaseModel):
    email: str
    name: str


class VerifyOTPBody(BaseModel):
    email: str
    otp: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _gen_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _issue_otp(email: str) -> None:
    otp = _gen_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_OTP_MINUTES)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE otps SET used = TRUE WHERE email = %s AND used = FALSE",
                (email,),
            )
            cur.execute(
                "INSERT INTO otps (email, otp_code, expires_at) VALUES (%s, %s, %s)",
                (email, otp, expires_at),
            )
        conn.commit()

    logger.info("Sending OTP to %s", email)
    send_email(
        email,
        "Your Clinic LM verification code",
        (
            f"Your verification code is: {otp}\n\n"
            f"This code expires in {_OTP_MINUTES} minutes.\n\n"
            "If you did not request this, you can safely ignore this email."
        ),
    )
    logger.info("OTP sent successfully to %s", email)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/request-otp")
def request_otp(body: RequestOTPBody):
    """Check whether an email is registered. Returns status to guide the frontend."""
    email = _normalise_email(body.email)
    logger.info("OTP requested for %s", email)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users WHERE email = %s", (email,))
            exists = cur.fetchone() is not None

    if not exists:
        logger.info("Email %s not registered, prompting registration", email)
        return {"status": "registration_required"}

    try:
        _issue_otp(email)
    except Exception:
        logger.exception("Failed to send OTP to %s", email)
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to send verification code. Please try again."},
        )

    return {"status": "otp_sent"}


@router.post("/register")
def register(body: RegisterBody):
    """Create a new user and send OTP for verification."""
    email = _normalise_email(body.email)
    name = body.name.strip()
    logger.info("Registration attempt for %s", email)

    if not name:
        return JSONResponse(status_code=400, content={"error": "Name is required"})

    user_id = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                return JSONResponse(status_code=409, content={"error": "Email already registered"})
            cur.execute(
                """
                INSERT INTO users (user_id, name, email, role_id, is_verified)
                VALUES (%s, %s, %s, %s, FALSE)
                """,
                (user_id, name, email, Role.FREE),
            )
        conn.commit()

    logger.info("Created user %s for %s", user_id, email)

    try:
        _issue_otp(email)
    except Exception:
        logger.exception("Failed to send OTP to %s after registration", email)
        return JSONResponse(
            status_code=500,
            content={"error": "Account created but failed to send verification code. Please try signing in to resend."},
        )

    return {"status": "otp_sent"}


@router.post("/verify-otp")
def verify_otp(body: VerifyOTPBody, response: Response):
    """Verify OTP, mark user as verified, create session, set cookie."""
    email = _normalise_email(body.email)
    otp = body.otp.strip()
    logger.info("OTP verification attempt for %s", email)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT otp_id FROM otps
                WHERE email = %s AND otp_code = %s AND used = FALSE AND expires_at > NOW()
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (email, otp),
            )
            otp_row = cur.fetchone()
            if not otp_row:
                logger.warning("Invalid or expired OTP for %s", email)
                return JSONResponse(status_code=400, content={"error": "Invalid or expired code"})

            cur.execute("UPDATE otps SET used = TRUE WHERE otp_id = %s", (otp_row[0],))

            cur.execute(
                "SELECT user_id, name, email, role_id FROM users WHERE email = %s",
                (email,),
            )
            user_row = cur.fetchone()
            if not user_row:
                logger.error("OTP valid but user not found for %s", email)
                return JSONResponse(status_code=404, content={"error": "User not found"})

            user_id, name, user_email, role_id = user_row
            cur.execute("UPDATE users SET is_verified = TRUE WHERE user_id = %s", (user_id,))

            session_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            expires = now + timedelta(days=_SESSION_DAYS)
            cur.execute(
                """
                INSERT INTO sessions (session_id, user_id, created_at, expires_at)
                VALUES (%s, %s, %s, %s)
                """,
                (session_id, user_id, now, expires),
            )
        conn.commit()

    logger.info("Session created for user %s (%s)", user_id, email)
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * _SESSION_DAYS,
    )
    return {
        "user_id": str(user_id),
        "name": name,
        "email": user_email,
        "role_id": role_id,
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("session_id")
    return {"ok": True}
