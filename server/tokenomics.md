# OS Tokenomics

## Overview

OS coin 采用 **Proof of Useful Work** 机制。系统为有价值的智力贡献铸造新币，发布任务需要烧币。

## 核心参数

```
总量上限:          1,000,000,000 OS
初始 base_reward:  1000 OS
Halving 触发:      每铸造 50,000,000 OS 减半
match_multiplier:  初始 1.0，随 halving 同步衰减
最低 base_reward:  1 OS（永不归零，尾部发行）
```

## 角色

- **Platform（官方）**：早期唯一可发任务的角色，把控任务质量
- **Miner**：调用 LLM API 改善 eval 分数，赚取 OS 币
- **Holder**：持有 OS 币，后期可参与治理

## 发任务

早期仅官方可发任务。发布者需烧 OS 币，系统按 match_multiplier 铸造等额币，组成奖池：

```
task_burn = 发布者决定的烧币数量
pool = task_burn + task_burn × match_multiplier
```

每个任务必须声明：
- `eval_type` + `eval_config`：评估方式
- `direction`：maximize 或 minimize
- `completion_threshold`：目标分数

## Miner 奖励公式

每次 eval improvement，Miner 获得：

```
reward = pool_payout + mint_payout

pool_payout  = pool_balance × improvement_ratio
mint_payout  = base_reward × improvement_ratio × match_multiplier
```

### improvement_ratio

```
delta = |new_score - old_score|
range = |threshold - baseline|       # baseline = 第一次提交的 score
progress = (old_score - baseline) / (threshold - baseline)
difficulty_bonus = 1 / (1 - progress)

improvement_ratio = (delta / range) × difficulty_bonus
```

- `delta / range`：改善幅度占总目标的百分比
- `difficulty_bonus`：越接近 threshold 越值钱
  - progress=0% → 1x
  - progress=50% → 2x
  - progress=90% → 10x
  - progress=99% → 100x

### improvement_ratio 上限

`improvement_ratio` 封顶为 `1.0`，防止单次提交抽空奖池或铸造过多。

### Completion bonus

当 score 达到或超过 threshold 时，触发 completion：
- 奖池剩余全部发给 completion 的 Miner
- 额外系统铸造 `base_reward × match_multiplier`（一次性）
- 任务状态变为 completed

## 数值示例

```
任务参数：
  task_burn = 100 OS
  match_multiplier = 1.0（当前 epoch）
  pool = 100 + 100 = 200 OS
  base_reward = 1000 OS（当前 epoch）
  threshold = 95
  baseline（首次提交）= 60

Miner A: 60 → 72
  delta = 12, range = 35, progress = 0%
  difficulty_bonus = 1 / (1 - 0) = 1.0
  improvement_ratio = (12/35) × 1.0 = 0.343
  pool_payout = 200 × 0.343 = 68.6 OS
  mint_payout = 1000 × 0.343 × 1.0 = 343 OS
  total = 411.6 OS

Miner B: 72 → 75
  delta = 3, range = 35, progress = 34.3%
  difficulty_bonus = 1 / (1 - 0.343) = 1.52
  improvement_ratio = (3/35) × 1.52 = 0.130
  pool_payout = 131.4 × 0.130 = 17.1 OS
  mint_payout = 1000 × 0.130 × 1.0 = 130 OS
  total = 147.1 OS

Miner C: 90 → 93
  delta = 3, range = 35, progress = 85.7%
  difficulty_bonus = 1 / (1 - 0.857) = 7.0
  improvement_ratio = (3/35) × 7.0 = 0.6
  pool_payout = pool_remaining × 0.6
  mint_payout = 1000 × 0.6 × 1.0 = 600 OS
  同样 3 分，末期价值远高于早期

Miner D: 93 → 95 (completion!)
  正常 improvement 奖励 + 奖池全部剩余 + completion bonus
```

## Halving 时间表

| 阶段 | 累计铸造 | base_reward | match_multiplier |
|------|---------|-------------|------------------|
| 1 | 0 - 50M | 1000 | 1.0 |
| 2 | 50M - 100M | 500 | 0.5 |
| 3 | 100M - 150M | 250 | 0.25 |
| 4 | 150M - 175M | 125 | 0.125 |
| ... | ... | ... | ... |
| 终态 | >950M | 1 | ~0 |

## 经济循环

```
早期:
  官方发任务（烧币）→ 系统 match 铸造 → Miner 赚币
  Miner 收入 = 大量系统铸造 + 少量奖池
  
中期（开放用户发任务后）:
  用户发任务（烧币）→ 系统 match 减少 → Miner 赚币
  Miner 收入 = 减少的系统铸造 + 增长的奖池
  
后期:
  系统铸造趋近于 0，match_multiplier 趋近于 0
  pool = task_burn（纯发布者付费）
  Miner 收入 ≈ 奖池分配
  自然过渡为双边市场
```

## 防刷机制

1. **早期官方垄断发任务** — 无法自导自演
2. **eval 服务端执行** — 无法伪造分数
3. **improvement 最小阈值** — score 变化 < 0.1% 不算有效 improvement
4. **同答案去重** — 相同 answer 不可重复提交
5. **difficulty_bonus 曲线** — 简单任务早期改善的系统铸造很低，刷不出多少币
