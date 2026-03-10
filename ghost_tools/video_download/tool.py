"""Video download tool with auto-conversion to H.264 for QuickTime compatibility."""

import json
import os
import re
import subprocess
import time
from pathlib import Path


def register(api):
    """Register the video_download tool."""

    def execute_video_download(url: str = "", filename: str = "", **kwargs):
        """Download video from Instagram/TikTok and convert to H.264."""
        if not url:
            return json.dumps({"status": "error", "error": "url is required"})

        # Detect platform
        platform = None
        if "instagram.com" in url.lower() or "instagr.am" in url.lower():
            platform = "instagram"
        elif "tiktok.com" in url.lower():
            platform = "tiktok"
        else:
            return json.dumps({"status": "error", "error": "Unsupported platform. Use Instagram or TikTok URL."})

        try:
            t0 = time.time()
            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)

            # Generate output filename
            if not filename:
                ts = time.strftime("%Y%m%d_%H%M%S")
                filename = f"video_{platform}_{ts}.mp4"
            elif not filename.endswith('.mp4'):
                filename += ".mp4"

            output_path = downloads_dir / filename

            # Step 1: Download with yt-dlp
            api.log(f"Downloading {platform} video...")
            dl_cmd = [
                "yt-dlp",
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "-o", str(output_path),
                "--no-playlist",
                url,
            ]
            result = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                api.log(f"yt-dlp error: {result.stderr}")
                return json.dumps({"status": "error", "error": f"Download failed: {result.stderr[:200]}"})

            # Find the downloaded file
            downloaded_files = list(downloads_dir.glob("video_*_*"))
            if not downloaded_files:
                return json.dumps({"status": "error", "error": "Downloaded file not found"})
            
            input_file = downloaded_files[-1]
            final_path = output_path

            # Step 2: Convert to H.264 if needed
            api.log("Converting to H.264...")
            conv_cmd = [
                "ffmpeg",
                "-i", str(input_file),
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                "-y",
                str(final_path),
            ]
            result = subprocess.run(conv_cmd, capture_output=True, text=True, timeout=300)
            
            # Clean up temp file if different from final
            if input_file != final_path and input_file.exists():
                input_file.unlink()

            if result.returncode != 0:
                api.log(f"ffmpeg error: {result.stderr}")
                return json.dumps({"status": "error", "error": f"Conversion failed: {result.stderr[:200]}"})

            elapsed = round(time.time() - t0, 2)
            file_size = final_path.stat().st_size

            return json.dumps({
                "status": "ok",
                "path": str(final_path),
                "platform": platform,
                "elapsed_secs": elapsed,
                "file_size_bytes": file_size,
            })

        except subprocess.TimeoutExpired:
            return json.dumps({"status": "error", "error": "Download/conversion timed out"})
        except Exception as e:
            api.log(f"video_download error: {e}")
            return json.dumps({"status": "error", "error": str(e)[:500]})

    api.register_tool({
        "name": "video_download",
        "description": "Download videos from Instagram or TikTok and convert to H.264 for QuickTime compatibility.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL of the Instagram or TikTok video to download",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename (optional, without extension)",
                },
            },
            "required": ["url"],
        },
        "execute": execute_video_download,
    })