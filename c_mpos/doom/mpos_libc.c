#include "py/dynruntime.h"
#include "py/stream.h"
#include "py/nlr.h"

#include <stdint.h>
#include <stdarg.h>
#include <string.h>

void *mpos_calloc(size_t nmemb, size_t size);
void *mpos_malloc(size_t size);
void mpos_free(void *ptr);
void *mpos_realloc(void *ptr, size_t size);

int mpos_ctype_toupper_table[256];
int mpos_ctype_toupper_inited;

// io.open, imported once (see mpos_open_file).
mp_obj_t g_open_fun;
int g_open_ready;

int mpos_vfprintf(void *stream, const char *fmt, va_list args);
void *mpos_fopen(const char *path, const char *mode);
int mpos_fclose(void *stream);
size_t mpos_fread(void *ptr, size_t size, size_t nmemb, void *stream);
size_t mpos_fwrite(const void *ptr, size_t size, size_t nmemb, void *stream);
int mpos_fseek(void *stream, long offset, int whence);
long mpos_ftell(void *stream);
int mpos_remove(const char *path);
int mpos_rename(const char *oldpath, const char *newpath);
int mpos_mkdir(const char *path, int mode);
int mpos_system(const char *cmd);
int mpos_chdir(const char *path);
void mpos_exit(int status);
char *mpos_getcwd(char *buf, size_t size);

struct timespec {
    long tv_sec;
    long tv_nsec;
};

#ifndef CLOCK_MONOTONIC
#define CLOCK_MONOTONIC 1
#endif

static int mpos_is_lower(int c) {
    return (c >= 'a' && c <= 'z');
}

static int mpos_is_upper(int c) {
    return (c >= 'A' && c <= 'Z');
}

int toupper(int c) {
    if (mpos_is_lower(c)) {
        return c - 'a' + 'A';
    }
    return c;
}

int tolower(int c) {
    if (mpos_is_upper(c)) {
        return c - 'A' + 'a';
    }
    return c;
}

int isspace(int c) {
    return (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v');
}

int isalpha(int c) {
    return mpos_is_lower(c) || mpos_is_upper(c);
}

int isdigit(int c) {
    return (c >= '0' && c <= '9');
}

const int *__ctype_toupper_loc(void) {
    if (!mpos_ctype_toupper_inited) {
        for (int i = 0; i < 256; ++i) {
            mpos_ctype_toupper_table[i] = i;
        }
        for (int i = 'a'; i <= 'z'; ++i) {
            mpos_ctype_toupper_table[i] = i - 'a' + 'A';
        }
        mpos_ctype_toupper_inited = 1;
    }
    return mpos_ctype_toupper_table;
}

int strcasecmp(const char *a, const char *b) {
    if (a == NULL || b == NULL) {
        return (a == b) ? 0 : (a ? 1 : -1);
    }

    while (*a && *b) {
        int ca = tolower((unsigned char)*a++);
        int cb = tolower((unsigned char)*b++);
        if (ca != cb) {
            return ca - cb;
        }
    }

    return (unsigned char)*a - (unsigned char)*b;
}

int strncasecmp(const char *a, const char *b, size_t n) {
    if (n == 0) {
        return 0;
    }

    if (a == NULL || b == NULL) {
        return (a == b) ? 0 : (a ? 1 : -1);
    }

    while (n-- > 0 && *a && *b) {
        int ca = tolower((unsigned char)*a++);
        int cb = tolower((unsigned char)*b++);
        if (ca != cb) {
            return ca - cb;
        }
    }

    if ((n == (size_t)-1) || (*a == '\0' && *b == '\0')) {
        return 0;
    }

    return (unsigned char)*a - (unsigned char)*b;
}

void *memcpy(void *dst, const void *src, size_t n) {
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    if (d == NULL || s == NULL) {
        return dst;
    }
    for (size_t i = 0; i < n; ++i) {
        d[i] = s[i];
    }
    return dst;
}

void *memset(void *dst, int c, size_t n) {
    unsigned char *d = (unsigned char *)dst;
    if (d == NULL) {
        return dst;
    }
    for (size_t i = 0; i < n; ++i) {
        d[i] = (unsigned char)c;
    }
    return dst;
}

void *memmove(void *dst, const void *src, size_t n) {
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    if (d == NULL || s == NULL || d == s || n == 0) {
        return dst;
    }
    if (d < s) {
        for (size_t i = 0; i < n; ++i) {
            d[i] = s[i];
        }
    } else {
        for (size_t i = n; i > 0; --i) {
            d[i - 1] = s[i - 1];
        }
    }
    return dst;
}

size_t strlen(const char *s) {
    size_t len = 0;
    while (s[len] != '\0') {
        ++len;
    }
    return len;
}

int strcmp(const char *a, const char *b) {
    while (*a && *b) {
        if (*a != *b) {
            return (unsigned char)*a - (unsigned char)*b;
        }
        ++a;
        ++b;
    }
    return (unsigned char)*a - (unsigned char)*b;
}

int strncmp(const char *a, const char *b, size_t n) {
    if (n == 0) {
        return 0;
    }
    while (n-- > 0 && *a && *b) {
        if (*a != *b) {
            return (unsigned char)*a - (unsigned char)*b;
        }
        ++a;
        ++b;
    }
    if ((n == (size_t)-1) || (*a == '\0' && *b == '\0')) {
        return 0;
    }
    return (unsigned char)*a - (unsigned char)*b;
}

char *strncpy(char *dst, const char *src, size_t n) {
    size_t i = 0;
    for (; i < n && src[i] != '\0'; ++i) {
        dst[i] = src[i];
    }
    for (; i < n; ++i) {
        dst[i] = '\0';
    }
    return dst;
}

int abs(int value) {
    return (value < 0) ? -value : value;
}

long labs(long value) {
    return (value < 0) ? -value : value;
}

char *strdup(const char *s) {
    if (s == NULL) {
        return NULL;
    }
    size_t len = strlen(s) + 1;
    char *copy = mpos_malloc(len);
    if (copy != NULL) {
        memcpy(copy, s, len);
    }
    return copy;
}

char *strchr(const char *s, int c) {
    while (*s) {
        if (*s == (char)c) {
            return (char *)s;
        }
        ++s;
    }
    if ((char)c == '\0') {
        return (char *)s;
    }
    return NULL;
}

char *strrchr(const char *s, int c) {
    const char *last = NULL;
    while (*s) {
        if (*s == (char)c) {
            last = s;
        }
        ++s;
    }
    if ((char)c == '\0') {
        return (char *)s;
    }
    return (char *)last;
}

char *strstr(const char *haystack, const char *needle) {
    if (*needle == '\0') {
        return (char *)haystack;
    }
    for (const char *h = haystack; *h; ++h) {
        const char *h_it = h;
        const char *n_it = needle;
        while (*h_it && *n_it && *h_it == *n_it) {
            ++h_it;
            ++n_it;
        }
        if (*n_it == '\0') {
            return (char *)h;
        }
    }
    return NULL;
}

int __isoc99_sscanf(const char *s, const char *fmt, ...) {
    (void)s;
    (void)fmt;
    return 0;
}

int sscanf(const char *s, const char *fmt, ...) {
    (void)s;
    (void)fmt;
    return 0;
}

int atoi(const char *s) {
    int sign = 1;
    int value = 0;

    if (s == NULL) {
        return 0;
    }

    while (*s == ' ' || *s == '\t' || *s == '\n' || *s == '\r') {
        ++s;
    }

    if (*s == '-') {
        sign = -1;
        ++s;
    } else if (*s == '+') {
        ++s;
    }

    while (*s >= '0' && *s <= '9') {
        value = value * 10 + (*s - '0');
        ++s;
    }

    return sign * value;
}

float atof(const char *s) {
    (void)s;
    return 0.0f;
}

static size_t mpos_strnlen(const char *s, size_t max_len) {
    if (s == NULL) {
        return 0;
    }
    size_t len = 0;
    while (len < max_len && s[len] != '\0') {
        ++len;
    }
    return len;
}

void *calloc(size_t nmemb, size_t size) {
    return mpos_calloc(nmemb, size);
}

void *malloc(size_t size) {
    return mpos_malloc(size);
}

void free(void *ptr) {
    mpos_free(ptr);
}

void *realloc(void *ptr, size_t size) {
    return mpos_realloc(ptr, size);
}

void *mpos_calloc(size_t nmemb, size_t size) {
    size_t total = nmemb * size;
    void *ptr = m_malloc(total);
    if (ptr != NULL) {
        mp_fun_table.memset_(ptr, 0, total);
    }
    return ptr;
}

void *mpos_malloc(size_t size) {
    return m_malloc(size);
}

void mpos_free(void *ptr) {
    m_free(ptr);
}

void *mpos_realloc(void *ptr, size_t size) {
    return m_realloc(ptr, size);
}



void *fopen(const char *path, const char *mode) {
    return mpos_fopen(path, mode);
}

int fclose(void *stream) {
    return mpos_fclose(stream);
}

size_t fread(void *ptr, size_t size, size_t nmemb, void *stream) {
    return mpos_fread(ptr, size, nmemb, stream);
}

size_t fwrite(const void *ptr, size_t size, size_t nmemb, void *stream) {
    return mpos_fwrite(ptr, size, nmemb, stream);
}

int fseek(void *stream, long offset, int whence) {
    return mpos_fseek(stream, offset, whence);
}

long ftell(void *stream) {
    return mpos_ftell(stream);
}

int remove(const char *path) {
    return mpos_remove(path);
}

int rename(const char *oldpath, const char *newpath) {
    return mpos_rename(oldpath, newpath);
}

int mkdir(const char *path, int mode) {
    return mpos_mkdir(path, mode);
}

int system(const char *cmd) {
    return mpos_system(cmd);
}

int chdir(const char *path) {
    return mpos_chdir(path);
}

void exit(int status) {
    mpos_exit(status);
    __builtin_unreachable();
}

char *getcwd(char *buf, size_t size) {
    return mpos_getcwd(buf, size);
}

const void *const stdout = (const void *)1;
const void *const stderr = (const void *)2;

typedef struct {
    mp_obj_t handle;
    const mp_stream_p_t *stream;
} mpos_file_t;

static mp_obj_t mpos_open_file(const char *path, const char *mode) {
    // C code expects fopen() to return NULL for a missing file, and Doom opens
    // plenty of optional files. MicroPython's open() raises instead, so catch
    // the exception here rather than letting it unwind through the engine.
    nlr_buf_t nlr;
    if (mp_fun_table.nlr_push(&nlr) != 0) {
        return mp_const_none;
    }
    // `mp_load_global("open")` only searches the module's globals (no builtins
    // fallback), so take io.open and keep it: one import for the session.
    if (!g_open_ready) {
        mp_obj_t io_module = mp_import_name(MP_QSTR_io, mp_const_none,
                                            MP_OBJ_NEW_SMALL_INT(0));
        g_open_fun = mp_load_attr(io_module, MP_QSTR_open);
        g_open_ready = 1;
    }
    mp_obj_t open_fun = g_open_fun;
    mp_obj_t args[2];
    size_t path_len = mpos_strnlen(path, 512);
    args[0] = mp_obj_new_str(path ? path : "", path_len);
    const char *mode_str = mode ? mode : "rb";
    size_t mode_len = mpos_strnlen(mode_str, 8);
    args[1] = mp_obj_new_str(mode_str, mode_len);
    mp_obj_t result = mp_call_function_n_kw(open_fun, 2, 0, args);
    mp_fun_table.nlr_pop();
    return result;
}

static mpos_file_t *mpos_file_wrap(mp_obj_t file_obj) {
    if (file_obj == mp_const_none) {
        return NULL;
    }
    mpos_file_t *file = mpos_malloc(sizeof(mpos_file_t));
    if (file == NULL) {
        return NULL;
    }
    file->handle = file_obj;
    // Read-only files (a WAD) do not support write, and get_stream_raise
    // would raise for them: try read+write, then read alone.
    nlr_buf_t nlr;
    if (mp_fun_table.nlr_push(&nlr) == 0) {
        file->stream = mp_fun_table.get_stream_raise(
            file_obj, MP_STREAM_OP_READ | MP_STREAM_OP_WRITE);
        mp_fun_table.nlr_pop();
        return file;
    }
    if (nlr.ret_val != NULL) {
        // fall through to read-only
    }
    if (mp_fun_table.nlr_push(&nlr) == 0) {
        file->stream = mp_fun_table.get_stream_raise(
            file_obj, MP_STREAM_OP_READ);
        mp_fun_table.nlr_pop();
        return file;
    }
    mpos_free(file);
    return NULL;
}

void *mpos_fopen(const char *path, const char *mode) {
    mp_obj_t file_obj = mpos_open_file(path, mode);
    void *wrapped = mpos_file_wrap(file_obj);
    return wrapped;
}

int mpos_fclose(void *stream) {
    if (stream == NULL) {
        return 0;
    }
    mpos_file_t *file = (mpos_file_t *)stream;
    mp_obj_t close_args[2];
    mp_load_method(file->handle, MP_QSTR_close, close_args);
    mp_fun_table.call_method_n_kw(0, 0, close_args);
    mpos_free(file);
    return 0;
}

size_t mpos_fread(void *ptr, size_t size, size_t nmemb, void *stream) {
    mpos_file_t *file = (mpos_file_t *)stream;
    size_t total = size * nmemb;
    int err = 0;
    int bytes = file->stream->read(file->handle, ptr, total, &err);
    if (bytes < 0) {
        return 0;
    }
    return (size_t)bytes / size;
}

size_t mpos_fwrite(const void *ptr, size_t size, size_t nmemb, void *stream) {
    mpos_file_t *file = (mpos_file_t *)stream;
    size_t total = size * nmemb;
    int err = 0;
    int bytes = file->stream->write(file->handle, ptr, total, &err);
    if (bytes < 0) {
        return 0;
    }
    return (size_t)bytes / size;
}

int mpos_fseek(void *stream, long offset, int whence) {
    mpos_file_t *file = (mpos_file_t *)stream;
    mp_obj_t seek_args[4];
    mp_load_method(file->handle, MP_QSTR_seek, seek_args);
    seek_args[2] = mp_obj_new_int(offset);
    seek_args[3] = mp_obj_new_int(whence);
    mp_fun_table.call_method_n_kw(2, 0, seek_args);
    return 0;
}

long mpos_ftell(void *stream) {
    mpos_file_t *file = (mpos_file_t *)stream;
    mp_obj_t tell_args[2];
    mp_load_method(file->handle, MP_QSTR_tell, tell_args);
    mp_obj_t pos_obj = mp_fun_table.call_method_n_kw(0, 0, tell_args);
    if (pos_obj == mp_const_none) {
        return -1;
    }
    return (long)mp_obj_get_int(pos_obj);
}

int mpos_remove(const char *path) {
    (void)path;
    return -1;
}

int mpos_rename(const char *oldpath, const char *newpath) {
    (void)oldpath;
    (void)newpath;
    return -1;
}

int mpos_mkdir(const char *path, int mode) {
    (void)mode;
    (void)path;
    return 0;
}

int mpos_system(const char *cmd) {
    (void)cmd;
    return -1;
}

int mpos_chdir(const char *path) {
    (void)path;
    return 0;
}

void mpos_exit(int status) {
    (void)status;
    mp_obj_t exc_type = mp_load_global(MP_QSTR_SystemExit);
    mp_obj_t args[1];
    args[0] = mp_obj_new_str("exit called", 11);
    mp_obj_t exc = mp_fun_table.call_function_n_kw(exc_type, 1, args);
    mp_fun_table.raise(exc);
    __builtin_unreachable();
}

char *mpos_getcwd(char *buf, size_t size) {
    (void)buf;
    (void)size;
    return NULL;
}

struct timeval {
    long tv_sec;
    long tv_usec;
};

// The engine's clock is a variable the Python side sets, so nothing here has
// to call back into MicroPython (a native module that imports on the hot path
// costs 32ms a frame).
uint32_t mpos_clock_ms;

void mpos_set_clock_ms(uint32_t now_ms) {
    mpos_clock_ms = now_ms;
}

uint32_t mpos_get_clock_ms(void) {
    return mpos_clock_ms;
}

int gettimeofday(struct timeval *tv, void *tz) {
    (void)tz;
    tv->tv_sec = mpos_clock_ms / 1000;
    tv->tv_usec = (mpos_clock_ms % 1000) * 1000;
    return 0;
}

int clock_gettime(int clk_id, struct timespec *ts) {
    (void)clk_id;
    if (ts == NULL) {
        return -1;
    }
    ts->tv_sec = mpos_clock_ms / 1000;
    ts->tv_nsec = (long)(mpos_clock_ms % 1000) * 1000000L;
    return 0;
}

long time(long *out) {
    if (out != NULL) {
        *out = mpos_clock_ms / 1000;
    }
    return mpos_clock_ms / 1000;
}

int mpos_errno;

// newlib's <ctype.h> macros index this table directly (with a +1 offset and a
// NUL entry at 0), so a natmod has to provide and fill it: the macros bypass
// the isalpha()/isdigit() functions below entirely.
char _ctype_[257];

// newlib's library functions want a per-thread reentrancy block even when they
// never touch it; a zeroed static one is enough for errno.
unsigned char g_reent_block[256];

struct _reent;
struct _reent *__getreent(void) {
    return (struct _reent *)g_reent_block;
}

void mpos_libc_init(void) {
    for (int c = 0; c < 256; c++) {
        int flags = 0;
        if (c >= 'A' && c <= 'Z') {
            flags |= 0x01;  // _U
        }
        if (c >= 'a' && c <= 'z') {
            flags |= 0x02;  // _L
        }
        if (c >= '0' && c <= '9') {
            flags |= 0x04;  // _N
        }
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v') {
            flags |= 0x08;  // _S
        }
        if ((c >= '!' && c <= '/') || (c >= ':' && c <= '@') ||
            (c >= '[' && c <= '`') || (c >= '{' && c <= '~')) {
            flags |= 0x10;  // _P
        }
        if (c < 0x20 || c == 0x7F) {
            flags |= 0x20;  // _C
        }
        if ((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') ||
            (c >= 'a' && c <= 'f')) {
            flags |= 0x40;  // _X
        }
        if (c == ' ' || c == '\t') {
            flags |= 0x80;  // _B
        }
        _ctype_[c + 1] = (char)flags;
    }
    _ctype_[0] = 0;
}

int *__errno_location(void) {
    return &mpos_errno;
}

int *__errno(void) {
    return &mpos_errno;
}
