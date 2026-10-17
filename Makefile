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

# Asset extraction: raw memory images, PNG graphics, room maps, music.
TOOLS = tools/mapper tools/asset_render
tools/%: tools/%.c src/spectrum.c src/spectrum.h src/z80.c tools/png.h
	$(CC) $(CFLAGS) -Isrc $< src/z80.c -o $@

extract: spellbound $(TOOLS)
	python3 tools/tap_extract.py $(TAP) --out extracted
	python3 tools/extract_assets.py extracted --out assets
	mkdir -p assets/rooms assets/music
	tools/mapper $(TAP) assets/rooms
	tools/asset_render $(TAP) assets
	./spellbound --headless --frames 3500 --wav assets/music/title_theme.wav $(TAP)

# Annotated disassembly (uses a coverage run to find code behind jump tables)
disasm: spellbound
	mkdir -p disasm
	./spellbound --headless --frames 3000 --key 300:z:6 --key 320:z:6 --key 340:z:6 \
	  --key 360:z:6 --key 380:z:6 --key 400:z:6 --key 450:space:6 --key 700:m:300 \
	  --key 1100:n:600 --key 1800:space:5 --coverage disasm/run.cov $(TAP)
	python3 tools/z80dis.py extracted/ram48.bin --entry 0x6803 --labels tools/labels.txt \
	  --coverage disasm/run.cov -o disasm/spellbound.asm
	python3 tools/z80dis.py extracted/bank4.bin --org 0xC000 --end 0x10000 --bank 4 \
	  --coverage disasm/run.cov -o disasm/bank4_music.asm

clean:
	rm -rf spellbound zextest Spellbound.app $(TOOLS)

.PHONY: all app extract disasm clean
