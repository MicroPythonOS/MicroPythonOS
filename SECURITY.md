# Security Policy

MicroPythonOS is an open, hobbyist operating system for ESP32-S3 badges. We take
security reports seriously and appreciate the effort it takes to send a good one.

## Reporting a vulnerability

Please report security issues **privately**, not as a public GitHub issue.

- Preferred: use GitHub's private vulnerability reporting on this repository
  (the "Security" tab, then "Report a vulnerability"). This needs to be turned
  on once under Settings > Security > Advisories.
- Alternatively, contact a maintainer directly.

<!-- Maintainer: add a security contact email above if you prefer email over
     GitHub's private reporting, and adjust the acknowledgement window below. -->

We aim to acknowledge a report within a week, and we will keep you posted while
we look into it. Please give us a reasonable window to ship a fix before
disclosing publicly.

## Supported versions

MicroPythonOS is developed on a rolling basis. Security fixes land on the latest
release; older firmware images are not maintained. Please update to the newest
release (via the OS Update app or the web flasher) before reporting.

## Scope and known limitations

MicroPythonOS runs on small microcontrollers with limited resources, and some
tradeoffs are intentional. The following are known and by design, so please do
not report them as vulnerabilities:

- **Secrets are stored unencrypted on the device.** WiFi passwords, Nostr private
  keys, and Nostr Wallet Connect (NWC) secrets live in plain JSON on the LittleFS
  partition. Anyone who can read the flash can read them.
- **No app sandboxing.** Installed apps share one MicroPython VM with full access
  to the system and to each other's data. Only install apps you trust.
- **Physical access means full compromise.** The USB/serial (REPL) interface and
  the flash are not protected against someone holding the device.
- **OTA updates trust a single origin.** Firmware is fetched over HTTPS from
  `updates.micropythonos.com`. TLS protects the transport, but images are not
  separately signed, so trust rests on that server and its certificate.
- **The optional settings webserver** exposes device controls over the local
  network when enabled. Only turn it on for networks you trust.

## In scope

Reports we would genuinely like to receive, for example:

- A **remote** party (over WiFi, a Nostr relay, or a fetched file) being able to
  read secrets, run code, or crash the device without physical access.
- Flaws in the crypto handling (secp256k1 / AES) beyond the at-rest storage
  tradeoff noted above.
- A malicious server or relay compromising the device through a normal app flow.
- OTA flaws that would let anyone other than the update server push an image.

## Thanks

Thank you for helping keep MicroPythonOS and its users safe.
