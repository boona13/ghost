"""Download Instagram/TikTok videos with H.264 auto-conversion for QuickTime."""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


def register(api):
    """Register the video_download tool."""

    def execute_video_download(url: str = "", output_dir: str = "", **kwargs):
        """Download a video from Instagram/TikTok and convert to H.264."""
        if not url:
            return json.dumps({"status": "error", "error": "url is required"})

        # Detect platform from URL
        url_lower = url.lower()
        if "instagram.com" in url_lower:
            platform = "instagram"
        elif "tiktok.com" in url_lower:
            platform = "tiktok"
        else:
            platform = "unknown"

        # Determine output directory
        if not output_dir:
            output_dir = str(Path.home() / "Downloads")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        try:
            # Step 1: Download with yt-dlp to temp location
            api.log(f"Downloading {platform} video from {url}")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                # yt-dlp downloads to a filename it chooses
                cmd = [
                    "yt-dlp", "-f", "best[ext=mp4]/best",
                    "--no-playlist", "-o", f"{tmpdir}/%(title).50s.%(ext)s",
                    url
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode != 0:
                    return json.dumps({
                        "status": "error", 
                        "error": f"Download failed: {result.stderr[:200]}"
                    })

                # Find the downloaded file - glob for any video file
                downloaded_files = list(Path(tmpdir).glob("*.[mM][pP][4Vv]"))
                if not downloaded_files:
                    downloaded_files = list(Path(tmpdir).glob("*"))
                    downloaded_files = [f for f in downloaded_files if f.is_file()]
                
                if not downloaded_files:
                    return json.dumps({"status": "error", "error": "No video file found after download"})
                
                src_file = downloaded_files[0]
                
                # Step 2: Convert to H.264 using ffmpeg
                ts = time.strftime("%Y%m%d_%H%M%S")
                filename = f"{platform}_video_{ts}.mp4"
                dst_file = Path(output_dir) / filename
                
                api.log(f"Converting to H.264: {dst_file}")
                
                # H.264 conversion with AAC audio, compatible with QuickTime
                convert_cmd = [
                    "ffmpeg", "-y", "-i", str(src_file),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(dst_file)
                ]
                conv_result = subprocess.run(convert_cmd, capture_output=True, text=True, timeout=600)
                
                if conv_result.returncode != 0:
                    return json.dumps({
                        "status": "error",
                        "error": f"Conversion failed: {conv_result.stderr[:200]}"
                    })

                file_size = dst_file.stat().st_size
                api.log(f"Video saved: {dst_file}")
                
                return json.dumps({
                    "status": "ok",
                    "path": str(dst_file),
                    "filename": filename,
                    "platform": platform,
                    "size_bytes": file_size,
                    "size_mb": round(file_size / (1024 * 1024), 2)
                })

        except subprocess.TimeoutExpired:
            return json.dumps({"status": "error", "error": "Download/conversion timed out"})
        except Exception as e:
            api.log(f"Video download error: {e}")
            return json.dumps({"status": "error", "error": str(e)[:200]})

    api.register_tool({
        "name": "video_download",
        "description": "Download video from Instagram or TikTok, auto-convert to H.264 for QuickTime compatibility.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL of the Instagram or TikTok video to download"
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory (default: ~/Downloads)",
                    "default": ""
                }
            },
            "required": ["url"]
        },
        "execute": execute_video_download,
    })