# Discord Badge Spoofer 🚀

A powerful, standalone, and dependency-free tool to inflate your Discord profile activity badges by simulating game launch and running telemetry events directly to Discord's Science endpoint.

> **Warning & Disclaimer**  
> This project is for educational and testing purposes only. Using this tool violates Discord's Terms of Service. Use it at your own risk and preferably on alternate accounts.

---

### 🌟 Features

- **Standalone GUI Application (`main.py`)**: Built with Python's native `tkinter` interface. Fully styled in dark theme with custom red Discord icon, **in-app "How to find?" help popups**, operation controls, live progress, and statistics.
- **Single File Architecture**: All engine logic, networking, and user interface are self-contained in a single executable Python script (`main.py`).
- **Zero External Dependencies**: Uses only Python standard library modules (`tkinter`, `urllib`, `dataclasses`, `json`, `threading`). No `pip install` required!
- **AppData Storage**: Saved credentials (`science_state.json`) and game data cache are automatically stored in `%APPDATA%\DiscordBadgeSpoofer` so the script can be run from anywhere.
- **Batch Processing**: Simulates thousands of played games and cumulative played hours seamlessly.

---

### 📋 Requirements & Environment

- **Python Version**: Python 3.10 or higher (`Python 3.10+`).
- **Operating System**: Windows, macOS, or Linux.
- **Dependencies**: None (100% Python Standard Library).

---

### 🚀 Quick Start

#### Method 1: One-Click Startup (Windows)
Double-click `start.bat`.

#### Method 2: Manual Terminal Execution

1. Clone or download the repository:
   ```bash
   git clone https://github.com/DynaMarley/discord-badge-spoofer.git
   cd discord-badge-spoofer
   ```
2. Run the application directly:
   ```bash
   python main.py
   ```

---

### 🔑 How to Find Credentials (Token & Cookie)

Inside the application (`main.py`), you can click **"(How to find?)"** next to each input field to open interactive help popups.

#### 1. Account Token (`token`)
1. Open Discord in your web browser (`https://discord.com/app`) or desktop client.
2. Press `Ctrl + Shift + I` (or `F12`) to open Developer Tools.
3. Switch to the **Network** tab.
4. Click any request sent to Discord's API (e.g., `/science`, `@me`, or `messages`).
5. Under **Request Headers**, locate the `Authorization` header.
6. Copy the entire `Authorization` string value and paste it into the **ACCOUNT TOKEN** field.

#### 2. Cloudflare Cookie (`cf_clearance`)
- **Method 1 (Application Tab)**:
  1. Open Discord in your web browser with Developer Tools (`F12`).
  2. Go to **Application** tab -> **Storage** -> **Cookies** -> `https://discord.com`.
  3. Locate `cf_clearance` under the **Name** column and copy its **Value**.
- **Method 2 (Network Tab)**:
  1. Go to the **Network** tab in Developer Tools (`F12`) and filter by `/science`.
  2. Click any `/science` request and copy the `cookie` header value under **Request Headers**.

---

### ⚙️ How It Works

Discord tracks played games and activity durations via telemetry events posted to `/api/v9/science`. This tool replicates the exact HTTP payload structure for `launch_game` and `running_game_heartbeat` events. Badges typically update on your Discord profile within 1-2 days.

---

## 📜 License & Credits

Created by **DynaMarley**
