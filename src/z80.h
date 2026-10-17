/* Small, portable Z80 interpreter (instruction-stepped).
 * Implements the documented and undocumented instruction set, including
 * the undocumented flags (bits 3/5), MEMPTR-free behaviour sufficient
 * for ZEXALL except BIT n,(HL) X/Y flags, IM 0/1/2, HALT and EI delay. */
#ifndef Z80_H
#define Z80_H
#include <stdint.h>

typedef struct Z80 Z80;
struct Z80 {
    union { struct { uint8_t f, a; }; uint16_t af; };
    union { struct { uint8_t c, b; }; uint16_t bc; };
    union { struct { uint8_t e, d; }; uint16_t de; };
    union { struct { uint8_t l, h; }; uint16_t hl; };
    union { struct { uint8_t ixl, ixh; }; uint16_t ix; };
    union { struct { uint8_t iyl, iyh; }; uint16_t iy; };
    uint16_t af_, bc_, de_, hl_;
    uint16_t sp, pc;
    uint8_t i, r, r7;     /* r7 holds bit 7 of R as written by LD R,A */
    uint8_t iff1, iff2, im;
    uint8_t halted;
    uint8_t ei_pending;   /* interrupts not accepted right after EI */
    uint8_t irq_line;     /* level-triggered maskable interrupt request */
    uint8_t irq_data;     /* value on the data bus during IM 2 ack */
    uint64_t cycles;

    void *ctx;
    uint8_t (*read)(void *ctx, uint16_t addr);
    void (*write)(void *ctx, uint16_t addr, uint8_t val);
    uint8_t (*in)(void *ctx, uint16_t port);
    void (*out)(void *ctx, uint16_t port, uint8_t val);
};

void z80_reset(Z80 *z);
/* Execute one instruction (or accept a pending interrupt). Returns T-states. */
int z80_step(Z80 *z);
/* Request NMI (edge). */
int z80_nmi(Z80 *z);

#endif
