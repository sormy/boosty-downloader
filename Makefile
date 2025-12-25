.PHONY: venv install dev test clean format lint version-patch version-minor version-major build publish help

VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

help:
	@echo "Available targets:"
	@echo "  venv          - Create virtual environment"
	@echo "  install       - Install package in venv"
	@echo "  dev           - Install in development mode with dev dependencies"
	@echo "  test          - Run tests"
	@echo "  clean         - Remove build artifacts"
	@echo "  format        - Format code with black"
	@echo "  lint          - Run linters"
	@echo "  build         - Build distribution packages"
	@echo "  publish       - Publish package to PyPI"
	@echo "  version-patch - Increment patch version (x.y.Z)"
	@echo "  version-minor - Increment minor version (x.Y.0)"
	@echo "  version-major - Increment major version (X.0.0)"

venv:
	python3 -m venv $(VENV)
	@echo "Virtual environment created. Activate with: source $(VENV)/bin/activate"

install: venv
	$(PIP) install .

dev: venv
	$(PIP) install -e ".[dev]"

test: venv
	$(PYTHON) -m pytest

clean:
	rm -rf build dist *.egg-info $(VENV)
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

format: venv
	$(VENV)/bin/black src/

lint: venv
	$(VENV)/bin/flake8 src/
	$(VENV)/bin/pyright src/

version-patch:
	@current=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	IFS='.' read -r major minor patch <<< "$$current"; \
	new_version="$$major.$$minor.$$((patch + 1))"; \
	sed -i.bak "s/^version = .*/version = \"$$new_version\"/" pyproject.toml && rm pyproject.toml.bak; \
	sed -i.bak "s/^__version__ = .*/__version__ = \"$$new_version\"/" src/boosty_dl/__init__.py && rm src/boosty_dl/__init__.py.bak; \
	echo "Version bumped from $$current to $$new_version"

version-minor:
	@current=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	IFS='.' read -r major minor patch <<< "$$current"; \
	new_version="$$major.$$((minor + 1)).0"; \
	sed -i.bak "s/^version = .*/version = \"$$new_version\"/" pyproject.toml && rm pyproject.toml.bak; \
	sed -i.bak "s/^__version__ = .*/__version__ = \"$$new_version\"/" src/boosty_dl/__init__.py && rm src/boosty_dl/__init__.py.bak; \
	echo "Version bumped from $$current to $$new_version"

version-major:
	@current=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	IFS='.' read -r major minor patch <<< "$$current"; \
	new_version="$$((major + 1)).0.0"; \
	sed -i.bak "s/^version = .*/version = \"$$new_version\"/" pyproject.toml && rm pyproject.toml.bak; \
	sed -i.bak "s/^__version__ = .*/__version__ = \"$$new_version\"/" src/boosty_dl/__init__.py && rm src/boosty_dl/__init__.py.bak; \
	echo "Version bumped from $$current to $$new_version"

build: venv
	rm -rf dist
	$(PYTHON) -m build

publish: build
	$(PYTHON) -m twine upload dist/*
