"""Video download tool with H.264 auto-conversion for QuickTime compatibility."""

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path


def register(api):
    """Register the video_download tool."""
    
    def _detect_platform(url: str) -> str:
        """Detect video platform from URL."""
        url_lower = url.lower()
        if "instagram.com" in url_lower or "instagr.am" in url_lower:
            return "instagram"
        if "tiktok.com" in url_lower:
            return "tiktok"
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "youtube"
        return "unknown"

    def _get_output_filename(platform: str, url: str) -> str:
        """Generate output filename based on platform and URL."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        # Extract video ID from URL for uniqueness
        video_id = ""
        if "instagram.com" in url:
            match = re.search(r'/reel/([A-Za-z0-9_-]+)', url)
            if match:
                video_id = match.group(1)[:8]
        elif "tiktok.com" in url:
            match = re.search(r'/video/(\d+)', url)
            if match:
                video_id = match.group(1)[:8]
        
        return f"{platform}_{video_id or 'video'}_{ts}.mp4"

    def execute_video_download(url: str = "", filename: str = "", **_kw):
        """Download video from Instagram/TikTok and convert to H.264 for QuickTime."""
        if not url:
            return json.dumps({"status": "error", "error": "url is required"})
        
        platform = _detect_platform(url)
        if platform == "unknown":
            return json.dumps({"status": "error", "error": "Unsupported platform. Use Instagram, TikTok, or YouTube URLs."})
        
        try:
            # Create temp dir for download
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                
                # Generate output filename if not provided
                if not filename:
                    filename = _get_output_filename(platform, url)
                
                output_path = tmp_path / filename
                
                # Build yt-dlp command - download to temp location
                cmd = [
                    "yt-dlp",
                    "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "--merge-output-format", "mp4",
                    "-o", str(output_path),
                    "--no-playlist",
                    url,
                ]
                
                # Run yt-dlp
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode != 0:
                    return json.dumps({
                        "status": "error",
                        "error": f"Download failed: {result.stderr[:500]}"
                    })
                
                # Check if file was downloaded
                if not output_path.exists():
                    # yt-dlp might have changed the filename
                    downloaded_files = list(tmp_path.glob("*.mp4"))
                    if not downloaded_files:
                        return json.dumps({"status": "error", "error": "No video file found after download"})
                    output_path = downloaded_files[0]
                
                # Convert to H.264 if needed using ffmpeg
                final_path = tmp_path / f"h264_{output_path.name}"
                convert_cmd = [
                    "ffmpeg",
                    "-i", str(output_path),
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "23",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    "-y",
                    str(final_path),
                ]
                
                conv_result = subprocess.run(convert_cmd, capture_output=True, text=True, timeout=300)
                
                if conv_result.returncode != 0:
                    # If conversion fails, use original
                    final_path = output_path
                
                # Copy to downloads folder
                downloads = Path.home() / "Downloads"
                downloads.mkdir(exist_ok=True)
                dest_path = downloads / final_path.name
                
                # Handle filename conflicts
                if dest_path.exists():
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    dest_path = downloads / f"{final_path.stem}_{ts}.mp4"
                
                import shutil
                shutil.copy2(final_path, dest_path)
                
                file_size = dest_path.stat().st_size
                
                return json.dumps({
                    "status": "ok",
                    "path": str(dest_path),
                    "filename": dest_path.name,
                    "platform": platform,
                    "size_bytes": file_size,
                    "size_mb": round(file_size / (1024 * 1024), 2),
                })
                
        except subprocess.TimeoutExpired:
            return json.dumps({"status": "error", "error": "Download timed out after 5 minutes"})
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)[:500]})

    api.register_tool({
        "name": "video_download",
        "description": "Download video from Instagram/TikTok/YouTube and convert to H.264 for QuickTime compatibility on macOS.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Video URL from Instagram, TikTok, or YouTube"},
                "filename": {"type": "string", "description": "Output filename (optional, auto-generated if empty)"},
            },
            "required": ["url"],
        },
        "execute": execute_video_download,
    })