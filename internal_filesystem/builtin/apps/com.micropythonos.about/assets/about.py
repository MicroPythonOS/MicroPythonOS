from mpos.apps import Activity

import mpos.info
import sys

class About(Activity):

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_border_width(0, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_pad_all(mpos.ui.pct_of_display_width(2), 0)
        # Make the screen focusable so it can be scrolled with the arrow keys
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(screen)

        label0 = lv.label(screen)
        label0.set_text(f"Hardware ID: {mpos.info.get_hardware_id()}")
        label1 = lv.label(screen)
        label1.set_text(f"MicroPythonOS version: {mpos.info.CURRENT_OS_VERSION}")
        label2 = lv.label(screen)
        label2.set_text(f"sys.version: {sys.version}")
        label3 = lv.label(screen)
        label3.set_text(f"sys.implementation: {sys.implementation}")
        label4 = lv.label(screen)
        label4.set_text(f"sys.platform: {sys.platform}")
        try:
            label5 = lv.label(screen)
            label5.set_text("") # otherwise it will show the default "Text" if there's an exception below
            from esp32 import Partition
            current = Partition(Partition.RUNNING)
            label5.set_text(f"Partition.RUNNING: {current}")
            next_partition = current.get_next_update()
            label6 = lv.label(screen)
            label6.set_text(f"Next update partition: {next_partition}")
        except Exception as e:
            print(f"Partition info got exception: {e}")
        try:
            print("Trying to find out additional board info, not available on every platform...")
            label7 = lv.label(screen)
            label7.set_text("") # otherwise it will show the default "Text" if there's an exception below
            import machine
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
            # This will throw an exception if there is already a "/builtin" folder present
            print("main.py: WARNING: could not import/run freezefs_mount_builtin: ", e)
            label11 = lv.label(screen)
            label11.set_text(f"freezefs_mount_builtin exception (normal on dev builds): {e}")

        self.setContentView(screen)
