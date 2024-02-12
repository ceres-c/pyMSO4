# pyMSO44
A python library for interfacing with the Tek MSO44 oscilloscope.

# Dependencies
Debian 12: `sudo apt update && sudo apt install python3 python3-pip python3-venv`

# Usage
## Setup
On a fresh Debian 12 install
```bash
sudo -E usermod -a -G dialout $USER
cp 50-newae.rules /etc/udev/rules.d/50-newae.rules
sudo systemctl mask ModemManager
sudo systemctl reboot # Udevadm reload + unplug device should do too
python3 -m venv venv
source venv/bin/activate
pip3 install pymso4
```

## Running CW305 examples
```bash
source venv/bin/activate
cd examples
pip3 install -r cw305_requirements.txt
jupyter lab --ip 0.0.0.0 cw305_capture_ch1_trigger_ch2.ipynb # Allow connections from any machine in the net
```
Then open the link in the terminal (adjusting the IP if you're connecting from a remote machine)

Alternatively, you can run an endurance test with:
```bash
source venv/bin/activate
cd examples
python3 cw305_endurance.py
```

# Troubleshooting
The MSO44 is an interesting beast, and sometimes it will not behave as
expected, nor as the documentation says. Here are some tips to get it to work.

1. **Lots of timeouts in VISA communication**

Use the `mso4.reboot()` method to reset the scope UI and VISA server.

2. **Unable to connect to the device (pyVisa not setting up the connection)**

Reboot the scope through the front button.
