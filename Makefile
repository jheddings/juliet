# Makefile for juliet

BASEDIR ?= $(PWD)
APPNAME ?= juliet
APPDIR ?= $(BASEDIR)/app/$(APPNAME)
SRCDIR ?= $(BASEDIR)/src

################################################################################
.PHONY: build

build:
	docker image build --tag "$(APPNAME):dev" "$(BASEDIR)"

################################################################################
.PHONY: rebuild

rebuild:
	docker image build --no-cache --tag "$(APPNAME):dev" "$(BASEDIR)"

################################################################################
.PHONY: run

run:
	docker container run --rm --tty --publish 5000:5000 \
		--volume "$(SRCDIR)":"/opt/$(APPNAME)" "$(APPNAME):dev"

################################################################################
.PHONY: shell

shell:
	docker container run --rm --tty --interactive \
		--volume "$(SRCDIR)":"/opt/$(APPNAME)" "$(APPNAME):dev" shell

################################################################################
.PHONY: venv

venv:
	python3 -m venv "$(BASEDIR)"
	bin/pip3 install -r requirements.txt
	echo "$(SRCDIR)" > "lib/*/site-packages/$(APPNAME).pth"

################################################################################
.PHONY: test

test:
	python3 -m unittest discover -v -s ./test

################################################################################
.PHONY: clean

clean:
	rm -f "$(SRCDIR)/*.pyc"
	rm -Rf "$(SRCDIR)/__pycache__"

################################################################################
.PHONY: clobber

# TODO deactivate first
clobber: clean
	rm -Rf "$(BASEDIR)/bin"
	rm -Rf "$(BASEDIR)/lib"
	rm -Rf "$(BASEDIR)/include"
	rm -f "$(BASEDIR)/pyvenv.cfg"

