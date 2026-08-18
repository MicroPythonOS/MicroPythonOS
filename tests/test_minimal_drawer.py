"""Minimal reproduction of the topmenu drawer crash."""
import sys
import gc
gc.collect()

import lvgl as lv
from mpos import ActivityNavigator, AppManager, NotificationManager, Notification
from mpos.ui import topmenu

# Simulate what the test setUp does
NotificationManager.cancel_all()
AppManager.start_app("com.micropythonos.launcher")
import time
time.sleep(0.5)

if topmenu.drawer_open:
    topmenu.close_drawer()
    time.sleep(0.5)

print("=== About to open drawer ===")
gc.collect()
topmenu.open_drawer()
print("=== Drawer opened ===")
time.sleep(0.5)

print("=== About to close drawer ===")
gc.collect()  
topmenu.close_drawer()
print("=== Drawer closed ===")
time.sleep(0.5)

print("=== About to open drawer again ===")
gc.collect()
topmenu.open_drawer()
print("=== Drawer opened again ===")
time.sleep(0.5)
topmenu.close_drawer()
print("ALL GOOD")
