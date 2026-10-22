# 背单词助手（Vocabulary Assistant）

本地运行的中文背单词工具：**自定义 Markdown 词书 + 每日任务 + FSRS 间隔重复 + 学习统计**。
数据保存在你自己的 MySQL 中，不依赖云账号。

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Node](https://img.shields.io/badge/node-20%2B-green.svg)
![MySQL](https://img.shields.io/badge/MySQL-8.x-orange.svg)

> 界面截图：请在首次运行后由维护者补充到 `docs/screenshots/`。本文档不放置虚构截图。

---

## 目录

- [功能](#功能)
- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [词书格式](#词书格式)
- [账号与数据隔离](#账号与数据隔离)
- [备份与恢复](#备份与恢复)
- [隐私与联网](#隐私与联网)
- [安全说明](#安全说明)
- [常见问题](#常见问题)
- [开发与测试](#开发与测试)
- [构建与发布](#构建与发布)
- [公开发布计划（P0 / P1）](#公开发布计划-p0--p1)
- [许可证与贡献](#许可证与贡献)

---

## 功能

- **多账号**：用户名 + 密码注册/登录；每个账号的词书、记忆状态、学习流水与统计完全隔离。
- **自定义词书**：上传 Markdown 表格（`.md` / `.markdown` / `.txt`），同书自动去重；支持拖拽、分页词表、搜索、状态筛选与单词纠错编辑。
- **FSRS 调度**：基于官方 `fsrs` 包（v6.3.2）的间隔重复，按记忆稳定性/难度计算下次复习时间。
- **每日任务**：6 档预设（新词 25–200 / 复习 50–400）+ 滑块微调。
- **学习流程**：新词自评（认识 / 不认识 / 熟知）→ 例句挖空 → 队尾快速复查；复习看英选中 / 看中选英，答错回队重学。
- **发音与快捷键**：空格发音；`1/2/3` 自评，`1-4` 选答案，回车继续。
- **统计**：打卡日历、近 3 个月热力图、记忆状态分布、近 30 天学习曲线、连续打卡。
- **数据管理**：导出 / 合并导入 JSON 备份（含 FSRS 状态与学习流水）、重置单本词书进度、修改密码。
- **体验细节**：404 页面、favicon、响应式布局、全局错误兜底、无障碍反馈。

## 系统要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Windows | 10 / 11 | 打包版当前仅支持 Windows |
| MySQL | 8.x | 必须在本机运行；服务名通常为 `MySQL80` |
| Python | 3.11 | 仅源码运行 / 构建时需要 |
| Node.js | 20+ | 仅源码运行 / 构建前端时需要 |

> **为什么需要 MySQL？** 本项目选择 MySQL 作为唯一数据库。打包版不会捆绑数据库，
> 首次使用前请先安装 MySQL 8.x 并启动服务。若你希望零依赖运行，可关注后续的 SQLite 方案。

## 快速开始

### 方式一：使用打包好的 exe（推荐给普通用户）

1. 下载 `背单词助手-1.0.0.exe`。
2. 确保本机 MySQL80 服务已启动。
3. 双击 exe。首次运行会在 `%APPDATA%\背单词助手\.env` 生成配置模板。
4. 用文本编辑器填写 `DB_USER` / `DB_PASSWORD`（建议使用专用账号，见下文），再次双击。
5. 浏览器会自动打开 `http://127.0.0.1:8000`，注册账号后即可使用。

> Windows SmartScreen 可能提示“未知发布者”，因为当前 exe **未做代码签名**。
> 校验 SHA-256 后再运行；若从源码自行构建，可忽略该提示。

### 方式二：一键启动（源码，已构建前端）

双击项目根目录的 **run.bat**。它会启动服务并打开浏览器；关闭命令行窗口即停止。

前置：`frontend/dist` 已存在，且 `backend/.venv` 已安装依赖。

### 方式三：开发模式

```bash
# 1. 建库（先把脚本里的 CHANGE_ME 改成强密码）
mysql -u root -p < scripts/setup_mysql.sql

# 2. 后端
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
# 编辑 .env，填入与 setup_mysql.sql 相同的密码
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# 3. 前端（另开终端）
cd frontend
npm ci
npm run dev
# 打开 http://localhost:5173
```

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：`GET /api/health` 返回 `{"ok": true, "db": "ok", "version": "1.0.0"}`
- 首次启动会自动建库（账号有 `CREATE` 权限时）、建表并执行版本化迁移。

### 数据库配置

- 源码模式：`backend/.env`（无论从哪个目录启动都会读取）。
- 打包模式：`%APPDATA%\背单词助手\.env`；若 exe 同目录存在旧版 `.env` 则优先使用。
- 推荐使用 `scripts/setup_mysql.sql` 创建的 `vocab_app` 最小权限账号，不要用 root 日常运行。
- 可用环境变量 `VOCAB_ENV_FILE` 显式指定配置文件。

常用可选项（完整列表见 [backend/.env.example](backend/.env.example)）：

```ini
COOKIE_SECURE=false          # 放在 HTTPS 反向代理后改为 true
SESSION_TTL_DAYS=30
MAX_UPLOAD_MB=10             # 单个词书文件上限
MAX_IMPORT_MB=50             # 备份文件上限
MAX_WORDS_PER_BOOK=20000
RATE_LIMIT_ENABLED=true
LOGIN_RATE_LIMIT=10          # 每 60 秒
REGISTER_RATE_LIMIT=10       # 每 3600 秒
PASSWORD_RATE_LIMIT=5        # 每 600 秒
```

## 词书格式

Markdown 表格，例句列可留空；例句按「英文 中文」写在一格（自动按首个中文字符拆分）：

```markdown
| 单词 | 音标 | 释义 | 例句 |
|------|------|------|------|
| abandon | /əˈbændən/ | v. 放弃；抛弃 | He abandoned the plan. 他放弃了计划。 |
| benefit | /ˈbenɪfɪt/ | n. 好处 v. 受益 | |
```

- 一级标题（`# 词书名`）会作为词书名；没有标题时使用文件名。
- 同一文件内重复单词自动跳过，导入结果会显示成功数 / 跳过数。
- 超长字段会按数据库列宽安全截断（单词 100、音标 200、释义 1000、中文例句 500），不会导致 500 错误。
- 上传上限默认 10 MB / 20,000 词，可在 `.env` 中调整。
- 示例见 [sample/示例词书.md](sample/示例词书.md)。

> 本项目不再随仓库分发任何第三方备考资料。你自行导入的词书内容由你自行负责其版权与使用权。

## 账号与数据隔离

- 首页提供「登录 / 注册」入口；**登录后才能开始学习**。
- 每个账号拥有独立的词书、单词记忆状态、学习流水和统计，账号之间互不可见。
- 密码使用 PBKDF2-SHA256（16 字节随机盐、260,000 次迭代）加盐哈希存储。
- 登录后签发 30 天有效的 HttpOnly 会话 Cookie（`SameSite=Lax`），服务端只保存 token 的 SHA-256。
- 支持修改密码：成功后吊销该账号的全部会话，需要用新密码重新登录。
- 支持「注销账号」：再次输入当前密码确认后，**物理删除**账号及其全部词书、单词、记忆状态、学习流水、会话和设置，不可恢复。
- 删除词书同样是物理删除，级联清除其下全部数据；若删除的是当前词书，会自动切换到剩余最近创建的一本。

## 备份与恢复

在「设置 → 数据备份」中：

- **导出备份**：下载带版本号的 JSON（`format: vocab-assistant-backup`, `version: 1`），包含词书、单词、FSRS 状态、学习流水与每日任务设置。
- **导入备份（合并）**：追加导入，不覆盖现有数据；同名词书自动改名为 `名称(2)`、`名称(3)`。
- 单个备份上限默认 50 MB；会校验格式、版本、词书数、单词数与流水数，非法文件返回 4xx 而不是 500。
- 备份文件包含个人学习数据，请妥善保管，不要上传到公开仓库。

命令行等价操作：

```bash
# 导出（使用登录 Cookie）
curl -b cookies.txt http://127.0.0.1:8000/api/export -o backup.json

# 导入
curl -b cookies.txt -F "file=@backup.json" http://127.0.0.1:8000/api/import
```

## 隐私与联网

- 应用**不包含遥测、统计 SDK、崩溃上报或广告**，不会主动把数据发送给维护者。
- 账号与学习数据只保存在本机 MySQL；备份文件由你自行保管。
- 发音优先使用浏览器 / 操作系统 TTS；没有可用英文语音时，会请求 `dict.youdao.com`
  的公开发音音频。该请求只发送当前单词，由浏览器直接发起。
- 服务只监听 `127.0.0.1`，不要直接暴露到公网或不可信局域网。

完整说明见 [docs/PRIVACY.md](docs/PRIVACY.md)。

## 安全说明

- 不要把真实密码写进代码或提交到版本库；`backend/.env` 已被 `.gitignore` 忽略。
- 推荐使用 `vocab_app` 最小权限账号（见 `scripts/setup_mysql.sql`），不要用 root 日常运行。
- 登录 / 注册 / 修改密码有进程内滑动窗口限流；本地单进程有效，多实例部署需换成共享存储。
- 上传与导入都有服务端大小 / 数量 / 字段长度限制，不能依赖前端校验。
- 打包版同源托管前端，已禁用 CORS；源码开发模式只允许本机 Vite 地址。
- `COOKIE_SECURE=false` 仅为本地 HTTP 默认值；放在 HTTPS 反向代理后请改为 `true`。
- 漏洞报告方式见 [SECURITY.md](SECURITY.md)。

## 常见问题

**启动时提示数据库连接失败 / 1045 / 2003？**
检查 MySQL80 服务是否运行、`.env` 中的账号密码是否正确、端口 3306 是否可达。
打包版配置文件在 `%APPDATA%\背单词助手\.env`。

**提示 1049 数据库不存在？**
账号需要有 `CREATE` 权限才能自动建库；否则请手动执行 `scripts/setup_mysql.sql`。

**端口 8000 被占用？**
关闭占用程序，或修改 `launcher.py` 中的 `PORT`（同时需要调整前端代理 / 同源访问方式）。

**页面打不开 / 只有 API？**
源码模式需要先执行 `cd frontend && npm run build` 生成 `frontend/dist`。

**exe 被 SmartScreen 拦截？**
当前发布版未做代码签名。请从可信来源下载并核对 SHA-256；介意时可自行从源码构建。

**忘记密码怎么办？**
本应用没有邮箱找回机制，因为它是本地应用。若其他会话仍登录，可在「设置 → 账号安全」修改；
否则只能注销账号重新开始（数据不可恢复）。建议定期导出备份。

**导入备份会覆盖现有数据吗？**
不会。导入是合并模式，同名词书会自动改名。当前版本不提供“替换全部数据”模式。

## 开发与测试

```bash
# 后端测试（需要 MySQL；会自动创建并删除独立临时库）
cd backend
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m pytest -ra

# 前端
cd frontend
npm run lint
npm run format:check
npm run test:run
npm run build
```

- 后端测试在 MySQL 不可用时**本地会 skip**；CI 中设置了 `CI=true`，不可用会直接失败，
  避免“全绿但一条 API 测试都没跑”。
- 新增结构变更必须追加 `backend/app/migrations.py` 中的迁移，不要修改已发布的历史迁移。
- 首次建库会走“压缩基线”，不会执行开发期迁移中的 `DELETE FROM`；旧库升级仍按版本执行。

## 构建与发布

```bash
# 一键构建 exe（会自动安装构建依赖、构建前端、复制许可文件并输出 SHA-256）
build_exe.bat

# 生成源码发布包（排除 .env / 构建产物 / 依赖 / 版权资料）
backend\.venv\Scripts\python.exe scripts\package_release.py

# 生成含 exe 的运行包
backend\.venv\Scripts\python.exe scripts\package_release.py --with-exe
```

发布前请逐项检查 [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)。

## 公开发布计划（P0 / P1）

> 本节按用户要求完整记录本次公开发布完善方案。`[x]` 表示本轮已完成，`[ ]` 表示需要人工或后续完成。

### 背景与决策

项目核心功能完整，审计后补齐公开发布所需的法务、仓库、工程、产品与文档能力。已确认：

- 许可证：**MIT**
- 数据库：**保持 MySQL 8.x**，不迁移 SQLite；文档明确前置条件
- 示例语料：**GRE PDF 及派生 Markdown 移出发布内容**，仅保留自编示例
- 范围：**P0 + 全部 P1**

### P0：发布前必须完成

- [x] 新增 MIT `LICENSE` 与 `THIRD_PARTY_NOTICES.md`
- [x] 移除受版权保护的 GRE PDF / 派生 Markdown / 提取脚本（已备份到项目外）
- [x] 补齐 `.gitignore`（`.env`、`backend/dist`、`frontend/dist`、依赖、构建产物）
- [x] 新增 `.gitattributes`、`.editorconfig`
- [x] 删除写死绝对路径的过期 PyInstaller spec
- [x] 初始化 git 仓库并提交（不推送远程）
- [x] 新增 GitHub Actions CI（后端 MySQL 测试、前端 lint/test/build、仓库卫生）
- [x] 重写 README，修正 `docs/设计方案.md` 中的过时描述
- [x] 新增 `docs/PRIVACY.md`、`SECURITY.md`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`
- [x] 明确分发形态：Windows exe / 源码；MySQL 为前置条件；未签名 exe 的 SmartScreen 提示
- [x] 修复打包：相对路径、图标、版本信息、校验和、许可文件随包
- [x] 锁定依赖版本（后端精确 pin，前端 `package-lock.json`）
- [x] 版本单一来源 `backend/app/version.py` = 1.0.0，`package.json` 同步

### P1：发布质量

**工程加固**

- [x] 上传大小 / 词数上限（默认 10 MB / 20,000 词，可配置）
- [x] 字段长度校验与安全截断，避免 MySQL `DataError` → 500
- [x] 登录 / 注册 / 改密码限流（429 + `Retry-After`）
- [x] `COOKIE_SECURE`、`SESSION_TTL_DAYS` 可配置
- [x] 今日任务消除 N+1（一次取候选池 + `selectinload`，40 词测试查询数 ≤ 15）
- [x] `/api/health` 检查数据库并返回版本；不可用返回 503
- [x] 请求日志、`X-Request-ID`、统一日志格式
- [x] 迁移基线：全新库盖章当前 schema，不执行破坏性开发期迁移；旧库保留升级路径
- [x] 后端 pytest：37 个用例（含限流、备份、迁移幂等、查询数）

**产品功能**

- [x] 修改密码（吊销全部会话）
- [x] 导出 / 合并导入 JSON 备份（含 FSRS 状态与学习流水）
- [x] 重置单本词书进度
- [x] 删除当前词书后自动回退到剩余词书
- [x] 词表内单词纠错编辑（含同书重复校验）

**前端体验**

- [x] 404 页面 + 路由标题
- [x] favicon、theme-color、页面描述
- [x] 全局错误兜底（Vue errorHandler / unhandledrejection / 路由加载失败）
- [x] 响应式布局（900px / 640px 断点、侧栏变顶栏、表格/弹窗/按钮自适应）
- [x] 按需引入 Element Plus 与 ECharts；主 JS 从 1.3 MB 降至约 371 KB
- [x] 无障碍：`aria-live` 答题反馈、图标按钮 `aria-label`、焦点样式、减少动画
- [x] 前端 Vitest：9 个用例（学习状态机、QuizCard、路由、发音兜底）

**文档与发布流程**

- [x] README 全面重写（安装、配置、备份、隐私、安全、FAQ、开发、构建）
- [x] `CHANGELOG.md` 1.0.0
- [x] `docs/RELEASE_CHECKLIST.md` 发布清单
- [x] `scripts/package_release.py` 发布打包（排除密钥与构建产物）
- [x] `scripts/check_repo_hygiene.py` 仓库卫生检查
- [x] ESLint / Prettier / Ruff 配置与 CI 检查

### 验证方式

```bash
# 后端
cd backend
.venv\Scripts\python -m pytest -ra

# 前端
cd frontend
npm run lint && npm run format:check && npm run test:run && npm run build

# 仓库卫生
python scripts/check_repo_hygiene.py
```

冒烟流程：注册两个账号 → 上传示例词书 → 学习新词/复习 → 修改密码 → 导出备份 →
导入到另一账号 → 重置进度 → 删除当前词书验证回退 → 访问未知路由 → 窄屏检查。

### 仍需人工完成

- [ ] 在真实浏览器（375 / 768 / 1024 / 桌面）完成一次 UI 冒烟并补充真实截图
- [ ] 在干净 Windows 机器上安装 MySQL 8.x，从零运行一次 exe
- [ ] 在 GitHub 上创建仓库、推送、确认首个 CI 绿灯、发布 Release 与校验和
- [ ] （可选）购买代码签名证书，消除 SmartScreen 未知发布者提示
- [ ] （后续）评估 SQLite / 自动更新 / 多语言等增强

### 风险与已知限制

- 限流是**进程内**实现，重启清零，不适用于多 worker / 多实例；本项目按本机单进程设计。
- 备份是**合并**导入，不提供一键覆盖；重复导入会生成带 `(2)` 后缀的副本。
- 学习统计按 MySQL 服务器本地日期聚合；请保持数据库与本机在同一时区。
- 仅 Windows 提供打包脚本；其他平台可运行源码。
- 未签名 exe 可能触发 SmartScreen；这是分发限制，不是程序缺陷。
- 本次未伪造 README 截图，截图需维护者实际运行后补充。

## 许可证与贡献

- 许可证：[MIT](LICENSE)
- 第三方组件与许可：[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- 隐私说明：[docs/PRIVACY.md](docs/PRIVACY.md)
- 数据库迁移：[docs/MIGRATIONS.md](docs/MIGRATIONS.md)
- 安全策略：[SECURITY.md](SECURITY.md)
- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)
- 行为准则：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- 更新日志：[CHANGELOG.md](CHANGELOG.md)

欢迎提交 Issue / PR。提交前请先阅读贡献指南并确保本地检查通过。
