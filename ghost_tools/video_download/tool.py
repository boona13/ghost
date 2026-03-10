"""Video download tool with H.264 auto-conversion for QuickTime compatibility."""

import json
import os
import subprocess
import time
from pathlib import Path


def register(api):
    """Register the video_download tool."""

    def video_download(url="", filename="", **_kw):
        """Download Instagram/TikTok videos with H.264 conversion."""
        if not url:
            return json.dumps({"status": "error", "error": "url is required"})

        # Determine platform from URL
        platform = "unknown"
        if "instagram.com" in url.lower():
            platform = "instagram"
        elif "tiktok.com" in url.lower():
            platform = "tiktok"

        # Generate output path
        ts = time.strftime("%Y%m%d_%H%M%S")
        default_name = f"{platform}_video_{ts}.mp4"
        filename = filename or default_name
        output_path = Path.home() / "Downloads" / filename

        try:
            t0 = time.time()

            # Step 1: Download video using yt-dlp
            api.log(f"Downloading video from {url}...")
            temp_output = str(output_path.with_suffix(".temp.mp4"))

            cmd_download = [
                "yt-dlp", "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "-o", temp_output, "--no-playlist", url
            ]
            subprocess.run(cmd_download, check=True, capture_output=True, timeout=300)

            # Find the downloaded file
            temp_files = list(Path.home() / "Downloads".glob("*.temp.mp4"))
            if not temp_files:
                return json.dumps({"status": "error", "error": "Download failed - no file found"})
            downloaded_file = temp_files[0]

            # Step 2: Convert to H.264 + AAC using ffmpeg
            api.log("Converting to H.264 for QuickTime compatibility...")
            cmd_convert = [
                "ffmpeg", "-i", str(downloaded_file),
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                "-y", str(output_path)
            ]
            subprocess.run(cmd_convert, check=True, capture_output=True, timeout=600)

            # Cleanup temp file
            downloaded_file.unlink(missing_ok=True)

            file_size = output_path.stat().st_size if output_path.exists() else 0
            elapsed = round(time.time() - t0, 2)

            return json.dumps({
                "status": "ok",
                "path": str(output_path),
                "platform": platform,
                "size_bytes": file_size,
                "elapsed_secs": elapsed
            })

        except subprocess.TimeoutExpired:
            return json.dumps({"status": "error", "error": "Download/conversion timed out"})
        except subprocess.CalledProcessError as e:
            return json.dumps({"status": "error", "error": f"Command failed: {e.stderr.decode()[:200]}"})
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)[:200]})

    api.register_tool({
        "name": "video_download",
        "description": "Download Instagram or TikTok videos with automatic H.264 conversion for QuickTime compatibility.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Instagram or TikTok video URL"},
                "filename": {"type": "string", "description": "Output filename (optional)"}
            },
            "required": ["url"]
        },
        "execute": video_download
    })
