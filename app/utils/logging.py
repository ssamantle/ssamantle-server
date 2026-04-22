import logging
from contextvars import ContextVar, Token
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import Request

from app.config import Settings


ANONYMOUS_SESSION_ID = "anonymous"
_request_session_id: ContextVar[str] = ContextVar(
    "request_session_id",
    default=ANONYMOUS_SESSION_ID,
)


class SessionContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = _request_session_id.get()
        trailing_spaces = " " * max(1, 9 - len(record.levelname))
        record.levelprefix = f"{record.levelname}:{trailing_spaces}"
        return True


def _parse_authorization_session_id(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return authorization


def resolve_session_id_from_request(request: Request) -> str:
    session_id = None
    try:
        session_id = request.session.get("session_id")
    except (AssertionError, RuntimeError, AttributeError):
        session_id = None

    if session_id:
        return str(session_id)

    header_session_id = _parse_authorization_session_id(
        request.headers.get("authorization")
    )
    if header_session_id:
        return str(header_session_id)
    return ANONYMOUS_SESSION_ID


def set_request_session_id(session_id: str | None) -> Token[str]:
    value = session_id or ANONYMOUS_SESSION_ID
    return _request_session_id.set(value)


def reset_request_session_id(token: Token[str]) -> None:
    _request_session_id.reset(token)


def _resolve_log_level(settings: Settings) -> int:
    return logging.DEBUG if settings.debug else logging.INFO


def setup_logging(settings: Settings) -> None:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(_resolve_log_level(settings))

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        fmt="%(levelprefix)s[%(asctime)s.%(msecs)03d] [%(session_id)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    session_filter = SessionContextFilter()

    stream_handler = logging.StreamHandler()
    stream_handler.addFilter(session_filter)
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        filename=log_dir / settings.log_file_name,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.addFilter(session_filter)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)


def getLogger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(name)