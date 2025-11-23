diff --git a/tools/mpremote/mpremote/main.py b/tools/mpremote/mpremote/main.py
index b30a1a213..015a31114 100644
--- a/tools/mpremote/mpremote/main.py
+++ b/tools/mpremote/mpremote/main.py
@@ -508,7 +508,7 @@ class State:
         self.ensure_connected()
         soft_reset = self._auto_soft_reset if soft_reset is None else soft_reset
         if soft_reset or not self.transport.in_raw_repl:
-            self.transport.enter_raw_repl(soft_reset=soft_reset)
+            self.transport.enter_raw_repl(soft_reset=False)
             self._auto_soft_reset = False
 
     def ensure_friendly_repl(self):
diff --git a/tools/mpremote/mpremote/transport_serial.py b/tools/mpremote/mpremote/transport_serial.py
index 6aed0bb49..b74bb68a0 100644
--- a/tools/mpremote/mpremote/transport_serial.py
+++ b/tools/mpremote/mpremote/transport_serial.py
@@ -139,7 +139,7 @@ class SerialTransport(Transport):
                 time.sleep(0.01)
         return data
 
-    def enter_raw_repl(self, soft_reset=True, timeout_overall=10):
+    def enter_raw_repl(self, soft_reset=False, timeout_overall=10):
         self.serial.write(b"\r\x03")  # ctrl-C: interrupt any running program
 
         # flush input (without relying on serial.flushInput())

