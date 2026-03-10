"""
Video download tool with H.264 auto-conversion for QuickTime compatibility.
Uses yt-dlp for downloading and ffmpeg for conversion.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path


def register(api):
    def execute_video_download(url="", filename="", **kwargs):
        if not url:
            return json.dumps({"status": "error", "error": "url is required"})
        
        # Detect platform
        url_lower = url.lower()
        if "instagram.com" in url_lower:
            platform = "instagram"
        elif "tiktok.com" in url_lower:
            platform = "tiktok"
        else:
            platform = "unknown"
        
        try:
            # Create temp dir for download
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                
                # Download with yt-dlp
                api.log(f"Downloading {platform} video from {url}...")
                
                # yt-dlp command - extract best video+audio
                ytdlp_cmd = [
                    "yt-dlp",
                    "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "--no-playlist",
                    "--output", str(tmpdir_path / "video.%(ext)s"),
                    url
                ]
                
                result = subprocess.run(
                    ytdlp_cmd,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode != 0:
                    api.log(f"yt-dlp error: {result.stderr}")
                    return json.dumps({"status": "error", "error": f"Download failed: {result.stderr[:200]}"})
                
                # Find downloaded file
                downloaded_files = list(tmpdir_path.glob("video.*"))
                if not downloaded_files:
                    return json.dumps({"status": "error", "error": "No video file found after download"})
                
                input_file = downloaded_files[0]
                
                # Convert to H.264 + AAC using ffmpeg
                output_filename = filename or f"{platform}_{input_file.stem}.mp4"
                output_path = Path.home() / "Downloads" / output_filename
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                api.log(f"Converting to H.264 for QuickTime compatibility...")
                
                # ffmpeg conversion to H.264/AAC
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", str(input_file),
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "23",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    "-y",
                    str(output_path)
                ]
                
                result = subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                
                if result.returncode != 0:
                    api.log(f"ffmpeg error: {result.stderr}")
                    return json.dumps({"status": "error", "error": f"Conversion failed: {result.stderr[:200]}"})
                
                file_size = output_path.stat().st_size
                
                return json.dumps({
                    "status": "ok",
                    "path": str(output_path),
                    "filename": output_filename,
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
        "description": "Download Instagram or TikTok videos and auto-convert to H.264 for QuickTime compatibility on macOS.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL of the Instagram or TikTok video to download"},
                "filename": {"type": "string", "description": "Optional output filename (default: auto-generated)"}
            },
            "required": ["url"]
        },
        "execute": execute_video_download
    })