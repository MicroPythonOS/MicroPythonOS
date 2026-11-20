// Console for a core blob.
//
// mpos_printf.c is shared between the native module and the flash-resident
// core. A native module gets MicroPython's mp_print_t; a core cannot call
// MicroPython, so it writes through the ABI's log() callback instead. Both
// satisfy the same two-symbol interface, which is all the formatter uses.
#ifndef MPOS_CORE_CONSOLE_H
#define MPOS_CORE_CONSOLE_H

#include <stddef.h>

typedef struct {
    void (*print_strn)(void *data, const char *str, size_t len);
    void *data;
} mp_print_t;

void mpos_core_console_write(void *data, const char *str, size_t len);

extern const mp_print_t mp_plat_print;

#endif  // MPOS_CORE_CONSOLE_H
