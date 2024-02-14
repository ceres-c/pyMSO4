# pyMSO44
A python library for interfacing with the Tek MSO4 oscilloscopes (tested with
MSO44).

See the [documentation](https://ceres-c.it/pyMSO4/) for more information.

# Troubleshooting
The MSO44 is an interesting beast, and sometimes it will not behave as
expected, nor as the documentation says. Here are some tips to get it to work.

1. **Lots of timeouts in VISA communication**

Use the `mso4.reboot()` method to reset the scope UI and VISA server.

2. **Unable to connect to the device (pyvisa not setting up the connection)**

Reboot the scope through the front button.
