# Download Manager — Browser Extension Manual Installation Guide (Sideloading)

This browser extension automatically captures file downloads and video streams directly from your web browser and routes them to the desktop **Download Manager** application via local WebSocket communication.

To install the extension manually (unpacked / developer mode), follow the step-by-step instructions below:

---

## 1. Google Chrome & Chromium-Based Browsers (Brave, Microsoft Edge, Opera, etc.)

1. Open your browser and navigate to the extensions management page:
   ```text
   chrome://extensions
   ```
   *(For Microsoft Edge: `edge://extensions`, for Opera: `opera://extensions`)*
2. Enable **Developer mode** using the toggle in the top-right corner.
3. Click the **Load unpacked** button in the top-left toolbar.
4. In the folder picker dialog, select the `extension` folder:
   - **Installed Application:**
     ```text
     %LOCALAPPDATA%\Programs\Download Manager\extension
     ```
   - **Source / Portable Build:**
     Select the `extension` directory located inside your Download Manager root folder.
5. The extension will be loaded instantly, and the `⚡` Download Manager icon will appear in your browser toolbar.
6. When the desktop Download Manager application is running, the extension badge will display a green **ON** status.

---

## 2. Mozilla Firefox

1. Open Firefox and navigate to:
   ```text
   about:debugging#/runtime/this-firefox
   ```
2. Click the **Load Temporary Add-on...** button.
3. Navigate into the `extension` folder and select the `manifest.json` file.
4. The extension will be loaded and will connect to the desktop app over local WebSocket.

---

## 3. Usage & Features

- **Automatic Download Interception:** Clicking download links for archives, binaries, or media files (ZIP, EXE, ISO, MP4, etc.) automatically cancels native browser downloads and transfers them to the multi-threaded desktop accelerator.
- **Smart Video Stream Sniffing:** When playing media streams (m3u8 playlists, DASH manifests, video embeds), floating 1-click download pills appear directly over the player.
- **Context Menu Integration:** Right-click any link, video, or image and select **"Download with Download Manager"**.
- **Extension Popup:** Click the toolbar icon to view real-time WebSocket connection status, toggle automatic capture on/off, or manually send URLs to the desktop client.
- **Startup Shield:** Built-in safeguards prevent restored tabs from spamming download requests when the browser is first launched.
