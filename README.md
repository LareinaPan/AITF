# AITF — AI 测试平台

 AI 测试平台 demo，当前已上线 **接口测试** 模块.

## 功能概览

| 模块 | 状态 | 说明 |
|------|------|------|
| 接口测试 | ✅ 已上线 | OpenAPI 解析、Postman 式用例、AI 生成、测试计划、Allure 报告、飞书通知 |
| 功能用例生成 | 🚧 构建中 | 首页入口已预留 |
| 性能测试 | 🚧 构建中 | 首页入口已预留 |

## 环境要求

| 依赖 | 版本建议 |
|------|----------|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |
| Docker / Docker Compose | 可选（推荐一键启动） |
| Allure CLI | 可选（本地开发；Docker 镜像已内置） |

## 快速开始（Docker Compose）

```bash
# 1. 克隆仓库并进入目录
cd AITF

# 2. 复制环境变量并按需填写 AI Key
cp .env.example .env

# 3. 启动前后端
docker compose up -d --build

# 4. 访问
# 前端: http://localhost:5173
# 后端: http://localhost:8000
# API 文档: http://localhost:8000/docs
```

> Docker 模式下数据库位于 `storage/aitf.db`，上传文件与 Allure 报告也在 `storage/` 目录。

## 本地开发启动

### 1. 环境变量

```bash
cp .env.example .env
```

关键配置项：

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | 默认 `sqlite:///./storage/aitf.db`（相对路径会解析到项目根目录） |
| `SECRET_KEY` | JWT 签名密钥，生产环境务必修改 |
| `OPENAI_API_KEY` | AI 用例生成所需（兼容 OpenAI 协议，如 DeepSeek） |
| `OPENAI_BASE_URL` | LLM API 地址 |
| `AI_MODEL` | 主模型名称 |
| `REPORT_BASE_URL` | Allure 报告外链前缀 |
| `VITE_API_BASE_URL` | 前端请求后端的 Base URL |

### 2. 后端

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 数据库迁移
alembic upgrade head

# 启动（建议带 reload）
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

健康检查：`GET http://localhost:8000/health`

### 3. 前端

```bash
cd frontend
npm install
npm run dev
```

访问：http://localhost:5173

## Demo 账号

平台无预置账号，首次使用请在 **注册页** 自行创建，或使用 seed 脚本（见下方「Demo 数据」）初始化。

推荐 Demo 账号（手动注册或 seed 后登录）：

| 字段 | 值 |
|------|-----|
| 用户名 | `demo` |
| 密码 | `Demo123456` |

## Demo 走查（接口测试模块）

详细逐步验收清单见 **[docs/demo/DEMO_CHECKLIST.md](./docs/demo/DEMO_CHECKLIST.md)**。

快速路径：

1. 登录 → 首页选择 **接口测试**
2. 进入 **Demo 商城 API**（或新建接口项目并上传 Swagger）
3. 确认 **环境变量** 中 `dev.base_url` 已配置
4. 单条执行用例，或使用 **AI 生成** draft 用例并确认入库
5. 打开 **Demo 冒烟计划**（或新建计划），绑定用例，配置 Cron
6. 手动执行计划 → 查看 Allure 报告 → 检查飞书通知（可选）

## Demo 数据

示例 Swagger 与 seed 脚本：

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
python scripts/seed_demo.py
```

| 资源 | 路径 |
|------|------|
| 示例 OpenAPI | `docs/demo/demo-openapi.json` |
| Seed 脚本 | `backend/scripts/seed_demo.py` |

Seed 将创建：

- 用户 `demo / Demo123456`
- 环境 `dev`（`base_url=https://jsonplaceholder.typicode.com`）
- 接口项目 **Demo 商城 API**（4 个接口、2 条用例、1 个测试计划）

脚本可重复执行（幂等），已存在的数据会跳过或更新。

## 运行测试

```bash
cd backend
source .venv/bin/activate
pytest -q
```

## 目录结构

```
AITF/
├── frontend/          # Vue 3 前端
├── backend/           # FastAPI 后端
│   ├── app/           # 应用代码
│   ├── alembic/       # 数据库迁移
│   └── tests/         # pytest 单元测试
├── storage/           # 运行时数据（DB、报告、上传，gitignore）
├── docker-compose.yml
├── architecture.md    # 架构设计
└── tasks.md           # 任务清单
```

## 常见问题

**Q: `/api/v1/dashboard/stats` 返回 404？**  
A: 后端代码更新后需重启 uvicorn；Docker 模式需 `docker compose up -d --build backend`。

**Q: AI 生成失败？**  
A: 检查 `.env` 中 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`AI_MODEL` 是否配置正确。

**Q: Allure 报告为 fallback HTML？**  
A: 本地需安装 Allure CLI 并配置 `ALLURE_CLI`；Docker 镜像已内置。

**Q: 用例执行请求不到 localhost 上的被测服务？**  
A: Docker 后端运行时，环境变量中设置 `RUNNER_HOST_ALIAS=host.docker.internal`。

## 文档

- [architecture.md](./architecture.md) — 架构设计
- [tasks.md](./tasks.md) — MVP 任务与验收清单
- [docs/demo/DEMO_CHECKLIST.md](./docs/demo/DEMO_CHECKLIST.md) — Demo 端到端验收清单
