# 发布清单

发布前逐项勾选。建议在干净的检出目录和一台干净的 Windows 机器上各走一遍。

## 1. 版本与内容

- [ ] `backend/app/version.py` 与 `frontend/package.json` 的版本号一致
- [ ] `CHANGELOG.md` 已添加对应版本条目
- [ ] README 的功能、系统要求、命令与实际一致
- [ ] `sample/` 中只有自编示例词书，没有第三方版权资料
- [ ] 没有在文档或代码中写入真实数据库口令

## 2. 仓库卫生

```bash
python scripts/check_repo_hygiene.py
git status --ignored
git ls-files
```

- [ ] 未跟踪 `.env`、`backend/dist/`、`backend/build/`、`frontend/dist/`、`node_modules/`
- [ ] 未跟踪 GRE PDF / 机经词书 / 提取脚本
- [ ] 未跟踪超过 5 MB 的非白名单文件
- [ ] 源码与构建脚本中没有本机绝对路径（如 `F:/study_material`）

## 3. 自动化检查

```bash
cd backend
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m pytest -ra

cd ../frontend
npm ci
npm run lint
npm run format:check
npm run test:run
npm run build
```

- [ ] 后端测试全部通过，API 测试未被 skip（CI 中必须有 MySQL service）
- [ ] 前端测试全部通过，`vue-tsc` 无错误
- [ ] GitHub Actions 首个流水线绿灯

## 4. 功能冒烟

用两个新账号走一遍：

- [ ] 注册 / 登录 / 退出；账号 A 看不到账号 B 的数据
- [ ] 上传 `sample/示例词书.md`，词书自动成为当前词书
- [ ] 上传超过上限的文件返回 413，且不产生词书
- [ ] 超长音标/释义/例句能导入且被截断
- [ ] 学习新词（认识/不认识/熟知、挖空、快速复查）
- [ ] 复习答错 → 详情 → 回队重学
- [ ] 修改密码：旧密码失败、新密码成功、其他会话失效
- [ ] 导出备份 → 另一账号导入 → 词书/状态/统计/设置一致
- [ ] 重置某本词书进度，单词保留且回到新词
- [ ] 删除当前词书后自动切换到剩余词书
- [ ] 访问未知路由显示 404；favicon 正常
- [ ] 375 / 768 / 1024 px 宽度无横向滚动，弹窗与按钮可用
- [ ] 键盘：空格、1/2/3、1-4、回车；答题对错可被读屏播报

## 5. 构建与产物

```bash
build_exe.bat
backend\.venv\Scripts\python.exe scripts\package_release.py
backend\.venv\Scripts\python.exe scripts\package_release.py --with-exe
```

- [ ] exe 可启动，浏览器打开 `http://127.0.0.1:8000`
- [ ] `%APPDATA%\背单词助手\.env` 首次生成，修改数据库口令后可连接
- [ ] 发布包根目录包含 LICENSE / README / LICENSES/THIRD_PARTY_NOTICES / docs/legal/PRIVACY / CHANGELOG
- [ ] 记录并公布 exe 与 zip 的 SHA-256
- [ ] 解压发布包确认不含 `.env`、数据库口令、GRE 资料、旧 exe、`node_modules`

## 6. 发布

- [ ] 打 tag（如 `v1.0.0`）
- [ ] 在 Release 中上传 exe、源码包、SHA-256 与 CHANGELOG
- [ ] 在 README 中更新下载链接（如有）
- [ ] 发布后检查一次干净机器安装流程

## 已知限制（发布时说明）

- 仅 Windows 提供打包；其他平台可源码运行
- 必须本机安装 MySQL 8.x
- exe 未签名，SmartScreen 可能提示未知发布者
- 限流为进程内实现，不适用于多 worker
- 备份为合并导入，不提供一键覆盖
- README 截图需维护者实际运行后补充
