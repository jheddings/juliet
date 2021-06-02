# Makefile for juliet

BASEDIR ?= $(PWD)
APPNAME ?= juliet
SRCDIR ?= $(BASEDIR)/src

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

bin/activate: requirements.txt
	python3 -m venv --prompt "$(APPNAME)" "$(BASEDIR)/.venv"
	"$(BASEDIR)/.venv/bin/pip3" install -r requirements.txt

venv: bin/activate
	echo "$(SRCDIR)" > "$(BASEDIR)/.venv/lib/*/site-packages/$(APPNAME).pth"

################################################################################
.PHONY: venv-configured

venv-configured:
ifneq ($(VIRTUAL_ENV), $(BASEDIR))
	$(error Must use venv !!)
endif

################################################################################
.PHONY: run

run: venv-configured test
	python3 -m juliet

################################################################################
.PHONY: test

test: venv-configured
	python3 -m unittest discover -v -s ./test

################################################################################
.PHONY: clean

clean:
	rm -Rf "$(BASEDIR)/build"
	rm -f "$(BASEDIR)/juliet.log"
	find "$(BASEDIR)" -type f -name "*.pyc" -delete -o -type d -name __pycache__ -delete

################################################################################
.PHONY: clobber

# TODO fail if venv activated
clobber: clean
	rm -Rf "$(BASEDIR)/dist"
	rm -Rf "$(BASEDIR)/.venv"

