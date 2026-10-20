# Commonroom LAN File Browser

Commonroom lets you browse files, download them, and play supported audio or video in a web browser from another device on your local network. The server runs on the computer that stores the files; other devices connect to it using a browser.

> **Important:** By default, signing in gives read-only access to every detected Windows drive, or to the project's `shared` folder on macOS and Linux. Use this only on a private network with devices and people you trust. See [Security and access](#security-and-access) before starting.

## What you need

- A computer running Windows, macOS, or Linux containing the files you want to access.
- Python 3.10 or newer installed on that computer.
- A phone, tablet, or other computer connected to the same trusted home or office network.
- No Python packages or separate web server are required; the project uses Python's standard library.

### Install Python

The server requires Python 3.10 or newer. If it is not installed, use the appropriate option below. These commands install Python using the platform's package manager:

- Windows (PowerShell; requires [Windows Package Manager](https://learn.microsoft.com/windows/package-manager/winget/)):
  ```powershell
  winget install --exact --id Python.Python.3.14
  ```
- macOS (requires [Homebrew](https://brew.sh/)):
  ```sh
  brew install python
  ```
- Ubuntu or Debian:
  ```sh
  sudo apt update
  sudo apt install python3
  ```
- Fedora:
  ```sh
  sudo dnf install python3
  ```
- Arch Linux:
  ```sh
  sudo pacman -S python
  ```

If the package manager is not available, install Python from [python.org](https://www.python.org/downloads/). Linux distributions vary; check that the installed version is at least 3.10. On Windows, enable the option to add Python to PATH during installation if offered. Open a new terminal after installation, then verify:

- Windows: `py -3 --version` (or `python --version`).
- macOS or Linux: `python3 --version`.

## Start the server

1. Open a terminal in the folder.

2. Start the server using the command for your system:

   - Windows: 
   ```powershell
     py -3 app.py
     ```
     (or `python app.py` if `py` is unavailable).

   - macOS or Linux:
   ```powershell
     python3 app.py
     ```

3. Read the startup output. It lists the available drives, the web address, and the password. Leave this terminal open while using the server.

## Connect from another device

1. Keep the server computer running and connected to the network.
2. Connect the other device to the same trusted Wi-Fi or local network. Guest Wi-Fi or client isolation may prevent devices from reaching each other.
3. On the server computer, copy the address shown after `Open:` in the terminal. It looks like `http://192.168.1.42:8000`; use the exact address printed on your computer, not this example.
4. Open that address in the other device's web browser.
5. Enter the server password and sign in. The browser displays the available drives or configured folders.

If your operating system asks whether Python may communicate through the firewall, allow access only on a trusted private network. If another device cannot connect, check the server computer's firewall settings.

## Browse, play, and download

- Select a drive or shared folder to open it. Select folders to continue browsing; use the breadcrumb path to return to an earlier folder or to the drive list.
- Use **Search this folder** to filter the items currently displayed. It does not search every folder on the drive recursively.
- Select **Play** beside supported audio and video files to open the in-page player. Playback depends on the browser and the media's codec; a file may need to be downloaded if the browser cannot play it.
- Select **Download** to save a file to the device you are using.
- Use **Refresh** to reload the current folder after files have changed on the server computer.
- Select **Sign out** when finished. Sessions expire after 12 hours; stopping the server ends all sessions immediately.

The browser is read-only. It cannot upload, edit, rename, or delete files on the server computer.

## Limit which folders are available

On Windows, all detected drives are available by default. On macOS and Linux, the `shared` folder inside the project is available by default. To share only chosen folders instead, pass one or more `--share` options; this disables the default drive/folder discovery. Each path must already exist.

For example, to share specific folders (replace the paths with folders that exist on your computer):

```powershell
py -3 app.py --share "D:\Media" --share "C:\Users\YourName\Documents"
```

On macOS or Linux, use paths such as:

```sh
python3 app.py --share "$HOME/Media" --share "$HOME/Documents"
```

A signed-in device can access files under each selected folder, subject to the account running the server's file permissions. Paths that escape a selected folder are rejected.

## Optional settings

The defaults work for most home networks: the server detects a local network address and listens on port `8000`.

Choose a different port if 8000 is already in use:

- Windows: `py -3 app.py --port 8080`.
- macOS or Linux: `python3 app.py --port 8080`.

The terminal will print the address to use, including the new port.

Choose a specific network interface if the computer has multiple network connections:

- Windows: `py -3 app.py --host 192.168.1.42`.
- macOS or Linux: `python3 app.py --host 192.168.1.42`.

Replace the example IP with the address of the server computer's interface on the network where your other device is connected. The app prints the address to open after startup.

You can combine settings, for example:

- Windows: `py -3 app.py --share "D:\Media" --port 8080`.
- macOS or Linux: `python3 app.py --share "$HOME/Media" --port 8080`.

## Stop the server

Return to the terminal running `app.py` and press **Ctrl+C**. The server prints a stopping message and exits. Closing that terminal also stops the server. It does not continue running in the background.

To start it again later, repeat the startup steps. The password remains `Test@1234` each time.

## Troubleshooting

**Python is not recognized**

Install Python 3.10 or newer, then open a new terminal. Check with `py -3 --version` or `python --version` on Windows, or `python3 --version` on macOS or Linux.

**The page opens on the server computer but not on another device**

Check that both devices are on the same private network, use the exact address printed by the server, and allow Python through the server computer's firewall on trusted private networks only. Some guest Wi-Fi networks block communication between connected devices. Do not use `localhost` or `127.0.0.1` from another device; those addresses refer to that other device itself.

**The server reports that the address or port is already in use**

Another program may be using port 8000, or another copy of this server may still be running. Stop the other server with Ctrl+C or start this one on another port: `py -3 app.py --port 8080` on Windows, or `python3 app.py --port 8080` on macOS or Linux.

**A drive or file is missing or inaccessible**

On Windows, only drives detected when the server starts are listed. On macOS and Linux, the project `shared` folder is listed by default unless you specify folders with `--share`. A disconnected drive or a file the account running the server cannot read may not be accessible. Restart the server after connecting a drive. Operating-system file permissions still apply.

**A video does not play**

Browser support varies by file type and codec. Try downloading the file and opening it with a media player on the receiving device.

## Security and access

- On Windows, all detected drives are available by default and may include personal documents and system files. On macOS and Linux, the project `shared` folder is available by default. Prefer `--share` to restrict access to chosen folders.
- Anyone who can sign in can browse and download files that the account running the server can read. The server does not provide separate accounts or per-device permissions.
- The server does not write, upload, edit, or delete files. Hidden files are not filtered out.
- Paths are constrained to their selected drive or shared folder. A path traversal or link pointing outside that root is not served.
- The login session lasts up to 12 hours. Restarting the server invalidates active sessions.
- Connections use plain HTTP, not HTTPS. A person able to monitor the local network could observe the password and file contents in transit. Use only a trusted private network. Do not configure router port forwarding or expose the server to the public internet.
- The fixed password is `Test@1234`, which is easy to guess and cannot be changed in the current app. Anyone who knows it can sign in. Use the server only on a trusted private network, and do not expose it to the public internet.

## Run the tests

From the project folder, run the command for your system:

- Windows: `py -3 -m unittest discover -s tests -v`.
- macOS or Linux: `python3 -m unittest discover -s tests -v`.

The tests cover path containment, login protection, browsing multiple roots, downloads, and media byte-range responses.

## Project files

- `app.py`: HTTP server, login/session handling, drive discovery, path checks, downloads, and media streaming.
- `index.html`: browser page structure.
- `static/app.css`: layout and responsive styling.
- `static/app.js`: sign-in, drive/folder navigation, search, downloads, and media playback.
- `static/icons/`: SVG icons for folders, drives, and common file types.
- `tests/test_server.py`: unit and local HTTP integration tests.