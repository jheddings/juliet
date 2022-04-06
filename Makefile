# Makefile for juliet

BASEDIR ?= $(PWD)
APPNAME ?= juliet
SRCDIR ?= $(BASEDIR)/$(APPNAME)
VENVDIR ?= $(BASEDIR)/.venv

WITH_VENV = source "$(VENVDIR)/bin/activate" &&

SOURCES = "$(SRCDIR)" "$(BASEDIR)/tests"

################################################################################
.PHONY: all

all: build test

################################################################################
.PHONY: build

build: test
	$(WITH_VENV) python3 -m build

################################################################################
.PHONY: rebuild

rebuild: clean build

################################################################################
.PHONY: venv

venv: requirements/core.txt requirements/dev.txt
	python3 -m venv --prompt "$(APPNAME)" "$(BASEDIR)/.venv"
	"$(BASEDIR)/.venv/bin/pip3" install --upgrade pip
	"$(BASEDIR)/.venv/bin/pip3" install -r requirements/core.txt
	"$(BASEDIR)/.venv/bin/pip3" install -r requirements/dev.txt

################################################################################
.PHONY: devenv

devenv: venv
	$(WITH_VENV) pre-commit install

################################################################################
.PHONY: run

run:
	$(WITH_VENV) python3 -m juliet

################################################################################
.PHONY: test

test:
	$(WITH_VENV) python3 -m unittest discover -v -s "$(BASEDIR)/tests"

################################################################################
.PHONY: preflight

preflight: test
	$(WITH_VENV) pre-commit run --all-files

################################################################################
.PHONY: clean

clean:
	rm -f "$(SRCDIR)/*.pyc"
	rm -Rf "$(SRCDIR)/__pycache__"
	rm -Rf "$(BASEDIR)/tests/__pycache__"

################################################################################
.PHONY: clobber

# TODO fail if venv activated
clobber: clean
	pre-commit uninstall
	rm -Rf "$(VENVDIR)"
