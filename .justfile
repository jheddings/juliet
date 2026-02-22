# justfile for juliet

basedir := justfile_directory()
srcdir := basedir / "juliet"

appname := "juliet"
appver := `uv version --short`

# run venv setup and preflight checks
default: setup preflight

# setup the local development environment
setup: venv
  uv run pre-commit install --install-hooks --overwrite

# sync the virtual environment
venv:
  uv sync --all-extras

# auto-format, lint-fix, and type-check
tidy: setup
  uv run ruff format "{{srcdir}}" "{{basedir}}/tests"
  uv run ruff check --fix "{{srcdir}}" "{{basedir}}/tests"
  uv run pyright "{{srcdir}}" "{{basedir}}/tests"

# run unit tests
test: setup
  uv run pytest "{{basedir}}/tests"

# run pre-commit hooks on all files
precommit: setup
  uv run pre-commit run --all-files --verbose

# full pre-commit + unit tests (gate for commits)
preflight: precommit test

# run juliet from source
run: setup
  uv run python3 -m juliet

# generate coverage reports
coverage: test
  uv run coverage report
  uv run coverage html

# build distribution packages
build-dist: preflight
  uv build

# remove caches and compiled files
clean:
  rm -f "{{basedir}}/.coverage"
  rm -rf "{{basedir}}/.pytest_cache"
  rm -rf "{{basedir}}/.ruff_cache"
  find "{{basedir}}" -name "*.pyc" -delete
  find "{{basedir}}" -name "__pycache__" -type d -exec rm -rf {} +

# remove everything including venv and dist
clobber: clean
  uv run pre-commit uninstall || true
  rm -rf "{{basedir}}/dist"
  rm -rf "{{basedir}}/.venv"
