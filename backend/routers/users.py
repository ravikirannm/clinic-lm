import uuid
from fastapi import APIRouter, Request, Response
from db.postgres import get_conn

router = APIRouter(prefix="/users")


@router.get("/me")
def get_me(request: Request, response: Response):
    raw = request.cookies.get("user_id")

    if raw:
        try:
            uid = str(uuid.UUID(raw))  # validate & normalise format
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT user_id FROM users WHERE user_id = %s", (uid,))
                    if cur.fetchone():
                        return {"user_id": uid}
        except ValueError:
            pass  # malformed cookie — fall through to create a new user

    new_id = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users (user_id) VALUES (%s)", (new_id,))
        conn.commit()

    response.set_cookie(
        key="user_id",
        value=new_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 365,  # 1 year
    )
    return {"user_id": new_id}
