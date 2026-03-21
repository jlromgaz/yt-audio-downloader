# YouTube Audio Downloader

A simple and efficient Python script to download audio from YouTube videos or entire playlists in high-quality (320kbps MP3). It uses `yt-dlp` for downloading and `ffmpeg` for audio conversion.

## Prerequisites

Before running the script, ensure you have the following installed:

1.  **Python 3**: Download it from the [Microsoft Store](https://apps.microsoft.com/store/search/Python) or the [official website](https://www.python.org/downloads/). During installation, make sure to check **"Add Python to PATH"**.
2.  **yt-dlp**: A command-line media downloader. You can install it via pip:
    ```bash
    pip install yt-dlp
    ```
    *(Alternatively, run `pip install -r requirements.txt`)*
3.  **ffmpeg**: Essential for converting downloaded videos to high-quality MP3. To install easily on Windows, run this in PowerShell or Command Prompt:
    ```powershell
    winget install ffmpeg
    ```
    *Note: Restart your terminal after installation.*

## How to Use

You can run the script by double-clicking `download_audio.py` or via the terminal:

1.  Open PowerShell or CMD in the project folder.
2.  Run the script:
    ```bash
    python download_audio.py
    ```
3.  Follow the prompts:
    *   Enter the YouTube URL (video or playlist).
    *   The script will automatically save the files to a folder named `YoutubeAudioDownloader` inside your **Downloads** folder.
    *   If the link is a playlist, it will create a subfolder with the playlist name.

## Features

- Downloads individual videos or full playlists.
- Converts audio to **MP3 at 320 kbps** (maximum quality).
- Automatically organizes files into folders.
- Progress bar and detailed console output.
