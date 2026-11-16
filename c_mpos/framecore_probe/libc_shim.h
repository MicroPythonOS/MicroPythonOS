// Declarations for libc_shim.c.
//
// A natmod is compiled without <string.h>/<stdlib.h>/<stdio.h> being usable for
// these functions (they are not linked), so the shim declares them itself. The
// signatures are the standard ones on purpose: engine sources that include the
// real headers still link against these definitions.

#ifndef FRAMECORE_LIBC_SHIM_H
#define FRAMECORE_LIBC_SHIM_H

#include <stddef.h>
#include <stdarg.h>

void *memset(void *s, int c, size_t n);
void *memcpy(void *dst, const void *src, size_t n);
void *memmove(void *dst, const void *src, size_t n);
int memcmp(const void *a, const void *b, size_t n);
size_t strlen(const char *s);
int strcmp(const char *a, const char *b);
int strncmp(const char *a, const char *b, size_t n);
char *strchr(const char *s, int c);
char *strcpy(char *dst, const char *src);
char *strncpy(char *dst, const char *src, size_t n);
int atoi(const char *s);
int abs(int value);
long labs(long value);
int vsnprintf(char *buf, size_t size, const char *fmt, va_list ap);
int snprintf(char *buf, size_t size, const char *fmt, ...);

#endif
