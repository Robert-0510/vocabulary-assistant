# FSRS 原理、效果证据与调度优化清单

> **文档状态**：新增总结文档（2026-11-01）
> **适用范围**：只讨论调度层——复习间隔、稳定性/难度、参数、排序、负载与新词节奏；不展开测试形式、内容、激励、评估等功能。
> **代码基线**：`backend/requirements.txt` 中的 `fsrs==6.3.2`，调度实现见 [scheduler.py](../../backend/app/services/scheduler.py)。
> **与总纲的关系**：项目全貌、数据模型、学习流程和路线图仍以 [项目介绍与方案设计.md](项目介绍与方案设计.md) 为准；本文只做 FSRS 专题总结，不替代总纲。

---

## 0. 本项目说明性文档清单

### 0.1 说明性文档

| 文档 | 位置 | 主要作用 | 与本文的关系 |
|------|------|----------|--------------|
| 背单词助手 README | [README.md](../../README.md) | 安装、使用、构建、发布、FAQ | 面向使用者的入口，不重复设计细节 |
| 项目介绍与方案设计（总纲） | [项目介绍与方案设计.md](项目介绍与方案设计.md) | 项目定位、架构、数据模型、学习流程、等价词组规划、路线图 | 本文的上层文档；FSRS 语义见其 §3.3、§4.4 |
| 数据库迁移说明 | [MIGRATIONS.md](../operations/MIGRATIONS.md) | 迁移版本、规则、破坏性变更 | 新增 `review_logs` / 设置字段时遵循其规则 |
| 隐私说明 | [PRIVACY.md](../legal/PRIVACY.md) | 收集范围、存储位置、联网边界 | 本地调度优化不改变隐私边界 |
| 发布清单 | [RELEASE_CHECKLIST.md](../operations/RELEASE_CHECKLIST.md) | 版本、仓库卫生、冒烟、构建、发布 | 调度改动进入发布前需走该清单 |
| 更新日志 | [CHANGELOG.md](../../CHANGELOG.md) | 版本变更记录 | 调度行为变化应记录 |
| 贡献指南 | [CONTRIBUTING.md](../../.github/CONTRIBUTING.md) | 环境、开发、提交前检查、PR 约定 | 实现本文清单时遵循 |
| 安全策略 | [SECURITY.md](../../.github/SECURITY.md) | 支持版本、漏洞报告、威胁模型 | 本地部署边界不变 |
| 行为准则 | [CODE_OF_CONDUCT.md](../../.github/CODE_OF_CONDUCT.md) | 社区行为规范 | 与调度实现无关 |
| 第三方组件与许可 | [THIRD_PARTY_NOTICES.md](../../LICENSES/THIRD_PARTY_NOTICES.md) | 后端/前端依赖许可、数据来源 | 引入优化器/新库时需更新 |
| 示例词书 | [示例词书.md](../../sample/示例词书.md) | Markdown 词书格式示例 | 调度不依赖词书内容，但依赖词条状态 |
| **本文** | [FSRS原理效果与优化清单.md](FSRS原理效果与优化清单.md) | FSRS 原理、公开效果证据、调度层优化清单 | 新增总结文档 |

> 目录约定：设计/算法文档在 `docs/design/`，迁移/发布文档在 `docs/operations/`，隐私政策在 `docs/legal/`；社区健康文件按 GitHub 约定放在 `.github/`；第三方许可通知在 `LICENSES/`。完整目录树见 [项目介绍与方案设计.md](项目介绍与方案设计.md) §0.1。

### 0.2 非说明性但相关的文本

以下文件不是“说明文档”，但和调度改动有关，单独列出避免混淆：

- `LICENSE`、`LICENSES/`（含 `THIRD_PARTY_NOTICES.md` 与许可证文本）：法律许可文本；
- `backend/requirements*.txt`：依赖清单（`fsrs==6.3.2` 在这里）；
- `backend/.env.example`：配置示例；
- `scripts/setup_mysql.sql`：数据库初始化脚本；
- `.github/workflows/ci.yml`：CI 配置；
- `assets/version_info.txt`：Windows 构建元数据；
- `release/*.zip`：发布产物。

### 0.3 本文的边界

本文把“评级”当作调度输入，不讨论如何出题、如何引导用户自评、如何做激励或评估功能。因此：

- 不提出新的测试形式；
- 不设计 UI；
- 不讨论打卡、排行榜、内容生成；
- 只讨论：**给定现有评级，如何更合理地安排下一次复习。**

---

## 1. 结论摘要

1. **FSRS 作为调度器够用。** FSRS-6 在公开 benchmark 上明显优于 HLR、Ebisu、FSRS-4.5 等模型；21 个参数、开源实现、默认参数稳健，适合本地单词 App。
2. **FSRS 不是 SOTA。** FSRS-7 和神经网络模型预测更准，但收益/成本不匹配；FSRS-6 已经处在“紧凑、可解释、易部署”的高性价比区间。
3. **FSRS 是模型，不是策略。** 它只回答“S/D 怎么变、下次间隔多少”；`desired_retention`、学习步进、积压处理、排序、每日上限都是策略，FSRS 不替你决定。
4. **只优化调度层时，最大收益来自策略与数据，而不是换公式。** 优先做：`desired_retention`、`review_logs`、按 R 排序、积压限流、步进、参数优化。
5. **不要为了“更先进”而迁 FSRS-7 或自研模型。** 日级调度收益约 1–2%；同日复习场景收益更大，但需要小数间隔和额外迁移成本。

一句话：

> **FSRS-6 默认参数已经够好；继续卷算法收益递减，把策略、日志、负载和校准做好更划算。**

---

## 2. FSRS 原理

### 2.1 三个核心变量

FSRS 用三个变量描述一张卡片：

| 变量 | 名称 | 含义 | 范围 |
|------|------|------|------|
| `R` | Retrievability（可提取性） | 当前时刻能回忆起来的概率 | 0–1 |
| `S` | Stability（稳定性） | 记忆稳定性，单位为天；`R` 降到 90% 所需时间 | > 0 |
| `D` | Difficulty（难度） | 这个词对学习者的难度 | 1–10 |

- `S` 越大，忘得越慢；
- `D` 越大，同样一次成功复习带来的 `S` 增长越少；
- FSRS 的“记忆状态”就是 `(S, D)`，`R` 是由 `S` 和时间推出来的。

UI 上的 `new / learning / reviewing / mastered` 只是投影，不是 FSRS 的调度变量。

### 2.2 遗忘曲线

FSRS-6 的遗忘曲线：

```text
R(t, S) = (1 + FACTOR * t / S) ^ (-w20)

FACTOR = 0.9 ^ (-1 / w20) - 1
```

其中 `t` 是距上次复习的天数，`w20` 是第 21 个参数，控制曲线衰减形状。这个式子保证：

```text
t = S 时，R = 0.9
```

所以 `S` 的定义是“R 降到 90% 所需的时间”。默认 `desired_retention = 0.9` 时，下次间隔约等于 `S`。

版本差异：

- FSRS-4.5：固定 `DECAY = -0.5`、`FACTOR = 19/81`；
- FSRS-5：19 个参数；
- FSRS-6：21 个参数，`w20` 可学习，曲线形状因用户而异；
- FSRS-7：34 个参数，支持小数间隔，重点改善同日复习。

### 2.3 评级

FSRS 使用四档评级：

| 评级 | 数值 | 含义 |
|------|------|------|
| Again | 1 | 完全忘记 / 答错 |
| Hard | 2 | 答对，但很费劲 / 不确定 |
| Good | 3 | 答对，正常努力 |
| Easy | 4 | 答对，几乎不费力 |

FSRS 只认这四档。评级是模型输入，不是模型输出；评级偏差会直接进入 `S/D`。

### 2.4 初始状态

第一次复习时直接查表：

```text
S0(G) = w[G-1]          # G=1..4
D0(G) = w4 - exp(w5 * (G-1)) + 1
```

- `w0–w3`：Again/Hard/Good/Easy 的初始稳定性；
- `w4–w5`：初始难度；
- `D` 截断到 `[1, 10]`。

用本项目默认参数：

| 首次评级 | 初始 S | 初始 D | 首次间隔（90% 目标） |
|----------|--------|--------|----------------------|
| Again | 0.212 天 | 6.413 | 1 分钟（学习步进） |
| Good | 2.3065 天 | 2.118 | 2 天 |
| Easy | 8.2956 天 | 1.000 | 8 天 |

初始评级会同时锚定 `S` 和 `D`，所以第一次点击的影响很大。

### 2.5 难度更新

每次复习后：

```text
ΔD = -w6 * (G - 3)

D' = D + (10 - D) / 9 * ΔD

D'' = w7 * D0(Easy) + (1 - w7) * D'
```

- `w6`：一次评级对难度的影响；
- Again 使 `D` 上升，Easy 使 `D` 下降，Good 基本不变；
- `(10 - D) / 9`：线性阻尼，避免 `D` 一下冲到 10；
- `w7`：均值回归强度，把 `D` 往“最易”方向拉，避免“ease hell”；
- 最后截断到 `[1, 10]`。

### 2.6 成功回忆后的稳定性

Hard/Good/Easy：

```text
S' = S * (
    1
    + exp(w8)
    * (11 - D)
    * S ^ (-w9)
    * (exp((1 - R) * w10) - 1)
    * hard_penalty
    * easy_bonus
)
```

| 项 | 作用 |
|----|------|
| `exp(w8)` | 基础增长率 |
| `(11 - D)` | 越难，增长越少 |
| `S ^ (-w9)` | 稳定性越高，继续提升越难（边际递减） |
| `exp((1 - R) * w10) - 1` | 越接近遗忘时答对，增长越大（间隔效应） |
| `hard_penalty = w15` | Hard 的惩罚系数 |
| `easy_bonus = w16` | Easy 的奖励系数 |

直观理解：

- 难题答对一次，收益小于简单题；
- 高稳定性卡片继续提升更难；
- 在“快忘了”时答对，说明这次复习很有价值，`S` 增长更大。

### 2.7 遗忘后的稳定性

Again：

```text
S_f = min(
    w11 * D ^ (-w12) * ((S + 1) ^ w13 - 1) * exp((1 - R) * w14),
    S / exp(w17 * w18)
)
```

- 忘记一个高稳定性词，不会回到“完全没学过”，而是保留一部分稳定性；
- `D` 越大、`S` 越小，遗忘后的 `S` 越小；
- FSRS-6 增加短期间隔上限，防止 post-lapse `S` 被高估。

### 2.8 同日复习

如果两次复习间隔小于 1 天，FSRS 使用短周期公式：

```text
S' = S * exp(w17 * (G - 3 + w18)) * S ^ (-w19)
```

- Hard/Good/Easy 保证增长因子 ≥ 1；
- Again 会降低 `S`；
- `w17–w19` 是同日复习专用参数；
- 不使用长期公式里的 `(1 - R)` 间隔效应。

**这是 FSRS-6 的薄弱点。** 公开 benchmark 中：

- 不含同日：FSRS-6 log loss `0.3460`，FSRS-7 `0.3401`；
- 含同日：FSRS-6 `0.3842`，FSRS-7 `0.3206`。

FSRS-7 在同日场景优势明显，因为它支持小数间隔。Anki 手册也指出：同一天重复多次对长期记忆贡献不大，减少同日重复通常比精修同日模型更有效。

### 2.9 下次间隔

给定目标留存率 `r = desired_retention`：

```text
I = S / FACTOR * (r ^ (1 / DECAY) - 1)

DECAY = -w20
```

性质：

- `r = 0.9` 时，`I = S`；
- `r` 越高，间隔越短、复习越多；
- `r` 越低，间隔越长、复习越少；
- 结果四舍五入到整数天，最小 1 天，最大 `maximum_interval`。

默认参数下的示例：

| 场景 | FSRS 看到的评级 | 结果 `S` | 结果 `D` | 下次 |
|------|------------------|----------|----------|------|
| 新词 Good | Good | 2.31 | 2.12 | 2 天 |
| 新词 Easy | Easy | 8.30 | 1.00 | 8 天 |
| 新词 Again | Again | 0.212 | 6.41 | 1 分钟 |
| 复习 S=10 Good | Good | 32.0 | 4.99 | 32 天 |
| 复习 S=10 Again | Again | 1.39 | 8.34 | 1 分钟重学 |
| 重学后 Good | Good | 1.43 | 8.33 | 1 天 |

> 数值基于本项目 `Scheduler` 配置（1 分钟步进、关闭 fuzzing、默认参数）模拟，仅用于说明量级。

### 2.10 学习步进与状态机

```text
New / Learning
   ├─ Again → 留在 Learning，step=0，短间隔
   ├─ Good  → 下一步；最后一步 → Review
   └─ Easy  → 直接 Review

Review
   ├─ Again → Relearning，短间隔
   └─ Hard/Good/Easy → 更新 S/D，按 desired_retention 算间隔

Relearning
   ├─ Again → 回到第 1 步
   └─ Good  → 最后一步 → Review
```

Anki 的建议：

- 学习/重学步进都小于 1 天；
- 步进数量尽量少；
- 同一天重复对长期记忆贡献不大，不要用大量同日复习“刷稳定”。

本项目的当前配置是：

```python
Scheduler(
    learning_steps=(timedelta(minutes=1),),
    relearning_steps=(timedelta(minutes=1),),
    enable_fuzzing=False,
)
```

含义：

- 新卡只有 1 个学习步进，一次 Good 就毕业；
- Again 后 1 分钟重学；
- 没有 10 分钟等中间步进；
- “learning”状态主要出现在失败卡上。

这不是错误，但会让同日复习占比偏高；标准 Anki 常用 `1m 10m`，重学 `10m`。

### 2.11 模糊化（fuzzing）

`enable_fuzzing` 在间隔 >2.5 天时加入小随机扰动，避免大量卡片同一天到期。

- 关闭：确定性、好测试；
- 开启：分散复习峰值；
- 对单用户、小词书影响小；可以后加，测试固定随机种子即可。

### 2.12 参数优化

FSRS-6 有 21 个参数，默认参数是“人群平均”，不是“你个人”。

优化器使用历史复习日志：

- 输入：`card_id`、`review_time`、`rating`、`review_state`、可选 `review_duration`；
- 输出：一组更适合该用户/该 preset 的参数；
- 目标：最小化 log loss（预测 `R` 与真实结果之间的误差）。

Anki 的经验：

- 少于几百条复习时，优化可能不可靠；
- 一般每月优化一次，或数据翻倍时再优化；
- 参数是 per-preset 的，不同材料可分开；
- 优化只改善预测校准，不修复评级噪声。

> 结论：**没有足够的 `review_logs`，不要谈参数优化。**

### 2.13 参数表

| 参数 | 作用 |
|------|------|
| `w0–w3` | Again/Hard/Good/Easy 的初始稳定性 |
| `w4–w5` | 初始难度 |
| `w6` | 一次评级对难度的影响 |
| `w7` | 难度均值回归强度 |
| `w8–w10` | 成功回忆后的稳定性增长（基础、边际递减、间隔效应） |
| `w11–w14` | 遗忘后的稳定性 |
| `w15` | Hard 惩罚 |
| `w16` | Easy 奖励 |
| `w17–w19` | 同日复习的稳定性 |
| `w20` | 遗忘曲线衰减形状 |

### 2.14 FSRS 不负责什么

- 不负责评级是否真实：猜对也会被当成功；
- 不负责题目形式：识别、填空、拼写、口语在模型里都只是一次评级；
- 不负责内容难度：多义项、例句难懂，FSRS 不知道；
- 不负责用户状态：疲劳、分心、时间压力，FSRS 不知道；
- 不负责学习策略：先学什么、每天多少、积压怎么办；
- 不负责“当前记忆等级”的展示：`S` 是稳定性，不是当前 `R`；`mastered` 只是 UI。

---

## 3. 效果证据

### 3.1 Benchmark 方法

SRS Benchmark 使用约 1 万名 Anki 用户、约 7.27 亿条复习记录，按时间切分训练/测试，评估：

- **Log Loss**：预测概率与真实结果的校准误差，越低越好；
- **RMSE (bins)**：分箱后的校准误差，越低越好；
- **AUC**：区分“记住/忘记”的能力，越高越好。

> 数据来源：[SRS Benchmark](https://github.com/open-spaced-repetition/srs-benchmark)。数字为 2026-11 时 README 的结果；数据来自 Anki，不是单词 App。

### 3.2 关键结果

| 算法 | 参数量 | 不含同日 Log Loss ↓ | 含同日 Log Loss ↓ | 备注 |
|------|--------|----------------------|--------------------|------|
| FSRS-6 | 21 | 0.3460 | 0.3842 | 本项目当前使用 |
| FSRS-7 | 34 | 0.3401 | 0.3206 | 小数间隔，同日更强；recency 变体为 0.3370 / 0.3178 |
| FSRS-5 | 19 | 0.3561 | 0.4565 | 同日处理较弱 |
| FSRS-4.5 | 17 | 0.3625 | 0.4286 | 更早版本 |
| HLR | 3 | 0.4694 | 0.705 | Duolingo 半衰期回归 |
| Ebisu v2 | 0 | 0.4989 | 0.772 | 贝叶斯模型 |
| RWKV-Instant | 2,762,884 | **0.2773** | **0.2660** | 神经模型，非实用规模 |

相对差距：

- FSRS-6 vs HLR：约 **26%** 更低 log loss；
- FSRS-6 vs Ebisu：约 **31%** 更低；
- FSRS-6 vs FSRS-4.5：约 **4.6%** 更低；
- FSRS-7 vs FSRS-6：不含同日约 **1.7%**，含同日约 **16.6%**。

FSRS-6 的 RMSE/AUC（不含同日）约为 `0.0653 / 0.7034`；FSRS-7 约为 `0.0634 / 0.7167`，recency 变体约为 `0.0593 / 0.7220`。

### 3.3 如何解读

1. **FSRS-6 明显优于旧算法和通用基线。** 对“日级复习”来说，它已经足够好。
2. **FSRS-6 → FSRS-7 的日级提升很小。** 1–2% 的预测差异，普通用户几乎感知不到。
3. **同日复习是 FSRS-6 的弱项。** 如果你的系统里同日复习很多，FSRS-7 的优势才会明显。
4. **神经模型是“上限参考”，不是产品选择。** 276 万参数、额外特征、训练/推理成本，不适合本地单词 App。
5. **预测准 ≠ 学习效果一定更好。** Benchmark 衡量的是召回概率预测，不是“用户是否学得更多、花时更少”；真实效果需要产品级 A/B 或长期 retention 数据。

### 3.4 证据边界

- 数据来自 Anki 用户，不是单词 App；词条类型、评级习惯不同；
- benchmark 不是随机对照试验，不能证明“用 FSRS 就比 SM-2 学得更多”；
- 小数据/噪声评级下，默认参数可能比优化参数更稳；
- 离线指标（Log Loss/RMSE/AUC）是代理指标，不能替代真实学习结果。

---

## 4. 本项目现状

### 4.1 代码位置

- 调度核心：[backend/app/services/scheduler.py](../../backend/app/services/scheduler.py)
- 评级映射：[scheduler.py L23-L35](../../backend/app/services/scheduler.py#L23-L35)
- 全局 Scheduler：[scheduler.py L31-L35](../../backend/app/services/scheduler.py#L31-L35)
- 状态派生：[scheduler.py L81-L88](../../backend/app/services/scheduler.py#L81-L88)
- 作答更新：[scheduler.py L91-L111](../../backend/app/services/scheduler.py#L91-L111)
- 今日任务/复习池：[backend/app/routers/study.py L195-L216](../../backend/app/routers/study.py#L195-L216)
- 提交作答：[study.py L226-L260](../../backend/app/routers/study.py#L226-L260)
- 数据模型：[backend/app/models.py L108-L138](../../backend/app/models.py#L108-L138)、[models.py L141-L159](../../backend/app/models.py#L141-L159)
- 设置模型：[models.py L173-L184](../../backend/app/models.py#L173-L184)

### 4.2 当前配置

| 项 | 当前值 | 影响 |
|----|--------|------|
| FSRS 版本 | `fsrs==6.3.2`（FSRS-6，21 参数） | 紧凑、稳定、开源 |
| 参数 | 默认参数 | 人群平均，未个性化 |
| `desired_retention` | 默认 `0.9`，未暴露 | 无法按目标调整工作量/保持率 |
| 学习步进 | `1m` | 一次 Good 即毕业；learning 状态短暂 |
| 重学步进 | `1m` | 同日重学占比偏高 |
| fuzzing | 关闭 | 到期峰值不打散；确定性好 |
| Scheduler 作用域 | 全局单例 | 所有用户/词书共用参数 |
| 复习排序 | `due ASC, lapses DESC` | 积压时不是“最可能忘的优先” |
| 复习池 | `stability IS NOT NULL AND due <= now` | 包含 Learning/Relearning 卡 |
| 日志 | `StudyLog(phase, result, studied_at)` | 缺 `rating/review_state/review_duration`，优化器不可用 |
| `ReviewLog` | 生成后丢弃（`_log`） | 丢失逐次复习的完整记录 |
| `mastered` | `S >= 90` 派生 UI 状态 | 不是 FSRS 调度目标，也不随逾期衰减 |

> **2026-11-01 方案 D 预告**（总纲 §5.10）：评级来源将由“自评三键”改为“不定项选择释义”，并首次启用 `Hard`（部分正确 → Hard）。
> **FSRS 算法、参数、步进都不变**，变的只是“如何从交互得到四档评级”；届时同步更新 §4.1 的评级映射行与本表。
> 需要注意的调度风险：识别型测试（选择题）系统性高估记忆强度，因此方案 D 规定“单道选择题上限 Good、Easy 默认关闭”，
> 并用 **due 当天正确率 ≈ `desired_retention`** 来验证映射是否偏乐观（§5.7）。

### 4.3 主要差距

1. **没有 `desired_retention` 控制**：只能用默认 0.9，不能做“少复习一点/多保留一点”的产品取舍。
2. **没有合格的 review logs**：`StudyLog` 不足以直接喂 `fsrs-optimizer`；缺 `review_state`、`rating`、`review_duration`。
3. **没有参数优化**：默认参数可用，但没有个性化路径。
4. **排序策略简单**：积压时按 due 升序，不是按当前 `R` 升序。
5. **没有积压限流**：新词和复习同时增长时容易过载。
6. **步进过短**：1 分钟单步让“学习阶段”几乎不存在，同日复习多。
7. **一个全局 Scheduler**：不同词书/考试类型无法用不同参数。

这些不是“错误”，而是当前阶段的简化；但在“只优化调度层”的前提下，它们正是最值得改的地方。

---

## 5. 调度优化清单

### 5.1 优先级总表

| 优先级 | 优化项 | 成本 | 预期收益 | 是否现在做 |
|--------|--------|------|----------|------------|
| P0 | 暴露 `desired_retention` | 低 | 高 | 是 |
| P0 | 补 `review_logs` | 低 | 高 | 是 |
| P0 | 积压时按 `R` 排序 | 低 | 中 | 是 |
| P0 | 积压时限制新词 | 低 | 中高 | 是 |
| P1 | 学习/重学步进调整 | 低 | 中 | 视前端 due 支持 |
| P1 | FSRS 参数优化 | 中 | 中 | 有数据后 |
| P1 | per-book/per-preset 参数 | 中 | 中 | 词书差异大时 |
| P1 | leech/suspend | 低 | 中 | 是 |
| P2 | fuzzing | 低 | 低 | 可选 |
| P2 | FSRS-7 评估 | 中高 | 中（同日场景） | 暂不 |
| P2 | 自研/神经模型 | 高 | 低（本项目） | 不做 |

### 5.2 P0：低风险、可独立验证

#### 5.2.1 暴露 `desired_retention`

- 在 `AppSetting` 增加字段，例如 `desired_retention`，默认 `0.90`；
- 提供三档：`0.85 / 0.90 / 0.95`；
- 构造 `Scheduler(desired_retention=...)` 时按用户设置传入；
- 文档/设置页说明：
  - 提高 → 间隔更短、复习更多、保持率更高；
  - 降低 → 间隔更长、复习更少、遗忘更多。
- 这是调度层最高杠杆的旋钮，Anki 手册也称其为本设置中最重要的 FSRS 选项。

#### 5.2.2 补 `review_logs`
现有 `StudyLog` 只有 `phase/result/studied_at`，不足以做优化。建议新增表或扩展字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 主键 |
| `user_id` | BIGINT | 账号 |
| `word_id` | BIGINT | 作为 `card_id` 使用 |
| `review_time` | DATETIME(3) | UTC；毫秒精度更佳 |
| `rating` | TINYINT | 1=Again, 2=Hard, 3=Good, 4=Easy |
| `review_state` | TINYINT | 0=New, 1=Learning, 2=Review, 3=Relearning |
| `review_duration` | INT NULL | 毫秒；可选，仅作分析 |
| `phase` | VARCHAR | 现有 `new_first/new_quiz/review/relearn`，便于兼容 |
| `stability_before/after` | DECIMAL | 可选，审计用 |
| `difficulty_before/after` | DECIMAL | 可选，审计用 |

要点：

- `review_state` 必须在**复习前**记录：`stability IS NULL` → 0；否则用当前 `state`；
- `rating` 由现有 `result` 映射：`unknown/wrong → 1`，`know/correct → 3`，`master → 4`；当前没有 Hard；
- 若暂时不动交互，可以先记录现有映射；Hard 缺失仍是已知限制；
- 新增表走 `../operations/MIGRATIONS.md` 的版本化规则，不要改已发布迁移。

#### 5.2.3 积压时按 `R` 排序

计算：

```text
R = (1 + FACTOR * elapsed_days / S) ^ (-w20)
```

- 正常情况：按 `due ASC`；
- 积压时：按 `R ASC`（最可能忘的优先）；
- 只对 Review 卡计算；Learning/Relearning 仍按 due；
- 这是 Anki FSRS 的 “Ascending retrievability” 思路。

收益：在 backlog 场景下，优先处理“最危险”的词，减少遗忘。

#### 5.2.4 积压时限制新词

建议策略：

```text
due_backlog = count(due <= now)
if due_backlog > review_per_day * 1.5:
    new_target = 0
elif due_backlog > review_per_day:
    new_target = floor(new_per_day / 2)
```

- 防止“新词 + 积压”双重过载；
- 与 Anki “backlog 时停新词”的建议一致；
- 需要在 `today` 接口里同步调整 `new_target`，避免进度条失真。

### 5.3 P1：需要数据或前端配合

#### 5.3.1 学习/重学步进

- 当前 `1m` 单步 → 一次 Good 毕业；
- 可考虑 `1m 10m`，重学 `10m`；
- 标准 Anki 建议步进 <1 天，数量尽量少；
- 如果前端队列不尊重 `due`，改步进只会让 due 变晚而实际仍立刻重试；此时应先把“何时重试”的调度权交回后端。

这是调度参数，不是新交互功能；但依赖前端按 `due` 取卡。

#### 5.3.2 FSRS 参数优化

- 使用 [`fsrs-optimizer`](https://github.com/open-spaced-repetition/fsrs-optimizer) 或 [`fsrs-rs-python`](https://github.com/open-spaced-repetition/fsrs-rs-python)；
- 输入按优化器 schema：`card_id/review_time/rating/review_state/review_duration`；
- 先离线回测：log loss、校准曲线、按间隔分桶的 retention；
- 数据少时保留默认参数；不要在小样本上追最优；
- 优化结果按用户/preset 存储，不覆盖默认参数；
- 优化频率：每月或数据翻倍时；不要每次启动都跑。

#### 5.3.3 per-book/per-preset 参数

- `Scheduler` 目前是全局单例；
- 不同词书（GRE/四六级/日常）难度分布不同，可以按 `book_id` 或“词书类型”分 preset；
- 数据不足时回退全局默认；
- 这与 Anki 的 preset 思路一致：参数按材料相似性分组，而不是每个 deck 单独一套。

#### 5.3.4 leech / suspend

- 连续多次 Again 的词，自动标记 `leech`；
- 策略可选：暂停复习、降低优先级、要求重学、提示用户；
- 目的：避免一个词反复占用复习预算；
- 这是调度策略，不需要新题型。

### 5.4 P2：可选或暂缓

| 项 | 建议 |
|----|------|
| fuzzing | 可开启，间隔 >2.5 天时加小幅扰动；测试固定 seed |
| `maximum_interval` | 可设为 5–10 年；默认 100 年对单词 App 偏长，但影响小 |
| FSRS-7 | 先观察同日复习占比；若很高且能支持小数间隔，再做迁移评估 |
| 自研模型/神经网络 | 不做；数据量和维护成本不匹配 |
| 固定 Ebbinghaus 1/3/7 | 不做；比 FSRS 更僵化 |

### 5.5 不做清单

1. **不要为了“更先进”迁 FSRS-7。** 日级收益约 1–2%；同日场景才明显。
2. **不要换回 SM-2 / HLR / Ebisu。** benchmark 上更差；HLR 需要大规模数据，Ebisu 生态小。
3. **不要自研神经网络。** 276 万参数的模型不适合本地单词 App。
4. **不要在几百条复习上优化 21 个参数。** 会过拟合；默认参数更稳。
5. **不要把 `mastered` 当调度目标。** `S>=90` 是 UI 标签，不是 FSRS 的 due/R。
6. **不要用 `review_duration` 直接改 `S`。** FSRS 不用它做调度；它只适合日志/分析。
7. **不要同时改算法和策略。** 先做可控的 P0，再做 P1；否则无法判断收益来自哪里。
8. **不要把选择题的对错直接当成回忆型测试的评级。** 识别远易于回忆，4 选 1 还有 25% 猜测基线；这类评级会系统性高估 `S`。要么压低映射（上限 Good、部分对→Hard），要么在题目层面提高难度，不要靠 FSRS 自己修正。

### 5.6 分阶段落地

| 阶段 | 内容 | 验收 |
|------|------|------|
| 第 1 阶段（1–2 天） | `desired_retention`、`review_logs`、按 R 排序、积压限流 | 能改目标留存；日志字段完整；backlog 时排序/限流生效 |
| 第 2 阶段（有数据后） | 参数优化、per-book 参数、leech/suspend | 离线 log loss/校准不劣于默认；复习量/逾期率可解释 |
| 第 3 阶段（可选） | fuzzing、FSRS-7 评估、maximum_interval | 有对比数据再决定；不影响现有行为 |

### 5.7 验收指标

调度层优化不应只看“感觉更准”，建议观察：

- **Log Loss / 校准**：预测 R 与实际正确率是否接近；
- **到期保持率**：due 当天的正确率是否接近 `desired_retention`；
- **复习量**：每天 review 数、逾期数、积压天数；
- **新词完成率**：积压限流后是否更稳定；
- **leech 比例**：反复失败的词是否下降；
- **不要同时追求“更少复习”和“更高保持率”**：这是 tradeoff，必须明确目标。

> 这些是调度工程指标，不是产品“评估功能”；不需要新增用户界面。

---

## 6. 相关开源站点

### 6.1 规范与算法

| 站点 | 内容 |
|------|------|
| [open-spaced-repetition](https://github.com/open-spaced-repetition) | FSRS 官方组织，所有仓库入口 |
| [FSRS Algorithm Wiki](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm) | 最值得先读：FSRS-6 公式、参数、版本演进 |
| [free-spaced-repetition-scheduler](https://github.com/open-spaced-repetition/free-spaced-repetition-scheduler) | FSRS 算法仓库（MIT） |
| [FSRS4Anki](https://github.com/open-spaced-repetition/fsrs4anki) | Anki 的 FSRS 调度器 + 优化器 |
| [FSRS4Anki Wiki](https://github.com/open-spaced-repetition/fsrs4anki/wiki) | 教程、ABC of FSRS、优化机制、指标 |
| [FSRS Optimizer](https://github.com/open-spaced-repetition/fsrs-optimizer) | 用 review logs 拟合 21 参数 |
| [FSRS4Anki Helper](https://github.com/open-spaced-repetition/fsrs4anki-helper) | Postpone/Advance/Load Balance/Easy Days |

### 6.2 实现库

| 站点 | 语言 / 说明 |
|------|-------------|
| [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) | Python，MIT；本项目当前使用这条线 |
| [ts-fsrs](https://github.com/open-spaced-repetition/ts-fsrs) | TypeScript，MIT |
| [fsrs-rs](https://github.com/open-spaced-repetition/fsrs-rs) | Rust，BSD-3-Clause；调度器 + 优化器 |
| [fsrs-rs-python](https://github.com/open-spaced-repetition/fsrs-rs-python) | Python 绑定；适合生产优化 |
| [FSRS Visualizer](https://open-spaced-repetition.github.io/anki_fsrs_visualizer/) | 参数/复习历史可视化 |

### 6.3 Anki 与文档

| 站点 | 内容 |
|------|------|
| [Anki](https://github.com/ankitects/anki) | AGPL-3.0；完整实现、FSRS 集成、统计 |
| [Anki 手册：FSRS](https://docs.ankiweb.net/deck-options.html#fsrs) | FSRS 开关、参数优化、desired retention、learning steps |
| [Anki 手册：FSRS FAQ](https://docs.ankiweb.net/faqs/frequently-asked-questions-about-fsrs) | 首间隔、Again/Good 两键、优化频率 |
| [Anki 手册：Studying](https://docs.ankiweb.net/studying.html) | 四键评级、Hard/Good/Easy 语义、card states |

### 6.4 基准、数据与对比

| 站点 | 内容 |
|------|------|
| [SRS Benchmark](https://github.com/open-spaced-repetition/srs-benchmark) | 当前最完整的公开 SRS benchmark |
| [SRS Benchmark 结果](https://github.com/open-spaced-repetition/srs-benchmark#result) | Log Loss / RMSE / AUC 表；本文数字来源 |
| [anki-revlogs-10k](https://huggingface.co/datasets/open-spaced-repetition/anki-revlogs-10k) | 1 万 Anki 用户、约 7.27 亿条复习记录 |
| [FSRS vs SM-17](https://github.com/open-spaced-repetition/fsrs-vs-sm17) | FSRS 与 SuperMemo SM-17 对比 |
| [FSRS vs SM-15](https://github.com/open-spaced-repetition/fsrs-vs-sm15) | 更早的 SuperMemo 对比 |
| [SuperMemo SM-18](https://supermemo.guru/wiki/Algorithm_SM-18) | SM-18 公开说明（算法非开源代码） |
| [Ebisu](https://github.com/fasiha/ebisu) | 贝叶斯 SRS |
| [HLR](https://github.com/duolingo/halflife-regression) | Duolingo 半衰期回归，含数据和代码 |

### 6.5 建议阅读顺序

1. [FSRS Algorithm Wiki](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm)
2. [SRS Benchmark 结果](https://github.com/open-spaced-repetition/srs-benchmark#result)
3. [Anki 手册 FSRS](https://docs.ankiweb.net/deck-options.html#fsrs)
4. [FSRS Optimizer](https://github.com/open-spaced-repetition/fsrs-optimizer)
5. [FSRS4Anki Wiki](https://github.com/open-spaced-repetition/fsrs4anki/wiki)

---

## 7. 参考与维护

### 7.1 项目内参考

- [README.md](../../README.md)
- [项目介绍与方案设计.md](项目介绍与方案设计.md)
- [MIGRATIONS.md](../operations/MIGRATIONS.md)
- [PRIVACY.md](../legal/PRIVACY.md)
- [RELEASE_CHECKLIST.md](../operations/RELEASE_CHECKLIST.md)
- [scheduler.py](../../backend/app/services/scheduler.py)
- [study.py](../../backend/app/routers/study.py)
- [models.py](../../backend/app/models.py)
- [requirements.txt](../../backend/requirements.txt)

### 7.2 外部参考

- [FSRS Algorithm Wiki](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm)
- [SRS Benchmark](https://github.com/open-spaced-repetition/srs-benchmark)
- [Anki 手册 FSRS](https://docs.ankiweb.net/deck-options.html#fsrs)
- [Anki 手册 FSRS FAQ](https://docs.ankiweb.net/faqs/frequently-asked-questions-about-fsrs)
- [FSRS Optimizer](https://github.com/open-spaced-repetition/fsrs-optimizer)
- [FSRS vs SM-17](https://github.com/open-spaced-repetition/fsrs-vs-sm17)
- [SuperMemo SM-18](https://supermemo.guru/wiki/Algorithm_SM-18)
- [Ebisu](https://github.com/fasiha/ebisu)
- [HLR](https://github.com/duolingo/halflife-regression)

### 7.3 维护规则

- 调度配置（`desired_retention`、步进、fuzzing、参数）变化时，更新 §4.2 和 §5；
- 升级 `fsrs` 库时，先核对版本（FSRS-5/6/7）、参数数量和 `review_logs` schema；
- 引用 benchmark 数字时标注日期；算法版本会更新，数字会变；
- 本文是总结文档，不替代 [项目介绍与方案设计.md](项目介绍与方案设计.md)；冲突时以总纲和代码为准，并回头修正本文。

---

## 附录：术语表

| 术语 | 说明 |
|------|------|
| FSRS | Free Spaced Repetition Scheduler；基于 DSR 的间隔重复算法 |
| DSR | Difficulty、Stability、Retrievability 三变量模型 |
| `S` | 稳定性；`R` 降到 90% 所需天数 |
| `D` | 难度；1–10 |
| `R` | 当前可提取性/回忆概率 |
| `desired_retention` | 目标留存率；默认 0.9；决定间隔长短 |
| Log Loss | 预测概率与真实结果的校准误差；越低越好 |
| RMSE (bins) | 分箱校准误差；越低越好 |
| AUC | 区分记住/忘记的能力；越高越好 |
| Leech | 反复失败的卡片 |
| Preset | 一组共享调度参数；Anki 术语 |
| Review log | 一次复习的记录：时间、评级、状态、耗时 |
| Hard | 答对但费劲/不确定；FSRS 的 2 分 |
| Again | 答错/忘记；FSRS 的 1 分 |

---

> **一句话总结**：FSRS-6 是当前单词 App 调度层的高性价比选择；不要再卷公式，优先把 `desired_retention`、`review_logs`、按 `R` 排序、积压限流和步进做好。FSRS-7 只在同日复习占比高时才值得评估。
