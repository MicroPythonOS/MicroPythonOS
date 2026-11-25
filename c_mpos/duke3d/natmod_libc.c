// The libc pieces a native module needs on a glibc host but cannot link.
//
// duke_libc.c implements the functions the engine calls (and the core needs).
// glibc's <ctype.h> is a set of inline functions that read tables returned by
// __ctype_b_loc()/__ctype_toupper_loc()/__ctype_tolower_loc(), and a native
// module has no libc to resolve those, so the tables live here. The stdio
// objects are symbols the engine mentions but never really uses: its stdio is
// mpos_printf.c (to the REPL) and duke_libc.c (to the host's files).

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

// glibc's ctype bit layout (_ISbit in <ctype.h>): the first eight flags live
// in the high byte of the unsigned short, the last four in the low byte.
#define GLIBC_IS_UPPER 0x0100
#define GLIBC_IS_LOWER 0x0200
#define GLIBC_IS_ALPHA 0x0400
#define GLIBC_IS_DIGIT 0x0800
#define GLIBC_IS_XDIGIT 0x1000
#define GLIBC_IS_SPACE 0x2000
#define GLIBC_IS_PRINT 0x4000
#define GLIBC_IS_GRAPH 0x8000
#define GLIBC_IS_BLANK 0x0001
#define GLIBC_IS_CNTRL 0x0002
#define GLIBC_IS_PUNCT 0x0004
#define GLIBC_IS_ALNUM 0x0008

unsigned short g_ctype_b[256];
int g_ctype_toupper[256];
int g_ctype_tolower[256];
const unsigned short *g_ctype_b_pointer;
const int *g_ctype_toupper_pointer;
const int *g_ctype_tolower_pointer;
int g_ctype_ready;

FILE *stdin;
FILE *stdout;
FILE *stderr;

static void ctype_init(void) {
    if (g_ctype_ready) {
        return;
    }
    for (int c = 0; c < 256; c++) {
        unsigned short flags = 0;
        if (c >= 'A' && c <= 'Z') {
            flags |= GLIBC_IS_UPPER | GLIBC_IS_ALPHA | GLIBC_IS_ALNUM;
        }
        if (c >= 'a' && c <= 'z') {
            flags |= GLIBC_IS_LOWER | GLIBC_IS_ALPHA | GLIBC_IS_ALNUM;
        }
        if (c >= '0' && c <= '9') {
            flags |= GLIBC_IS_DIGIT | GLIBC_IS_XDIGIT | GLIBC_IS_ALNUM;
        }
        if ((c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f')) {
            flags |= GLIBC_IS_XDIGIT;
        }
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' ||
            c == '\v') {
            flags |= GLIBC_IS_SPACE;
        }
        if (c == ' ' || c == '\t') {
            flags |= GLIBC_IS_BLANK;
        }
        if (c >= 0x20 && c < 0x7f) {
            flags |= GLIBC_IS_PRINT;
        }
        if (c > 0x20 && c < 0x7f) {
            flags |= GLIBC_IS_GRAPH;
        }
        if (c < 0x20 || c == 0x7f) {
            flags |= GLIBC_IS_CNTRL;
        }
        if (c > 0x20 && c < 0x7f &&
            !(flags & (GLIBC_IS_ALPHA | GLIBC_IS_DIGIT))) {
            flags |= GLIBC_IS_PUNCT;
        }
        g_ctype_b[c] = flags;
        g_ctype_toupper[c] = (c >= 'a' && c <= 'z') ? c - 'a' + 'A' : c;
        g_ctype_tolower[c] = (c >= 'A' && c <= 'Z') ? c - 'A' + 'a' : c;
    }
    g_ctype_ready = 1;
}

const unsigned short **__ctype_b_loc(void) {
    ctype_init();
    g_ctype_b_pointer = g_ctype_b;
    return &g_ctype_b_pointer;
}

const int **__ctype_toupper_loc(void) {
    ctype_init();
    g_ctype_toupper_pointer = g_ctype_toupper;
    return &g_ctype_toupper_pointer;
}

const int **__ctype_tolower_loc(void) {
    ctype_init();
    g_ctype_tolower_pointer = g_ctype_tolower;
    return &g_ctype_tolower_pointer;
}

#undef getc
int getc(FILE *stream) {
    return fgetc(stream);
}

// scriplib's CON parser reads numbers with strtod. No libc, so parse the same
// subset the engine writes (sign, digits, fraction, exponent, end pointer).
double strtod(const char *text, char **endptr) {
    const char *p = text;
    int sign = 1;
    double value = 0.0;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') {
        p++;
    }
    if (*p == '-') {
        sign = -1;
        p++;
    } else if (*p == '+') {
        p++;
    }
    while (*p >= '0' && *p <= '9') {
        value = value * 10.0 + (*p - '0');
        p++;
    }
    if (*p == '.') {
        double scale = 0.1;
        p++;
        while (*p >= '0' && *p <= '9') {
            value += (*p - '0') * scale;
            scale *= 0.1;
            p++;
        }
    }
    if (*p == 'e' || *p == 'E') {
        int exponent = 0;
        int exponent_sign = 1;
        const char *start = p;
        p++;
        if (*p == '-') {
            exponent_sign = -1;
            p++;
        } else if (*p == '+') {
            p++;
        }
        if (*p >= '0' && *p <= '9') {
            while (*p >= '0' && *p <= '9') {
                exponent = exponent * 10 + (*p - '0');
                p++;
            }
            while (exponent-- > 0) {
                value = exponent_sign > 0 ? value * 10.0 : value / 10.0;
            }
        } else {
            p = start;
        }
    }
    if (endptr != NULL) {
        *endptr = (char *)p;
    }
    return sign * value;
}
