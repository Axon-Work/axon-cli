# axon-dev

Monorepo for Axon development.

## Layout

- `cli/` - Axon CLI and TUI client
- `server/` - Axon API server
- `sandbox/` - Axon code execution sandbox
- `docs/` - Shared project docs

`cli/`, `server/`, and `sandbox/` are Git submodules.

Clone with submodules:

```bash
git clone --recurse-submodules git@github.com:Axon-AI-Net/axon-dev.git
```

If you already cloned the repo:

```bash
git submodule update --init --recursive
```

Each subproject keeps its own `README.md` and local documentation.
