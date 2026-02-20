from pydantic import BaseModel
from typing import List


class Config(BaseModel):
    """手性碳验证插件配置"""

    # ----------------------------------------------------------------
    # 远程验证码 API（chiral-carbon-captcha 服务地址）
    # 参考：https://github.com/leafLeaf9/chiral-carbon-captcha
    # ----------------------------------------------------------------

    # 服务根地址，末尾不加斜杠
    chiral_verify_api_base: str = "http://localhost:9999"

    # API 请求超时（秒）
    chiral_verify_api_timeout: float = 10.0

    # ----------------------------------------------------------------
    # 验证流程配置
    # ----------------------------------------------------------------

    # 用户回答超时时间（秒）
    chiral_verify_timeout: int = 120

    # 最大错误次数
    chiral_verify_max_attempts: int = 3

    # 超时/失败后自动拒绝
    chiral_verify_auto_reject: bool = True

    # 管理员 QQ 号列表（可手动审核）
    chiral_verify_admin_ids: List[int] = []

    # 是否在私聊发送题目（False 则在群内 @）
    chiral_verify_use_private: bool = True
