"""
API 客户端模块

通过 POST 请求向 chiral-carbon-captcha 服务获取验证码题目。

接口：POST /chiral-carbon-captcha/getChiralCarbonCaptcha
参考：https://github.com/leafLeaf9/chiral-carbon-captcha
Swagger：http://<host>:9999/swagger-ui/index.html
        #/chiral-carbon-captcha-controller/getChiralCarbonCaptchaUsingPOST

典型响应结构（根据源码推断）：
{
  "code": 200,
  "data": {
    "questionId":   "uuid-string",
    "imageBase64":  "data:image/png;base64,iVBOR...",
    "chiralCount":  3,
    "moleculeName": "Cholesterol"
  }
}
"""

from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass

import httpx


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class CaptchaQuestion:
    question_id: str          # 服务端返回的题目 ID
    image_base64: str         # 完整 data URI 或裸 base64 字符串
    chiral_count: int         # 正确答案（手性碳数量）
    molecule_name: str = ""   # 化合物名称（展示用，可能为空）


# ---------------------------------------------------------------------------
# API 调用
# ---------------------------------------------------------------------------

async def fetch_captcha(api_base: str, timeout: float = 10.0) -> CaptchaQuestion:
    """
    向远程 API 请求一道手性碳验证题。

    :param api_base: 服务根地址，例如 "http://localhost:9999"
    :param timeout:  请求超时（秒）
    :raises RuntimeError: 请求失败或响应格式异常时抛出
    """
    url = f"{api_base.rstrip('/')}/chiral-carbon-captcha/getChiralCarbonCaptcha"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json={})
        resp.raise_for_status()
        body = resp.json()

    # 兼容两种常见包装格式：
    #   { "code": 200, "data": { ... } }      ← Spring 统一返回体
    #   { "questionId": ..., ... }             ← 直接返回
    data = body.get("data", body)

    question_id  = str(data.get("questionId",  data.get("id",     "")))
    image_b64    = str(data.get("imageBase64", data.get("image",  "")))
    chiral_count = int(data.get("chiralCount", data.get("count",  data.get("answer", 0))))
    mol_name     = str(data.get("moleculeName",data.get("name",   "")))

    if not image_b64:
        raise RuntimeError("API 响应中缺少 imageBase64 字段，请检查服务是否正常")

    return CaptchaQuestion(
        question_id=question_id,
        image_base64=image_b64,
        chiral_count=chiral_count,
        molecule_name=mol_name,
    )


# ---------------------------------------------------------------------------
# 图片工具
# ---------------------------------------------------------------------------

def save_image_to_temp(image_b64: str) -> str:
    """
    将 base64 图片写入临时 PNG 文件，返回文件路径。
    调用方负责删除该文件（os.unlink）。
    """
    if "," in image_b64:          # 去掉 data URI 前缀
        image_b64 = image_b64.split(",", 1)[1]

    img_bytes = base64.b64decode(image_b64)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(img_bytes)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# 答案验证（本地）
# ---------------------------------------------------------------------------

def verify_answer(question: CaptchaQuestion, user_input: str) -> tuple[bool, str]:
    """
    本地验证用户输入的手性碳数量。
    :returns: (是否正确, 反馈消息)
    """
    try:
        user_count = int(user_input.strip())
    except ValueError:
        return False, "❌ 请输入一个整数，例如输入 "2" 表示有 2 个手性碳。"

    name_hint = f"【{question.molecule_name}】" if question.molecule_name else "该化合物"

    if user_count == question.chiral_count:
        return True, f"✅ 回答正确！\n{name_hint}共有 {question.chiral_count} 个手性碳。"
    else:
        return False, (
            f"❌ 回答错误。\n"
            f"你的答案：{user_count}，正确答案：{question.chiral_count}"
        )
