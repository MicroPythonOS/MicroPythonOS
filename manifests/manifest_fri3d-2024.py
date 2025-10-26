freeze('/tmp/', 'boot.py') # Hardware initialization - this file is copied from boot_fri3d-2024.py to /tmp by the build script to have it named boot.py
freeze('internal_filesystem/', 'main.py') # User Interface initialization
freeze('internal_filesystem/lib', '') # Additional libraries
freeze('freezeFS/', 'freezefs_mount_builtin.py') # Built-in apps
