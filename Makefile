SOURCE = REEL
VERSION = $(shell cat doc/version)

GCC=gcc
GXX=g++ -std=c++11

export GCC GXX

CFLAGS=-g -O2 -D_linux_ -Wno-deprecated-declarations
CXXFLAGS=-g -O2
LDFLAGS=
DESTDIR=

PREFIX=/usr
EXEC_PREFIX=${PREFIX}
LIBDIR=${EXEC_PREFIX}/lib
BINDIR=${EXEC_PREFIX}/bin
LAUNCHERDIR=${EXEC_PREFIX}/share/applications
ICONDIR=${EXEC_PREFIX}/share/icons/hicolor/scalable/apps

export CFLAGS CXXFLAGS LDFLAGS DESTDIR PREFIX EXEC_PREFIX LIBDIR BINDIR

INSTALL=/usr/bin/install -c
OBJCOPY=objcopy
LD=/usr/bin/ld -m elf_x86_64

GTK_INSTALL =
QT_INSTALL =

export CFLAGS CXXFLAGS LDFLAGS DESTDIR INSTALL OBJCOPY LD

.PHONY: all clean install rebuild _build

all: _build

clean:
	@rm -rvf out

install: out/libdriveio.so.0 out/libmakemkv.so.1 out/libmmbd.so.0 out/mmccextr out/mmgplsrv out/makemkvcon
	$(INSTALL) -D -m 644 out/libdriveio.so.0  $(DESTDIR)$(LIBDIR)/libdriveio.so.0
	$(INSTALL) -D -m 644 out/libmakemkv.so.1  $(DESTDIR)$(LIBDIR)/libmakemkv.so.1
	$(INSTALL) -D -m 644 out/libmmbd.so.0     $(DESTDIR)$(LIBDIR)/libmmbd.so.0

ifeq ($(DESTDIR),)
	ldconfig
endif

	$(INSTALL) -D -m 755 out/mmccextr         $(DESTDIR)$(BINDIR)/mmccextr
	$(INSTALL) -D -m 755 out/mmgplsrv         $(DESTDIR)$(BINDIR)/mmgplsrv
	$(INSTALL) -D -m 755 out/makemkvcon       $(DESTDIR)$(BINDIR)/makemkvcon
	$(INSTALL) -D -m 755 src/reel             $(DESTDIR)$(BINDIR)/reel

ifeq ($(GTK_INSTALL),yes)
	$(INSTALL) -D -m 755 src/core/*.py  $(DESTDIR)$(LIBDIR)/reel/core/
	$(INSTALL) -D -m 755 src/ui/*.py   $(DESTDIR)$(LIBDIR)/reel/ui/
	$(INSTALL) -D -m 755 src/main.py  $(DESTDIR)$(LIBDIR)/reel/
endif

	$(INSTALL) -D -m 644 data/comMLSTidbits.Reel.desktop $(DESTDIR)$(LAUNCHERDIR)/
	$(INSTALL) -D -m 644 data/icons/scalable/comMLSTidbits.Reel.svg $(DESTDIR)$(ICONDIR)/

	$(INSTALL) -D -m 644 data/ui/* $(DESTDIR)$(PREFIX)/share/reel/ui/

_build:
	@mkdir -p _build
	@echo "Building REEL $(VERSION) in _build/"
	@cp -r src/* _build/

# Copy documentation files to the build directory
	@echo "Copying documentation files to _build/doc/"
	@cp -r doc _build/
	@cp CODE_OF_CONDUCT.md _build/doc/
	@cp COPYING _build/doc/
	@cp README.md _build/doc/
	@cp CONTRIBUTING.md _build/doc/

# Copy data files to the build directory
	@echo "Copying data files to _build/data/"
	@cp -r data _build/
