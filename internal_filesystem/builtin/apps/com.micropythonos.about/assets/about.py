from mpos import Activity, pct_of_display_width

import mpos.info
import sys

class About(Activity):

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_border_width(0, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_pad_all(pct_of_display_width(2), 0)
        # Make the screen focusable so it can be scrolled with the arrow keys
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(screen)

        label0 = lv.label(screen)
        label0.set_text(f"MicroPythonOS version: {mpos.info.CURRENT_OS_VERSION}")
        label1 = lv.label(screen)
        label1.set_text(f"Hardware ID: {mpos.info.get_hardware_id()}")
        label2 = lv.label(screen)
        label2.set_text(f"sys.version: {sys.version}")
        label3 = lv.label(screen)
        label3.set_text(f"sys.implementation: {sys.implementation}")

        sys_mpy = sys.implementation._mpy
        label30 = lv.label(screen)
        label30.set_text(f'mpy version: {sys_mpy & 0xff}')
        label31 = lv.label(screen)
        label31.set_text(f'mpy sub-version: {sys_mpy >> 8 & 3}')
        arch = [None, 'x86', 'x64',
            'armv6', 'armv6m', 'armv7m', 'armv7em', 'armv7emsp', 'armv7emdp',
            'xtensa', 'xtensawin', 'rv32imc', 'rv64imc'][(sys_mpy >> 10) & 0x0F]
        flags = ""
        if arch:
            flags += ' -march=' + arch
        if (sys_mpy >> 16) != 0:
            flags += ' -march-flags=' + (sys_mpy >> 16)
        if len(flags) > 0:
            label32 = lv.label(screen)
            label32.set_text('mpy flags: ' + flags)

        label4 = lv.label(screen)
        label4.set_text(f"sys.platform: {sys.platform}")
        label15 = lv.label(screen)
        label15.set_text(f"sys.path: {sys.path}")

        import micropython
        label16 = lv.label(screen)
        label16.set_text(f"micropython.opt_level(): {micropython.opt_level()}")
        import gc
        label17 = lv.label(screen)
        label17.set_text(f"Memory: {gc.mem_free()} free, {gc.mem_alloc()} allocated, {gc.mem_alloc()+gc.mem_free()} total")
        # These are always written to sys.stdout
        #label16.set_text(f"micropython.mem_info(): {micropython.mem_info()}")
        #label18 = lv.label(screen)
        #label18.set_text(f"micropython.qstr_info(): {micropython.qstr_info()}")
        label19 = lv.label(screen)
        label19.set_text(f"mpos.__path__: {mpos.__path__}") # this will show .frozen if the /lib folder is frozen (prod build)
        try:
            from esp32 import Partition
            label5 = lv.label(screen)
            label5.set_text("") # otherwise it will show the default "Text" if there's an exception below
            current = Partition(Partition.RUNNING)
            label5.set_text(f"Partition.RUNNING: {current}")
            next_partition = current.get_next_update()
            label6 = lv.label(screen)
            label6.set_text(f"Next update partition: {next_partition}")
        except Exception as e:
            print(f"Partition info got exception: {e}")
        try:
            print("Trying to find out additional board info, not available on every platform...")
            import machine
            label7 = lv.label(screen)
            label7.set_text("") # otherwise it will show the default "Text" if there's an exception below
            label7.set_text(f"machine.freq: {machine.freq()}")
            label8 = lv.label(screen)
            label8.set_text(f"machine.unique_id(): {machine.unique_id()}")
            label9 = lv.label(screen)
            label9.set_text(f"machine.wake_reason(): {machine.wake_reason()}")
            label10 = lv.label(screen)
            label10.set_text(f"machine.reset_cause(): {machine.reset_cause()}")
        except Exception as e:
            print(f"Additional board info got exception: {e}")
        try:
            print("Trying to find out freezefs info, this only works on production builds...") # dev builds already have the /builtin folder
            import freezefs_mount_builtin
            label11 = lv.label(screen)
            label11.set_text(f"freezefs_mount_builtin.date_frozen: {freezefs_mount_builtin.date_frozen}")
            label12 = lv.label(screen)
            label12.set_text(f"freezefs_mount_builtin.files_folders: {freezefs_mount_builtin.files_folders}")
            label13 = lv.label(screen)
            label13.set_text(f"freezefs_mount_builtin.sum_size: {freezefs_mount_builtin.sum_size}")
            label14 = lv.label(screen)
            label14.set_text(f"freezefs_mount_builtin.version: {freezefs_mount_builtin.version}")
        except Exception as e:
            # This will throw an EEXIST exception if there is already a "/builtin" folder present
            # It will throw "no module named 'freezefs_mount_builtin'" if there is no frozen filesystem
            # It's possible that the user had a dev build with a non-frozen /buitin folder in the vfat storage partition,
            # and then they install a prod build (with OSUpdate) that then is unable to mount the freezefs into /builtin
            # BUT which will still have the frozen-inside /lib folder. So the user will be able to install apps into /builtin
            # but they will not be able to install libraries into /lib.
            print("main.py: WARNING: could not import/run freezefs_mount_builtin: ", e)
            label11 = lv.label(screen)
            label11.set_text(f"freezefs_mount_builtin exception (normal if internal storage partition has overriding /builtin folder): {e}")
        # Disk usage:
        import os
        try:
            stat = os.statvfs('/')
            total_space = stat[0] * stat[2]
            free_space = stat[0] * stat[3]
            used_space = total_space - free_space
            label20 = lv.label(screen)
            label20.set_text(f"Total space in /: {total_space} bytes")
            label21 = lv.label(screen)
            label21.set_text(f"Free space in /: {free_space} bytes")
            label22 = lv.label(screen)
            label22.set_text(f"Used space in /: {used_space} bytes")
        except Exception as e:
            print(f"About app could not get info on / filesystem: {e}")
        try:
            stat = os.statvfs('/sdcard')
            total_space = stat[0] * stat[2]
            free_space = stat[0] * stat[3]
            used_space = total_space - free_space
            label23 = lv.label(screen)
            label23.set_text(f"Total space /sdcard: {total_space} bytes")
            label24 = lv.label(screen)
            label24.set_text(f"Free space /sdcard: {free_space} bytes")
            label25 = lv.label(screen)
            label25.set_text(f"Used space /sdcard: {used_space} bytes")
        except Exception as e:
            print(f"About app could not get info on /sdcard filesystem: {e}")
        self.setContentView(screen)
