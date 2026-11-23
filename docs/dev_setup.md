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

Check: `java -version` says 17.

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

An emulator that looks like the head unit: in Android Studio, Device Manager, create a device with a new hardware profile: 10.1 inch, 2000 x 1200, landscape, with an Android 12 (API 31) x86_64 system image. Adjust the resolution and density once the real head unit's numbers are in `docs/verify.md`.

Check: `adb version` works and `emulator -list-avds` lists the device.

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

## Installing the app on the head unit without ADB

The head unit's developer options are locked by a code we do not have yet (its Factory settings code is 8888; change nothing there except a USB or ADB debugging switch, if it has one). Until then, install builds over Wi-Fi from the laptop:

```bash
python3 -m http.server 8000 --directory android/app/build/outputs/apk/debug
```

On the head unit, open `http://<laptop IP>:8000/app-debug.apk` in the browser and allow it to install. `hostname -I` on the laptop shows its IP; both must be on the same Wi-Fi. Without ADB, the app keeps its own log and shows it on a debug screen.

## 6. Claude Code on the laptop

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

```bash
cd ~/cartdash && claude
```

`CLAUDE.md` at the repo root tells a session where the project stands. Phase 0's steps are in `docs/plan.md`.
