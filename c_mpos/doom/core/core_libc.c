// Minimal freestanding C library for a core blob.
//
// A core is linked at a fixed address and executed from flash: there is no
// libc and it cannot call the firmware, so everything doomgeneric expects from
// C lives here, on top of the core ABI. Deliberately small - only what the
// engine uses - and every host service (memory, files, console) goes through
// the ABI so it stays the host's policy.

#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "../../core_abi.h"

// Set by the port before anything else (see doom_core.c).
static const mpos_core_abi_t *s_abi;

// The newlib ctype macros index this table directly; it is filled in when the
// core starts, which keeps it in .bss (a core has no initialised data).
char _ctype_[257];

// newlib declares these as FILE pointers; our stdio ignores the stream. The
// engine only reads them, and the console goes through log() regardless.
void *stdout;
void *stderr;
void *stdin;

static int s_errno;
static int s_exit_requested;

static char ctype_flags(int c) {
    char flags = 0;
    if (c >= 'A' && c <= 'Z') {
        flags |= 0x01;  // _U
    }
    if (c >= 'a' && c <= 'z') {
        flags |= 0x02;  // _L
    }
    if (c >= '0' && c <= '9') {
        flags |= 0x04;  // _N
    }
    if (c == ' ' || (c >= '\t' && c <= '\r')) {
        flags |= 0x08;  // _S
    }
    if (c > ' ' && c < 0x7f && !(flags & 0x07)) {
        flags |= 0x20;  // _P
    }
    if (c >= 0 && (c < ' ' || c == 0x7f)) {
        flags |= 0x40;  // _C
    }
    if ((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')) {
        flags |= 0x80;  // _X
    }
    if (c == ' ' || c == '\t') {
        flags = (char)(flags | 0x00);
    }
    return flags;
}

void mpos_libc_init(const mpos_core_abi_t *abi) {
    s_abi = abi;
    _ctype_[0] = 0;
    for (int c = -1; c < 256; c++) {
        _ctype_[c + 1] = c < 0 ? 0 : ctype_flags(c);
    }
}

int mpos_libc_exit_requested(void) {
    return s_exit_requested;
}

// -- memory ------------------------------------------------------------------

// Every block carries its size, which is what makes realloc possible: the host
// only hands out buffers, it does not track them for us.
typedef struct {
    size_t size;
} block_header_t;

void *malloc(size_t size) {
    if (s_abi == NULL) {
        return NULL;
    }
    unsigned char *raw = (unsigned char *)s_abi->alloc(s_abi->host,
                                                       (uint32_t)(size + sizeof(block_header_t)));
    if (raw == NULL) {
        return NULL;
    }
    ((block_header_t *)raw)->size = size;
    return raw + sizeof(block_header_t);
}

void free(void *ptr) {
    // The host keeps every allocation alive until the core stops; the engine
    // allocates its zone once and never churns memory.
    (void)ptr;
}

void *calloc(size_t nmemb, size_t size) {
    size_t total = nmemb * size;
    void *ptr = malloc(total);
    if (ptr != NULL) {
        memset(ptr, 0, total);
    }
    return ptr;
}

void *realloc(void *ptr, size_t size) {
    if (ptr == NULL) {
        return malloc(size);
    }
    block_header_t *header = (block_header_t *)((unsigned char *)ptr - sizeof(block_header_t));
    if (size <= header->size) {
        return ptr;
    }
    void *replacement = malloc(size);
    if (replacement == NULL) {
        return NULL;
    }
    memcpy(replacement, ptr, header->size);
    return replacement;
}

// -- strings and memory blocks -----------------------------------------------

void *memcpy(void *dst, const void *src, size_t n) {
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    while (n-- > 0) {
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
        while (n-- > 0) {
            *d++ = *s++;
        }
    } else {
        d += n;
        s += n;
        while (n-- > 0) {
            *--d = *--s;
        }
    }
    return dst;
}

void *memset(void *dst, int c, size_t n) {
    unsigned char *d = (unsigned char *)dst;
    while (n-- > 0) {
        *d++ = (unsigned char)c;
    }
    return dst;
}

int memcmp(const void *a, const void *b, size_t n) {
    const unsigned char *pa = (const unsigned char *)a;
    const unsigned char *pb = (const unsigned char *)b;
    while (n-- > 0) {
        if (*pa != *pb) {
            return (int)*pa - (int)*pb;
        }
        pa++;
        pb++;
    }
    return 0;
}

size_t strlen(const char *s) {
    size_t len = 0;
    while (s[len] != '\0') {
        len++;
    }
    return len;
}

int strcmp(const char *a, const char *b) {
    while (*a && *a == *b) {
        a++;
        b++;
    }
    return (unsigned char)*a - (unsigned char)*b;
}

int strncmp(const char *a, const char *b, size_t n) {
    while (n-- > 0 && *a && *a == *b) {
        a++;
        b++;
    }
    if (n == (size_t)-1) {
        return 0;
    }
    return (unsigned char)*a - (unsigned char)*b;
}

char *strcpy(char *dst, const char *src) {
    char *out = dst;
    while ((*dst++ = *src++) != '\0') {
    }
    return out;
}

char *strncpy(char *dst, const char *src, size_t n) {
    size_t i = 0;
    for (; i < n && src[i] != '\0'; i++) {
        dst[i] = src[i];
    }
    for (; i < n; i++) {
        dst[i] = '\0';
    }
    return dst;
}

char *strcat(char *dst, const char *src) {
    strcpy(dst + strlen(dst), src);
    return dst;
}

static int lower(int c) {
    return (c >= 'A' && c <= 'Z') ? c - 'A' + 'a' : c;
}

int strcasecmp(const char *a, const char *b) {
    while (*a && lower((unsigned char)*a) == lower((unsigned char)*b)) {
        a++;
        b++;
    }
    return lower((unsigned char)*a) - lower((unsigned char)*b);
}

int strncasecmp(const char *a, const char *b, size_t n) {
    while (n-- > 0 && *a && lower((unsigned char)*a) == lower((unsigned char)*b)) {
        a++;
        b++;
    }
    if (n == (size_t)-1) {
        return 0;
    }
    return lower((unsigned char)*a) - lower((unsigned char)*b);
}

char *strchr(const char *s, int c) {
    for (;; s++) {
        if (*s == (char)c) {
            return (char *)s;
        }
        if (*s == '\0') {
            return NULL;
        }
    }
}

char *strrchr(const char *s, int c) {
    const char *found = NULL;
    for (;; s++) {
        if (*s == (char)c) {
            found = s;
        }
        if (*s == '\0') {
            return (char *)found;
        }
    }
}

char *strstr(const char *haystack, const char *needle) {
    const size_t len = strlen(needle);
    if (len == 0) {
        return (char *)haystack;
    }
    for (; *haystack; haystack++) {
        if (*haystack == *needle && strncmp(haystack, needle, len) == 0) {
            return (char *)haystack;
        }
    }
    return NULL;
}

int toupper(int c) {
    return (c >= 'a' && c <= 'z') ? c - 'a' + 'A' : c;
}

int tolower(int c) {
    return lower(c);
}

char *strdup(const char *s) {
    const size_t len = strlen(s) + 1;
    char *copy = (char *)malloc(len);
    if (copy != NULL) {
        memcpy(copy, s, len);
    }
    return copy;
}

// -- numbers -----------------------------------------------------------------

int abs(int value) {
    return value < 0 ? -value : value;
}

long labs(long value) {
    return value < 0 ? -value : value;
}

double fabs(double value) {
    return value < 0 ? -value : value;
}

int atoi(const char *s) {
    int sign = 1;
    int value = 0;
    while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r') {
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

double atof(const char *s) {
    // The engine only reads a couple of config floats; integers cover them.
    return (double)atoi(s);
}

// Doom parses its config with sscanf ("%i", "%x", " 0x%x", " 0%o").
int sscanf(const char *s, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int conversions = 0;
    while (*fmt) {
        if (*fmt == ' ') {
            while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r') {
                s++;
            }
            fmt++;
            continue;
        }
        if (*fmt != '%') {
            if (*s != *fmt) {
                break;
            }
            s++;
            fmt++;
            continue;
        }
        fmt++;
        int base = 10;
        if (*fmt == 'i') {
            base = 0;  // autodetect: 0x -> 16, 0 -> 8
            fmt++;
        } else if (*fmt == 'x' || *fmt == 'X') {
            base = 16;
            fmt++;
        } else if (*fmt == 'o') {
            base = 8;
            fmt++;
        } else if (*fmt == 'd' || *fmt == 'u') {
            fmt++;
        }
        while (*s == ' ' || *s == '\t') {
            s++;
        }
        int sign = 1;
        if (*s == '-') {
            sign = -1;
            s++;
        }
        int explicit_base = base != 0;
        if (!explicit_base && s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
            base = 16;
            s += 2;
        } else if (!explicit_base && s[0] == '0') {
            base = 8;
        } else if (!explicit_base) {
            base = 10;
        }
        int value = 0;
        int digits = 0;
        for (;;) {
            int digit;
            const char c = *s;
            if (c >= '0' && c <= '9') {
                digit = c - '0';
            } else if (c >= 'a' && c <= 'f') {
                digit = c - 'a' + 10;
            } else if (c >= 'A' && c <= 'F') {
                digit = c - 'A' + 10;
            } else {
                break;
            }
            if (digit >= base) {
                break;
            }
            value = value * base + digit;
            digits++;
            s++;
        }
        if (digits == 0) {
            break;
        }
        int *out = va_arg(ap, int *);
        if (out != NULL) {
            *out = sign * value;
        }
        conversions++;
    }
    va_end(ap);
    return conversions;
}

// -- stdio -------------------------------------------------------------------

// Read-only stdio over the host's file reader. The engine opens the IWAD, reads
// its directory and lumps, and never writes (savegames are out of scope).
#define CORE_FILE_SLOTS 4
#define CORE_FILE_PATH 128

typedef struct {
    int used;
    long offset;
    long size;
    char path[CORE_FILE_PATH];
} core_file_t;

static core_file_t s_files[CORE_FILE_SLOTS];

void *fopen(const char *path, const char *mode) {
    if (s_abi == NULL || path == NULL) {
        return NULL;
    }
    if (mode != NULL && mode[0] != 'r') {
        return NULL;  // the flash-resident core has no writable files
    }
    if (strlen(path) >= CORE_FILE_PATH) {
        return NULL;
    }
    for (int i = 0; i < CORE_FILE_SLOTS; i++) {
        core_file_t *file = &s_files[i];
        if (file->used) {
            continue;
        }
        const int size = s_abi->file_size(s_abi->host, path);
        if (size < 0) {
            return NULL;
        }
        file->used = 1;
        file->offset = 0;
        file->size = size;
        strcpy(file->path, path);
        return file;
    }
    return NULL;
}

int fclose(void *stream) {
    core_file_t *file = (core_file_t *)stream;
    if (file == NULL) {
        return -1;
    }
    file->used = 0;
    return 0;
}

size_t fread(void *ptr, size_t size, size_t nmemb, void *stream) {
    core_file_t *file = (core_file_t *)stream;
    if (file == NULL || !file->used || size == 0 || nmemb == 0) {
        return 0;
    }
    size_t bytes = size * nmemb;
    if (file->offset >= file->size) {
        return 0;
    }
    if ((long)bytes > file->size - file->offset) {
        bytes = (size_t)(file->size - file->offset);
        bytes -= bytes % size;
    }
    const int got = s_abi->read_file(s_abi->host, file->path,
                                     (uint32_t)file->offset, ptr, (uint32_t)bytes);
    if (got <= 0) {
        return 0;
    }
    file->offset += got;
    return (size_t)got / size;
}

size_t fwrite(const void *ptr, size_t size, size_t nmemb, void *stream) {
    (void)ptr;
    (void)size;
    (void)nmemb;
    (void)stream;
    return 0;
}

int fseek(void *stream, long offset, int whence) {
    core_file_t *file = (core_file_t *)stream;
    if (file == NULL || !file->used) {
        return -1;
    }
    long target = offset;
    if (whence == 1) {
        target = file->offset + offset;
    } else if (whence == 2) {
        target = file->size + offset;
    }
    if (target < 0) {
        return -1;
    }
    file->offset = target;
    return 0;
}

long ftell(void *stream) {
    core_file_t *file = (core_file_t *)stream;
    if (file == NULL || !file->used) {
        return -1;
    }
    return file->offset;
}

int remove(const char *path) {
    (void)path;
    return -1;
}

int rename(const char *from, const char *to) {
    (void)from;
    (void)to;
    return -1;
}

int mkdir(const char *path, int mode) {
    (void)path;
    (void)mode;
    return -1;
}

int system(const char *command) {
    (void)command;
    return -1;
}

int chdir(const char *path) {
    (void)path;
    return -1;
}

char *getcwd(char *buf, size_t size) {
    if (buf != NULL && size > 1) {
        buf[0] = '/';
        buf[1] = '\0';
        return buf;
    }
    return NULL;
}

// -- process -----------------------------------------------------------------

void exit(int status) {
    // I_Error() ends here. There is nothing to unwind in a core, so record it
    // and let tick() become a no-op instead of taking the device down.
    (void)status;
    s_exit_requested = 1;
}

int *__errno(void) {
    return &s_errno;
}

int *__errno_location(void) {
    return &s_errno;
}

struct _reent;

struct _reent *__getreent(void) {
    // Only reached by newlib functions we replace; a word of storage is enough.
    static long reent_stub[16];
    return (struct _reent *)reent_stub;
}
