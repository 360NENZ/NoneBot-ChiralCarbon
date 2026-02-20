"""
chiral_carbon_verify/session.py
会话状态管理器
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .questions import CaptchaQuestion


@dataclass
class VerifySession:
    user_id: int
    group_id: int
    question: CaptchaQuestion
    attempts: int = 0
    max_attempts: int = 3
    created_at: float = field(default_factory=time.time)
    timeout: int = 120


_sessions: Dict[int, VerifySession] = {}


def create_session(
    user_id: int,
    group_id: int,
    question: CaptchaQuestion,
    max_attempts: int = 3,
    timeout: int = 120,
) -> VerifySession:
    session = VerifySession(
        user_id=user_id,
        group_id=group_id,
        question=question,
        max_attempts=max_attempts,
        timeout=timeout,
    )
    _sessions[user_id] = session
    return session


def get_session(user_id: int) -> Optional[VerifySession]:
    session = _sessions.get(user_id)
    if session and _is_expired(session):
        del _sessions[user_id]
        return None
    return session


def remove_session(user_id: int) -> None:
    _sessions.pop(user_id, None)


def _is_expired(session: VerifySession) -> bool:
    return (time.time() - session.created_at) > session.timeout


def get_expired_sessions() -> List[VerifySession]:
    expired = [s for s in list(_sessions.values()) if _is_expired(s)]
    for s in expired:
        _sessions.pop(s.user_id, None)
    return expired


def increment_attempt(user_id: int) -> int:
    session = get_session(user_id)
    if session:
        session.attempts += 1
        return session.attempts
    return 0
