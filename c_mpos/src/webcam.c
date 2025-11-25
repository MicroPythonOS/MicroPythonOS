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
#include "py/obj.h"
#include "py/runtime.h"
#include "py/mperrno.h"

#define WIDTH 640
#define HEIGHT 480
#define NUM_BUFFERS 1
#define OUTPUT_WIDTH 240
#define OUTPUT_HEIGHT 240

#define WEBCAM_DEBUG_PRINT(...) mp_printf(&mp_plat_print, __VA_ARGS__)

static const mp_obj_type_t webcam_type;

typedef struct _webcam_obj_t {
    mp_obj_base_t base;
    int fd;
    char device[64];           // Device path (e.g., "/dev/video0")
    void *buffers[NUM_BUFFERS];
    size_t buffer_length;
    int frame_count;
    unsigned char *gray_buffer; // For grayscale
    uint16_t *rgb565_buffer;   // For RGB565
    int input_width;           // Webcam capture width (from V4L2)
    int input_height;          // Webcam capture height (from V4L2)
    int output_width;          // Configurable output width (default OUTPUT_WIDTH)
    int output_height;         // Configurable output height (default OUTPUT_HEIGHT)
} webcam_obj_t;

static void yuyv_to_rgb565(unsigned char *yuyv, uint16_t *rgb565, int in_width, int in_height, int out_width, int out_height) {
    // Crop to largest square that fits in the input frame
    int crop_size = (in_width < in_height) ? in_width : in_height;
    int crop_x_offset = (in_width - crop_size) / 2;
    int crop_y_offset = (in_height - crop_size) / 2;

    // Calculate scaling ratios
    float x_ratio = (float)crop_size / out_width;
    float y_ratio = (float)crop_size / out_height;

    for (int y = 0; y < out_height; y++) {
        for (int x = 0; x < out_width; x++) {
            int src_x = (int)(x * x_ratio) + crop_x_offset;
            int src_y = (int)(y * y_ratio) + crop_y_offset;

            // YUYV format: Y0 U Y1 V (4 bytes for 2 pixels)
            // Ensure we're aligned to even pixel boundary
            int src_x_even = (src_x / 2) * 2;
            int src_base_index = (src_y * in_width + src_x_even) * 2;

            // Extract Y, U, V values
            int y0;
            if (src_x % 2 == 0) {
                // Even pixel: use Y0
                y0 = yuyv[src_base_index];
            } else {
                // Odd pixel: use Y1
                y0 = yuyv[src_base_index + 2];
            }
            int u = yuyv[src_base_index + 1];
            int v = yuyv[src_base_index + 3];

            // YUV to RGB conversion (ITU-R BT.601)
            int c = y0 - 16;
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
            uint16_t r5 = (r >> 3) & 0x1F;
            uint16_t g6 = (g >> 2) & 0x3F;
            uint16_t b5 = (b >> 3) & 0x1F;

            rgb565[y * out_width + x] = (r5 << 11) | (g6 << 5) | b5;
        }
    }
}

static void yuyv_to_grayscale(unsigned char *yuyv, unsigned char *gray, int in_width, int in_height, int out_width, int out_height) {
    // Crop to largest square that fits in the input frame
    int crop_size = (in_width < in_height) ? in_width : in_height;
    int crop_x_offset = (in_width - crop_size) / 2;
    int crop_y_offset = (in_height - crop_size) / 2;

    // Calculate scaling ratios
    float x_ratio = (float)crop_size / out_width;
    float y_ratio = (float)crop_size / out_height;

    for (int y = 0; y < out_height; y++) {
        for (int x = 0; x < out_width; x++) {
            int src_x = (int)(x * x_ratio) + crop_x_offset;
            int src_y = (int)(y * y_ratio) + crop_y_offset;

            // YUYV format: Y0 U Y1 V (4 bytes for 2 pixels)
            // Ensure we're aligned to even pixel boundary
            int src_x_even = (src_x / 2) * 2;
            int src_base_index = (src_y * in_width + src_x_even) * 2;

            // Extract Y value
            unsigned char y_val;
            if (src_x % 2 == 0) {
                // Even pixel: use Y0
                y_val = yuyv[src_base_index];
            } else {
                // Odd pixel: use Y1
                y_val = yuyv[src_base_index + 2];
            }

            gray[y * out_width + x] = y_val;
        }
    }
}

static void save_raw(const char *filename, unsigned char *data, int width, int height) {
    FILE *fp = fopen(filename, "wb");
    if (!fp) {
        WEBCAM_DEBUG_PRINT("Cannot open file %s: %s\n", filename, strerror(errno));
        return;
    }
    fwrite(data, 1, width * height, fp);
    fclose(fp);
}

static void save_raw_rgb565(const char *filename, uint16_t *data, int width, int height) {
    FILE *fp = fopen(filename, "wb");
    if (!fp) {
        WEBCAM_DEBUG_PRINT("Cannot open file %s: %s\n", filename, strerror(errno));
        return;
    }
    fwrite(data, sizeof(uint16_t), width * height, fp);
    fclose(fp);
}

static int init_webcam(webcam_obj_t *self, const char *device, int width, int height) {
    // Store device path for later use (e.g., reconfigure)
    strncpy(self->device, device, sizeof(self->device) - 1);
    self->device[sizeof(self->device) - 1] = '\0';

    self->fd = open(device, O_RDWR);
    if (self->fd < 0) {
        WEBCAM_DEBUG_PRINT("Cannot open device: %s\n", strerror(errno));
        return -errno;
    }

    struct v4l2_format fmt = {0};
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = width;
    fmt.fmt.pix.height = height;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_YUYV;
    fmt.fmt.pix.field = V4L2_FIELD_ANY;
    if (ioctl(self->fd, VIDIOC_S_FMT, &fmt) < 0) {
        WEBCAM_DEBUG_PRINT("Cannot set format: %s\n", strerror(errno));
        close(self->fd);
        return -errno;
    }

    // Store actual format (driver may adjust dimensions)
    width = fmt.fmt.pix.width;
    height = fmt.fmt.pix.height;

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
            close(self->fd);
            return -errno;
        }
        self->buffer_length = buf.length;
        self->buffers[i] = mmap(NULL, buf.length, PROT_READ | PROT_WRITE, MAP_SHARED, self->fd, buf.m.offset);
        if (self->buffers[i] == MAP_FAILED) {
            WEBCAM_DEBUG_PRINT("Cannot map buffer: %s\n", strerror(errno));
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

    // Store the input dimensions (actual values from V4L2, may be adjusted by driver)
    self->input_width = width;
    self->input_height = height;

    // Initialize output dimensions with defaults if not already set
    if (self->output_width == 0) self->output_width = OUTPUT_WIDTH;
    if (self->output_height == 0) self->output_height = OUTPUT_HEIGHT;

    WEBCAM_DEBUG_PRINT("Webcam initialized: input %dx%d, output %dx%d\n",
                       self->input_width, self->input_height,
                       self->output_width, self->output_height);

    // Allocate buffers with configured output dimensions
    self->gray_buffer = (unsigned char *)malloc(self->output_width * self->output_height * sizeof(unsigned char));
    self->rgb565_buffer = (uint16_t *)malloc(self->output_width * self->output_height * sizeof(uint16_t));
    if (!self->gray_buffer || !self->rgb565_buffer) {
        WEBCAM_DEBUG_PRINT("Cannot allocate buffers: %s\n", strerror(errno));
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

    if (!self->gray_buffer) {
        self->gray_buffer = (unsigned char *)malloc(self->output_width * self->output_height * sizeof(unsigned char));
        if (!self->gray_buffer) {
            mp_raise_OSError(MP_ENOMEM);
        }
    }
    if (!self->rgb565_buffer) {
        self->rgb565_buffer = (uint16_t *)malloc(self->output_width * self->output_height * sizeof(uint16_t));
        if (!self->rgb565_buffer) {
            mp_raise_OSError(MP_ENOMEM);
        }
    }

    const char *fmt = mp_obj_str_get_str(format);
    if (strcmp(fmt, "grayscale") == 0) {
        yuyv_to_grayscale(self->buffers[buf.index], self->gray_buffer,
                         self->input_width, self->input_height,
                         self->output_width, self->output_height);
        // char filename[32];
        // snprintf(filename, sizeof(filename), "frame_%03d.raw", self->frame_count++);
        // save_raw(filename, self->gray_buffer, self->output_width, self->output_height);
        mp_obj_t result = mp_obj_new_memoryview('b', self->output_width * self->output_height, self->gray_buffer);
        res = ioctl(self->fd, VIDIOC_QBUF, &buf);
        if (res < 0) {
            mp_raise_OSError(-res);
        }
        return result;
    } else {
        yuyv_to_rgb565(self->buffers[buf.index], self->rgb565_buffer,
                      self->input_width, self->input_height,
                      self->output_width, self->output_height);
        // char filename[32];
        // snprintf(filename, sizeof(filename), "frame_%03d.rgb565", self->frame_count++);
        // save_raw_rgb565(filename, self->rgb565_buffer, self->output_width, self->output_height);
        mp_obj_t result = mp_obj_new_memoryview('b', self->output_width * self->output_height * 2, self->rgb565_buffer);
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
        { MP_QSTR_width, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = WIDTH} },
        { MP_QSTR_height, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = HEIGHT} },
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
    self->gray_buffer = NULL;
    self->rgb565_buffer = NULL;
    self->input_width = 0;    // Will be set from V4L2 format in init_webcam
    self->input_height = 0;   // Will be set from V4L2 format in init_webcam
    self->output_width = 0;   // Will use default OUTPUT_WIDTH in init_webcam
    self->output_height = 0;  // Will use default OUTPUT_HEIGHT in init_webcam

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
     *   input_width, input_height: V4L2 capture resolution (optional)
     *   output_width, output_height: Output buffer resolution (optional)
     *
     * If not specified, dimensions remain unchanged.
     */

    enum { ARG_self, ARG_input_width, ARG_input_height, ARG_output_width, ARG_output_height };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_self, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_input_width, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_input_height, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_output_width, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_output_height, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    webcam_obj_t *self = MP_OBJ_TO_PTR(args[ARG_self].u_obj);

    // Get new dimensions (keep current if not specified)
    int new_input_width = args[ARG_input_width].u_int;
    int new_input_height = args[ARG_input_height].u_int;
    int new_output_width = args[ARG_output_width].u_int;
    int new_output_height = args[ARG_output_height].u_int;

    if (new_input_width == 0) new_input_width = self->input_width;
    if (new_input_height == 0) new_input_height = self->input_height;
    if (new_output_width == 0) new_output_width = self->output_width;
    if (new_output_height == 0) new_output_height = self->output_height;

    // Validate dimensions
    if (new_input_width <= 0 || new_input_height <= 0 || new_input_width > 3840 || new_input_height > 2160) {
        mp_raise_ValueError(MP_ERROR_TEXT("Invalid input dimensions"));
    }
    if (new_output_width <= 0 || new_output_height <= 0 || new_output_width > 3840 || new_output_height > 2160) {
        mp_raise_ValueError(MP_ERROR_TEXT("Invalid output dimensions"));
    }

    // Check if anything changed
    if (new_input_width == self->input_width &&
        new_input_height == self->input_height &&
        new_output_width == self->output_width &&
        new_output_height == self->output_height) {
        return mp_const_none;  // Nothing to do
    }

    WEBCAM_DEBUG_PRINT("Reconfiguring webcam: %dx%d -> %dx%d (input), %dx%d -> %dx%d (output)\n",
                       self->input_width, self->input_height, new_input_width, new_input_height,
                       self->output_width, self->output_height, new_output_width, new_output_height);

    // Remember device path before deinit (which closes fd)
    char device[64];
    strncpy(device, self->device, sizeof(device));

    // Set desired output dimensions before reinit
    self->output_width = new_output_width;
    self->output_height = new_output_height;

    // Clean shutdown and reinitialize with new input dimensions
    deinit_webcam(self);
    int res = init_webcam(self, device, new_input_width, new_input_height);

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
