# CLAUDE.md — Axon CLI Release Repo

## 语言

所有交流使用中文。

## Overview

CLI 发布专用 repo。PyPI 包名 `axonwork`，当前版本 `0.2.7`。源码开发在 `axon-dev/cli/`，此 repo 仅用于版本管理和 PyPI 发布。

## ⚠️ 开发请去 axon-dev/cli/

此 repo 的源码从 `axon-dev/cli/` 同步而来。所有功能开发、bug 修复、测试均在 axon-dev 进行。

## 发布流程

1. 在 `axon-dev/cli/` 完成开发和测试
2. 同步代码到本 repo 的 `axon/` 目录
3. 更新 `pyproject.toml` 的 `version` 字段
4. `git tag v{version} && git push --tags`
5. **在 GitHub 创建 Release**（必须，body 按下方格式写）
   - `publish-cli.yml` 自动发布到 PyPI
   - `trigger-tweet.yml` 自动触发 `axon-marketing` 发推（用 release body 作为推文 body）

### Release body 格式（严格协议）

axon-marketing 会把 release body 直接作为推文 body。每行写一条 `<emoji> <description>`。允许 markdown heading（如 `## What's New`）和空行，marketing 会忽略它们。

示例：

```
## What's New

✨ Add score direction indicators
✨ Rename LiteLLM backend to API
🔧 Fix network progress calculation
🔒 Harden sandbox against malicious miner code
```

Emoji 映射约定（与 axon-marketing 对齐）：

| Emoji | 用途 |
|-------|------|
| ✨ | feat — 新功能 |
| 🔧 | fix — 修复 |
| 📝 | docs — 文档 |
| 🚀 | ci — CI/CD |
| 🔒 | security — 安全 |
| ♻️ | refactor — 重构 |
| 🏎️ | perf — 性能 |
| 🧪 | test — 测试 |
| ⚡ | 其他 |

字符预算：推文整体 ≤ 280 字符（含 header `𝛙 AXON vX.Y.Z` 和 footer tagline + release URL，约 80 字符），release body 部分大约 200 字符预算。超出部分 marketing 会从下往上截断。

## CI/CD 工作流

### publish-cli.yml（GitHub Release 触发）
1. 校验 git tag 与 pyproject.toml version 一致
2. `python -m build` 构建 wheel + sdist
3. PyPI 发布（trusted publisher，无需 token）
4. 上传 release assets

### trigger-tweet.yml（GitHub Release published 触发）
- 读 `github.event.release.body`，通过 `gh workflow run x-release-post.yml --field release_notes="$RELEASE_NOTES"` 传给 axon-marketing
- 只打 tag 不创建 release → 不发推（v0.2.7 就踩过这个坑）

## 版本管理

`pyproject.toml` 中的 version 必须与 git tag 一致（CI 校验）。

## Secrets

- **PyPI**：trusted publisher（无需 token）
- **MARKETING_PAT**：GitHub PAT（repo + workflow scope），用于跨 repo 触发 axon-marketing

## 命令

```bash
# 测试
python -m pytest tests/ -v
# 本地安装
pip install -e .
# 构建
python -m build
```

## 依赖

typer, httpx, litellm, rich, eth-account, simple-term-menu（详见 pyproject.toml）
