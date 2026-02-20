"""
NoneBot Plugin: Chiral Carbon Verification
==========================================
Verifies group join requests by asking applicants to identify
chiral carbon atoms in a molecule structure.

Requirements:
    pip install nonebot2 nonebot-adapter-onebot rdkit pillow

Usage:
    Place this folder in your NoneBot plugins directory.
    Add "chiral_carbon_verify" to your plugin list in pyproject.toml or bot.py.

Config (in .env):
    CHIRAL_VERIFY_TIMEOUT=120        # seconds before verification expires
    CHIRAL_VERIFY_MAX_ATTEMPTS=3     # max wrong answers before rejection
    CHIRAL_VERIFY_AUTO_REJECT=true   # auto-reject on timeout/fail
    CHIRAL_VERIFY_ADMIN_IDS=[]       # list of admin QQ IDs for manual override
"""

from nonebot import get_plugin_config, require, get_bot
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_apscheduler")

from .config import Config
from .handler import (
    group_request_handler,
    verify_answer_handler,
    admin_approve_handler,
    admin_reject_handler,
)

__plugin_meta__ = PluginMetadata(
    name="手性碳验证入群",
    description="通过识别手性碳原子来验证入群申请，防止机器人和非化学背景用户",
    usage=(
        "入群申请时，机器人会向申请人发送一道手性碳识别题目。\n"
        "用户需在规定时间内回复正确的手性碳数量或编号。\n"
        "答对即可通过审核，答错或超时则拒绝入群。"
    ),
    config=Config,
    extra={
        "author": "YourName",
        "version": "1.0.0",
    },
)

__all__ = [
    "group_request_handler",
    "verify_answer_handler",
    "admin_approve_handler",
    "admin_reject_handler",
]
