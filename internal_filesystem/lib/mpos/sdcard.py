import os
import machine

sdcard = None

# This gets called by (the device-specific) boot*.py
def inform_sdcard(so):
    global sdcard
    sdcard = so

def format_sdcard(sdcard):
    """Format the SD card with FAT filesystem"""
    try:
        print("Formatting SD card...")
        # Unmount if already mounted
        try:
            os.umount('/sdcard')
        except:
            pass
        
        # Format the SD card (this erases all data!)
        sdcard.format()
        print("SD card formatted successfully")
        return True
    except Exception as e:
        print(f"WARNING: Failed to format SD card: {e}")
        return False

# Tries to mount and returns True if it worked
def try_mount(sdcard):
    try:
        os.mount(sdcard, '/sdcard')
        print("SD card mounted successfully at /sdcard")
        return True
    except Exception as e:
        print(f"WARNING: failed to mount SD card: {e}")
        return False

# Returns True if everything successful, otherwise False if it failed to mount
def mount_sdcard_optional_format():
    global sdcard # should have been initialized by inform_sdcard()

    if not sdcard:
        print("WARNING: no machine.SDCard object has been initialized at boot, aborting...")
        return False

    # Try to detect SD card
    try:
        sdcard.info()
        print("SD card detected")
    except Exception as e:
        print(f"WARNING: sdcard.info() got exception: {e}")
        print("SD card not detected or hardware issue")
        return False

    if not try_mount(sdcard):
        if format_sdcard(sdcard):
            if not try_mount(sdcard):
                print(f"WARNING: failed to mount SD card even after formatting, aborting...")
                return False
        else:
            print("WARNING: Could not format SD card - check hardware connections or reformat on a PC. Aborting...")
            return False

    try:
        print("SD card contents:", os.listdir('/sdcard'))
    except Exception as e:
        print(f"WARNING: SD card did not fail to mount but could not list SD card contents: {e}")
        return False

    print("SD card mounted successfully!")
    return True
