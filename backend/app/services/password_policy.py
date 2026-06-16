"""Política de senhas fortes para utilizadores."""
from __future__ import annotations

import re

_MIN_LEN = 8


def validate_password_strength(senha: str) -> None:
    """Levanta ValueError com mensagem em português se a senha for fraca."""
    s = senha or ""
    if len(s) < _MIN_LEN:
        raise ValueError(f"A senha deve ter pelo menos {_MIN_LEN} caracteres.")
    if not re.search(r"[a-z]", s):
        raise ValueError("A senha deve incluir pelo menos uma letra minúscula.")
    if not re.search(r"[A-Z]", s):
        raise ValueError("A senha deve incluir pelo menos uma letra maiúscula.")
    if not re.search(r"\d", s):
        raise ValueError("A senha deve incluir pelo menos um número.")
    if not re.search(r"[^A-Za-z0-9]", s):
        raise ValueError("A senha deve incluir pelo menos um carácter especial.")


def password_requirements_text() -> str:
    return (
        f"Mínimo {_MIN_LEN} caracteres, com letras maiúsculas e minúsculas, "
        "números e carácter especial."
    )
