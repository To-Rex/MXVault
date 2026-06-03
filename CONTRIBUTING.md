# Contributing to MXVault

Thank you for considering contributing to MXVault! This document outlines the guidelines for contributing.

## Code of Conduct

By participating, you agree to maintain a respectful and inclusive environment.

## How to Contribute

### Reporting Bugs

- Check if the bug has already been reported in Issues
- Provide a clear description including steps to reproduce
- Include environment details (OS, Python version, etc.)

### Feature Requests

- Open an issue describing the feature and use case
- Discuss implementation approach before submitting PRs

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Follow the existing code style and architecture patterns
4. Add type hints to all new code
5. Write tests for new functionality
6. Update documentation as needed
7. Run linting and type checks
8. Submit a PR with a clear description

## Development Setup

```bash
git clone https://github.com/yourusername/mxvault.git
cd mxvault
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # for development dependencies
alembic upgrade head
python run.py
```

## Architecture

- `app/main.py` — FastAPI application entry point
- `app/models/` — SQLAlchemy ORM models
- `app/schemas/` — Pydantic validation schemas
- `app/services/` — Business logic layer
- `app/api/` — Route handlers
- `app/templates/` — Jinja2 templates
- `app/static/` — Static assets
- `app/utils/` — Utility functions

## Coding Standards

- Python 3.12+ type hints on all functions
- Clean, modular, maintainable code
- Follow repository pattern for data access
- Use service layer for business logic
- Write descriptive commit messages
- Keep functions small and focused

## Testing

```bash
pytest tests/
```

## Questions?

Open a discussion or issue on GitHub.
