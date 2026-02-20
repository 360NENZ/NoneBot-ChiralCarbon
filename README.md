# NoneBot-ChiralCarbon

一个基于 **NoneBot2 + OneBot V11** 的入群验证插件。  
新成员加入群聊后，机器人私聊发送手性碳识别题目（分子结构图），  
答对方可留群，答错或超时自动踢出。

题目图片与答案由 **[chiral-carbon-captcha](https://github.com/leafLeaf9/chiral-carbon-captcha)** API 动态提供，无需本地题库。

---

## 效果预览

```
用户加入群聊
    ↓
机器人私聊发送分子结构图 + 题目说明
群内 @ 提示用户查看私信
    ↓
用户私聊回复纯数字（如 "3"）
    ↓
答对 ✅ → 无操作，欢迎留群
答错超过上限 ❌ → 踢出群聊
超时未答 ⏰ → 踢出群聊
```

---

## 安装

```bash
pip install nonebot2 nonebot-adapter-onebot nonebot-plugin-apscheduler httpx
```

将 `chiral_carbon_verify/` 文件夹放入 NoneBot 项目的 `src/plugins/` 目录，  
并在 `pyproject.toml` 中注册：

```toml
[tool.nonebot]
plugins = ["chiral_carbon_verify"]
```

---

## 依赖：验证码 API

插件依赖独立部署的 `chiral-carbon-captcha` 服务提供题目图片和答案。  
推荐使用 Docker 一键部署：

```bash
docker pull woxigousade/chiral-carbon-captcha:latest
docker run -d --name chiral-carbon-captcha -p 9999:9999 \
    woxigousade/chiral-carbon-captcha:latest
```

服务启动后 Swagger 文档：`http://localhost:9999/swagger-ui/index.html`

---

## 配置

在 `.env` 或 `.env.prod` 中添加以下配置项：

```env
# 验证码 API 服务地址
CHIRAL_VERIFY_API_BASE=http://localhost:9999

# API 请求超时（秒）
CHIRAL_VERIFY_API_TIMEOUT=10.0

# 用户回答超时时间（秒，默认 10 分钟）
CHIRAL_VERIFY_TIMEOUT=600

# 最大错误次数
CHIRAL_VERIFY_MAX_ATTEMPTS=5

# 超时/答错达上限后自动踢出
CHIRAL_VERIFY_AUTO_REJECT=true

# 管理员 QQ 号列表（API 故障时接收告警通知）
CHIRAL_VERIFY_ADMIN_IDS=[123456789]
```

---

## 使用说明

### 验证流程

1. 新成员加入群聊（邀请或申请均触发）
2. 机器人向新成员**私聊**发送分子结构图，同时群内 @ 提示查看私信
3. 新成员在**私聊或群内**直接回复手性碳数量（纯数字，如 `3`）
4. 答对 → 验证通过，无需其他操作
5. 答错超过上限 / 超时未答 → 自动踢出群聊

> 若私聊发送失败（用户未添加机器人好友），自动回退为群内 @ 发题。

### 帮助命令

任何人均可发送以下命令查看说明（**无需前缀**）：

| 命令 | 说明 |
|------|------|
| `手性碳帮助` | 查看插件使用说明 |
| `CChelp` | 同上（区分大小写） |

### 管理员命令

超级管理员可使用以下命令手动干预待验证用户：

| 命令 | 说明 |
|------|------|
| `/approve <QQ号>` | 手动通过验证（带 `/` 前缀） |
| `/reject <QQ号> [原因]` | 手动踢出用户（带 `/` 前缀） |
| `手动通过 <QQ号>` | 同上，无需 `/` 前缀 |
| `手动拒绝 <QQ号> [原因]` | 同上，无需 `/` 前缀 |

> 超级管理员在 `.env` 中通过 `SUPERUSERS=["QQ号"]` 配置。

---

## API 接口说明

**请求**

```http
POST /captcha/chiralCarbon/getChiralCarbonCaptcha
Content-Type: application/json

{}
```

**响应**

```json
{
  "status": true,
  "code": 200,
  "message": "操作成功",
  "data": {
    "data": {
      "cid": 505089,
      "base64": "data:image/png;base64,iVBORw0KGgo...",
      "regions": [
        {"x": 120, "y": 85},
        {"x": 230, "y": 142}
      ]
    }
  }
}
```

插件从 `regions` 数组长度推断手性碳数量，兼容以下字段名变体：

| 字段用途 | 支持的字段名 |
|---------|------------|
| 题目 ID | `cid` / `questionId` / `id` |
| 图片数据 | `base64` / `imageBase64` / `image` |
| 手性碳数量 | `chiralCount` / `count` / `answer` / `regions` 数组长度 |
| 化合物名称 | `moleculeName` / `name` / `title` |

---

## 文件结构

```
chiral_carbon_verify/
├── __init__.py    # 插件入口与元信息
├── config.py      # Pydantic 配置模型
├── questions.py   # API 客户端、答案验证
├── session.py     # 内存会话状态管理
├── handler.py     # NoneBot 事件处理器 + 定时任务
└── README.md      # 本文档
```

---

## 许可证

MIT
