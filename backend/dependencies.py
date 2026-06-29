from fastapi import Depends, HTTPException, Request
from db.postgres import get_conn
from models.roles import Role


def get_current_user(request: Request) -> dict:
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.user_id, u.name, u.email, u.role_id
                FROM sessions s
                JOIN users u ON u.user_id = s.user_id
                WHERE s.session_id = %s AND s.expires_at > NOW()
                """,
                (session_id,),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return {
        "user_id": str(row[0]),
        "name": row[1],
        "email": row[2],
        "role_id": row[3],
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role_id"] != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
