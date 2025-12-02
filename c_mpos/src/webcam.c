#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/videodev2.h>
#include <sys/mman.h>
#include <string.h>
#include <errno.h>
#include <stdint.h>
#include <limits.h>
#include "py/obj.h"
#include "py/runtime.h"
#include "py/mperrno.h"

#define NUM_BUFFERS 1
#define MAX_SUPPORTED_RESOLUTIONS 32

#define WEBCAM_DEBUG_PRINT(...) mp_printf(&mp_plat_print, __VA_ARGS__)

static const mp_obj_type_t webcam_type;

// Resolution structure for storing supported formats
typedef struct {
    int width;
    int height;
} resolution_t;

// Cache of supported resolutions from V4L2 device
typedef struct {
    resolution_t resolutions[MAX_SUPPORTED_RESOLUTIONS];
    int count;
} supported_resolutions_t;

typedef struct _webcam_obj_t {
    mp_obj_base_t base;
    int fd;
    char device[64];           // Device path (e.g., "/dev/video0")
    void *buffers[NUM_BUFFERS];
    size_t buffer_length;
    int frame_count;
    unsigned char *gray_buffer; // For grayscale conversion
    uint16_t *rgb565_buffer;   // For RGB565 conversion

    // Separate capture and output dimensions
    int capture_width;         // What V4L2 actually captures
    int capture_height;
    int output_width;          // What user requested
    int output_height;

    // Supported resolutions cache
    supported_resolutions_t supported_res;
} webcam_obj_t;

// Helper function to convert single YUV pixel to RGB565
static inline uint16_t yuv_to_rgb565(int y_val, int u, int v) {
    int c = y_val - 16;
    int d = u - 128;
    int e = v - 128;

    int r = (298 * c + 409 * e + 128) >> 8;
    int g = (298 * c - 100 * d - 208 * e + 128) >> 8;
    int b = (298 * c + 516 * d + 128) >> 8;

    // Clamp to valid range
    r = r < 0 ? 0 : (r > 255 ? 255 : r);
    g = g < 0 ? 0 : (g > 255 ? 255 : g);
    b = b < 0 ? 0 : (b > 255 ? 255 : b);

    // Convert to RGB565
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
}

static void yuyv_to_rgb565(unsigned char *yuyv, uint16_t *rgb565,
                          int capture_width, int capture_height,
                          int output_width, int output_height) {
    // Convert YUYV to RGB565 with cropping or padding support
    // YUYV format: Y0 U Y1 V (4 bytes for 2 pixels, chroma shared)

    // Clear entire output buffer to black (RGB565 0x0000)
    memset(rgb565, 0, output_width * output_height * sizeof(uint16_t));

    if (output_width <= capture_width && output_height <= capture_height) {
        // Cropping case: extract center region from capture
        int offset_x = (capture_width - output_width) / 2;
        int offset_y = (capture_height - output_height) / 2;
        offset_x = (offset_x / 2) * 2;  // YUYV alignment (even offset)

        for (int y = 0; y < output_height; y++) {
            for (int x = 0; x < output_width; x += 2) {
                int src_y = offset_y + y;
                int src_x = offset_x + x;
                int src_index = (src_y * capture_width + src_x) * 2;

                int y0 = yuyv[src_index + 0];
                int u  = yuyv[src_index + 1];
                int y1 = yuyv[src_index + 2];
                int v  = yuyv[src_index + 3];

                int dst_index = y * output_width + x;
                rgb565[dst_index] = yuv_to_rgb565(y0, u, v);
                rgb565[dst_index + 1] = yuv_to_rgb565(y1, u, v);
            }
        }
    } else {
        // Padding case: center capture in larger output buffer
        int offset_x = (output_width - capture_width) / 2;
        int offset_y = (output_height - capture_height) / 2;
        offset_x = (offset_x / 2) * 2;  // YUYV alignment (even offset)

        for (int y = 0; y < capture_height; y++) {
            for (int x = 0; x < capture_width; x += 2) {
                int src_index = (y * capture_width + x) * 2;

                int y0 = yuyv[src_index + 0];
                int u  = yuyv[src_index + 1];
                int y1 = yuyv[src_index + 2];
                int v  = yuyv[src_index + 3];

                int dst_y = offset_y + y;
                int dst_x = offset_x + x;
                int dst_index = dst_y * output_width + dst_x;
                rgb565[dst_index] = yuv_to_rgb565(y0, u, v);
                rgb565[dst_index + 1] = yuv_to_rgb565(y1, u, v);
            }
        }
    }
}

static void yuyv_to_grayscale(unsigned char *yuyv, unsigned char *gray,
                             int capture_width, int capture_height,
                             int output_width, int output_height) {
    // Extract Y (luminance) values from YUYV with cropping or padding support
    // YUYV format: Y0 U Y1 V (4 bytes for 2 pixels)

    // Clear entire output buffer to black (0x00)
    memset(gray, 0, output_width * output_height);

    if (output_width <= capture_width && output_height <= capture_height) {
        // Cropping case: extract center region from capture
        int offset_x = (capture_width - output_width) / 2;
        int offset_y = (capture_height - output_height) / 2;
        offset_x = (offset_x / 2) * 2;  // YUYV alignment (even offset)

        for (int y = 0; y < output_height; y++) {
            for (int x = 0; x < output_width; x++) {
                int src_y = offset_y + y;
                int src_x = offset_x + x;
                // Y values are at even indices in YUYV
                gray[y * output_width + x] = yuyv[(src_y * capture_width + src_x) * 2];
            }
        }
    } else {
        // Padding case: center capture in larger output buffer
        int offset_x = (output_width - capture_width) / 2;
        int offset_y = (output_height - capture_height) / 2;
        offset_x = (offset_x / 2) * 2;  // YUYV alignment (even offset)

        for (int y = 0; y < capture_height; y++) {
            for (int x = 0; x < capture_width; x++) {
                int dst_y = offset_y + y;
                int dst_x = offset_x + x;
                // Y values are at even indices in YUYV
                gray[dst_y * output_width + dst_x] = yuyv[(y * capture_width + x) * 2];
            }
        }
    }
}

static void save_raw_generic(const char *filename, void *data, size_t elem_size, int width, int height) {
    FILE *fp = fopen(filename, "wb");
    if (!fp) {
        WEBCAM_DEBUG_PRINT("Cannot open file %s: %s\n", filename, strerror(errno));
        return;
    }
    fwrite(data, elem_size, width * height, fp);
    fclose(fp);
}

// Query supported YUYV resolutions from V4L2 device
static int query_supported_resolutions(int fd, supported_resolutions_t *supported) {
    struct v4l2_fmtdesc fmt_desc;
    struct v4l2_frmsizeenum frmsize;
    int found_yuyv = 0;

    supported->count = 0;

    // First, check if device supports YUYV format
    memset(&fmt_desc, 0, sizeof(fmt_desc));
    fmt_desc.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;

    for (fmt_desc.index = 0; ; fmt_desc.index++) {
        if (ioctl(fd, VIDIOC_ENUM_FMT, &fmt_desc) < 0) {
            break;
        }
        if (fmt_desc.pixelformat == V4L2_PIX_FMT_YUYV) {
            found_yuyv = 1;
            break;
        }
    }

    if (!found_yuyv) {
        WEBCAM_DEBUG_PRINT("Warning: YUYV format not found\n");
        return -1;
    }

    // Enumerate frame sizes for YUYV
    memset(&frmsize, 0, sizeof(frmsize));
    frmsize.pixel_format = V4L2_PIX_FMT_YUYV;

    for (frmsize.index = 0; supported->count < MAX_SUPPORTED_RESOLUTIONS; frmsize.index++) {
        if (ioctl(fd, VIDIOC_ENUM_FRAMESIZES, &frmsize) < 0) {
            break;
        }

        if (frmsize.type == V4L2_FRMSIZE_TYPE_DISCRETE) {
            supported->resolutions[supported->count].width = frmsize.discrete.width;
            supported->resolutions[supported->count].height = frmsize.discrete.height;
            supported->count++;
            WEBCAM_DEBUG_PRINT("  Found resolution: %dx%d\n",
                              frmsize.discrete.width, frmsize.discrete.height);
        }
    }

    if (supported->count == 0) {
        WEBCAM_DEBUG_PRINT("Warning: No discrete YUYV resolutions found, using common defaults\n");
        // Fallback to common resolutions if enumeration fails
        const resolution_t defaults[] = {
            {160, 120}, {320, 240}, {640, 480}, {1280, 720}, {1920, 1080}
        };
        for (int i = 0; i < 5 && i < MAX_SUPPORTED_RESOLUTIONS; i++) {
            supported->resolutions[i] = defaults[i];
            supported->count++;
        }
    }

    WEBCAM_DEBUG_PRINT("Total supported resolutions: %d\n", supported->count);
    return 0;
}

// Find the best capture resolution for the requested output size
static resolution_t find_best_capture_resolution(int requested_width, int requested_height,
                                                   supported_resolutions_t *supported) {
    resolution_t best;
    int found_candidate = 0;
    int min_area = INT_MAX;

    // Check for exact match first
    for (int i = 0; i < supported->count; i++) {
        if (supported->resolutions[i].width == requested_width &&
            supported->resolutions[i].height == requested_height) {
            WEBCAM_DEBUG_PRINT("Found exact resolution match: %dx%d\n",
                              requested_width, requested_height);
            return supported->resolutions[i];
        }
    }

    // Find smallest resolution that contains the requested size
    for (int i = 0; i < supported->count; i++) {
        if (supported->resolutions[i].width >= requested_width &&
            supported->resolutions[i].height >= requested_height) {
            int area = supported->resolutions[i].width * supported->resolutions[i].height;
            if (area < min_area) {
                min_area = area;
                best = supported->resolutions[i];
                found_candidate = 1;
            }
        }
    }

    if (found_candidate) {
        WEBCAM_DEBUG_PRINT("Best capture resolution for %dx%d: %dx%d (will crop)\n",
                          requested_width, requested_height, best.width, best.height);
        return best;
    }

    // No containing resolution found, use largest available (will need padding)
    best = supported->resolutions[0];
    for (int i = 1; i < supported->count; i++) {
        int area = supported->resolutions[i].width * supported->resolutions[i].height;
        int best_area = best.width * best.height;
        if (area > best_area) {
            best = supported->resolutions[i];
        }
    }

    WEBCAM_DEBUG_PRINT("Warning: Requested %dx%d exceeds max supported, capturing at %dx%d (will pad with black)\n",
                      requested_width, requested_height, best.width, best.height);
    return best;
}

static int init_webcam(webcam_obj_t *self, const char *device, int requested_width, int requested_height) {
    // Store device path for later use (e.g., reconfigure)
    strncpy(self->device, device, sizeof(self->device) - 1);
    self->device[sizeof(self->device) - 1] = '\0';

    self->fd = open(device, O_RDWR);
    if (self->fd < 0) {
        WEBCAM_DEBUG_PRINT("Cannot open device: %s\n", strerror(errno));
        return -errno;
    }

    // Query supported resolutions (first time only)
    if (self->supported_res.count == 0) {
        WEBCAM_DEBUG_PRINT("Querying supported resolutions...\n");
        if (query_supported_resolutions(self->fd, &self->supported_res) < 0) {
            // Query failed, but continue with fallback defaults
            WEBCAM_DEBUG_PRINT("Resolution query failed, continuing with defaults\n");
        }
    }

    // Find best capture resolution for requested output
    resolution_t best = find_best_capture_resolution(requested_width, requested_height,
                                                      &self->supported_res);

    // Store requested output dimensions
    self->output_width = requested_width;
    self->output_height = requested_height;

    // Configure V4L2 with capture resolution
    struct v4l2_format fmt = {0};
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = best.width;
    fmt.fmt.pix.height = best.height;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_YUYV;
    fmt.fmt.pix.field = V4L2_FIELD_ANY;
    if (ioctl(self->fd, VIDIOC_S_FMT, &fmt) < 0) {
        WEBCAM_DEBUG_PRINT("Cannot set format: %s\n", strerror(errno));
        close(self->fd);
        return -errno;
    }

    // Store actual capture dimensions (driver may adjust)
    self->capture_width = fmt.fmt.pix.width;
    self->capture_height = fmt.fmt.pix.height;

    struct v4l2_requestbuffers req = {0};
    req.count = NUM_BUFFERS;
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    if (ioctl(self->fd, VIDIOC_REQBUFS, &req) < 0) {
        WEBCAM_DEBUG_PRINT("Cannot request buffers: %s\n", strerror(errno));
        close(self->fd);
        return -errno;
    }

    for (int i = 0; i < NUM_BUFFERS; i++) {
        struct v4l2_buffer buf = {0};
        buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index = i;
        if (ioctl(self->fd, VIDIOC_QUERYBUF, &buf) < 0) {
            WEBCAM_DEBUG_PRINT("Cannot query buffer: %s\n", strerror(errno));
            // Unmap any already-mapped buffers
            for (int j = 0; j < i; j++) {
                munmap(self->buffers[j], self->buffer_length);
            }
            close(self->fd);
            return -errno;
        }
        self->buffer_length = buf.length;
        self->buffers[i] = mmap(NULL, buf.length, PROT_READ | PROT_WRITE, MAP_SHARED, self->fd, buf.m.offset);
        if (self->buffers[i] == MAP_FAILED) {
            WEBCAM_DEBUG_PRINT("Cannot map buffer: %s\n", strerror(errno));
            // Unmap any already-mapped buffers
            for (int j = 0; j < i; j++) {
                munmap(self->buffers[j], self->buffer_length);
            }
            close(self->fd);
            return -errno;
        }
    }

    for (int i = 0; i < NUM_BUFFERS; i++) {
        struct v4l2_buffer buf = {0};
        buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index = i;
        if (ioctl(self->fd, VIDIOC_QBUF, &buf) < 0) {
            WEBCAM_DEBUG_PRINT("Cannot queue buffer: %s\n", strerror(errno));
            return -errno;
        }
    }

    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (ioctl(self->fd, VIDIOC_STREAMON, &type) < 0) {
        WEBCAM_DEBUG_PRINT("Cannot start streaming: %s\n", strerror(errno));
        return -errno;
    }

    self->frame_count = 0;

    WEBCAM_DEBUG_PRINT("Webcam initialized: capture=%dx%d, output=%dx%d\n",
                       self->capture_width, self->capture_height,
                       self->output_width, self->output_height);

    // Allocate conversion buffers based on OUTPUT dimensions
    self->gray_buffer = (unsigned char *)malloc(self->output_width * self->output_height * sizeof(unsigned char));
    self->rgb565_buffer = (uint16_t *)malloc(self->output_width * self->output_height * sizeof(uint16_t));
    if (!self->gray_buffer || !self->rgb565_buffer) {
        WEBCAM_DEBUG_PRINT("Cannot allocate conversion buffers: %s\n", strerror(errno));
        free(self->gray_buffer);
        free(self->rgb565_buffer);
        close(self->fd);
        return -errno;
    }
    return 0;
}

static void deinit_webcam(webcam_obj_t *self) {
    if (self->fd < 0) return;

    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    ioctl(self->fd, VIDIOC_STREAMOFF, &type);

    for (int i = 0; i < NUM_BUFFERS; i++) {
        if (self->buffers[i] != MAP_FAILED) {
            munmap(self->buffers[i], self->buffer_length);
        }
    }

    free(self->gray_buffer);
    self->gray_buffer = NULL;
    free(self->rgb565_buffer);
    self->rgb565_buffer = NULL;

    // Clear resolution cache (device may change on reconnect)
    self->supported_res.count = 0;

    close(self->fd);
    self->fd = -1;
}

static mp_obj_t free_buffer(webcam_obj_t *self) {
    free(self->gray_buffer);
    self->gray_buffer = NULL;
    free(self->rgb565_buffer);
    self->rgb565_buffer = NULL;
    return mp_const_none;
}

static mp_obj_t capture_frame(mp_obj_t self_in, mp_obj_t format) {
    int res = 0;
    webcam_obj_t *self = MP_OBJ_TO_PTR(self_in);
    struct v4l2_buffer buf = {0};
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    res = ioctl(self->fd, VIDIOC_DQBUF, &buf);
    if (res < 0) {
        mp_raise_OSError(-res);
    }

    // Buffers should already be allocated in init_webcam
    if (!self->gray_buffer || !self->rgb565_buffer) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Buffers not allocated"));
    }

    const char *fmt = mp_obj_str_get_str(format);
    if (strcmp(fmt, "grayscale") == 0) {
        // Pass all 6 dimensions: capture (source) and output (destination)
        yuyv_to_grayscale(
            self->buffers[buf.index],
            self->gray_buffer,
            self->capture_width,   // Source dimensions
            self->capture_height,
            self->output_width,    // Destination dimensions
            self->output_height
        );
        // Return memoryview with OUTPUT dimensions
        mp_obj_t result = mp_obj_new_memoryview('b',
            self->output_width * self->output_height,
            self->gray_buffer);
        res = ioctl(self->fd, VIDIOC_QBUF, &buf);
        if (res < 0) {
            mp_raise_OSError(-res);
        }
        return result;
    } else {
        // Pass all 6 dimensions: capture (source) and output (destination)
        yuyv_to_rgb565(
            self->buffers[buf.index],
            self->rgb565_buffer,
            self->capture_width,   // Source dimensions
            self->capture_height,
            self->output_width,    // Destination dimensions
            self->output_height
        );
        // Return memoryview with OUTPUT dimensions
        mp_obj_t result = mp_obj_new_memoryview('b',
            self->output_width * self->output_height * 2,
            self->rgb565_buffer);
        res = ioctl(self->fd, VIDIOC_QBUF, &buf);
        if (res < 0) {
            mp_raise_OSError(-res);
        }
        return result;
    }
}

static mp_obj_t webcam_init(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_device, ARG_width, ARG_height };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_device, MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_width, MP_ARG_REQUIRED | MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_height, MP_ARG_REQUIRED | MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    const char *device = "/dev/video0";
    if (args[ARG_device].u_obj != MP_OBJ_NULL) {
        device = mp_obj_str_get_str(args[ARG_device].u_obj);
    }

    int width = args[ARG_width].u_int;
    int height = args[ARG_height].u_int;

    webcam_obj_t *self = m_new_obj(webcam_obj_t);
    self->base.type = &webcam_type;
    self->fd = -1;

    int res = init_webcam(self, device, width, height);
    if (res < 0) {
        mp_raise_OSError(-res);
    }

    return MP_OBJ_FROM_PTR(self);
}
MP_DEFINE_CONST_FUN_OBJ_KW(webcam_init_obj, 0, webcam_init);

static mp_obj_t webcam_deinit(mp_obj_t self_in) {
    webcam_obj_t *self = MP_OBJ_TO_PTR(self_in);
    deinit_webcam(self);
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(webcam_deinit_obj, webcam_deinit);

static mp_obj_t webcam_free_buffer(mp_obj_t self_in) {
    webcam_obj_t *self = MP_OBJ_TO_PTR(self_in);
    return free_buffer(self);
}
MP_DEFINE_CONST_FUN_OBJ_1(webcam_free_buffer_obj, webcam_free_buffer);

static mp_obj_t webcam_capture_frame(mp_obj_t self_in, mp_obj_t format) {
    webcam_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->fd < 0) {
        mp_raise_OSError(MP_EIO);
    }
    return capture_frame(self, format);
}
MP_DEFINE_CONST_FUN_OBJ_2(webcam_capture_frame_obj, webcam_capture_frame);

static mp_obj_t webcam_reconfigure(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    /*
     * Reconfigure webcam resolution by reinitializing.
     *
     * This elegantly reuses deinit_webcam() and init_webcam() instead of
     * duplicating V4L2 setup code.
     *
     * Parameters:
     *   width, height: Resolution (optional, keeps current if not specified)
     */

    enum { ARG_self, ARG_width, ARG_height };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_self, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_width, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_height, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    webcam_obj_t *self = MP_OBJ_TO_PTR(args[ARG_self].u_obj);

    // Get new dimensions (keep current if not specified)
    int new_width = args[ARG_width].u_int;
    int new_height = args[ARG_height].u_int;

    if (new_width == 0) new_width = self->output_width;
    if (new_height == 0) new_height = self->output_height;

    // Validate dimensions
    if (new_width <= 0 || new_height <= 0 || new_width > 3840 || new_height > 2160) {
        mp_raise_ValueError(MP_ERROR_TEXT("Invalid dimensions"));
    }

    // Check if anything changed
    if (new_width == self->output_width && new_height == self->output_height) {
        return mp_const_none;  // Nothing to do
    }

    WEBCAM_DEBUG_PRINT("Reconfiguring webcam: %dx%d -> %dx%d\n",
                       self->output_width, self->output_height, new_width, new_height);

    // Clean shutdown and reinitialize with new resolution
    // Note: deinit_webcam doesn't touch self->device, so it's safe to use directly
    deinit_webcam(self);
    int res = init_webcam(self, self->device, new_width, new_height);

    if (res < 0) {
        mp_raise_OSError(-res);
    }

    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_KW(webcam_reconfigure_obj, 1, webcam_reconfigure);

static const mp_obj_type_t webcam_type = {
    { &mp_type_type },
    .name = MP_QSTR_Webcam,
};

static const mp_rom_map_elem_t mp_module_webcam_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_webcam) },
    { MP_ROM_QSTR(MP_QSTR_Webcam), MP_ROM_PTR(&webcam_type) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&webcam_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_capture_frame), MP_ROM_PTR(&webcam_capture_frame_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&webcam_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_free_buffer), MP_ROM_PTR(&webcam_free_buffer_obj) },
    { MP_ROM_QSTR(MP_QSTR_reconfigure), MP_ROM_PTR(&webcam_reconfigure_obj) },
};
static MP_DEFINE_CONST_DICT(mp_module_webcam_globals, mp_module_webcam_globals_table);

const mp_obj_module_t webcam_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mp_module_webcam_globals,
};

MP_REGISTER_MODULE(MP_QSTR_webcam, webcam_user_cmodule);
