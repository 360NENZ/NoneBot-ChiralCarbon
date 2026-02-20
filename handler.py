"""
chiral_carbon_verify/handler.py
事件处理器

1. group_join_handler      — 监听成员入群通知，发送验证题目（不禁言）
2. verify_answer_handler   — 接收私聊/群聊纯数字答案
3. admin_approve_handler   — /approve <QQ>（管理员，需 / 前缀）
4. admin_reject_handler    — /reject  <QQ>（管理员，需 / 前缀）
5. admin_approve_kw        — 手动通过 <QQ>（无需前缀）
6. admin_reject_kw         — 手动拒绝 <QQ>（无需前缀）
7. help_handler            — 手性碳帮助 / CChelp（无需前缀）
8. timeout_checker         — 定时任务，超时踢出
"""

import re

from nonebot import get_bot, on_notice, on_command, on_message, require
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupIncreaseNoticeEvent,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageSegment,
    Message,
)
from nonebot.adapters.onebot.v11.permission import GROUP, PRIVATE
from nonebot.log import logger
from nonebot.params import CommandArg, EventPlainText
from nonebot.permission import SUPERUSER
from nonebot.plugin import get_plugin_config

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from .config import Config
from .questions import fetch_captcha, verify_answer
from .session import (
    create_session,
    get_session,
    remove_session,
    get_expired_sessions,
    increment_attempt,
)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

config: Config = get_plugin_config(Config)

# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _make_img_segment(image_base64: str) -> MessageSegment:
    b64 = image_base64
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    return MessageSegment.image(f"base64://{b64}")


def _help_text() -> str:
    timeout_min = config.chiral_verify_timeout // 60
    return (
        "📖 【手性碳入群验证 · 使用说明】\n\n"
        "🔬 验证流程\n"
        "  1. 新成员入群后，机器人私聊发送分子结构图\n"
        "  2. 观察图片，回复手性碳的数量（纯数字）\n"
        f"  3. 限时 {timeout_min} 分钟，共 {config.chiral_verify_max_attempts} 次机会\n"
        "  4. 答对即完成验证；答错或超时将被移出群聊\n\n"
        "📌 什么是手性碳？\n"
        "  连接四个不同取代基的碳原子，\n"
        "  在结构图中通常以楔形键标注立体化学。\n\n"
        "🛠 管理员命令（超级管理员）\n"
        "  /approve <QQ号>        手动通过验证\n"
        "  /reject  <QQ号> [原因] 手动踢出用户\n"
        "  手动通过 <QQ号>        同上（无需前缀）\n"
        "  手动拒绝 <QQ号> [原因] 同上（无需前缀）\n\n"
        f"⚙️ 当前配置\n"
        f"  验证时限：{timeout_min} 分钟\n"
        f"  最大尝试：{config.chiral_verify_max_attempts} 次\n"
        f"  超时自动踢出：{'是' if config.chiral_verify_auto_reject else '否'}"
    )


# ---------------------------------------------------------------------------
# 1. 入群通知处理器
# ---------------------------------------------------------------------------

group_join_handler = on_notice(priority=5)


@group_join_handler.handle()
async def handle_group_join(bot: Bot, event: GroupIncreaseNoticeEvent):
    user_id  = event.user_id
    group_id = event.group_id

    if user_id == event.self_id:
        return

    logger.info(f"[手性碳验证] 新成员入群: user={user_id}, group={group_id}, sub_type={event.sub_type}")

    try:
        question = await fetch_captcha(
            api_base=config.chiral_verify_api_base,
            timeout=config.chiral_verify_api_timeout,
        )
    except Exception as e:
        logger.error(f"[手性碳验证] 获取验证码失败: {e}")
        for admin_id in config.chiral_verify_admin_ids:
            try:
                await bot.send_private_msg(
                    user_id=admin_id,
                    message=(
                        f"⚠️ 手性碳验证 API 不可用，请手动审核新成员。\n"
                        f"用户：{user_id}，群：{group_id}\n"
                        f"错误：{e}"
                    ),
                )
            except Exception:
                pass
        return

    create_session(
        user_id=user_id,
        group_id=group_id,
        question=question,
        max_attempts=config.chiral_verify_max_attempts,
        timeout=config.chiral_verify_timeout,
    )

    timeout_min = config.chiral_verify_timeout // 60
    name_part   = f"（{question.molecule_name}）" if question.molecule_name else ""
    img_seg     = _make_img_segment(question.image_base64)

    intro = (
        f"\n👋 你好！你刚加入了群 {group_id}，需要完成手性碳识别验证才算入群成功。\n\n"
        f"📚 【验证题目】{name_part}\n"
        f"请观察下方分子结构图，回复图中手性碳的数量（纯数字，如 2）。\n"
    )
    hint = (
        f"\n⏰ 限时 {timeout_min} 分钟，共 {config.chiral_verify_max_attempts} 次机会。\n"
        f"验证失败或超时将被移出群聊。\n"
        f"发送 手性碳帮助 或 CChelp 可查看说明。"
    )

    private_msg = MessageSegment.text(intro) + img_seg + MessageSegment.text(hint)

    sent_private = False
    try:
        await bot.send_private_msg(user_id=user_id, message=private_msg)
        sent_private = True
        logger.info(f"[手性碳验证] 已私聊 {user_id} 发送验证题目")
    except Exception as e:
        logger.warning(f"[手性碳验证] 私聊失败，回退群内发送: {e}")

    if sent_private:
        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=(
                    f"[CQ:at,qq={user_id}] 验证题目已通过私聊发送，"
                    f"请查看私信并直接回复手性碳数量（纯数字）。\n"
                    f"限时 {timeout_min} 分钟，共 {config.chiral_verify_max_attempts} 次机会，"
                    f"超时或答错将被移出群聊。"
                ),
            )
        except Exception as e:
            logger.warning(f"[手性碳验证] 群内提示失败: {e}")
    else:
        group_msg = MessageSegment.at(user_id) + MessageSegment.text(intro) + img_seg + MessageSegment.text(hint)
        try:
            await bot.send_group_msg(group_id=group_id, message=group_msg)
            logger.info(f"[手性碳验证] 已群内向 {user_id} 发题（回退）")
        except Exception as e:
            logger.error(f"[手性碳验证] 发送题目失败: {e}")


# ---------------------------------------------------------------------------
# 2. 答案处理器（rule 匹配：纯数字 + 有待验证会话）
# ---------------------------------------------------------------------------

def _is_pending_user(event: GroupMessageEvent | PrivateMessageEvent) -> bool:
    text = event.get_plaintext().strip()
    if not re.fullmatch(r"\d+", text):
        return False
    session = get_session(event.user_id)
    if not session:
        return False
    if isinstance(event, GroupMessageEvent):
        return session.group_id == event.group_id
    return True


verify_answer_handler = on_message(
    rule=_is_pending_user,
    permission=GROUP | PRIVATE,
    priority=5,
    block=True,
)


@verify_answer_handler.handle()
async def handle_verify_answer(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    user_id = event.user_id
    session = get_session(user_id)
    if not session:
        return

    group_id  = session.group_id
    user_text = event.get_plaintext().strip()
    correct, feedback = verify_answer(session.question, user_text)

    if correct:
        remove_session(user_id)
        await bot.send(event, f"{feedback}\n\n🎉 验证通过，欢迎加入！")
        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=f"[CQ:at,qq={user_id}] ✅ 验证通过，欢迎！",
            )
        except Exception:
            pass
        logger.info(f"[手性碳验证] {user_id} 验证通过")

    else:
        attempts  = increment_attempt(user_id)
        remaining = session.max_attempts - attempts

        if remaining <= 0:
            remove_session(user_id)
            await bot.send(event, f"{feedback}\n\n😔 已超过最大尝试次数，即将移出群聊。")
            if config.chiral_verify_auto_reject:
                try:
                    await bot.set_group_kick(
                        group_id=group_id,
                        user_id=user_id,
                        reject_add_request=True,
                    )
                    logger.info(f"[手性碳验证] {user_id} 验证失败，已踢出群 {group_id}")
                except Exception as e:
                    logger.error(f"[手性碳验证] 踢出用户失败: {e}")
        else:
            await bot.send(
                event,
                f"{feedback}\n\n还有 {remaining} 次机会，请重新作答。",
            )


# ---------------------------------------------------------------------------
# 帮助：通用 approve/reject 逻辑（供多个 handler 复用）
# ---------------------------------------------------------------------------

async def _do_approve(bot: Bot, target_id: int) -> str:
    session = get_session(target_id)
    if not session:
        return f"未找到 {target_id} 的待验证会话。"
    remove_session(target_id)
    try:
        await bot.send_group_msg(
            group_id=session.group_id,
            message=f"✅ 管理员已手动通过 [CQ:at,qq={target_id}] 的验证。",
        )
    except Exception as e:
        logger.warning(f"[手性碳验证] 群内通知失败: {e}")
    return f"✅ 已手动通过 {target_id} 的验证。"


async def _do_reject(bot: Bot, target_id: int, reason: str) -> str:
    session = get_session(target_id)
    if not session:
        return f"未找到 {target_id} 的待验证会话。"
    remove_session(target_id)
    try:
        await bot.send_group_msg(
            group_id=session.group_id,
            message=f"❌ 管理员已拒绝 [CQ:at,qq={target_id}] 的验证，原因：{reason}",
        )
    except Exception as e:
        logger.warning(f"[手性碳验证] 群内通知失败: {e}")
    try:
        await bot.set_group_kick(
            group_id=session.group_id,
            user_id=target_id,
            reject_add_request=True,
        )
    except Exception as e:
        logger.error(f"[手性碳验证] 踢出用户失败: {e}")
        return f"踢出失败：{e}"
    return f"❌ 已踢出 {target_id}，原因：{reason}"


# ---------------------------------------------------------------------------
# 3. /approve（带前缀，on_command）
# ---------------------------------------------------------------------------

admin_approve_handler = on_command(
    "approve",
    permission=SUPERUSER,
    priority=1,
    block=True,
)


@admin_approve_handler.handle()
async def handle_admin_approve(bot: Bot, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await admin_approve_handler.finish("用法：/approve <QQ号>")
        return
    try:
        target_id = int(arg)
    except ValueError:
        await admin_approve_handler.finish(f"QQ 号格式不正确：{arg}")
        return
    result = await _do_approve(bot, target_id)
    await admin_approve_handler.finish(result)


# ---------------------------------------------------------------------------
# 4. /reject（带前缀，on_command）
# ---------------------------------------------------------------------------

admin_reject_handler = on_command(
    "reject",
    permission=SUPERUSER,
    priority=1,
    block=True,
)


@admin_reject_handler.handle()
async def handle_admin_reject(bot: Bot, args: Message = CommandArg()):
    parts = args.extract_plain_text().strip().split(maxsplit=1)
    if not parts or not parts[0]:
        await admin_reject_handler.finish("用法：/reject <QQ号> [原因]")
        return
    try:
        target_id = int(parts[0])
    except ValueError:
        await admin_reject_handler.finish(f"QQ 号格式不正确：{parts[0]}")
        return
    reason = parts[1] if len(parts) > 1 else "管理员手动拒绝"
    result = await _do_reject(bot, target_id, reason)
    await admin_reject_handler.finish(result)


# ---------------------------------------------------------------------------
# 5. 手动通过（无前缀，on_message rule）
# ---------------------------------------------------------------------------

def _is_approve_cmd(event: GroupMessageEvent | PrivateMessageEvent) -> bool:
    return event.get_plaintext().strip().startswith("手动通过")


admin_approve_kw = on_message(
    rule=_is_approve_cmd,
    permission=SUPERUSER,
    priority=1,
    block=True,
)


@admin_approve_kw.handle()
async def handle_approve_kw(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    text  = event.get_plaintext().strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await bot.send(event, "用法：手动通过 <QQ号>")
        return
    try:
        target_id = int(parts[1].strip())
    except ValueError:
        await bot.send(event, f"QQ 号格式不正确：{parts[1].strip()}")
        return
    result = await _do_approve(bot, target_id)
    await bot.send(event, result)


# ---------------------------------------------------------------------------
# 6. 手动拒绝（无前缀，on_message rule）
# ---------------------------------------------------------------------------

def _is_reject_cmd(event: GroupMessageEvent | PrivateMessageEvent) -> bool:
    return event.get_plaintext().strip().startswith("手动拒绝")


admin_reject_kw = on_message(
    rule=_is_reject_cmd,
    permission=SUPERUSER,
    priority=1,
    block=True,
)


@admin_reject_kw.handle()
async def handle_reject_kw(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    text  = event.get_plaintext().strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await bot.send(event, "用法：手动拒绝 <QQ号> [原因]")
        return
    sub   = parts[1].strip().split(maxsplit=1)
    try:
        target_id = int(sub[0])
    except ValueError:
        await bot.send(event, f"QQ 号格式不正确：{sub[0]}")
        return
    reason = sub[1] if len(sub) > 1 else "管理员手动拒绝"
    result = await _do_reject(bot, target_id, reason)
    await bot.send(event, result)


# ---------------------------------------------------------------------------
# 7. 帮助（无前缀，on_message rule）
# ---------------------------------------------------------------------------

_HELP_KEYWORDS = {"手性碳帮助", "CChelp"}


def _is_help_cmd(event: GroupMessageEvent | PrivateMessageEvent) -> bool:
    return event.get_plaintext().strip() in _HELP_KEYWORDS


help_handler = on_message(
    rule=_is_help_cmd,
    permission=GROUP | PRIVATE,
    priority=5,
    block=True,
)


@help_handler.handle()
async def handle_help(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    await bot.send(event, _help_text())


# ---------------------------------------------------------------------------
# 8. 定时任务：超时踢出（每 30 秒检查一次）
# ---------------------------------------------------------------------------

@scheduler.scheduled_job("interval", seconds=30, id="chiral_verify_timeout_check")
async def check_expired_sessions():
    expired = get_expired_sessions()
    if not expired:
        return

    try:
        bot = get_bot()
    except Exception:
        logger.warning("[手性碳验证] 获取 bot 实例失败，跳过超时处理")
        return

    for session in expired:
        logger.info(f"[手性碳验证] 用户 {session.user_id} 验证超时")
        if config.chiral_verify_auto_reject:
            try:
                await bot.send_group_msg(
                    group_id=session.group_id,
                    message=f"⏰ [CQ:at,qq={session.user_id}] 验证超时，已移出群聊。",
                )
            except Exception:
                pass
            try:
                await bot.set_group_kick(
                    group_id=session.group_id,
                    user_id=session.user_id,
                    reject_add_request=True,
                )
            except Exception as e:
                logger.error(f"[手性碳验证] 超时踢出失败（user={session.user_id}）: {e}")
