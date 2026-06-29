from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from db.postgres import get_conn
from dependencies import get_current_user, require_admin
from models.roles import ROLE_DEFINITIONS, get_all_roles

router = APIRouter(prefix="/users")


@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    return user


@router.get("/roles")
def list_roles():
    return get_all_roles()


@router.get("")
def list_users(admin: dict = Depends(require_admin)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, name, email, role_id, is_verified, created_at
                FROM users
                WHERE email IS NOT NULL
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()
    return [
        {
            "user_id": str(r[0]),
            "name": r[1],
            "email": r[2],
            "role_id": r[3],
            "is_verified": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]


class UpdateUserBody(BaseModel):
    name: str | None = None
    role_id: int | None = None


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    body: UpdateUserBody,
    admin: dict = Depends(require_admin),
):
    if body.role_id is not None and body.role_id not in ROLE_DEFINITIONS:
        return JSONResponse(status_code=400, content={"error": "Invalid role"})

    updates: list[str] = []
    values: list = []
    if body.name is not None:
        updates.append("name = %s")
        values.append(body.name.strip())
    if body.role_id is not None:
        updates.append("role_id = %s")
        values.append(body.role_id)

    if not updates:
        return JSONResponse(status_code=400, content={"error": "No fields to update"})

    values.append(user_id)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE user_id = %s AND email IS NOT NULL",
                values,
            )
            if cur.rowcount == 0:
                return JSONResponse(status_code=404, content={"error": "User not found"})
        conn.commit()
    return {"ok": True}


@router.delete("/{user_id}")
def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["user_id"]:
        return JSONResponse(status_code=400, content={"error": "Cannot delete your own account"})

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM users WHERE user_id = %s AND email IS NOT NULL",
                (user_id,),
            )
            if cur.rowcount == 0:
                return JSONResponse(status_code=404, content={"error": "User not found"})
        conn.commit()
    return {"ok": True}
