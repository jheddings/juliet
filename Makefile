# Makefile for juliet

BASEDIR ?= $(PWD)
SRCDIR ?= $(BASEDIR)/$(APPNAME)
VENVDIR ?= $(BASEDIR)/.venv

APPNAME ?= $(shell grep -m1 '^name' "$(BASEDIR)/pyproject.toml" | sed -e 's/name.*"\(.*\)"/\1/')
APPVER ?= $(shell grep -m1 '^version' "$(BASEDIR)/pyproject.toml" | sed -e 's/version.*"\(.*\)"/\1/')

WITH_VENV = poetry run

################################################################################
.PHONY: all

all: venv build test

################################################################################
.PHONY: venv

venv:
	poetry install --sync
	$(WITH_VENV) pre-commit install --install-hooks --overwrite

################################################################################
.PHONY: build-pkg

build-pkg: venv preflight test
	poetry --no-interaction build

################################################################################
.PHONY: build

build: preflight test build-pkg

################################################################################
.PHONY: run

run: venv
	$(WITH_VENV) python3 -m juliet

################################################################################
.PHONY: test

test: venv preflight
	$(WITH_VENV) pytest $(BASEDIR)/tests

################################################################################
.PHONY: test-coverage

test-coverage: venv
	$(WITH_VENV) coverage run "--source=$(SRCDIR)" -m pytest $(BASEDIR)/tests 

################################################################################
.PHONY: coverage-report

coverage-report: venv test-coverage
	$(WITH_VENV) coverage report

################################################################################
.PHONY: coverage-html

coverage-html: venv test-coverage
	$(WITH_VENV) coverage html

################################################################################
.PHONY: coverage

coverage: coverage-report coverage-html

################################################################################
.PHONY: preflight

preflight: venv
	$(WITH_VENV) pre-commit run --all-files --verbose

################################################################################
.PHONY: clean

clean:
	rm -f "$(BASEDIR)/.coverage"
	rm -Rf "$(BASEDIR)/.pytest_cache"
	find "$(BASEDIR)" -name "*.pyc" -print | xargs rm -f
	find "$(BASEDIR)" -name '__pycache__' -print | xargs rm -Rf

################################################################################
.PHONY: clobber

clobber: clean
	$(WITH_VENV) pre-commit uninstall
	rm -Rf "$(BASEDIR)/htmlcov"
	rm -Rf "$(BASEDIR)/dist"
	rm -Rf "$(BASEDIR)/.venv"
