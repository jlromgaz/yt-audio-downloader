import os
import sys
import subprocess

def check_dependencies():
    """Checks if yt_dlp and ffmpeg are installed."""
    missing = []
    try:
        import yt_dlp
    except ImportError:
        missing.append("yt-dlp (Install it by running in your terminal: pip install yt-dlp)")

    try:
        # Check if ffmpeg is accessible
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        missing.append("ffmpeg (Required to convert audio to MP3. Download it from https://ffmpeg.org/ and add it to your Windows PATH. Or install it with: winget install ffmpeg)")

    if missing:
        print("The following dependencies are missing to run the script:")
        for m in missing:
            print(f" - {m}")
        sys.exit(1)

def get_downloads_folder():
    """Gets the path to the Windows 'Downloads' folder."""
    return os.path.join(os.path.expanduser('~'), 'Downloads')

def main():
    print("========================================")
    print("      YouTube Audio Downloader")
    print("========================================\n")
    
    # Check if all dependencies are installed before proceeding
    check_dependencies()
    import yt_dlp

    url = input("> Enter the YouTube link (individual video or playlist): ").strip()
    if not url:
        print("\nError: You must enter a valid link.")
        return

    # Create base path: C:\Users\Username\Downloads\YoutubeAudioDownloader
    base_path = os.path.join(get_downloads_folder(), 'YoutubeAudioDownloader')
    os.makedirs(base_path, exist_ok=True)
    
    print(f"\n[+] Audio files will be automatically saved in: {base_path}")

    # Define the output template
    # File structure: c:/.../YoutubeAudioDownloader/[playlist_title]/[title].mp3
    output_template = '%(playlist_title)s/%(title)s.%(ext)s'
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'paths': {'home': base_path},
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320', # Highest MP3 quality: 320 kbps
        }],
        'outtmpl': output_template,
        'noplaylist': False, # Allows downloading full playlists
        'quiet': False, # Shows progress bar and details in console
        'ignoreerrors': True, # Ignores private or deleted videos and continues with the rest
    }

    print("\n[~] Starting download and conversion to high-quality MP3...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            print("\n[OK] Process completed successfully! Audio files have been saved in:", base_path)
    except Exception as e:
        print(f"\n[ERROR] An error occurred during download or conversion: {e}")

if __name__ == "__main__":
    main()
