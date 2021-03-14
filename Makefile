# Makefile for juliet

BASEDIR ?= $(PWD)
APPNAME ?= juliet
SRCDIR ?= $(BASEDIR)/src

################################################################################
.PHONY: all

all: build test

################################################################################
.PHONY: build

build: configured test
	python3 -m build

################################################################################
.PHONY: rebuild

rebuild: clean build

################################################################################
.PHONY: venv

venv:
	python3 -m venv "$(BASEDIR)"
	bin/pip3 install -r requirements.txt

################################################################################
.PHONY: configured

configured:
ifneq ($(VIRTUAL_ENV), $(BASEDIR))
	$(error Must use venv !!)
endif

################################################################################
.PHONY: test

test: configured
	python3 -m unittest discover -v -s ./test

################################################################################
.PHONY: deploy

deploy: test
	python3 -m twine upload --repository testpypi dist/*

################################################################################
.PHONY: clean

clean:
	rm -f "$(SRCDIR)/*.pyc"
	rm -Rf "$(SRCDIR)/__pycache__"
	rm -f "$(BASEDIR)/juliet.log"
	rm -Rf "$(BASEDIR)/build"

################################################################################
.PHONY: clobber

# TODO fail if venv activated
clobber: clean
	rm -Rf "$(BASEDIR)/dist"
	rm -Rf "$(BASEDIR)/bin"
	rm -Rf "$(BASEDIR)/lib"
	rm -Rf "$(BASEDIR)/include"
	rm -f "$(BASEDIR)/pyvenv.cfg"

