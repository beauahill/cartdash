# Development setup (Ubuntu laptop)

What the laptop needs for Phase 0: the Python tools, Java 17, the Android SDK and emulator, and PlatformIO for the ESP32. Run each block once. Commands are for Ubuntu 22.04 or newer.

## 1. Repo

```bash
cd ~/cartdash
```

```bash
git pull
```

## 2. Python tools

```bash
sudo apt install -y python3-venv python3-pip
```

```bash
python3 -m venv .venv
```

```bash
. .venv/bin/activate
```

```bash
pip install -r tools/requirements.txt matplotlib
```

Check: `python3 -m pytest tools/tests -q` passes.

## 3. Java 17 (for Gradle builds from the command line)

```bash
sudo apt install -y openjdk-17-jdk
```

Check: `java -version` says 17. If a newer JDK is the default (`/usr/lib/jvm` holds several), point Gradle at 17 instead of changing the default:

```bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
```

## 4. Android Studio, SDK, and emulator

```bash
sudo snap install android-studio --classic
```

Start it once (`android-studio`), choose the Standard setup, and let it download the SDK, platform tools, and emulator.

The emulator needs hardware virtualization (KVM):

```bash
sudo apt install -y qemu-kvm cpu-checker
```

```bash
kvm-ok
```

```bash
sudo usermod -aG kvm $USER
```

Make the SDK tools available in a terminal by adding these lines to `~/.bashrc`:

```bash
export ANDROID_HOME=$HOME/Android/Sdk
export PATH=$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator
```

An emulator that looks like the head unit: Android 12 (API 31), the plain x86_64 image with no Google Play (the head unit may not have it either), 2000 x 1200 at density 240, landscape. From a terminal:

```bash
sdkmanager "system-images;android-31;default;x86_64"
```

```bash
avdmanager create avd -n cartdash_headunit -k "system-images;android-31;default;x86_64" -d "10.1in WXGA (Tablet)"
```

Then set `hw.lcd.width=2000`, `hw.lcd.height=1200`, `hw.lcd.density=240`, `hw.initialOrientation=landscape`, and `hw.ramSize=2048` in `~/.android/avd/cartdash_headunit.avd/config.ini`. Adjust the resolution and density once the real head unit's numbers are in `docs/verify.md`. (`sdkmanager` and `avdmanager` live in `$ANDROID_HOME/cmdline-tools/latest/bin`.)

Check: `adb version` works and `emulator -list-avds` lists the device.

Two things to know about the emulator:

- **Memory.** It used 3.3 GB once booted, with `hw.ramSize=2048`. With 16 GB of RAM, a second emulator or another project's Gradle daemons can run the laptop out of memory, and the kernel then kills an emulator. Run one emulator at a time, and do not build with Gradle while it boots.
- **Port 5555.** An emulator on the default console port (5554) also holds host port 5555, which is the port `fake_esp.py` and `TcpSource` use. Start the Cart Dash emulator on another port, and if any other emulator is on 5554, run `fake_esp.py` on another port too and tell the app:

```bash
emulator -avd cartdash_headunit -port 5580
```

```bash
python3 tools/fake_esp.py --tcp 5600
```

```bash
adb -s emulator-5580 shell am start -n com.cartdash/.MainActivity --es source TCP --ei tcp_port 5600
```

## 5. PlatformIO (ESP32 firmware)

```bash
sudo apt install -y pipx
```

```bash
pipx ensurepath
```

```bash
pipx install platformio
```

Let your user open the ESP32's USB serial port without sudo:

```bash
sudo usermod -aG dialout $USER
```

Log out and back in after the `usermod` commands so the new groups apply.

Check: `pio --version` works. With the ESP32-S3 plugged into its native USB port, `ls /dev/ttyACM*` shows it.

## 6. Phase 0: build and run

Firmware, from `firmware/`:

```bash
pio test -e native
```

```bash
pio run -e host && .pio/build/host/program 5
```

That prints 5 s of the simulated stream on the laptop, no board needed. With the board plugged in:

```bash
pio run -t upload && pio device monitor
```

Android, from `android/` (`local.properties` with `sdk.dir=$HOME/Android/Sdk` is made by Android Studio, or write it by hand):

```bash
./gradlew testDebugUnitTest assembleDebug
```

```bash
adb -s emulator-5580 install -r app/build/outputs/apk/debug/app-debug.apk
```

The app starts on its own simulator (SIM badge). Tap SOURCE at the bottom left to switch to TCP and `fake_esp.py`.

## ADB to the head unit over Wi-Fi

The head unit's USB ports are hosts (they will talk to the ESP32), so ADB goes over Wi-Fi. Android 12L has Wireless debugging built in.

1. On the head unit, open Settings, System, Developer options. The code is 7890 plus the current hour. The Factory settings code (8888) is a different menu: change nothing there.
2. In Developer options, turn on USB debugging and Wireless debugging. Put the head unit and the laptop on the same Wi-Fi.
3. Tap Wireless debugging, then Pair device with pairing code. It shows an address with a pairing port and a six digit code. On the laptop:

```bash
adb pair <head unit IP>:<pairing port>
```

4. Type the code when asked. Then connect to the address on the main Wireless debugging screen (a different port from the pairing one):

```bash
adb connect <head unit IP>:<port>
```

5. `adb devices` lists it as `<IP>:<port>`. Address it with `adb -s <IP>:<port>`, never bare `adb`, because the emulator is running too.

The port changes each time Wireless debugging restarts (Wi-Fi drop, sleep, reboot), so repeat `adb connect` after a key cycle. Pairing is remembered. This is for the bench only: on the cart the head unit's Wi-Fi belongs to wireless CarPlay, and nothing in the design needs it on Wi-Fi.

Install a build:

```bash
adb -s <IP>:<port> install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Fallback without ADB: serve the APK from the laptop and open it in the head unit's browser.

```bash
python3 -m http.server 8000 --directory android/app/build/outputs/apk/debug
```

Then open `http://<laptop IP>:8000/app-debug.apk` on the head unit and allow the install. `hostname -I` on the laptop shows its IP.

## 7. Claude Code on the laptop

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

```bash
cd ~/cartdash && claude
```

`CLAUDE.md` at the repo root tells a session where the project stands. Phase 0's steps are in `docs/plan.md`.
