"""
事件处理器

1. group_request_handler   — 监听入群申请，调用 API 获取题目并发送
2. verify_answer_handler   — 监听私聊回复，判断答案
3. admin_approve_handler   — 管理员手动通过
4. admin_reject_handler    — 管理员手动拒绝
5. timeout_checker         — 定时任务，处理超时
"""

import os

from nonebot import get_bot, on_request, on_command, on_message, require
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupRequestEvent,
    PrivateMessageEvent,
    MessageSegment,
    Message,
)
from nonebot.adapters.onebot.v11.permission import PRIVATE
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import get_plugin_config

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from .config import Config
from .questions import fetch_captcha, save_image_to_temp, verify_answer
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
# 1. 入群申请处理器
# ---------------------------------------------------------------------------

group_request_handler = on_request(priority=5)


@group_request_handler.handle()
async def handle_group_request(bot: Bot, event: GroupRequestEvent):
    if event.sub_type != "add":
        return

    user_id  = event.user_id
    group_id = event.group_id
    flag     = event.flag

    logger.info(f"[手性碳验证] 入群申请: user={user_id}, group={group_id}")

    # ── 从远程 API 取题 ──────────────────────────────────────────────────
    try:
        question = await fetch_captcha(
            api_base=config.chiral_verify_api_base,
            timeout=config.chiral_verify_api_timeout,
        )
    except Exception as e:
        logger.error(f"[手性碳验证] 获取验证码失败: {e}")
        # API 不可用时，通知管理员并暂不处理该申请
        for admin_id in config.chiral_verify_admin_ids:
            try:
                await bot.send_private_msg(
                    user_id=admin_id,
                    message=(
                        f"⚠️ 手性碳验证 API 不可用，无法自动审核。\n"
                        f"待审核用户：{user_id}，群：{group_id}\n"
                        f"错误信息：{e}"
                    ),
                )
            except Exception:
                pass
        return

    # ── 创建会话 ─────────────────────────────────────────────────────────
    create_session(
        user_id=user_id,
        group_id=group_id,
        flag=flag,
        question=question,
        max_attempts=config.chiral_verify_max_attempts,
        timeout=config.chiral_verify_timeout,
    )

    # ── 将 base64 图片写入临时文件 ────────────────────────────────────────
    tmp_path = None
    img_segment = None
    try:
        tmp_path = save_image_to_temp(question.image_base64)
        img_segment = MessageSegment.image(f"file://{tmp_path}")
    except Exception as e:
        logger.warning(f"[手性碳验证] 图片保存失败: {e}")

    # ── 构造题目消息 ──────────────────────────────────────────────────────
    name_part = f"（{question.molecule_name}）" if question.molecule_name else ""
    header = (
        f"👋 你好！你申请加入群 {group_id} ，需要通过手性碳识别验证。\n\n"
        f"📚 【题目】\n"
        f"请观察下方分子结构图{name_part}，回答其中手性碳的数量。\n\n"
    )
    footer = (
        f"\n⏰ 请在 {config.chiral_verify_timeout} 秒内，"
        f"私聊本机器人回复手性碳的数量（纯数字）。\n"
        f"共有 {config.chiral_verify_max_attempts} 次机会。\n"
        f"例：若认为有 2 个手性碳，直接回复 \"2\"。"
    )

    if img_segment:
        full_msg = Message(header) + img_segment + Message(footer)
    else:
        full_msg = Message(header + "（图片加载失败，请联系管理员）" + footer)

    # ── 发送 ──────────────────────────────────────────────────────────────
    send_ok = False
    if config.chiral_verify_use_private:
        try:
            await bot.send_private_msg(user_id=user_id, message=full_msg)
            send_ok = True
            logger.info(f"[手性碳验证] 已私聊 {user_id} 发送题目")
        except Exception as e:
            logger.warning(f"[手性碳验证] 私聊 {user_id} 失败: {e}")

    if not send_ok:
        try:
            await bot.send_group_msg(
                group_id=group_id,
                message=f"[CQ:at,qq={user_id}] 请私聊机器人完成手性碳验证后方可入群。",
            )
        except Exception as e:
            logger.error(f"[手性碳验证] 群内通知也失败: {e}")

    # 清理临时图片文件
    if tmp_path:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 2. 私聊答案处理器
# ---------------------------------------------------------------------------

verify_answer_handler = on_message(permission=PRIVATE, priority=10, block=False)


@verify_answer_handler.handle()
async def handle_verify_answer(bot: Bot, event: PrivateMessageEvent):
    user_id = event.user_id
    session = get_session(user_id)
    if not session:
        return  # 不是待验证用户，忽略

    user_text = event.get_plaintext().strip()
    if not user_text:
        return

    correct, feedback = verify_answer(session.question, user_text)

    if correct:
        remove_session(user_id)
        await bot.send(event, f"{feedback}\n\n🎉 验证通过，正在为你同意入群申请...")
        try:
            await bot.set_group_add_request(
                flag=session.flag,
                sub_type="add",
                approve=True,
            )
            logger.info(f"[手性碳验证] {user_id} 验证通过，已同意入群 {session.group_id}")
        except Exception as e:
            logger.error(f"[手性碳验证] 同意入群失败: {e}")
            await bot.send(event, "⚠️ 自动同意入群时出错，请联系管理员手动处理。")

    else:
        attempts  = increment_attempt(user_id)
        remaining = session.max_attempts - attempts

        if remaining <= 0:
            remove_session(user_id)
            await bot.send(event, f"{feedback}\n\n😔 已超过最大尝试次数，验证失败。")
            if config.chiral_verify_auto_reject:
                try:
                    await bot.set_group_add_request(
                        flag=session.flag,
                        sub_type="add",
                        approve=False,
                        reason="手性碳验证失败（超出尝试次数）",
                    )
                    logger.info(f"[手性碳验证] {user_id} 验证失败，已拒绝入群")
                except Exception as e:
                    logger.error(f"[手性碳验证] 拒绝入群失败: {e}")
        else:
            await bot.send(
                event,
                f"{feedback}\n\n还有 {remaining} 次机会，请重新回答。",
            )


# ---------------------------------------------------------------------------
# 3 & 4. 管理员手动命令
# ---------------------------------------------------------------------------

admin_approve_handler = on_command(
    "手动通过",
    aliases={"approve_verify"},
    permission=SUPERUSER,
    priority=5,
)

admin_reject_handler = on_command(
    "手动拒绝",
    aliases={"reject_verify"},
    permission=SUPERUSER,
    priority=5,
)


@admin_approve_handler.handle()
async def handle_admin_approve(bot: Bot, event: PrivateMessageEvent, args: Message = CommandArg()):
    """用法：手动通过 <QQ号>"""
    try:
        target_id = int(args.extract_plain_text().strip())
    except ValueError:
        await admin_approve_handler.finish("请提供正确的 QQ 号，例如：手动通过 123456789")
        return

    session = get_session(target_id)
    if not session:
        await admin_approve_handler.finish(f"未找到 {target_id} 的待验证会话。")
        return

    remove_session(target_id)
    try:
        await bot.set_group_add_request(flag=session.flag, sub_type="add", approve=True)
        await admin_approve_handler.finish(f"✅ 已手动同意 {target_id} 加入群 {session.group_id}。")
    except Exception as e:
        await admin_approve_handler.finish(f"操作失败：{e}")


@admin_reject_handler.handle()
async def handle_admin_reject(bot: Bot, event: PrivateMessageEvent, args: Message = CommandArg()):
    """用法：手动拒绝 <QQ号> [原因]"""
    parts = args.extract_plain_text().strip().split(maxsplit=1)
    if not parts:
        await admin_reject_handler.finish("请提供正确的 QQ 号，例如：手动拒绝 123456789 原因")
        return

    try:
        target_id = int(parts[0])
    except ValueError:
        await admin_reject_handler.finish("QQ 号格式不正确。")
        return

    reason  = parts[1] if len(parts) > 1 else "管理员手动拒绝"
    session = get_session(target_id)
    if not session:
        await admin_reject_handler.finish(f"未找到 {target_id} 的待验证会话。")
        return

    remove_session(target_id)
    try:
        await bot.set_group_add_request(
            flag=session.flag, sub_type="add", approve=False, reason=reason
        )
        await admin_reject_handler.finish(
            f"❌ 已手动拒绝 {target_id} 加入群 {session.group_id}。原因：{reason}"
        )
    except Exception as e:
        await admin_reject_handler.finish(f"操作失败：{e}")


# ---------------------------------------------------------------------------
# 5. 定时任务：清理超时会话
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
        try:
            await bot.send_private_msg(
                user_id=session.user_id,
                message="⏰ 验证超时，本次入群申请已被拒绝。请重新申请并在规定时间内完成验证。",
            )
        except Exception:
            pass

        if config.chiral_verify_auto_reject:
            try:
                await bot.set_group_add_request(
                    flag=session.flag,
                    sub_type="add",
                    approve=False,
                    reason="手性碳验证超时",
                )
            except Exception as e:
                logger.error(f"[手性碳验证] 超时拒绝失败（flag={session.flag}）: {e}")
