# Python Best Practices

## Code Style

Follow **PEP 8** for formatting:
- 4-space indentation (no tabs).
- Lines no longer than 79 characters for code, 72 for docstrings.
- Two blank lines between top-level definitions; one blank line between methods.

Use a linter and formatter in CI:
- **ruff** — fast, drop-in replacement for flake8 + isort.
- **black** — opinionated, zero-config formatter.
- **mypy** — static type checking.

---

## Type Annotations

Annotate all public function signatures:

```python
from typing import Optional, List

def search(query: str, top_k: int = 5) -> List[dict]:
    ...
```

Use `TypedDict` for structured dictionaries passed between components:

```python
from typing_extensions import TypedDict

class SearchResult(TypedDict):
    content: str
    score: float
    source: str
```

---

## Error Handling

- Catch specific exceptions, not bare `except:`.
- Log errors with context before re-raising or returning an error state.
- Use custom exception classes for domain errors to make try/except blocks expressive.

```python
class DocumentLoadError(RuntimeError):
    """Raised when a document cannot be loaded or parsed."""
```

---

## Testing

Use **pytest** with a clear directory structure:

```
tests/
├── conftest.py          # shared fixtures
├── test_agents.py
└── test_rag.py
```

Key practices:
- One test class per logical unit; one test function per scenario.
- Use `unittest.mock.patch` to isolate external dependencies (APIs, DBs).
- Name tests descriptively: `test_returns_empty_list_when_no_documents_found`.
- Aim for both positive (happy path) and negative (edge case, adversarial) tests.

---

## Project Structure

```
project/
├── src/          # application source code
│   ├── __init__.py
│   └── module.py
├── tests/        # test suite
├── docs/         # documentation
├── data/         # datasets and sample files
├── .env.example  # environment variable template (never commit .env)
├── requirements.txt
└── README.md
```

---

## Environment and Dependencies

- Store all configuration in environment variables; never hard-code secrets.
- Use `python-dotenv` to load `.env` files in development.
- Pin major versions in `requirements.txt`; use a lock file (`pip-compile`) for
  reproducible installs.
- Prefer virtual environments: `python -m venv .venv && source .venv/bin/activate`.

---

## Logging

Use the standard `logging` module rather than `print`:

```python
import logging

logger = logging.getLogger(__name__)
logger.info("Processing %d documents", len(docs))
```

Configure at application entry point:

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
```
