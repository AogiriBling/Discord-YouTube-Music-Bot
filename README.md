
---

# ⚡ ZAPBOT — Discord Music Bot

> A modern Discord music bot powered by `discord.py` and `yt-dlp`.
>
> > Search YouTube, play audio in voice channels, manage queues, loop songs, and control playback with slash commands.

---

## ✨ Features

* **🎵 Slash Command Music Player** (`/play`, `/pause`, `/resume`, `/skip`, `/stop`, `/queue`, `/loop`, `/disconnect`)
* **📜 Queue System** : per-server queues, now playing info
* **🔁 Loop Mode** : repeat the current track, do twice for unloop
* **🎧 High-Quality Audio** via FFmpeg + yt-dlp
* **🤖 Smart VC Behavior** : auto-leaves empty channels
* **🛡️ Stable Playback** : reconnect logic & error handling

---

## ⚙️ Requirements

* Python **3.9+**
* Install libraries:

  ```python
  pip install discord.py yt-dlp
  ```
* **FFmpeg is required**
  You must download FFmpeg and **add it to your system PATH**:

  * **Windows:** Download from [https://ffmpeg.org](https://ffmpeg.org) → extract → add `/bin` folder to PATH

---

## 💻 Commands

| Command        | Description                          |
| -------------- | ------------------------------------ |
| `/play <song>` | Search or play directly from YouTube |
| `/queue`       | View queue + now playing             |
| `/skip`        | Skip current song                    |
| `/pause`       | Pause audio                          |
| `/resume`      | Resume audio                         |
| `/loop`        | Toggle loop mode                     |
| `/stop`        | Stop music & clear queue             |
| `/disconnect`  | Disconnect bot                       |

---

## 🚀 Setup

1. Install dependencies
2. Download **FFmpeg** and make sure it’s added to **PATH**
3. Open the script and add your bot token at the bottom.
4. Run the bot.

---

## 🖼️ Preview

![ZapBot](https://i.vgy.me/hncSKC.png)

---
