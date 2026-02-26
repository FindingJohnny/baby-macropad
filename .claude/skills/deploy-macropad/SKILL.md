# Deploy Macropad

Deploy the baby-macropad service to the Raspberry Pi and verify it is running.

## Device Info
- **Pi hostname**: nursery-macropad (10.0.0.75)
- **Pi user**: nursery
- **SSH**: `ssh nursery@10.0.0.75`
- **App directory**: `/home/nursery/baby-macropad`
- **Venv**: `/home/nursery/macropad-venv`
- **Service**: baby-macropad (systemd)
- **Branch**: main

## Steps

1. **Push to main** (if there are unpushed commits):
   ```bash
   git push origin main
   ```

2. **Pull and restart on Pi**:
   ```bash
   ssh nursery@10.0.0.75 'cd ~/baby-macropad && git pull && sudo systemctl restart baby-macropad'
   ```

3. **Verify startup** (check for errors in last 20 lines):
   ```bash
   ssh nursery@10.0.0.75 'sudo journalctl -u baby-macropad -n 20 --no-pager'
   ```
   Expected: "Macropad controller running" and "Dashboard refreshed" with no errors.

4. **Verify buttons work** (optional, if testing):
   ```bash
   ssh nursery@10.0.0.75 'sudo journalctl -u baby-macropad -f'
   ```
   Press a button on the device — should see "Key N pressed" and API response logs.

## Troubleshooting

- **Device not found**: Check USB connection. Run `ssh nursery@10.0.0.75 'lsusb | grep 5548'`.
- **hidraw missing**: Reset USB hub: `ssh nursery@10.0.0.75 'echo 0 | sudo tee /sys/bus/usb/devices/1-1/authorized && sleep 1 && echo 1 | sudo tee /sys/bus/usb/devices/1-1/authorized'`
- **Screen off after deploy**: The SDK's `init()` briefly clears the screen. Icons should reappear within 1-2 seconds.
- **LED ring stays on**: Known issue — `init()` may reset LED state. Service calls `turn_off_leds()` after init but firmware may override.

## Reporting

On success: "Macropad deployed and running on nursery-macropad (10.0.0.75) from commit `<hash>`."
On failure: Report the specific error from journalctl.
