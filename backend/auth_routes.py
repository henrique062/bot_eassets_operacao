"""
Rotas de autenticação: login e dados do usuário atual.
"""

import json
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import database as db
from auth import create_access_token, get_current_user, verify_password

auth_router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: str = Field(..., example="seu@email.com", description="E-mail do usuário")
    password: str = Field(..., example="sua_senha", description="Senha do usuário")


class UserSettingRequest(BaseModel):
    value: object = Field(..., description="Valor da configuração (qualquer JSON)")


@auth_router.post(
    "/login",
    summary="Gerar token JWT",
    response_description="Token Bearer e dados do usuário autenticado",
)
async def login(payload: LoginRequest):
    """
    Autentica com email e senha e retorna o token JWT para usar nas demais rotas.

    **Como usar o token:**
    Adicione o header `Authorization: Bearer <token>` em todas as requisições protegidas.

    O token tem validade de **7 dias**.
    """
    email = (payload.email or "").strip().lower()
    password = payload.password or ""

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email e senha são obrigatórios",
        )

    row = await db.fetchrow(
        "SELECT id, email, password_hash, role, active FROM users WHERE email = $1",
        email,
    )

    if not row or not row["active"] or not verify_password(password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
        )

    token = create_access_token(row["id"], row["email"], row["role"])

    return {
        "success": True,
        "token": token,
        "user": {
            "id": row["id"],
            "email": row["email"],
            "role": row["role"],
        },
    }


@auth_router.get("/me", summary="Dados do usuário autenticado")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Retorna id, email e role do usuário dono do token Bearer informado."""
    row = await db.fetchrow(
        "SELECT id, email, role, created_at FROM users WHERE id = $1",
        current_user["id"],
    )
    return {
        "success": True,
        "user": {
            "id": row["id"],
            "email": row["email"],
            "role": row["role"],
            "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
        },
    }


@auth_router.get("/settings", summary="Listar configurações do usuário")
async def get_user_settings(current_user: dict = Depends(get_current_user)):
    """Retorna todas as configurações salvas do usuário, incluindo chaves de API da Binance/Bybit."""
    rows = await db.fetch(
        "SELECT key, value, description FROM user_settings WHERE user_id = $1",
        current_user["id"],
    )
    settings = {}
    for r in rows:
        settings[r["key"]] = {
            "value": r["value"] if isinstance(r["value"], dict) else json.loads(r["value"]),
            "description": r["description"],
        }
    return {"success": True, "settings": settings}


@auth_router.put("/settings/{key}", summary="Salvar configuração do usuário")
async def update_user_setting(
    key: str,
    payload: UserSettingRequest,
    current_user: dict = Depends(get_current_user),
):
    """Salva ou atualiza uma configuração do usuário (ex: chaves de API da Binance)."""
    json_val = json.dumps(payload.value)
    await db.execute(
        """
        INSERT INTO user_settings (user_id, key, value)
        VALUES ($1, $2, $3::jsonb)
        ON CONFLICT (user_id, key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = NOW()
        """,
        current_user["id"], key, json_val,
    )
    return {"success": True, "message": f"Configuração '{key}' atualizada"}
