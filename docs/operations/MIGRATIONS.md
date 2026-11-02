# 数据库迁移说明

迁移实现位于 `backend/app/migrations.py`，启动时由 `init_db()` 自动执行。

## 版本

| 版本 | 内容 | 是否破坏数据 |
|------|------|--------------|
| 1 | 基线（最初由 `create_all` 建表） | 否 |
| 2 | 用 FSRS 列替换旧的 SM-2 列（`ease` / `interval_days` / `due_date` / `last_review_at`） | **是**：先清空词书/单词/状态/流水 |
| 3 | 引入多账号：给业务表补 `user_id`、重建 `settings` | **是**：清空账号体系之前的无主数据 |
| 4 | 二部图三表 `senses` / `word_senses` / `sense_states`；扩展 `study_logs.phase`（`meaning`/`group`）与 `result`（`partial`） | 否：只增表 / 扩枚举，不动既有数据 |
| 5 | 简化义项图映射：删 `senses.definition_en`、`senses.merged_into`、`word_senses.gloss_raw`；删 `senses` 的 `(book_id, label_zh, pos)` 唯一键，改普通索引 | 否：只删没人用的列与约束；`label_zh` 仍非空 |

### 版本 5 的理由

- **删 `(book_id, label_zh, pos)` 唯一键**：2026-11-03 顶点重建后，同一中文标签会对应多个义项顶点（866 个义项只有 761 个不同标签，105 个重复，例如「贬低」对应两个义项）。保留唯一键会让导入直接失败。
- **删 `definition_en`**：英文释义已被排除出建图依据（见 实现大事记 §7），全项目没有调用方。
- **删 `merged_into`**：顶点改为每次全量重建，不需要保留合并痕迹；`status`（active / needs_review）仍在。
- **删 `gloss_raw`**：无调用方；每个词的措辞保留在 `label_zh` 与释义来源里。

已在 MySQL 8.4.9 上实测（2026-11-03）：三列删除、唯一键替换为索引后，同一 `label_zh` 的多行可以共存；新导入脚本 `src/scripts/import_vertices_v5.py` 端到端导入 857 义项 / 2,105 边 / 857 张义项卡。

## 全新数据库

先检查数据库中是否已有 `word_books` / `users` / `schema_migrations`：

- **没有**（全新库）：`create_all` 直接按当前模型建表，然后把版本 1/2/3/4/5 全部标记为已应用。
  不会执行版本 2/3 中的 `DELETE FROM`。
- **有**（旧库升级）：保留原有路径，按序执行尚未应用的迁移。

这样既能让新用户快速得到最新结构，也能让开发期旧库继续升级。

## 规则

- 结构变更必须在 `MIGRATIONS` 末尾追加新版本，**不要修改已发布的迁移**。
- MySQL 的 DDL 会隐式提交，迁移不是完全事务性的；升级前请备份数据库。
- 旧库升级到版本 2/3 会清空业务数据，这是开发期设计的取舍；公开发布后如需兼容旧数据，
  应新增迁移而不是复用这两个破坏性版本。
- 迁移版本记录在 `schema_migrations` 表中。

