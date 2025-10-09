freeze('internal_filesystem/', 'boot_unix.py') # Hardware initialization
freeze('internal_filesystem/', 'main.py') # User Interface initialization
freeze('internal_filesystem/lib', '') # Additional libraries
freeze('../freezeFS/', 'freezefs_mount_builtin.py') # Built-in apps
