# Makefile for juliet

BASEDIR ?= $(PWD)
SRCDIR ?= $(BASEDIR)/$(APPNAME)
VENVDIR ?= $(BASEDIR)/.venv

APPNAME ?= $(shell grep -m1 '^name' "$(BASEDIR)/pyproject.toml" | sed -e 's/name.*"\(.*\)"/\1/')
APPVER ?= $(shell grep -m1 '^version' "$(BASEDIR)/pyproject.toml" | sed -e 's/version.*"\(.*\)"/\1/')

WITH_VENV = poetry run


.PHONY: all
all: venv preflight build


.PHONY: venv
venv:
	poetry install --sync --no-interaction
	$(WITH_VENV) pre-commit install --install-hooks --overwrite


poetry.lock: venv
	poetry lock --no-update --no-interaction


.PHONY: build-dist
build-dist: preflight
	poetry build --no-interaction


.PHONY: build
build: build-dist


.PHONY: run
run: venv
	$(WITH_VENV) python3 -m juliet


.PHONY: static-checks
static-checks: venv
	$(WITH_VENV) pre-commit run --all-files --verbose


.PHONY: unit-tests
unit-tests: venv
	$(WITH_VENV) coverage run "--source=$(SRCDIR)" -m \
		pytest $(BASEDIR)/tests


.PHONY: coverage-report
coverage-report: venv unit-tests
	$(WITH_VENV) coverage report


.PHONY: coverage-html
coverage-html: venv unit-tests
	$(WITH_VENV) coverage html


.PHONY: coverage
coverage: coverage-report coverage-html


.PHONY: preflight
preflight: static-checks unit-tests coverage-report


.PHONY: clean
clean:
	rm -f "$(BASEDIR)/.coverage"
	rm -Rf "$(BASEDIR)/.pytest_cache"
	find "$(BASEDIR)" -name "*.pyc" -print | xargs rm -f
	find "$(BASEDIR)" -name '__pycache__' -print | xargs rm -Rf


.PHONY: clobber
clobber: clean
	$(WITH_VENV) pre-commit uninstall
	rm -Rf "$(BASEDIR)/htmlcov"
	rm -Rf "$(BASEDIR)/dist"
	poetry env remove --all --no-interaction
