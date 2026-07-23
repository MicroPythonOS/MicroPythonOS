"""
test_async_dns_local_segfault.py - Verify .local DNS does not segfault.

.local domains trigger mDNS (libnss_mdns4_minimal on Linux) which is not
thread-safe when called from MicroPython's _thread workers and segfaults.
The fix in async_dns.py resolves .local synchronously on the main thread
on Linux to avoid the thread-unsafe NSS module.
"""

import unittest


class TestAsyncDnsLocal(unittest.TestCase):
    def test_local_domain_does_not_segfault(self):
        """
        .local domains must not crash the process (exit 139 / SIGSEGV).
        They may resolve (real mDNS host) or raise OSError (NXDOMAIN) —
        either is fine as long as the process stays alive.
        """
        import asyncio

        async def run():
            from mpos.net.download_manager import DownloadManager
            try:
                await DownloadManager.download_url("http://invalid-url-that-does-not-exist.local/")
            except OSError:
                pass

        asyncio.run(run())

    def test_non_local_domain_also_clean(self):
        import asyncio

        async def run():
            from mpos.net.download_manager import DownloadManager
            try:
                await DownloadManager.download_url("http://invalid-url-that-does-not-exist.com/")
            except OSError:
                pass

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
