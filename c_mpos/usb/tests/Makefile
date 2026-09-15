# Host unit tests for ../src/usb_hid.c: the real file is compiled with
# stub IDF/FreeRTOS headers (stubs/) against a scriptable fake stack
# (fake_usb_host.c). No hardware, no sleep (fake clock).
CC ?= gcc
CFLAGS ?= -std=c99 -Wall -Wextra -g -Istubs -I../src

test_hid_host: test_hid_host.c fake_usb_host.c fake_usb_host.h ../src/usb_hid.c ../src/usb_hid.h
	$(CC) $(CFLAGS) -o $@ test_hid_host.c fake_usb_host.c

.PHONY: test
test: test_hid_host
	./test_hid_host

.PHONY: clean
clean:
	rm -f test_hid_host
