# Design: OS Token On-Chain (Base L2)

## 经济模型

```
官方卖 OS:  Year 1: 1 USDC = 10 OS
            Year 2: 1 USDC = 5 OS  (annual halving)
            Year 3: 1 USDC = 2.5 OS
            ...

流通:
  Publisher 用 USDC 买 OS → 烧 OS 发任务 → 系统 match 铸造 → Miner 赚 OS
  Miner 在 Uniswap (Base) 卖 OS 换 USDC

注册不送币。
```

## 架构变更

```
现在:
  CLI → 邮箱/密码 → JWT → 后端数据库 → balance 字段

上链后:
  CLI → 本地钱包 → 签名 → 后端验证签名 → 链上合约 → ERC-20 余额
```

## 智能合约 (Solidity on Base)

### 1. OSToken.sol — ERC-20 代币
```
- 名称: OpenScienceNet (OS)
- 官方 mint 函数 (onlyOwner): 卖给 Publisher 时 mint
- 年度 halving: saleRate 每年减半
- burn 函数: 发任务时烧币
```

### 2. TokenSale.sol — 官方售卖
```
- buy(uint256 usdcAmount): Publisher 用 USDC 买 OS
- 汇率: year1=10, year2=5, year3=2.5...
- 收到的 USDC 进入 treasury
- 可选: 每年手动触发 halving 或按 block 自动计算
```

### 3. TaskRegistry.sol — 任务管理
```
- createTask(title, evalType, threshold, osBurn): 烧 OS 创建任务
- 系统 match: 合约 mint 等额 OS 进入 pool
- pool 锁定在合约里
```

### 4. RewardDistributor.sol — 奖励发放
```
- submitResult(taskId, miner, score, proof): 后端签名的 eval 结果
- 合约验证签名 → 发放 pool + mint 奖励给 miner
- 需要 oracle 签名者地址 (后端的私钥)
```

## 认证变更

```
现在:                          上链后:
邮箱 + 密码 → JWT              钱包地址 → 签名 → 验证

CLI onboard:
  1. 生成 ETH 钱包 (私钥存 ~/.oscli/wallet.json)
  2. 显示地址
  3. 不需要注册 — 地址就是身份

API auth:
  1. CLI 生成 nonce 请求: GET /api/auth/nonce?address=0x...
  2. 后端返回随机 nonce
  3. CLI 用私钥签名 nonce
  4. POST /api/auth/verify {address, signature, nonce}
  5. 后端验证签名 → 返回 JWT (后续请求用)
```

## 文件变更清单

### 新建: opensciencenet-contracts/
```
contracts/
  ├── OSToken.sol
  ├── TokenSale.sol
  ├── TaskRegistry.sol
  └── RewardDistributor.sol
scripts/
  └── deploy.ts
test/
  └── ...
hardhat.config.ts
package.json
```

### 修改: opensciencenet-backend/
```
app/auth.py         → 钱包签名验证 (EIP-712) 替代密码
app/models.py       → User 表: address 替代 email/password
app/rewards.py      → 调用合约发奖励替代数据库 +balance
app/routers/tasks.py → 调用合约创建任务替代数据库操作
新增: app/chain.py   → Web3 合约交互封装
新增: app/routers/wallet.py → nonce/verify/balance 端点
```

### 修改: opensciencenet-cli/
```
src/config.ts       → 加 wallet (address, encrypted private key)
src/commands/onboard.tsx → 生成钱包替代注册
src/commands/auth.tsx    → 签名验证替代密码登录
src/api.ts          → 请求带签名
新增: src/wallet.ts  → 钱包生成/签名/加密
```

## 分阶段实施

### Phase 1: 合约 + 钱包 (1-2 周)
- 写 4 个合约 + 测试
- 部署到 Base Sepolia 测试网
- CLI 生成钱包
- 后端钱包签名验证

### Phase 2: 链上任务 + 奖励 (1-2 周)
- 后端对接合约 (创建任务、发奖励)
- USDC 买 OS 流程
- eval 结果签名上链

### Phase 3: DEX 流动性 (1 周)
- Uniswap V3 OS/USDC 池
- 初始流动性 (官方提供)
- CLI 显示 OS 价格

### Phase 4: 主网 (迁移)
- Base Sepolia → Base Mainnet
- 审计合约
- 正式上线

## 技术栈新增

- Hardhat + Solidity (合约开发)
- ethers.js v6 (CLI 钱包 + 签名)
- web3.py / web3.js (后端合约交互)
- Base Sepolia RPC (测试网)
- Uniswap V3 SDK (DEX 集成)

## 关键决策

1. **合约是否可升级?** 建议用 UUPS proxy — 早期需要修 bug
2. **Oracle 签名者** — 后端用一个 EOA 签 eval 结果, 合约信任这个地址
3. **Gas 谁付?** 矿工领奖需要 Base ETH 付 gas (~$0.001)
4. **钱包加密** — 私钥用用户密码加密存在 ~/.oscli/wallet.json
