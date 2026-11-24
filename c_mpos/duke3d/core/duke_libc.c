// The C library a Duke3D core gets.
//
// A core is linked at fixed addresses and runs from flash, so it cannot call
// the firmware's libc. Everything the engine expects is here, on top of the
// core ABI: a first-fit heap over the RAM the host lends it, read-only files
// served by the host's reader (the GRP lives in a host buffer and is never
// copied into the core), the string/parse helpers, and stubs for the desktop
// services a badge has none of (directories, wall clock, save files).
//
// Duke is 1990s C and touches more of libc than Doom did, but it uses *no*
// floating-point library: its maths is the Build engine's fixed point, and the
// only doubles are in config/DEF parsing (atof) and printf.

#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <stdarg.h>
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <dirent.h>
#include <time.h>

#include "../../core_abi.h"
#include "duke_libc.h"
#include "duke_platform.h"

static const mpos_core_abi_t *s_abi;

// The newlib ctype macros index this table directly (index c+1).
char _ctype_[257];

static int s_errno;
static int s_exit_requested;

static char ctype_flags(int c) {
    char flags = 0;
    if (c >= 'A' && c <= 'Z') flags |= 0x01;  // _U
    if (c >= 'a' && c <= 'z') flags |= 0x02;  // _L
    if (c >= '0' && c <= '9') flags |= 0x04;  // _N
    if (c == ' ' || (c >= '\t' && c <= '\r')) flags |= 0x08;  // _S
    if (c > ' ' && c < 0x7f && !(flags & 0x07)) flags |= 0x20;  // _P
    if (c >= 0 && (c < ' ' || c == 0x7f)) flags |= 0x40;  // _C
    if ((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')
            || (c >= 'A' && c <= 'F')) flags |= 0x80;  // _X
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

// -- heap --------------------------------------------------------------------
//
// One contiguous arena that the host allocates through abi->alloc(). Blocks
// carry a size and a free flag; free() coalesces neighbours, because Duke
// releases tile caches and lookups as it changes resolution.

typedef struct heap_block {
    size_t size;                    // payload bytes
    int free;
    struct heap_block *next;
} heap_block_t;

#define HEAP_ALIGN 8
#define HEAP_HDR ((sizeof(heap_block_t) + HEAP_ALIGN - 1) & ~(size_t)(HEAP_ALIGN - 1))

static heap_block_t *s_heap;
static size_t s_heap_size;
static size_t s_heap_used;

void mpos_heap_init(void *base, size_t size) {
    uintptr_t start = ((uintptr_t)base + HEAP_ALIGN - 1) & ~(uintptr_t)(HEAP_ALIGN - 1);
    size_t lost = (size_t)(start - (uintptr_t)base);
    if (size <= lost + HEAP_HDR * 2) {
        s_heap = NULL;
        return;
    }
    s_heap = (heap_block_t *)start;
    s_heap->size = size - lost - HEAP_HDR;
    s_heap->free = 1;
    s_heap->next = NULL;
    s_heap_size = s_heap->size;
    s_heap_used = 0;
}

size_t mpos_heap_free(void) {
    size_t free_bytes = 0;
    for (heap_block_t *block = s_heap; block != NULL; block = block->next) {
        if (block->free) {
            free_bytes += block->size;
        }
    }
    return free_bytes;
}

size_t mpos_heap_largest(void) {
    size_t largest = 0;
    for (heap_block_t *block = s_heap; block != NULL; block = block->next) {
        if (block->free && block->size > largest) {
            largest = block->size;
        }
    }
    return largest;
}

void *malloc(size_t size) {
    if (s_heap == NULL || size == 0) {
        return NULL;
    }
    size = (size + HEAP_ALIGN - 1) & ~(size_t)(HEAP_ALIGN - 1);
    for (heap_block_t *block = s_heap; block != NULL; block = block->next) {
        if (!block->free || block->size < size) {
            continue;
        }
        // Split when the remainder can hold a header and a useful block.
        if (block->size >= size + HEAP_HDR + HEAP_ALIGN) {
            heap_block_t *rest = (heap_block_t *)((uintptr_t)(block + 1) + size);
            rest->size = block->size - size - HEAP_HDR;
            rest->free = 1;
            rest->next = block->next;
            block->next = rest;
            block->size = size;
        }
        block->free = 0;
        s_heap_used += block->size;
        return (void *)(block + 1);
    }
    return NULL;
}

void free(void *ptr) {
    if (ptr == NULL || s_heap == NULL) {
        return;
    }
    heap_block_t *block = (heap_block_t *)ptr - 1;
    if (block->free) {
        return;  // double free: ignore rather than corrupt the list
    }
    block->free = 1;
    s_heap_used -= block->size;
    // Coalesce forward, then from the start once.
    for (heap_block_t *b = s_heap; b != NULL; b = b->next) {
        while (b->free && b->next != NULL && b->next->free) {
            b->size += HEAP_HDR + b->next->size;
            b->next = b->next->next;
        }
    }
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
    if (size == 0) {
        free(ptr);
        return NULL;
    }
    heap_block_t *block = (heap_block_t *)ptr - 1;
    if (block->size >= size) {
        return ptr;
    }
    void *replacement = malloc(size);
    if (replacement == NULL) {
        return NULL;
    }
    memcpy(replacement, ptr, block->size);
    free(ptr);
    return replacement;
}

size_t heap_caps_get_free_size(unsigned caps) {
    (void)caps;
    return mpos_heap_free();
}

size_t heap_caps_get_largest_free_block(unsigned caps) {
    (void)caps;
    return mpos_heap_largest();
}

void *heap_caps_malloc(size_t size, unsigned caps) {
    (void)caps;
    return malloc(size);
}

void heap_caps_free(void *ptr) {
    free(ptr);
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

void *memchr(const void *s, int c, size_t n) {
    const unsigned char *p = (const unsigned char *)s;
    while (n-- > 0) {
        if (*p == (unsigned char)c) {
            return (void *)p;
        }
        p++;
    }
    return NULL;
}

size_t strlen(const char *s) {
    size_t len = 0;
    while (s[len] != '\0') {
        len++;
    }
    return len;
}

size_t strnlen(const char *s, size_t n) {
    size_t len = 0;
    while (len < n && s[len] != '\0') {
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

char *strncat(char *dst, const char *src, size_t n) {
    char *out = dst + strlen(dst);
    while (n-- > 0 && *src) {
        *out++ = *src++;
    }
    *out = '\0';
    return dst;
}

size_t strlcpy(char *dst, const char *src, size_t size) {
    size_t len = strlen(src);
    if (size > 0) {
        size_t copy = len < size - 1 ? len : size - 1;
        memcpy(dst, src, copy);
        dst[copy] = '\0';
    }
    return len;
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

size_t strspn(const char *s, const char *accept) {
    size_t n = 0;
    while (s[n] && strchr(accept, s[n]) != NULL) {
        n++;
    }
    return n;
}

size_t strcspn(const char *s, const char *reject) {
    size_t n = 0;
    while (s[n] && strchr(reject, s[n]) == NULL) {
        n++;
    }
    return n;
}

char *strpbrk(const char *s, const char *accept) {
    while (*s) {
        if (strchr(accept, *s) != NULL) {
            return (char *)s;
        }
        s++;
    }
    return NULL;
}

char *strtok(char *s, const char *delim) {
    static char *next;
    if (s == NULL) {
        s = next;
    }
    if (s == NULL) {
        return NULL;
    }
    s += strspn(s, delim);
    if (*s == '\0') {
        next = NULL;
        return NULL;
    }
    char *end = s + strcspn(s, delim);
    if (*end == '\0') {
        next = NULL;
    } else {
        *end = '\0';
        next = end + 1;
    }
    return s;
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

int strcoll(const char *a, const char *b) {
    return strcmp(a, b);
}

// -- numbers -----------------------------------------------------------------

int abs(int value) { return value < 0 ? -value : value; }
long labs(long value) { return value < 0 ? -value : value; }
int atoi(const char *s) { return (int)strtol(s, NULL, 10); }
long atol(const char *s) { return strtol(s, NULL, 10); }

long strtol(const char *s, char **endptr, int base) {
    const char *p = s;
    int sign = 1;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r' || *p == '\f') {
        p++;
    }
    if (*p == '-') {
        sign = -1;
        p++;
    } else if (*p == '+') {
        p++;
    }
    if (base == 0) {
        if (p[0] == '0' && (p[1] == 'x' || p[1] == 'X')) {
            base = 16;
            p += 2;
        } else if (p[0] == '0') {
            base = 8;
        } else {
            base = 10;
        }
    } else if (base == 16 && p[0] == '0' && (p[1] == 'x' || p[1] == 'X')) {
        p += 2;
    }
    long value = 0;
    const char *start = p;
    for (;;) {
        int digit;
        const char c = *p;
        if (c >= '0' && c <= '9') {
            digit = c - '0';
        } else if (c >= 'a' && c <= 'z') {
            digit = c - 'a' + 10;
        } else if (c >= 'A' && c <= 'Z') {
            digit = c - 'A' + 10;
        } else {
            break;
        }
        if (digit >= base) {
            break;
        }
        value = value * base + digit;
        p++;
    }
    if (endptr != NULL) {
        *endptr = (char *)(p == start ? s : p);
    }
    return sign * value;
}

unsigned long strtoul(const char *s, char **endptr, int base) {
    return (unsigned long)strtol(s, endptr, base);
}

double atof(const char *s) {
    // CON/DEF numbers are mostly integers; handle a decimal fraction too so a
    // scriptere's "1.5" is not silently 1.
    const char *p = s;
    int sign = 1;
    double value = 0.0;
    while (*p == ' ' || *p == '\t') p++;
    if (*p == '-') { sign = -1; p++; } else if (*p == '+') { p++; }
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
    return sign * value;
}

// Duke parses its CON files with sscanf("\"%[^\"]\""), and the network menu
// with "%d.%d.%d.%d". That is the whole surface; no more is implemented.
int sscanf(const char *s, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int conversions = 0;
    while (*fmt) {
        if (*fmt == ' ') {
            while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r') s++;
            fmt++;
            continue;
        }
        if (*fmt != '%') {
            if (*s != *fmt) break;
            s++;
            fmt++;
            continue;
        }
        fmt++;
        if (*fmt == '[') {
            // %[^"] - a run of bytes up to the first inside the bracket set.
            int negate = 0;
            fmt++;
            if (*fmt == '^') { negate = 1; fmt++; }
            const char *set = fmt;
            while (*fmt && *fmt != ']') fmt++;
            const char *set_end = fmt;
            if (*fmt == ']') fmt++;
            char *out = va_arg(ap, char *);
            int n = 0;
            while (*s) {
                int in = 0;
                for (const char *q = set; q < set_end; q++) {
                    if (*q == *s) { in = 1; break; }
                }
                if (in == negate) break;
                out[n++] = *s++;
            }
            out[n] = '\0';
            conversions++;
            continue;
        }
        int base = 10;
        if (*fmt == 'd' || *fmt == 'u' || *fmt == 'i') {
            base = (*fmt == 'i') ? 0 : 10;
            fmt++;
        } else if (*fmt == 'x' || *fmt == 'X') {
            base = 16;
            fmt++;
        } else if (*fmt == 'c') {
            char *out = va_arg(ap, char *);
            *out = *s++;
            fmt++;
            conversions++;
            continue;
        } else if (*fmt == 'f') {
            double *out = va_arg(ap, double *);
            *out = atof(s);
            while (*s && *s != ' ') s++;
            fmt++;
            conversions++;
            continue;
        } else {
            break;
        }
        while (*s == ' ' || *s == '\t') s++;
        char *end = NULL;
        long value = strtol(s, &end, base);
        if (end == s) break;
        s = end;
        int *out = va_arg(ap, int *);
        if (out != NULL) *out = (int)value;
        conversions++;
    }
    va_end(ap);
    return conversions;
}

// -- stdio -------------------------------------------------------------------
//
// A file is an index into this table. Reads go to the host's file reader; the
// only writable files the engine opens are its config and savegames, whose
// contents are discarded (there is nowhere to persist them on a core session).
// Returning a live stream keeps the engine's error paths quiet.

#define CORE_FILE_SLOTS 8
#define CORE_FILE_PATH 128

typedef struct {
    int used;
    int writable;
    long offset;
    long size;
    char path[CORE_FILE_PATH];
} core_file_t;

static core_file_t s_files[CORE_FILE_SLOTS];

static core_file_t *file_for(int fd) {
    if (fd < 0 || fd >= CORE_FILE_SLOTS) return NULL;
    return s_files[fd].used ? &s_files[fd] : NULL;
}

// The host's file callbacks take a MicroPython string; a DOS filename with a
// high-bit byte would raise UnicodeError inside the ABI call (and surface as a
// failed frame). Paths are made ASCII first, for the ABI and for the table.
static void clean_path(const char *path, char *out) {
    int i = 0;
    for (; path[i] != '\0' && i < CORE_FILE_PATH - 1; i++) {
        out[i] = (unsigned char)path[i] >= 0x80 ? '?' : path[i];
    }
    out[i] = '\0';
}

static core_file_t *file_open(const char *path, int writable) {
    if (s_abi == NULL || path == NULL) return NULL;
    if (strlen(path) >= CORE_FILE_PATH) return NULL;
    char clean[CORE_FILE_PATH];
    clean_path(path, clean);
    for (int i = 0; i < CORE_FILE_SLOTS; i++) {
        core_file_t *file = &s_files[i];
        if (file->used) continue;
        int size = writable ? 0 : s_abi->file_size(s_abi->host, clean);
        if (!writable && size < 0) return NULL;
        file->used = 1;
        file->writable = writable;
        file->offset = 0;
        file->size = size;
        strcpy(file->path, clean);
        return file;
    }
    return NULL;
}

static void file_close(core_file_t *file) {
    if (file != NULL) file->used = 0;
}

int open(const char *path, int flags, ...) {
    const int writable = (flags & 3) != 0;  // O_WRONLY|O_RDWR
    core_file_t *file = file_open(path, writable);
    return file == NULL ? -1 : (int)(file - s_files);
}

int close(int fd) {
    core_file_t *file = file_for(fd);
    if (file == NULL) return -1;
    file_close(file);
    return 0;
}

ssize_t read(int fd, void *buf, size_t count) {
    core_file_t *file = file_for(fd);
    if (file == NULL || file->writable || buf == NULL) return -1;
    // A start-up that reads hundreds of lumps would otherwise keep the CPU for
    // seconds; the host turns the sentinel into a scheduler yield. In the game
    // every eighth read is enough to keep the idle task fed without making a
    // cache-miss burst pay a tick per tile.
    {
        static unsigned read_count;
        if (!duke_platform_running() || ((++read_count & 7u) == 0)) {
            duke_platform_idle();
        }
    }
    if (file->offset >= file->size) return 0;
    size_t left = (size_t)(file->size - file->offset);
    if (count > left) count = left;
    int got = s_abi->read_file(s_abi->host, file->path,
                               (uint32_t)file->offset, buf, (uint32_t)count);
    if (got <= 0) return got < 0 ? -1 : 0;
    file->offset += got;
    return got;
}

ssize_t write(int fd, const void *buf, size_t count) {
    core_file_t *file = file_for(fd);
    (void)buf;
    if (file == NULL || !file->writable) return -1;
    file->offset += (long)count;
    if (file->offset > file->size) file->size = file->offset;
    return (long)count;
}

off_t lseek(int fd, off_t offset, int whence) {
    core_file_t *file = file_for(fd);
    if (file == NULL) return -1;
    long target = offset;
    if (whence == 1) target = file->offset + offset;
    else if (whence == 2) target = file->size + offset;
    if (target < 0) return -1;
    file->offset = target;
    return target;
}

int stat(const char *path, struct stat *buf) {
    (void)path;
    (void)buf;
    return -1;
}

int fstat(int fd, struct stat *buf) {
    core_file_t *file = file_for(fd);
    if (file == NULL) {
        return -1;
    }
    if (buf != NULL) {
        memset(buf, 0, sizeof(*buf));
        buf->st_size = file->size;
        buf->st_mode = 0100644;
    }
    return 0;
}

int access(const char *path, int mode) {
    (void)mode;
    if (s_abi == NULL || path == NULL) return -1;
    char clean[CORE_FILE_PATH];
    clean_path(path, clean);
    return s_abi->file_size(s_abi->host, clean) < 0 ? -1 : 0;
}

int unlink(const char *path) {
    (void)path;
    return -1;
}

int rmdir(const char *path) {
    (void)path;
    return -1;
}

int mkdir(const char *path, mode_t mode) {
    (void)path;
    (void)mode;
    return -1;
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

// Directories: a core has no filesystem to walk. FixFilePath() gives up
// cleanly when opendir() says there is none, and the user-map menu checks it.
DIR *opendir(const char *path) {
    (void)path;
    return NULL;
}

struct dirent *readdir(DIR *dir) {
    (void)dir;
    return NULL;
}

int closedir(DIR *dir) {
    (void)dir;
    return 0;
}

// FILE* is a pointer to one of the slots above; newlib's FILE is opaque to the
// engine, which only passes it back to us.
static core_file_t *file_of(FILE *stream) {
    core_file_t *file = (core_file_t *)stream;
    if (file < s_files || file >= s_files + CORE_FILE_SLOTS || !file->used) {
        return NULL;
    }
    return file;
}

FILE *fopen(const char *path, const char *mode) {
    const int writable = mode != NULL && (mode[0] == 'w' || mode[0] == 'a');
    return (FILE *)file_open(path, writable);
}

int fclose(FILE *stream) {
    core_file_t *file = file_of(stream);
    if (file == NULL) return -1;
    file_close(file);
    return 0;
}

size_t fread(void *ptr, size_t size, size_t nmemb, FILE *stream) {
    core_file_t *file = file_of(stream);
    if (file == NULL || size == 0 || nmemb == 0) return 0;
    size_t bytes = size * nmemb;
    ssize_t got = read((int)(file - s_files), ptr, bytes);
    if (got <= 0) return 0;
    return (size_t)got / size;
}

size_t fwrite(const void *ptr, size_t size, size_t nmemb, FILE *stream) {
    core_file_t *file = file_of(stream);
    if (file == NULL) return 0;
    write((int)(file - s_files), ptr, size * nmemb);
    return nmemb;
}

int fseek(FILE *stream, long offset, int whence) {
    core_file_t *file = file_of(stream);
    if (file == NULL) return -1;
    return lseek((int)(file - s_files), offset, whence) < 0 ? -1 : 0;
}

long ftell(FILE *stream) {
    core_file_t *file = file_of(stream);
    return file == NULL ? -1 : file->offset;
}

int fgetc(FILE *stream) {
    unsigned char c;
    return fread(&c, 1, 1, stream) == 1 ? c : -1;
}

int fputc(int c, FILE *stream) {
    unsigned char ch = (unsigned char)c;
    return fwrite(&ch, 1, 1, stream) == 1 ? c : -1;
}

char *fgets(char *s, int size, FILE *stream) {
    if (size <= 0) return NULL;
    int n = 0;
    while (n < size - 1) {
        unsigned char c;
        if (fread(&c, 1, 1, stream) != 1) break;
        s[n++] = (char)c;
        if (c == '\n') break;
    }
    if (n == 0) return NULL;
    s[n] = '\0';
    return s;
}

int feof(FILE *stream) {
    core_file_t *file = file_of(stream);
    return file == NULL || file->offset >= file->size;
}

int ferror(FILE *stream) {
    (void)stream;
    return 0;
}

void clearerr(FILE *stream) {
    (void)stream;
}

int fileno(FILE *stream) {
    core_file_t *file = file_of(stream);
    return file == NULL ? -1 : (int)(file - s_files);
}

// -- process / environment / time --------------------------------------------

void exit(int status) {
    // Error() ends here. Nothing can unwind in a core, so record the request
    // and jump out of the engine: continuing after ShutDown() runs on freed
    // memory. core_init() arms the jump before it calls the engine.
    (void)status;
    s_exit_requested = 1;
    mpos_fatal_jump();
}

void _exit(int status) {
    exit(status);
}

void abort(void) {
    s_exit_requested = 1;
    mpos_fatal_jump();
}

void __assert_func(const char *file, int line, const char *func, const char *expr) {
    (void)func;
    char line_buf[160];
    snprintf(line_buf, sizeof(line_buf), "assert failed: %s:%d: %s",
             file ? file : "?", line, expr ? expr : "?");
    if (s_abi != NULL) s_abi->log(s_abi->host, line_buf);
    s_exit_requested = 1;
    mpos_fatal_jump();
}

int *__errno(void) { return &s_errno; }
int *__errno_location(void) { return &s_errno; }

// newlib's inline accessors reach for the reentrancy structure. Nothing here
// uses its contents (our stdio replaces the functions that would), and the
// engine's errno is the plain int above.
struct _reent;
struct _reent *__getreent(void) {
    static long reent_stub[32];
    return (struct _reent *)reent_stub;
}

char *getenv(const char *name) {
    (void)name;
    return NULL;
}

int putenv(char *string) {
    (void)string;
    return 0;
}

int setenv(const char *name, const char *value, int overwrite) {
    (void)name;
    (void)value;
    (void)overwrite;
    return 0;
}

int system(const char *command) {
    (void)command;
    return -1;
}

int getchar(void) { return -1; }

char *strerror(int error) {
    (void)error;
    return (char *)"error";
}

int fsync(int fd) {
    (void)fd;
    return 0;
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

// A clock the engine only uses for seeds and for the timestamp in a demo/save
// name. The host's live millisecond clock is enough for both.
time_t time(time_t *out) {
    uint32_t ms = s_abi != NULL ? s_abi->now_ms(s_abi->host) : 0;
    time_t seconds = (time_t)(ms / 1000);
    if (out != NULL) *out = seconds;
    return seconds;
}

struct tm *localtime(const time_t *clock) {
    static struct tm value;
    time_t seconds = clock != NULL ? *clock : 0;
    value.tm_sec = (int)(seconds % 60);
    value.tm_min = (int)((seconds / 60) % 60);
    value.tm_hour = (int)((seconds / 3600) % 24);
    value.tm_mday = 1 + (int)((seconds / 86400) % 28);
    value.tm_mon = 0;
    value.tm_year = 126;
    value.tm_wday = (int)((4 + seconds / 86400) % 7);
    value.tm_yday = (int)((seconds / 86400) % 365);
    value.tm_isdst = 0;
    return &value;
}

// -- random ------------------------------------------------------------------

// The engine wants reproducible-looking noise for demos and AI; a small LCG is
// cheaper than newlib's random() and has no hidden state.
static unsigned long s_rand_state = 1;

void srand(unsigned int seed) {
    s_rand_state = seed ? seed : 1;
}

int rand(void) {
    s_rand_state = (s_rand_state * 1103515245UL + 12345UL) & 0x7fffffffUL;
    return (int)(s_rand_state >> 16) & 0x7fff;
}

// -- qsort -------------------------------------------------------------------

void qsort(void *base, size_t nmemb, size_t size,
           int (*compare)(const void *, const void *)) {
    unsigned char *array = (unsigned char *)base;
    for (size_t i = 1; i < nmemb; i++) {
        size_t j = i;
        while (j > 0 && compare(array + (j - 1) * size, array + j * size) > 0) {
            unsigned char tmp[64];
            unsigned char *a = array + (j - 1) * size;
            unsigned char *b = array + j * size;
            // size is tiny here (pointers or ints); a bounded stack copy keeps
            // this free of an allocation that could fail mid-sort.
            size_t n = size < sizeof(tmp) ? size : sizeof(tmp);
            memcpy(tmp, a, n);
            memcpy(a, b, n);
            memcpy(b, tmp, n);
            j--;
        }
    }
}
