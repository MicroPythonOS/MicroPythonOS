// The slice of libc a legacy framebuffer engine asks for.
//
// A MicroPython native module is not linked against libc: only the MicroPython
// C API and libgcc/libm are available, so anything an engine calls from
// <string.h>/<stdlib.h>/<stdio.h> has to be provided here. Breakout needed two
// of these; an engine port needs the rest, and finding out which ones the
// compiler actually wants is the point of this spike.
//
// Definitions are kept small and self-contained. They are non-static so the
// linker keeps them, and prefixed with nothing because the engine sources are
// compiled unmodified and call the standard names.

#include <stddef.h>
#include <stdint.h>
#include <stdarg.h>

void *memset(void *s, int c, size_t n) {
    unsigned char *p = (unsigned char *)s;
    uint32_t word = (uint32_t)c & 0xFF;
    word |= word << 8;
    word |= word << 16;
    while (n >= 4) {
        *(uint32_t *)p = word;
        p += 4;
        n -= 4;
    }
    while (n--) {
        *p++ = (unsigned char)c;
    }
    return s;
}

void *memcpy(void *dst, const void *src, size_t n) {
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    while (n--) {
        *d++ = *s++;
    }
    return dst;
}

void *memmove(void *dst, const void *src, size_t n) {
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    if (d == s || n == 0) {
        return dst;
    }
    if (d < s) {
        while (n--) {
            *d++ = *s++;
        }
    } else {
        d += n;
        s += n;
        while (n--) {
            *--d = *--s;
        }
    }
    return dst;
}

int memcmp(const void *a, const void *b, size_t n) {
    const unsigned char *pa = (const unsigned char *)a;
    const unsigned char *pb = (const unsigned char *)b;
    while (n--) {
        if (*pa != *pb) {
            return (int)*pa - (int)*pb;
        }
        pa++;
        pb++;
    }
    return 0;
}

size_t strlen(const char *s) {
    const char *p = s;
    while (*p) {
        p++;
    }
    return (size_t)(p - s);
}

int strcmp(const char *a, const char *b) {
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return (int)(unsigned char)*a - (int)(unsigned char)*b;
}

int strncmp(const char *a, const char *b, size_t n) {
    while (n && *a && *a == *b) {
        a++;
        b++;
        n--;
    }
    if (n == 0) {
        return 0;
    }
    return (int)(unsigned char)*a - (int)(unsigned char)*b;
}

char *strchr(const char *s, int c) {
    char ch = (char)c;
    while (*s) {
        if (*s == ch) {
            return (char *)s;
        }
        s++;
    }
    return (ch == '\0') ? (char *)s : NULL;
}

char *strcpy(char *dst, const char *src) {
    char *d = dst;
    while ((*d++ = *src++) != '\0') {
    }
    return dst;
}

char *strncpy(char *dst, const char *src, size_t n) {
    char *d = dst;
    while (n && *src) {
        *d++ = *src++;
        n--;
    }
    while (n--) {
        *d++ = '\0';
    }
    return dst;
}

int atoi(const char *s) {
    int sign = 1;
    int value = 0;
    while (*s == ' ' || *s == '\t' || *s == '\n') {
        s++;
    }
    if (*s == '-') {
        sign = -1;
        s++;
    } else if (*s == '+') {
        s++;
    }
    while (*s >= '0' && *s <= '9') {
        value = value * 10 + (*s - '0');
        s++;
    }
    return sign * value;
}

int abs(int value) {
    return (value < 0) ? -value : value;
}

long labs(long value) {
    return (value < 0) ? -value : value;
}

// A printf small enough for the engine's own diagnostics and for drawing a
// frame counter on screen. Supports %d, %u, %x, %s, %c, %% and "%0Nd" padding.
// The return value is the length that would have been written, like C.
static size_t emit_char(char *buf, size_t size, size_t pos, char c) {
    if (size != 0 && pos + 1 < size) {
        buf[pos] = c;
    }
    return pos + 1;
}

static size_t emit_padded(char *buf, size_t size, size_t pos, const char *text,
                          int text_len, int width, int zero) {
    int pad = (width > text_len) ? width - text_len : 0;
    for (int i = 0; i < pad; i++) {
        pos = emit_char(buf, size, pos, zero ? '0' : ' ');
    }
    for (int i = 0; i < text_len; i++) {
        pos = emit_char(buf, size, pos, text[i]);
    }
    return pos;
}

static int format_unsigned(char *out, unsigned int value, unsigned int base,
                           int upper) {
    const char *digits = upper ? "0123456789ABCDEF" : "0123456789abcdef";
    char reversed[16];
    int n = 0;
    if (value == 0) {
        reversed[n++] = '0';
    }
    while (value != 0) {
        reversed[n++] = digits[value % base];
        value /= base;
    }
    for (int i = 0; i < n; i++) {
        out[i] = reversed[n - 1 - i];
    }
    return n;
}

static int format_signed(char *out, int value) {
    int n = 0;
    unsigned int magnitude;
    if (value < 0) {
        out[n++] = '-';
        magnitude = (unsigned int)(-(value + 1)) + 1u;
    } else {
        magnitude = (unsigned int)value;
    }
    return n + format_unsigned(out + n, magnitude, 10, 0);
}

int vsnprintf(char *buf, size_t size, const char *fmt, va_list ap) {
    size_t pos = 0;
    while (*fmt) {
        char c = *fmt++;
        if (c != '%') {
            pos = emit_char(buf, size, pos, c);
            continue;
        }
        int zero = 0;
        int width = -1;
        if (*fmt == '0') {
            zero = 1;
            fmt++;
        }
        if (*fmt >= '0' && *fmt <= '9') {
            width = 0;
            while (*fmt >= '0' && *fmt <= '9') {
                width = width * 10 + (*fmt++ - '0');
            }
        }
        char tmp[24];
        int len = 0;
        char spec = *fmt++;
        switch (spec) {
            case 'd':
            case 'i': {
                len = format_signed(tmp, va_arg(ap, int));
                pos = emit_padded(buf, size, pos, tmp, len, width, zero);
                break;
            }
            case 'u': {
                len = format_unsigned(tmp, va_arg(ap, unsigned int), 10, 0);
                pos = emit_padded(buf, size, pos, tmp, len, width, zero);
                break;
            }
            case 'x':
            case 'X': {
                len = format_unsigned(tmp, va_arg(ap, unsigned int), 16,
                                      spec == 'X');
                pos = emit_padded(buf, size, pos, tmp, len, width, zero);
                break;
            }
            case 'c': {
                tmp[0] = (char)va_arg(ap, int);
                pos = emit_padded(buf, size, pos, tmp, 1, width, zero);
                break;
            }
            case 's': {
                const char *text = va_arg(ap, const char *);
                if (text == NULL) {
                    text = "(null)";
                }
                len = (int)strlen(text);
                pos = emit_padded(buf, size, pos, text, len, width, zero);
                break;
            }
            case '%': {
                pos = emit_char(buf, size, pos, '%');
                break;
            }
            case '\0': {
                fmt--;
                break;
            }
            default: {
                pos = emit_char(buf, size, pos, '%');
                pos = emit_char(buf, size, pos, spec);
                break;
            }
        }
    }
    if (size != 0) {
        size_t end = (pos < size) ? pos : size - 1;
        buf[end] = '\0';
    }
    return (int)pos;
}

int snprintf(char *buf, size_t size, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int result = vsnprintf(buf, size, fmt, ap);
    va_end(ap);
    return result;
}
