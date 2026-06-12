"""
Módulo de autenticação JWT para o backend.
Gerencia hash de senhas, geração e validação de tokens.
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

import database as db

# ──────────────────────────────────────────────────────────────
# Configuração
# ──────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("JWT_SECRET", "b7f3e2a1d4c8f9e0b6a5d3c7f1e4a2b8d5c9f0e3a1b7d4c8f2e5a3b9d6c0f4")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 dias

bearer_scheme = HTTPBearer(auto_error=False)


# ──────────────────────────────────────────────────────────────
# Utilitários de senha e token
# ──────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    """Verifica se a senha plain corresponde ao hash armazenado (bcrypt $2a$ ou $2b$)."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def hash_password(plain: str) -> str:
    """Gera hash bcrypt de uma senha."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def create_access_token(user_id: int, email: str, role: str) -> str:
    """Gera um token JWT com validade de ACCESS_TOKEN_EXPIRE_HOURS horas."""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decodifica e valida um token JWT. Lança JWTError se inválido."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ──────────────────────────────────────────────────────────────
# Dependência FastAPI
# ──────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    Dependência para proteger rotas.
    Extrai e valida o token Bearer do header Authorization.
    Retorna dict com id, email e role do usuário.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await _resolve_user_from_token(credentials.credentials)


async def get_current_user_sse(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    token: str | None = Query(default=None),
) -> dict:
    """
    Dependência para SSE (EventSource).
    EventSource não permite customizar header Authorization em navegadores,
    então aceitamos token por query string como fallback.
    """
    bearer_token = credentials.credentials if credentials else None
    token_value = bearer_token or token
    if not token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _resolve_user_from_token(token_value)


async def _resolve_user_from_token(token_value: str) -> dict:
    try:
        payload = decode_token(token_value)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    row = await db.fetchrow(
        "SELECT id, email, role, active FROM users WHERE id = $1", user_id
    )
    if not row or not row["active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou inativo",
        )

    return {"id": row["id"], "email": row["email"], "role": row["role"]}
