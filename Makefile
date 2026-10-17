# Spellbound native build. Needs SDL2:
#   macOS:  brew install sdl2
#   Linux:  apt install libsdl2-dev
CC      ?= cc
CFLAGS  ?= -O2 -Wall -Wextra
SDL_CFLAGS := $(shell sdl2-config --cflags)
SDL_LIBS   := $(shell sdl2-config --libs)

SRC = src/main.c src/spectrum.c src/z80.c
HDR = src/spectrum.h src/z80.h
TAP ?= original/S_BND128.TAP

all: spellbound

spellbound: $(SRC) $(HDR)
	$(CC) $(CFLAGS) $(SDL_CFLAGS) -Isrc $(SRC) -o $@ $(SDL_LIBS)

zextest: tests/zextest.c src/z80.c src/z80.h
	$(CC) $(CFLAGS) -Isrc tests/zextest.c src/z80.c -o $@

# macOS application bundle (double-clickable). Copies the TAP inside the
# bundle if it exists, so the game starts without arguments.
app: spellbound
	sh tools/make_app.sh $(TAP)

extract:
	python3 tools/tap_extract.py $(TAP) --out extracted
	python3 tools/extract_assets.py extracted --out assets

clean:
	rm -rf spellbound zextest Spellbound.app

.PHONY: all app extract clean
