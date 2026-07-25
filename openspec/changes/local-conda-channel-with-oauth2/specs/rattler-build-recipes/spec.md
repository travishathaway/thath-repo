# Spec: rattler-build Recipes

## Capability

Two minimal `noarch: python` conda recipes used to populate the local channel for testing. Built via `rattler-build`; output goes to `channel/` (gitignored).

## Requirements

### Package: `greet`

**Location**: `recipes/greet/recipe.yaml`

**Package metadata**:
- Name: `greet`
- Version: `0.1.0`
- License: MIT

**Build**:
- `noarch: python`
- No compiled components
- Installable via `python -m pip install .` inside the recipe

**Source**:
- Inline source within the recipe directory (a minimal `setup.py` or `pyproject.toml` + source file)

**Python module** (`greet/__init__.py` or `greet.py`):
```python
def hello(name: str) -> str:
    return f"Hello, {name}!"
```

**Requirements**:
- host: `python`, `pip`
- run: `python`

---

### Package: `timeutils`

**Location**: `recipes/timeutils/recipe.yaml`

**Package metadata**:
- Name: `timeutils`
- Version: `0.1.0`
- License: MIT

**Build**:
- `noarch: python`
- No compiled components

**Python module** (`timeutils/__init__.py` or `timeutils.py`):
```python
from datetime import datetime, timezone

def now() -> str:
    return datetime.now(timezone.utc).isoformat()
```

**Requirements**:
- host: `python`, `pip`
- run: `python`

---

### rattler-build Output

Both recipes are built with:
```
rattler-build build recipes/<name>/recipe.yaml --output-dir channel
```

Output layout under `channel/`:
```
channel/
├── noarch/
│   ├── greet-0.1.0-pyhd8ed1ab_0.conda
│   ├── timeutils-0.1.0-pyhd8ed1ab_0.conda
│   └── repodata.json
└── channeldata.json
```

## Constraints

- Recipes must build successfully on both `linux-64` and `osx-arm64` (noarch ensures this)
- No internet access required at build time (pure Python, no compiled deps)
- The `channel/` directory is gitignored; recipes are checked in
- Each recipe directory must be self-contained (source files alongside `recipe.yaml`)
