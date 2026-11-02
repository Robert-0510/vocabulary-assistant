# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增

- **词汇—释义二部图**：新增 `senses`（义项）、`word_senses`（词↔义项边）、`sense_states`（义项卡）三张表与迁移 v4；等价关系不再存“词—词”边，而是“共享同一义项”
- **两种新题型**：`meaning_multi`（看单词，多选全部释义）与 `equiv_group`（看锚词，多选同义组成员）；服务端判分，不下发答案
- **评级映射**：全对 → Good、部分正确 → **Hard**（首次启用）、全错 → Again；FSRS 算法与参数不变
- **义项级 FSRS**：一张义项卡 = 一组同义替换，多义词按义项拆成多张卡；词级卡保留给没有同义伙伴的义项
- **真题导入流水线**：`scripts/check_exam_answers.py`（校验答案表）、`scripts/import_exam.py`（答案 → JSON）、`scripts/import_sense_graph.py`（义项图 → 数据库，幂等，支持 `--book-id` / `--force` / `--dry-run`）
- **前端**：`MeaningMultiCard`、`EquivGroupCard`、`SenseResultPanel` 三个组件；学习状态机新增 `meaning` / `group` 步骤；`1–9` 键切换选项、回车提交
- **文档**：`docs/design/二部图数据表示.md`（图在库里怎么存 + SQL 还原）、`docs/operations/新功能交接单.md`、`docs/operations/实现大事记.md`

### 变更

- `/api/study/progress` 增加 `sense_target` / `sense_done`；`new_done` 计入新题型对应的 `meaning` 阶段
- 词书里没有义项数据时，自动回退到原有题型（向后兼容）

### 修复

- 义项碎片化：同一概念曾被拆成多个义项顶点（`capricious` 一度散落在 6 个义项里，导致多选题出现 6 个“正确选项”）；改为按「边」聚类后为 831 个义项，`capricious` 收敛为 2 个
- 进度统计漏算新题型，答完题后进度条仍为 0
- 删除与规范位置重复的文档副本

### 移除

- 根目录重复的 `CODE_OF_CONDUCT.md`、`CONTRIBUTING.md`、`SECURITY.md`、`THIRD_PARTY_NOTICES.md`（`.github/` 与 `LICENSES/` 下已有）
- `build_exe.bat`、`run.bat`，构建流程改由 `scripts/build_exe.py` 承担

### 已知限制

- 尚未做用户实验，缺少学习效果数据
- 6 个超过 8 个词的义项被标记为待复核（多由松散等价边串联）

## [1.0.0] - 2026-10-21

首个公开发布版本。

### 新增

- 多账号注册 / 登录 / 注销，词书与学习数据按账号隔离
- 自定义 Markdown 词书上传、词表分页搜索、词书切换与删除
- FSRS 间隔重复调度，新词自评、例句挖空、复习测试与当日错词重学
- 打卡日历、热力图、记忆状态分布与近 30 天学习曲线
- 修改密码（使其他会话失效）
- 数据导出 / 导入备份（包含 FSRS 记忆状态）
- 重置单本词书的进度
- 词表内单词纠错编辑
- 登录 / 注册限流
- 请求日志、请求 ID 与数据库健康检查
- MIT 许可证、隐私说明、安全策略、贡献指南与发布清单
- GitHub Actions CI（后端 MySQL 测试、前端 lint/test/build）

### 变更

- 上传词书限制大小与词数，超长字段安全截断，避免数据库错误
- 今日任务题目生成消除 N+1 查询
- 删除当前词书后自动切换到剩余词书
- 前端按需引入 Element Plus / ECharts，减小打包体积
- 增加 404 页面、favicon、移动端响应式布局与全局错误兜底
- 依赖版本锁定，提供可复现构建

### 移除

- 不再随仓库分发第三方 GRE 备考资料及其提取脚本
- 移除写死绝对路径的过期 PyInstaller spec

### 已知限制

- 仅支持 Windows 打包；源码模式可在其他平台运行
- 需要本机安装并运行 MySQL 8.x
- 发布 exe 未做代码签名，Windows SmartScreen 可能提示未知发布者
- 暂无自动更新与云同步
