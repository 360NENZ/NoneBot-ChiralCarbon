# 手性碳验证入群插件 `chiral_carbon_verify`

一个基于 **NoneBot2 + OneBot V11** 的入群验证插件。  
题目图片及答案完全由 **[chiral-carbon-captcha](https://github.com/leafLeaf9/chiral-carbon-captcha)** 远程 API 提供，无需本地题库或 RDKit。

---

## 架构一览

```
用户申请入群
    │
    ▼
NoneBot 插件收到 GroupRequestEvent
    │
    ▼  POST /chiral-carbon-captcha/getChiralCarbonCaptcha
远程 API（chiral-carbon-captcha 服务）
    │  返回 { questionId, imageBase64, chiralCount, ... }
    ▼
私聊发送验证码图片给申请人
    │
    ▼  用户回复数字
本地比对 chiralCount
    │
   ┌┴────────────────┐
   │                 │
答对 ✅           答错/超时 ❌
同意入群          拒绝入群
```

---

## 安装

```bash
# NoneBot 核心依赖
pip install nonebot2 nonebot-adapter-onebot nonebot-plugin-apscheduler

# HTTP 客户端（插件使用 httpx 调用验证码 API）
pip install httpx
```

将 `chiral_carbon_verify/` 文件夹放入 NoneBot 项目的 `plugins/` 目录，
并在 `pyproject.toml` 中注册：

```toml
[tool.nonebot]
plugins = ["chiral_carbon_verify"]
```

---

## 验证码 API 部署

插件依赖独立运行的 `chiral-carbon-captcha` 服务。  
最简单的方式是 Docker：

```bash
docker pull woxigousade/chiral-carbon-captcha:latest
docker run -d --name chiral-carbon-captcha -p 9999:9999 \
    woxigousade/chiral-carbon-captcha:latest
```

服务启动后，Swagger 文档可在以下地址查看：
```
http://localhost:9999/swagger-ui/index.html
```

---

## 配置项

在 `.env` 或 `.env.prod` 中添加：

```env
# 验证码 API 服务地址（默认已配置为公共演示服务）
CHIRAL_VERIFY_API_BASE=http://localhost:9999

# API 请求超时（秒）
CHIRAL_VERIFY_API_TIMEOUT=10.0

# 用户回答超时时间（秒）
CHIRAL_VERIFY_TIMEOUT=120

# 最大错误次数
CHIRAL_VERIFY_MAX_ATTEMPTS=3

# 超时/失败后是否自动拒绝
CHIRAL_VERIFY_AUTO_REJECT=true

# 管理员 QQ 号（逗号分隔，API 故障时接收告警）
CHIRAL_VERIFY_ADMIN_IDS=[123456789]

# true=私聊发题，false=群内 @ 发题
CHIRAL_VERIFY_USE_PRIVATE=true
```

---

## API 请求 / 响应格式

**请求**

```http
POST /chiral-carbon-captcha/getChiralCarbonCaptcha
Content-Type: application/json

{}
```

**响应**（Spring 统一返回体）

```json
{
  "code": 200,
  "data": {
    "questionId":   "550e8400-e29b-41d4-a716-446655440000",
    "imageBase64":  "data:image/png;base64,iVBORw0KGgo...",
    "chiralCount":  3,
    "moleculeName": "Cholesterol"
  }
}
```

插件会兼容以下字段名变体：

| 标准字段        | 兼容字段              |
|----------------|----------------------|
| `questionId`   | `id`                 |
| `imageBase64`  | `image`              |
| `chiralCount`  | `count` / `answer`   |
| `moleculeName` | `name`               |

---

## 管理员命令（超级用户私聊机器人）

| 命令                       | 说明                       |
|---------------------------|---------------------------|
| `手动通过 <QQ号>`          | 强制通过某用户的验证         |
| `手动拒绝 <QQ号> [原因]`   | 强制拒绝某用户的申请         |

---

## 文件结构

```
chiral_carbon_verify/
├── __init__.py   # 插件入口与元信息
├── config.py     # Pydantic 配置模型
├── questions.py  # API 客户端、图片工具、答案验证
├── session.py    # 会话状态管理（内存）
├── handler.py    # NoneBot 事件处理器 + 定时任务
└── README.md     # 本文档
```

---

## 许可证

MIT
