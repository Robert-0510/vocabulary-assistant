# 贡献指南

感谢你愿意改进背单词助手。提交代码前请先阅读本指南。

## 环境

- Python ≥ 3.11（推荐 3.11）
- Node.js ≥ 20
- MySQL 8.x
- Windows 为主要支持平台；其他平台可运行源码，但打包脚本目前仅覆盖 Windows

## 本地开发

```bash
# 后端
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# 前端（另开终端）
cd frontend
npm ci
npm run dev
```

数据库配置见 `backend/.env.example` 与 `scripts/setup_mysql.sql`。

## 提交前检查

```bash
cd backend
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m pytest

cd ../frontend
npm run lint
npm run test
npm run build
```

## 代码约定

- 后端：Python 3.11 类型标注；结构变更必须追加 `backend/app/migrations.py` 中的迁移，
  不修改已发布的迁移。
- 前端：Vue 3 `<script setup>` + TypeScript；沿用 Element Plus 与现有中文文案风格。
- 新增接口必须校验资源归属，跨账号访问返回 404。
- 涉及数据库写入的输入必须受长度/大小限制，避免把 `DataError` 暴露成 500。
- 新增功能请补充对应测试。

## Pull Request

1. 从主分支创建功能分支。
2. 保持提交聚焦；说明动机、行为变化与验证方式。
3. 确保 CI 通过。
4. 涉及 UI 的改动请附截图或录屏（如果条件允许）。
5. 不要提交 `.env`、数据库口令、构建产物或个人学习数据。

## 许可证

提交即表示你同意以本项目的 MIT 许可证贡献这些代码。
