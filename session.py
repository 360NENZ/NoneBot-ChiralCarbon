"""
会话状态管理器

存储待验证用户的状态：
  - 题目（来自 API 的 CaptchaQuestion）
  - 已用次数
  - 申请信息（flag / group_id / user_id）
  - 过期时间
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .questions import CaptchaQuestion


@dataclass
class VerifySession:
    user_id: int
    group_id: int
    flag: str                    # 入群申请的 flag，用于 approve/reject
    question: CaptchaQuestion
    attempts: int = 0
    max_attempts: int = 3
    created_at: float = field(default_factory=time.time)
    timeout: int = 120           # seconds


# 全局状态字典：user_id -> VerifySession
_sessions: Dict[int, VerifySession] = {}


def create_session(
    user_id: int,
    group_id: int,
    flag: str,
    question: CaptchaQuestion,
    max_attempts: int = 3,
    timeout: int = 120,
) -> VerifySession:
    session = VerifySession(
        user_id=user_id,
        group_id=group_id,
        flag=flag,
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
    """返回并移除所有已过期的会话（用于定时任务清理）"""
    expired = [s for s in list(_sessions.values()) if _is_expired(s)]
    for s in expired:
        _sessions.pop(s.user_id, None)
    return expired


def increment_attempt(user_id: int) -> int:
    """增加错误次数，返回当前次数"""
    session = get_session(user_id)
    if session:
        session.attempts += 1
        return session.attempts
    return 0
