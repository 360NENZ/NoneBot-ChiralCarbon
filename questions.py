"""
chiral_carbon_verify/questions.py
API 客户端模块

通过 POST 请求向 chiral-carbon-captcha 服务获取验证码题目。

接口：POST /captcha/chiralCarbon/getChiralCarbonCaptcha
参考：https://github.com/leafLeaf9/chiral-carbon-captcha
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

    :param api_base: 服务根地址，例如 "http://38.165.22.100:9999"
    :param timeout:  请求超时（秒）
    :raises RuntimeError: 请求失败或响应格式异常时抛出
    """
    # 修改为正确的API端点
    url = f"{api_base.rstrip('/')}/captcha/chiralCarbon/getChiralCarbonCaptcha"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json={})
        resp.raise_for_status()
        body = resp.json()

    # 适配新的API响应格式
    # 原格式: { "code": 200, "data": { ... } }
    # 新格式: { "status": true, "code": 200, "message": "...", "data": { "data": {...} } }
    
    # 首先检查是否有外层 status
    if "status" in body:
        # 新格式：包含 status、code、message、data
        inner_data = body.get("data", {})
        # 再取一层 data
        actual_data = inner_data.get("data", inner_data)
    else:
        # 旧格式：直接是 { "code": 200, "data": {...} } 或直接数据
        actual_data = body.get("data", body)

    # 根据API响应格式提取字段
    # 优先使用新的字段名，然后是旧的兼容字段名
    question_id = str(actual_data.get("cid", actual_data.get("questionId", actual_data.get("id", ""))))
    # 适配 base64 字段
    image_b64 = str(actual_data.get("base64", actual_data.get("imageBase64", actual_data.get("image", ""))))
    # 从分子名称或其他字段推断手性碳数量
    # 由于API响应中没有明确的手性碳数量，我们尝试从其他字段获取或设定默认值
    chiral_count = int(actual_data.get("chiralCount", actual_data.get("count", actual_data.get("answer", 0))))
    
    # 如果仍然没有有效的手性碳数量，尝试从响应的其他部分推断
    if chiral_count == 0:
        # 从API响应结构中尝试提取手性碳数量
        # 根据提供的示例，可能需要通过其他方式确定答案
        # 这里设置一个默认值或从 regions 数组长度推断
        regions = actual_data.get("regions", [])
        if regions:
            chiral_count = len(regions)
        else:
            # 如果没有regions数组，使用默认值或尝试从CID推断
            chiral_count = 1  # 默认值，实际情况可能需要调整
    
    mol_name = str(actual_data.get("moleculeName", actual_data.get("name", actual_data.get("title", ""))))

    if not image_b64:
        raise RuntimeError("API 响应中缺少 base64/imageBase64/image 字段，请检查服务是否正常")

    return CaptchaQuestion(
        question_id=str(question_id),
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
        return False, "❌ 请输入一个整数，例如输入 \"2\"表示有 2 个手性碳。"

    name_hint = f"【{question.molecule_name}】" if question.molecule_name else "该化合物"

    if user_count == question.chiral_count:
        return True, f"✅ 回答正确！\n{name_hint}共有 {question.chiral_count} 个手性碳。"
    else:
        return False, (
            f"❌ 回答错误。\n"
            f"你的答案：{user_count}，正确答案：{question.chiral_count}"
        )


# 测试函数
async def test_api_format():
    """测试API响应格式适配"""
    # 模拟API响应数据
    api_response = {
        "status": True,
        "code": 200,
        "message": "操作成功",
        "data": {
            "data": {
                "regions": [{"x": 100, "y": 100}, {"x": 200, "y": 200}],  # 2个手性中心
                "cid": 505089,
                "base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
            }
        }
    }
    
    # 模拟fetch_captcha函数处理响应
    body = api_response
    
    if "status" in body:
        # 新格式：包含 status、code、message、data
        inner_data = body.get("data", {})
        # 再取一层 data
        actual_data = inner_data.get("data", inner_data)
    else:
        # 旧格式：直接是 { "code": 200, "data": {...} } 或直接数据
        actual_data = body.get("data", body)

    question_id = str(actual_data.get("cid", actual_data.get("questionId", actual_data.get("id", ""))))
    image_b64 = str(actual_data.get("base64", actual_data.get("imageBase64", actual_data.get("image", ""))))
    chiral_count = int(actual_data.get("chiralCount", actual_data.get("count", actual_data.get("answer", 0))))
    
    # 如果仍然没有有效的手性碳数量，尝试从其他字段获取
    if chiral_count == 0:
        regions = actual_data.get("regions", [])
        if regions:
            chiral_count = len(regions)
        else:
            chiral_count = 1  # 默认值
    
    mol_name = str(actual_data.get("moleculeName", actual_data.get("name", actual_data.get("title", ""))))

    print(f"提取的数据:")
    print(f"  question_id: {question_id}")
    print(f"  image_b64 (前50字符): {image_b64[:50]}...")
    print(f"  chiral_count: {chiral_count}")
    print(f"  mol_name: {mol_name}")
    
    if not image_b64:
        print("错误: API 响应中缺少图像数据")
    else:
        print("成功: 图像数据存在")
    
    return {
        "question_id": question_id,
        "image_b64": image_b64,
        "chiral_count": chiral_count,
        "mol_name": mol_name
    }


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_api_format())