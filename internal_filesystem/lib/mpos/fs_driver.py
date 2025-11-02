# Original author: mhepp(https://forum.lvgl.io/u/mhepp/summary)
# Copyright (c) 2024 - 2025 Kevin G. Schlosser
# Added directory support, upstreamed at https://github.com/lvgl-micropython/lvgl_micropython/issues/398


import lvgl as lv
import struct


def _fs_open_cb(drv, path, mode):

    if mode == lv.FS_MODE.WR:
        p_mode = 'wb'
    elif mode == lv.FS_MODE.RD:
        p_mode = 'rb'
    elif mode == lv.FS_MODE.WR | lv.FS_MODE.RD:
        p_mode = 'rb+'
    else:
        raise RuntimeError("fs_open_callback() - open mode error, %s is invalid mode" % mode)

    try:
        f = open(path, p_mode)

    except OSError as e:
        raise RuntimeError("fs_open_callback(%s) exception: %s" % (path, e))

    return {'file' : f, 'path': path}


def _fs_close_cb(drv, fs_file):
    try:
        fs_file.__cast__()['file'].close()
    except OSError as e:
        raise RuntimeError("fs_close_callback(%s) exception: %s" % (fs_file.__cast__()['path'], e))

    return lv.FS_RES.OK


def _fs_read_cb(drv, fs_file, buf, btr, br):
    try:
        tmp_data = fs_file.__cast__()['file'].read(btr)
        buf.__dereference__(btr)[0:len(tmp_data)] = tmp_data
        br.__dereference__(4)[0:4] = struct.pack("<L", len(tmp_data))
    except OSError as e:
        raise RuntimeError("fs_read_callback(%s) exception %s" % (fs_file.__cast__()['path'], e))

    return lv.FS_RES.OK


def _fs_seek_cb(drv, fs_file, pos, whence):
    try:
        fs_file.__cast__()['file'].seek(pos, whence)
    except OSError as e:
        raise RuntimeError("fs_seek_callback(%s) exception %s" % (fs_file.__cast__()['path'], e))

    return lv.FS_RES.OK


def _fs_tell_cb(drv, fs_file, pos):
    try:
        tpos = fs_file.__cast__()['file'].tell()
        pos.__dereference__(4)[0:4] = struct.pack("<L", tpos)
    except OSError as e:
        raise RuntimeError("fs_tell_callback(%s) exception %s" % (fs_file.__cast__()['path'], e))

    return lv.FS_RES.OK


def _fs_write_cb(drv, fs_file, buf, btw, bw):
    try:
        wr = fs_file.__cast__()['file'].write(buf.__dereference__(btw)[0:btw])
        bw.__dereference__(4)[0:4] = struct.pack("<L", wr)
    except OSError as e:
        raise RuntimeError("fs_write_callback(%s) exception %s" % (fs_file.__cast__()['path'], e))

    return lv.FS_RES.OK

def _fs_dir_open_cb(drv, path):
    #print(f"_fs_dir_open_cb for path '{path}'")
    try:
        import os # for ilistdir()
        path = path.rstrip('/') # LittleFS handles trailing flashes fine, but vfs.VfsFat returns an [Errno 22] EINVAL
        return {'iterator' : os.ilistdir(path)}
    except Exception as e:
        print(f"_fs_dir_open_cb exception: {e}")
        return None

def _fs_dir_read_cb(drv, lv_fs_dir_t, buf, btr):
    try:
        iterator = lv_fs_dir_t.__cast__()['iterator']
        nextfile = iterator.__next__()
        #print(f"nextfile: {nextfile}")
        filename = nextfile[0]
        entry_type = nextfile[1]  # Type field
        if entry_type == 0x4000:
            #print(f"{filename} is a directory")
            filename = f"/{filename}"
        # Convert filename to bytes with null terminator
        tmp_data_bytes = filename.encode() + b'\x00'
        buf.__dereference__(btr)[0:len(tmp_data_bytes)] = tmp_data_bytes
        return lv.FS_RES.OK
    except StopIteration:
        # Clear buffer and return FS_ERR when iteration ends
        buf.__dereference__(btr)[0:1] = b'\x00'  # Empty string (null byte)
        return lv.FS_RES.NOT_EX  # Next entry "does not exist"
    except Exception as e:
        print(f"_fs_dir_read_cb exception: {e}")
        return lv.FS_RES.UNKNOWN

def _fs_dir_close_cb(drv, lv_fs_dir_t):
    #print(f"_fs_dir_close_cb called")
    # No need to cleanup the iterator so nothing to do
    return lv.FS_RES.OK

def fs_register(fs_drv, letter, cache_size=500):

    fs_drv.init()
    fs_drv.letter = ord(letter)
    fs_drv.open_cb = _fs_open_cb
    fs_drv.read_cb = _fs_read_cb
    fs_drv.write_cb = _fs_write_cb
    fs_drv.seek_cb = _fs_seek_cb
    fs_drv.tell_cb = _fs_tell_cb
    fs_drv.close_cb = _fs_close_cb
    fs_drv.dir_open_cb = _fs_dir_open_cb
    fs_drv.dir_read_cb = _fs_dir_read_cb
    #fs_drv.dir_close_cb = _fs_dir_close_cb

    if cache_size >= 0:
        fs_drv.cache_size = cache_size

    fs_drv.register()

