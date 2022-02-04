# Makefile for juliet

BASEDIR ?= $(PWD)
APPNAME ?= juliet
SRCDIR ?= $(BASEDIR)/$(APPNAME)
VENVDIR ?= $(BASEDIR)/.venv

SOURCES = "$(SRCDIR)" "$(BASEDIR)/tests"

################################################################################
.PHONY: all

all: build test

################################################################################
.PHONY: build

build: venv-configured test
	python3 -m build

################################################################################
.PHONY: rebuild

rebuild: clean build

################################################################################
.PHONY: venv

bin/activate: requirements/core.txt requirements/dev.txt
	python3 -m venv --prompt "$(APPNAME)" "$(BASEDIR)/.venv"
	"$(BASEDIR)/.venv/bin/pip3" install --upgrade pip
	"$(BASEDIR)/.venv/bin/pip3" install -r requirements/core.txt
	"$(BASEDIR)/.venv/bin/pip3" install -r requirements/dev.txt

venv: bin/activate
	echo "$(SRCDIR)" > "$(BASEDIR)/.venv/lib/*/site-packages/$(APPNAME).pth"

################################################################################
.PHONY: venv-configured

venv-configured:
ifneq ($(VIRTUAL_ENV), $(VENVDIR))
	$(error Must use venv !!)
endif

################################################################################
.PHONY: run

run: venv-configured test
	python3 -m juliet

################################################################################
.PHONY: static_check

static_check: venv-configured
	isort --profile black $(SOURCES)
	black $(SOURCES)
	flake8 --ignore=E266,E402,E501 $(SOURCES)

################################################################################
.PHONY: test

test: venv-configured
	python3 -m unittest discover -v -s "$(BASEDIR)/tests"

################################################################################
.PHONY: preflight

preflight: static_check test

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
	rm -Rf "$(VENVDIR)"

