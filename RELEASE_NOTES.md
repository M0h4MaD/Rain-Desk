# RainDesk 1.0.1

Fixes sound stuttering reported on Windows 11.

## Changes
- Larger audio buffer, faster refill after a timer delay.
- Requests precise timers and opts out of Windows power throttling while sound is playing.
- Audio underruns are logged (raindesk.log) to help diagnose problems.

## Download
RainDesk-1.0.1-win64.zip

SHA-256: `D5B19589CE2750108B291C4F55A8D79F2999D39D6D83A209E85544B68FCF9855`

## Known limitations
- Tested on Windows 10 (the stutter fix is not yet confirmed on Windows 11).
- Not code-signed, so SmartScreen may warn: More info, then Run anyway.

License: MIT.
