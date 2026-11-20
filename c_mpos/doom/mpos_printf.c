// printf family for the Doom port.
//
// MicroPython's own mp_vprintf supports %d/%u/%x/%s/%c/%p only. Doom is 1990s
// C: it uses %i (144 times), %o, %f, %02i, % li, %.8s, and M_snprintf's return
// value for savegame truncation checks. Delegating to mp_vprintf silently
// printed the format character instead of the value ("joystick_buttoni"
// instead of "joystick_button0"), so the formatting happens here.

// A core blob has no MicroPython to call, so it gets the same formatter with a
// console that writes through the core ABI (see core/core_console.h).
#ifdef MPOS_CORE
#include "core/core_console.h"
#else
#include "py/dynruntime.h"
#endif

#include <stddef.h>
#include <stdarg.h>
#include <stdint.h>

typedef void (*mpos_emit_t)(void *ctx, char c);

typedef struct {
    char *buf;
    size_t size;
    size_t pos;
} mpos_str_ctx_t;

static void emit_str(void *ctx, char c) {
    mpos_str_ctx_t *out = (mpos_str_ctx_t *)ctx;
    if (out->pos + 1 < out->size) {
        out->buf[out->pos] = c;
    }
    out->pos++;
}

typedef struct {
    const mp_print_t *print;
} mpos_console_ctx_t;

static void emit_console(void *ctx, char c) {
    mpos_console_ctx_t *out = (mpos_console_ctx_t *)ctx;
    out->print->print_strn(out->print->data, &c, 1);
}

static void emit_repeat(mpos_emit_t emit, void *ctx, char c, int count) {
    for (int i = 0; i < count; i++) {
        emit(ctx, c);
    }
}

static int utoa(unsigned long long value, unsigned int base, int upper,
                char *out) {
    const char *digits = upper ? "0123456789ABCDEF" : "0123456789abcdef";
    char reversed[32];
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

// Fixed/scientific notation for %f/%e/%g. Enough for Doom's diagnostics.
static int ftoa(double value, int precision, int upper, int scientific,
                char *out) {
    int n = 0;
    int exponent = 0;
    const char exponent_char = upper ? 'E' : 'e';
    if (precision < 0) {
        precision = 6;
    }
    if (precision > 9) {
        precision = 9;
    }
    if (value != value) {  // NaN
        const char *nan = upper ? "NAN" : "nan";
        for (int i = 0; i < 3; i++) {
            out[n++] = nan[i];
        }
        return n;
    }
    if (value < 0.0) {
        out[n++] = '-';
        value = -value;
    }
    if (scientific) {
        while (value >= 10.0) {
            value /= 10.0;
            exponent++;
        }
        while (value >= 1e-300 && value < 1.0) {
            value *= 10.0;
            exponent--;
        }
    }
    unsigned long long scale = 1;
    for (int i = 0; i < precision; i++) {
        scale *= 10;
    }
    double scaled = value * (double)scale + 0.5;
    unsigned long long whole = (unsigned long long)scaled;
    char digits[32];
    int count = utoa(whole, 10, 0, digits);
    if (count <= precision) {
        int pad = precision + 1 - count;
        for (int i = 0; i < pad; i++) {
            out[n++] = '0';
        }
        count += pad;
    }
    for (int i = 0; i < count; i++) {
        if (precision && i == count - precision) {
            out[n++] = '.';
        }
        out[n++] = digits[i];
    }
    if (precision == 0) {
        // "1." style output is avoided: the caller asked for none.
    }
    if (scientific) {
        out[n++] = exponent_char;
        out[n++] = exponent < 0 ? '-' : '+';
        char exp_digits[8];
        int exp_len = utoa((unsigned long long)(exponent < 0 ? -exponent : exponent),
                           10, 0, exp_digits);
        if (exp_len < 2) {
            out[n++] = '0';
        }
        for (int i = 0; i < exp_len; i++) {
            out[n++] = exp_digits[i];
        }
    }
    return n;
}

static int mpos_vformat(mpos_emit_t emit, void *ctx, const char *fmt,
                        va_list ap) {
    int written = 0;
    while (*fmt) {
        const char c = *fmt++;
        if (c != '%') {
            emit(ctx, c);
            written++;
            continue;
        }

        int left = 0;
        int zero = 0;
        int plus = 0;
        int space = 0;
        int alternate = 0;
        for (;;) {
            if (*fmt == '-') {
                left = 1;
            } else if (*fmt == '0') {
                zero = 1;
            } else if (*fmt == '+') {
                plus = 1;
            } else if (*fmt == ' ') {
                space = 1;
            } else if (*fmt == '#') {
                alternate = 1;
            } else {
                break;
            }
            fmt++;
        }

        int width = 0;
        if (*fmt == '*') {
            width = va_arg(ap, int);
            if (width < 0) {
                left = 1;
                width = -width;
            }
            fmt++;
        } else {
            while (*fmt >= '0' && *fmt <= '9') {
                width = width * 10 + (*fmt++ - '0');
            }
        }

        int precision = -1;
        if (*fmt == '.') {
            fmt++;
            precision = 0;
            if (*fmt == '*') {
                precision = va_arg(ap, int);
                fmt++;
            } else {
                while (*fmt >= '0' && *fmt <= '9') {
                    precision = precision * 10 + (*fmt++ - '0');
                }
            }
        }

        int is_long = 0;
        if (*fmt == 'l') {
            fmt++;
            is_long = 1;
            if (*fmt == 'l') {
                fmt++;
                is_long = 2;
            }
        } else if (*fmt == 'h') {
            fmt++;
            if (*fmt == 'h') {
                fmt++;
            }
        } else if (*fmt == 'z' || *fmt == 'j' || *fmt == 't') {
            fmt++;
            is_long = sizeof(size_t) > sizeof(int);
        }

        char text[64];
        int len = 0;
        int negative = 0;
        int numeric = 0;
        const char *spec = fmt - 1;

        switch (*fmt++) {
            case 'd':
            case 'i': {
                long long value;
                if (is_long == 2) {
                    value = va_arg(ap, long long);
                } else if (is_long == 1) {
                    value = va_arg(ap, long);
                } else {
                    value = va_arg(ap, int);
                }
                if (value < 0) {
                    negative = 1;
                    value = -value;
                }
                len = utoa((unsigned long long)value, 10, 0, text);
                numeric = 1;
                break;
            }
            case 'u':
                len = utoa(is_long ? va_arg(ap, unsigned long)
                                   : (unsigned long)va_arg(ap, unsigned int),
                           10, 0, text);
                numeric = 1;
                break;
            case 'o':
                len = utoa(va_arg(ap, unsigned int), 8, 0, text);
                numeric = 1;
                break;
            case 'x':
            case 'X':
                len = utoa(va_arg(ap, unsigned int), 16, *spec == 'X', text);
                numeric = 1;
                break;
            case 'p': {
                unsigned long value = (unsigned long)(uintptr_t)va_arg(ap, void *);
                text[len++] = '0';
                text[len++] = 'x';
                char digits[24];
                int n = utoa(value, 16, 0, digits);
                for (int i = 0; i < n; i++) {
                    text[len++] = digits[i];
                }
                width = 0;
                zero = 0;
                break;
            }
            case 'c':
                text[len++] = (char)va_arg(ap, int);
                break;
            case 's': {
                const char *s = va_arg(ap, const char *);
                if (s == NULL) {
                    s = "(null)";
                }
                int max = 0;
                while (s[max] && (precision < 0 || max < precision)) {
                    max++;
                }
                // A path or a message can be longer than `text`, so emit it
                // instead of copying it into that fixed buffer.
                const int padding = (width > max) ? width - max : 0;
                if (!left) {
                    emit_repeat(emit, ctx, ' ', padding);
                }
                for (int i = 0; i < max; i++) {
                    emit(ctx, s[i]);
                }
                if (left) {
                    emit_repeat(emit, ctx, ' ', padding);
                }
                written += max + padding;
                continue;
            }
            case 'f':
            case 'F':
            case 'e':
            case 'E':
            case 'g':
            case 'G': {
                double value = va_arg(ap, double);
                const int scientific = (*spec == 'e' || *spec == 'E');
                len = ftoa(value, precision, *spec == 'F' || *spec == 'E' ||
                           *spec == 'G', scientific, text);
                if (text[0] == '-') {
                    negative = 1;
                    len--;
                    for (int i = 0; i < len; i++) {
                        text[i] = text[i + 1];
                    }
                }
                break;
            }
            case '%':
                emit(ctx, '%');
                written++;
                continue;
            case 'n':
                // Doom passes %n nowhere that matters; consume the pointer.
                (void)va_arg(ap, void *);
                continue;
            case '\0':
                fmt--;
                continue;
            default: {
                emit(ctx, '%');
                emit(ctx, *spec);
                written += 2;
                continue;
            }
        }

        char sign = 0;
        if (negative) {
            sign = '-';
        } else if (plus) {
            sign = '+';
        } else if (space) {
            sign = ' ';
        }
        // C's precision on an integer is a minimum number of digits ("%.3d"
        // of 33 is "033"), and it turns off the '0' flag.
        int extra_zeros = 0;
        if (numeric && precision > len) {
            extra_zeros = precision - len;
        }
        if (precision >= 0) {
            zero = 0;
        }
        const int total = len + extra_zeros + (sign ? 1 : 0);
        const int padding = (width > total) ? width - total : 0;
        if (!left && !zero) {
            emit_repeat(emit, ctx, ' ', padding);
        }
        if (sign) {
            emit(ctx, sign);
        }
        if (!left && zero) {
            emit_repeat(emit, ctx, '0', padding);
        }
        emit_repeat(emit, ctx, '0', extra_zeros);
        for (int i = 0; i < len; i++) {
            emit(ctx, text[i]);
        }
        if (left) {
            emit_repeat(emit, ctx, ' ', padding);
        }
        written += total + padding;
    }
    return written;
}

int vsnprintf(char *buf, size_t size, const char *fmt, va_list ap) {
    mpos_str_ctx_t ctx = { buf, size, 0 };
    int result = mpos_vformat(emit_str, &ctx, fmt, ap);
    if (size != 0) {
        size_t end = ctx.pos < size ? ctx.pos : size - 1;
        buf[end] = '\0';
    }
    return result;
}

int snprintf(char *buf, size_t size, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int result = vsnprintf(buf, size, fmt, ap);
    va_end(ap);
    return result;
}

int vsprintf(char *buf, const char *fmt, va_list ap) {
    return vsnprintf(buf, (size_t)-1 / 2, fmt, ap);
}

int sprintf(char *buf, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int result = vsprintf(buf, fmt, ap);
    va_end(ap);
    return result;
}

int vprintf(const char *fmt, va_list ap) {
    mpos_console_ctx_t ctx = { &mp_plat_print };
    return mpos_vformat(emit_console, &ctx, fmt, ap);
}

int printf(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int result = vprintf(fmt, ap);
    va_end(ap);
    return result;
}

// The engine's file streams all resolve to the console: no savegames yet.
int vfprintf(void *stream, const char *fmt, va_list ap) {
    (void)stream;
    return vprintf(fmt, ap);
}

int fprintf(void *stream, const char *fmt, ...) {
    (void)stream;
    va_list ap;
    va_start(ap, fmt);
    int result = vprintf(fmt, ap);
    va_end(ap);
    return result;
}

int puts(const char *s) {
    mpos_console_ctx_t ctx = { &mp_plat_print };
    while (*s) {
        emit_console(&ctx, *s++);
    }
    emit_console(&ctx, '\n');
    return 0;
}

int fputs(const char *s, void *stream) {
    (void)stream;
    mpos_console_ctx_t ctx = { &mp_plat_print };
    while (*s) {
        emit_console(&ctx, *s++);
    }
    return 0;
}

int putchar(int c) {
    const char ch = (char)c;
    mp_plat_print.print_strn(mp_plat_print.data, &ch, 1);
    return c;
}

int fflush(void *stream) {
    (void)stream;
    return 0;
}
