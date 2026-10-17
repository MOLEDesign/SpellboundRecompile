/* Z80 interpreter. See z80.h. */
#include "z80.h"

#define FC 0x01
#define FN 0x02
#define FP 0x04
#define F3 0x08
#define FH 0x10
#define F5 0x20
#define FZ 0x40
#define FS 0x80

static uint8_t sz53[256], sz53p[256], parity[256];
static int tables_ready;

static void init_tables(void)
{
    for (int i = 0; i < 256; i++) {
        int p = 1;
        for (int b = 0; b < 8; b++) if (i & (1 << b)) p ^= 1;
        parity[i] = p ? FP : 0;
        sz53[i] = (i & (FS | F3 | F5)) | (i == 0 ? FZ : 0);
        sz53p[i] = sz53[i] | parity[i];
    }
    tables_ready = 1;
}

#define RD(a) z->read(z->ctx, (uint16_t)(a))
#define WR(a, v) z->write(z->ctx, (uint16_t)(a), (uint8_t)(v))

static inline uint8_t fetch(Z80 *z) { return RD(z->pc++); }
static inline uint16_t fetch16(Z80 *z) { uint16_t l = fetch(z); return l | (uint16_t)fetch(z) << 8; }
static inline uint16_t rd16(Z80 *z, uint16_t a) { return RD(a) | (uint16_t)RD(a + 1) << 8; }
static inline void wr16(Z80 *z, uint16_t a, uint16_t v) { WR(a, v & 0xff); WR(a + 1, v >> 8); }
static inline void push(Z80 *z, uint16_t v) { z->sp -= 2; wr16(z, z->sp, v); }
static inline uint16_t pop(Z80 *z) { uint16_t v = rd16(z, z->sp); z->sp += 2; return v; }
static inline void inc_r(Z80 *z) { z->r = (z->r & 0x80) | ((z->r + 1) & 0x7f); }

void z80_reset(Z80 *z)
{
    if (!tables_ready) init_tables();
    z->af = z->bc = z->de = z->hl = 0xffff;
    z->ix = z->iy = 0xffff;
    z->af_ = z->bc_ = z->de_ = z->hl_ = 0xffff;
    z->sp = 0xffff; z->pc = 0;
    z->i = z->r = 0;
    z->iff1 = z->iff2 = 0; z->im = 0;
    z->halted = 0; z->ei_pending = 0;
    z->irq_line = 0; z->irq_data = 0xff;
    z->cycles = 0;
}

/* ---- ALU ---- */
static inline void add8(Z80 *z, uint8_t v, int carry)
{
    int c = carry ? (z->f & FC) : 0;
    unsigned r = z->a + v + c;
    uint8_t lookup = ((z->a & 0x88) >> 3) | ((v & 0x88) >> 2) | ((r & 0x88) >> 1);
    static const uint8_t hc[8] = {0, FH, FH, FH, 0, 0, 0, FH};
    static const uint8_t ov[8] = {0, 0, 0, FP, FP, 0, 0, 0};
    z->a = (uint8_t)r;
    z->f = (r & 0x100 ? FC : 0) | hc[lookup & 7] | ov[lookup >> 4] | sz53[z->a];
}
static inline void sub8(Z80 *z, uint8_t v, int carry, int store)
{
    int c = carry ? (z->f & FC) : 0;
    unsigned r = z->a - v - c;
    uint8_t lookup = ((z->a & 0x88) >> 3) | ((v & 0x88) >> 2) | ((r & 0x88) >> 1);
    static const uint8_t hc[8] = {0, 0, FH, 0, FH, 0, FH, FH};
    static const uint8_t ov[8] = {0, FP, 0, 0, 0, 0, FP, 0};
    uint8_t res = (uint8_t)r;
    uint8_t f = (r & 0x100 ? FC : 0) | FN | hc[lookup & 7] | ov[lookup >> 4];
    if (store) { z->a = res; z->f = f | sz53[res]; }
    else z->f = f | (res & FS) | (res ? 0 : FZ) | (v & (F3 | F5)); /* CP: X/Y from operand */
}
static inline void and8(Z80 *z, uint8_t v) { z->a &= v; z->f = FH | sz53p[z->a]; }
static inline void xor8(Z80 *z, uint8_t v) { z->a ^= v; z->f = sz53p[z->a]; }
static inline void or8(Z80 *z, uint8_t v) { z->a |= v; z->f = sz53p[z->a]; }
static void alu(Z80 *z, int op, uint8_t v)
{
    switch (op) {
    case 0: add8(z, v, 0); break;
    case 1: add8(z, v, 1); break;
    case 2: sub8(z, v, 0, 1); break;
    case 3: sub8(z, v, 1, 1); break;
    case 4: and8(z, v); break;
    case 5: xor8(z, v); break;
    case 6: or8(z, v); break;
    case 7: sub8(z, v, 0, 0); break;
    }
}
static inline uint8_t inc8(Z80 *z, uint8_t v)
{
    uint8_t r = v + 1;
    z->f = (z->f & FC) | (r == 0x80 ? FP : 0) | ((r & 0x0f) ? 0 : FH) | sz53[r];
    return r;
}
static inline uint8_t dec8(Z80 *z, uint8_t v)
{
    uint8_t r = v - 1;
    z->f = (z->f & FC) | FN | (r == 0x7f ? FP : 0) | ((v & 0x0f) ? 0 : FH) | sz53[r];
    return r;
}
static inline uint16_t add16(Z80 *z, uint16_t a, uint16_t b)
{
    unsigned r = a + b;
    uint8_t lookup = ((a & 0x0800) >> 11) | ((b & 0x0800) >> 10) | ((r & 0x0800) >> 9);
    static const uint8_t hc[8] = {0, FH, FH, FH, 0, 0, 0, FH};
    z->f = (z->f & (FS | FZ | FP)) | (r & 0x10000 ? FC : 0) | ((r >> 8) & (F3 | F5)) | hc[lookup];
    return (uint16_t)r;
}
static inline uint16_t adc16(Z80 *z, uint16_t a, uint16_t b)
{
    unsigned r = a + b + (z->f & FC);
    uint8_t lookup = ((a & 0x8800) >> 11) | ((b & 0x8800) >> 10) | ((r & 0x8800) >> 9);
    static const uint8_t hc[8] = {0, FH, FH, FH, 0, 0, 0, FH};
    static const uint8_t ov[8] = {0, 0, 0, FP, FP, 0, 0, 0};
    uint16_t res = (uint16_t)r;
    z->f = (r & 0x10000 ? FC : 0) | ov[lookup >> 4] | ((res >> 8) & (F3 | F5 | FS)) | hc[lookup & 7] | (res ? 0 : FZ);
    return res;
}
static inline uint16_t sbc16(Z80 *z, uint16_t a, uint16_t b)
{
    unsigned r = a - b - (z->f & FC);
    uint8_t lookup = ((a & 0x8800) >> 11) | ((b & 0x8800) >> 10) | ((r & 0x8800) >> 9);
    static const uint8_t hc[8] = {0, 0, FH, 0, FH, 0, FH, FH};
    static const uint8_t ov[8] = {0, FP, 0, 0, 0, 0, FP, 0};
    uint16_t res = (uint16_t)r;
    z->f = (r & 0x10000 ? FC : 0) | FN | ov[lookup >> 4] | ((res >> 8) & (F3 | F5 | FS)) | hc[lookup & 7] | (res ? 0 : FZ);
    return res;
}
/* CB rotate/shift group */
static uint8_t rot(Z80 *z, int op, uint8_t v)
{
    uint8_t r, c;
    switch (op) {
    case 0: c = v >> 7; r = (v << 1) | c; break;                 /* RLC */
    case 1: c = v & 1; r = (v >> 1) | (c << 7); break;           /* RRC */
    case 2: c = v >> 7; r = (v << 1) | (z->f & FC); break;       /* RL */
    case 3: c = v & 1; r = (v >> 1) | ((z->f & FC) << 7); break; /* RR */
    case 4: c = v >> 7; r = v << 1; break;                       /* SLA */
    case 5: c = v & 1; r = (v >> 1) | (v & 0x80); break;         /* SRA */
    case 6: c = v >> 7; r = (v << 1) | 1; break;                 /* SLL */
    default: c = v & 1; r = v >> 1; break;                       /* SRL */
    }
    z->f = sz53p[r] | c;
    return r;
}

static inline int cond(Z80 *z, int y)
{
    switch (y) {
    case 0: return !(z->f & FZ);
    case 1: return z->f & FZ;
    case 2: return !(z->f & FC);
    case 3: return z->f & FC;
    case 4: return !(z->f & FP);
    case 5: return z->f & FP;
    case 6: return !(z->f & FS);
    default: return z->f & FS;
    }
}

/* register access; idx: 0=HL,1=IX,2=IY. (HL) handled by caller */
static inline uint8_t get_r(Z80 *z, int r, int idx)
{
    switch (r) {
    case 0: return z->b; case 1: return z->c; case 2: return z->d; case 3: return z->e;
    case 4: return idx == 0 ? z->h : idx == 1 ? z->ixh : z->iyh;
    case 5: return idx == 0 ? z->l : idx == 1 ? z->ixl : z->iyl;
    default: return z->a;
    }
}
static inline void set_r(Z80 *z, int r, int idx, uint8_t v)
{
    switch (r) {
    case 0: z->b = v; break; case 1: z->c = v; break; case 2: z->d = v; break; case 3: z->e = v; break;
    case 4: if (idx == 0) z->h = v; else if (idx == 1) z->ixh = v; else z->iyh = v; break;
    case 5: if (idx == 0) z->l = v; else if (idx == 1) z->ixl = v; else z->iyl = v; break;
    default: z->a = v; break;
    }
}
static inline uint16_t *rp(Z80 *z, int p, int idx)
{
    switch (p) {
    case 0: return &z->bc; case 1: return &z->de;
    case 2: return idx == 0 ? &z->hl : idx == 1 ? &z->ix : &z->iy;
    default: return &z->sp;
    }
}
static inline uint16_t *rp2(Z80 *z, int p, int idx)
{
    if (p == 3) return &z->af;
    return rp(z, p, idx);
}

static int exec_cb(Z80 *z, int idx, uint16_t addr)
{
    uint8_t op = fetch(z);
    int x = op >> 6, y = (op >> 3) & 7, r = op & 7;
    uint8_t v;
    if (idx == 0) {
        inc_r(z);
        v = (r == 6) ? RD(z->hl) : get_r(z, r, 0);
        if (x == 1) {
            uint8_t t = v & (1 << y);
            z->f = (z->f & FC) | FH | (t ? 0 : (FZ | FP)) | (t & FS);
            if (r == 6) return 12;
            z->f |= v & (F3 | F5);
            return 8;
        }
        if (x == 0) v = rot(z, y, v);
        else if (x == 2) v &= ~(1 << y);
        else v |= 1 << y;
        if (r == 6) { WR(z->hl, v); return 15; }
        set_r(z, r, 0, v);
        return 8;
    }
    v = RD(addr);
    if (x == 1) {
        uint8_t t = v & (1 << y);
        z->f = (z->f & FC) | FH | (t ? 0 : (FZ | FP)) | (t & FS) | ((addr >> 8) & (F3 | F5));
        return 16; /* +4 for the DD/FD prefix */
    }
    if (x == 0) v = rot(z, y, v);
    else if (x == 2) v &= ~(1 << y);
    else v |= 1 << y;
    WR(addr, v);
    if (r != 6) set_r(z, r, 0, v);
    return 19;
}

static int exec_ed(Z80 *z)
{
    uint8_t op = fetch(z);
    inc_r(z);
    int x = op >> 6, y = (op >> 3) & 7, zz = op & 7, p = y >> 1, q = y & 1;
    if (x == 1) {
        switch (zz) {
        case 0: { uint8_t v = z->in(z->ctx, z->bc); if (y != 6) set_r(z, y, 0, v);
                  z->f = (z->f & FC) | sz53p[v]; return 12; }
        case 1: z->out(z->ctx, z->bc, y == 6 ? 0 : get_r(z, y, 0)); return 12;
        case 2: if (q == 0) z->hl = sbc16(z, z->hl, *rp(z, p, 0)); else z->hl = adc16(z, z->hl, *rp(z, p, 0)); return 15;
        case 3: { uint16_t a = fetch16(z);
                  if (q == 0) wr16(z, a, *rp(z, p, 0)); else *rp(z, p, 0) = rd16(z, a); return 20; }
        case 4: { uint8_t a = z->a; z->a = 0; sub8(z, a, 0, 1); return 8; }
        case 5: z->pc = pop(z); z->iff1 = z->iff2; return 14;
        case 6: { static const uint8_t m[8] = {0, 0, 1, 2, 0, 0, 1, 2}; z->im = m[y]; return 8; }
        default:
            switch (y) {
            case 0: z->i = z->a; return 9;
            case 1: z->r = z->a; return 9;
            case 2: z->a = z->i; z->f = (z->f & FC) | sz53[z->a] | (z->iff2 ? FP : 0); return 9;
            case 3: z->a = z->r; z->f = (z->f & FC) | sz53[z->a] | (z->iff2 ? FP : 0); return 9;
            case 4: { uint8_t t = RD(z->hl); WR(z->hl, (z->a << 4) | (t >> 4));
                      z->a = (z->a & 0xf0) | (t & 0x0f); z->f = (z->f & FC) | sz53p[z->a]; return 18; }
            case 5: { uint8_t t = RD(z->hl); WR(z->hl, (t << 4) | (z->a & 0x0f));
                      z->a = (z->a & 0xf0) | (t >> 4); z->f = (z->f & FC) | sz53p[z->a]; return 18; }
            default: return 8;
            }
        }
    }
    if (x == 2 && zz <= 3 && y >= 4) {
        int dec = y & 1, rep = y & 2;
        switch (zz) {
        case 0: { /* LDI/LDD */
            uint8_t v = RD(z->hl); WR(z->de, v);
            if (dec) { z->hl--; z->de--; } else { z->hl++; z->de++; }
            z->bc--;
            uint8_t n = v + z->a;
            z->f = (z->f & (FS | FZ | FC)) | (z->bc ? FP : 0) | (n & F3) | ((n << 4) & F5);
            if (rep && z->bc) { z->pc -= 2; return 21; }
            return 16; }
        case 1: { /* CPI/CPD */
            uint8_t v = RD(z->hl);
            uint8_t r = z->a - v;
            uint8_t h = ((z->a & 0x0f) - (v & 0x0f)) & 0x10;
            if (dec) z->hl--; else z->hl++;
            z->bc--;
            uint8_t n = r - (h ? 1 : 0);
            z->f = (z->f & FC) | FN | h | (z->bc ? FP : 0) | (r & FS) | (r ? 0 : FZ) | (n & F3) | ((n << 4) & F5);
            if (rep && z->bc && r) { z->pc -= 2; return 21; }
            return 16; }
        case 2: { /* INI/IND */
            uint8_t v = z->in(z->ctx, z->bc);
            WR(z->hl, v);
            if (dec) z->hl--; else z->hl++;
            z->b--;
            unsigned k = v + (uint8_t)(dec ? z->c - 1 : z->c + 1);
            z->f = sz53[z->b] | (v & 0x80 ? FN : 0) | (k > 255 ? (FH | FC) : 0) | parity[(k & 7) ^ z->b];
            if (rep && z->b) { z->pc -= 2; return 21; }
            return 16; }
        default: { /* OUTI/OUTD */
            uint8_t v = RD(z->hl);
            z->b--;
            z->out(z->ctx, z->bc, v);
            if (dec) z->hl--; else z->hl++;
            unsigned k = v + z->l;
            z->f = sz53[z->b] | (v & 0x80 ? FN : 0) | (k > 255 ? (FH | FC) : 0) | parity[(k & 7) ^ z->b];
            if (rep && z->b) { z->pc -= 2; return 21; }
            return 16; }
        }
    }
    return 8; /* NONI / NOP */
}

static int exec_main(Z80 *z, uint8_t op, int idx)
{
    int x = op >> 6, y = (op >> 3) & 7, zz = op & 7, p = y >> 1, q = y & 1;
    const int extra = 0; /* prefix cost is added by the caller */
    uint16_t *HL = idx == 0 ? &z->hl : idx == 1 ? &z->ix : &z->iy;

#define ADDR_HL() (idx ? (uint16_t)(*HL + (int8_t)fetch(z)) : z->hl)

    switch (x) {
    case 0:
        switch (zz) {
        case 0:
            switch (y) {
            case 0: return 4 + extra;
            case 1: { uint16_t t = z->af; z->af = z->af_; z->af_ = t; return 4 + extra; }
            case 2: { int8_t d = (int8_t)fetch(z); z->b--; if (z->b) { z->pc += d; return 13 + extra; } return 8 + extra; }
            case 3: { int8_t d = (int8_t)fetch(z); z->pc += d; return 12 + extra; }
            default: { int8_t d = (int8_t)fetch(z); if (cond(z, y - 4)) { z->pc += d; return 12 + extra; } return 7 + extra; }
            }
        case 1:
            if (q == 0) { *rp(z, p, idx) = fetch16(z); return 10 + extra; }
            *HL = add16(z, *HL, *rp(z, p, idx)); return 11 + extra;
        case 2:
            switch (y) {
            case 0: WR(z->bc, z->a); return 7 + extra;
            case 1: z->a = RD(z->bc); return 7 + extra;
            case 2: WR(z->de, z->a); return 7 + extra;
            case 3: z->a = RD(z->de); return 7 + extra;
            case 4: wr16(z, fetch16(z), *HL); return 16 + extra;
            case 5: *HL = rd16(z, fetch16(z)); return 16 + extra;
            case 6: WR(fetch16(z), z->a); return 13 + extra;
            default: z->a = RD(fetch16(z)); return 13 + extra;
            }
        case 3:
            if (q == 0) (*rp(z, p, idx))++; else (*rp(z, p, idx))--;
            return 6 + extra;
        case 4:
            if (y == 6) { uint16_t a = ADDR_HL(); WR(a, inc8(z, RD(a))); return idx ? 19 : 11; }
            set_r(z, y, idx, inc8(z, get_r(z, y, idx))); return 4 + extra;
        case 5:
            if (y == 6) { uint16_t a = ADDR_HL(); WR(a, dec8(z, RD(a))); return idx ? 19 : 11; }
            set_r(z, y, idx, dec8(z, get_r(z, y, idx))); return 4 + extra;
        case 6:
            if (y == 6) { uint16_t a = ADDR_HL(); WR(a, fetch(z)); return idx ? 15 : 10; }
            set_r(z, y, idx, fetch(z)); return 7 + extra;
        default:
            switch (y) {
            case 0: { uint8_t c = z->a >> 7; z->a = (z->a << 1) | c;
                      z->f = (z->f & (FS | FZ | FP)) | (z->a & (F3 | F5)) | c; break; }
            case 1: { uint8_t c = z->a & 1; z->a = (z->a >> 1) | (c << 7);
                      z->f = (z->f & (FS | FZ | FP)) | (z->a & (F3 | F5)) | c; break; }
            case 2: { uint8_t c = z->a >> 7; z->a = (z->a << 1) | (z->f & FC);
                      z->f = (z->f & (FS | FZ | FP)) | (z->a & (F3 | F5)) | c; break; }
            case 3: { uint8_t c = z->a & 1; z->a = (z->a >> 1) | ((z->f & FC) << 7);
                      z->f = (z->f & (FS | FZ | FP)) | (z->a & (F3 | F5)) | c; break; }
            case 4: { /* DAA */
                uint8_t a = z->a, corr = 0, c = z->f & FC;
                if ((z->f & FH) || (a & 0x0f) > 9) corr = 0x06;
                if (c || a > 0x99) { corr |= 0x60; c = FC; }
                if (z->f & FN) { z->a -= corr; z->f = (z->f & FN) | c | (((a ^ z->a) & 0x10)) | sz53p[z->a]; }
                else { z->a += corr; z->f = c | ((a ^ z->a) & 0x10) | sz53p[z->a]; }
                break; }
            case 5: z->a = ~z->a; z->f = (z->f & (FS | FZ | FP | FC)) | FH | FN | (z->a & (F3 | F5)); break;
            case 6: z->f = (z->f & (FS | FZ | FP)) | FC | (z->a & (F3 | F5)); break;
            default: z->f = ((z->f & (FS | FZ | FP | FC)) | ((z->f & FC) ? FH : 0) | (z->a & (F3 | F5))) ^ FC; break;
            }
            return 4 + extra;
        }
    case 1:
        if (y == 6 && zz == 6) { z->halted = 1; z->pc--; return 4; }
        if (y == 6) { uint16_t a = ADDR_HL(); WR(a, get_r(z, zz, 0)); return idx ? 15 : 7; }
        if (zz == 6) { uint16_t a = ADDR_HL(); set_r(z, y, 0, RD(a)); return idx ? 15 : 7; }
        set_r(z, y, idx, get_r(z, zz, idx)); return 4 + extra;
    case 2:
        if (zz == 6) { uint16_t a = ADDR_HL(); alu(z, y, RD(a)); return idx ? 15 : 7; }
        alu(z, y, get_r(z, zz, idx)); return 4 + extra;
    default:
        switch (zz) {
        case 0: if (cond(z, y)) { z->pc = pop(z); return 11 + extra; } return 5 + extra;
        case 1:
            if (q == 0) { *rp2(z, p, idx) = pop(z); return 10 + extra; }
            switch (p) {
            case 0: z->pc = pop(z); return 10 + extra;
            case 1: { uint16_t t;
                      t = z->bc; z->bc = z->bc_; z->bc_ = t;
                      t = z->de; z->de = z->de_; z->de_ = t;
                      t = z->hl; z->hl = z->hl_; z->hl_ = t; return 4 + extra; }
            case 2: z->pc = *HL; return 4 + extra;
            default: z->sp = *HL; return 6 + extra;
            }
        case 2: { uint16_t a = fetch16(z); if (cond(z, y)) z->pc = a; return 10 + extra; }
        case 3:
            switch (y) {
            case 0: z->pc = fetch16(z); return 10 + extra;
            case 1: /* CB prefix */
                if (idx) { uint16_t a = (uint16_t)(*HL + (int8_t)fetch(z)); return exec_cb(z, idx, a); }
                return exec_cb(z, 0, 0);
            case 2: z->out(z->ctx, (uint16_t)(z->a << 8) | fetch(z), z->a); return 11 + extra;
            case 3: { uint8_t n = fetch(z); z->a = z->in(z->ctx, (uint16_t)(z->a << 8) | n); return 11 + extra; }
            case 4: { uint16_t t = rd16(z, z->sp); wr16(z, z->sp, *HL); *HL = t; return 19 + extra; }
            case 5: { uint16_t t = z->de; z->de = z->hl; z->hl = t; return 4 + extra; }
            case 6: z->iff1 = z->iff2 = 0; return 4 + extra;
            default: z->iff1 = z->iff2 = 1; z->ei_pending = 1; return 4 + extra;
            }
        case 4: { uint16_t a = fetch16(z); if (cond(z, y)) { push(z, z->pc); z->pc = a; return 17 + extra; } return 10 + extra; }
        case 5:
            if (q == 0) { push(z, *rp2(z, p, idx)); return 11 + extra; }
            switch (p) {
            case 0: { uint16_t a = fetch16(z); push(z, z->pc); z->pc = a; return 17 + extra; }
            case 1: inc_r(z); return 4 + exec_main(z, fetch(z), 1);
            case 2: return 4 + exec_ed(z);
            default: inc_r(z); return 4 + exec_main(z, fetch(z), 2);
            }
        case 6: alu(z, y, fetch(z)); return 7 + extra;
        default: push(z, z->pc); z->pc = y * 8; return 11 + extra;
        }
    }
#undef ADDR_HL
}

int z80_nmi(Z80 *z)
{
    if (z->halted) { z->halted = 0; z->pc++; }
    z->iff1 = 0;
    inc_r(z);
    push(z, z->pc);
    z->pc = 0x66;
    z->cycles += 11;
    return 11;
}

int z80_step(Z80 *z)
{
    int t;
    if (z->irq_line && z->iff1 && !z->ei_pending) {
        if (z->halted) { z->halted = 0; z->pc++; }
        z->iff1 = z->iff2 = 0;
        inc_r(z);
        if (z->im == 2) {
            push(z, z->pc);
            z->pc = rd16(z, (uint16_t)(z->i << 8) | z->irq_data);
            t = 19;
        } else {
            /* IM 0 with 0xFF on the bus behaves like RST 38 */
            push(z, z->pc);
            z->pc = 0x38;
            t = 13;
        }
        z->cycles += t;
        return t;
    }
    z->ei_pending = 0;
    inc_r(z);
    t = exec_main(z, fetch(z), 0);
    z->cycles += t;
    return t;
}
