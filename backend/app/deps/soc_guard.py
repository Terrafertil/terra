"""Bloqueia operações quando o modo SOC está ativo."""
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.soc_service import SOC_BLOCK_MSG, is_soc_locked


def require_operacoes_liberadas(
    db: Annotated[Session, Depends(get_db)],
) -> None:
    if is_soc_locked(db):
        raise HTTPException(status_code=423, detail=SOC_BLOCK_MSG)
