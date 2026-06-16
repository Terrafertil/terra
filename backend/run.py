"""Entrypoint para rodar com `python run.py` ou via serviço do Windows."""
import uvicorn

from app.config import settings


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()
