"""
Video download tool — downloads videos from X, Instagram, TikTok, YouTube, etc.
Optionally converts to H.264/AAC for QuickTime compatibility (macOS only by default).
"""
import json
import platform
import subprocess
import tempfile
from pathlib import Path

_PLATFORM_HINTS = {
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "x.com": "x",
    "twitter.com": "x",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
}

_IS_MACOS = platform.system() == "Darwin"


def register(api):
    def execute_video_download(url="", filename="", convert="auto", **kwargs):
        if not url:
            return json.dumps({"status": "error", "error": "url is required"})

        url_lower = url.lower()
        source = "video"
        for domain, name in _PLATFORM_HINTS.items():
            if domain in url_lower:
                source = name
                break

        should_convert = (
            convert == "yes"
            or (convert == "auto" and _IS_MACOS)
        )

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)

                api.log(f"Downloading {source} video from {url}...")

                ytdlp_cmd = [
                    "yt-dlp",
                    "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "--no-playlist",
                    "--output", str(tmpdir_path / "video.%(ext)s"),
                    url,
                ]

                result = subprocess.run(
                    ytdlp_cmd,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                if result.returncode != 0:
                    api.log(f"yt-dlp failed: {result.stderr[:120]}")
                    return json.dumps({"status": "error", "error": f"Download failed: {result.stderr[:200]}"})

                downloaded_files = list(tmpdir_path.glob("video.*"))
                if not downloaded_files:
                    return json.dumps({"status": "error", "error": "No video file found after download"})

                input_file = downloaded_files[0]
                output_filename = filename or f"{source}_{input_file.stem}.mp4"
                output_path = Path.home() / "Downloads" / output_filename
                output_path.parent.mkdir(parents=True, exist_ok=True)

                if should_convert:
                    api.log("Converting to H.264/AAC for QuickTime compatibility (macOS)...")

                    ffmpeg_cmd = [
                        "ffmpeg", "-nostdin",
                        "-i", str(input_file),
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "aac", "-b:a", "128k",
                        "-movflags", "+faststart",
                        "-y", str(output_path),
                    ]

                    result = subprocess.run(
                        ffmpeg_cmd,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        timeout=240,
                    )

                    if result.returncode != 0:
                        api.log(f"ffmpeg failed: {result.stderr[:120]}")
                        return json.dumps({"status": "error", "error": f"Conversion failed: {result.stderr[:200]}"})
                else:
                    import shutil
                    shutil.copy2(str(input_file), str(output_path))

                api.log(f"Video saved to {output_path}")
                file_size = output_path.stat().st_size

                return json.dumps({
                    "status": "ok",
                    "path": str(output_path),
                    "filename": output_filename,
                    "platform": source,
                    "converted": should_convert,
                    "size_bytes": file_size,
                    "size_mb": round(file_size / (1024 * 1024), 2),
                })

        except subprocess.TimeoutExpired:
            return json.dumps({"status": "error", "error": "Download/conversion timed out"})
        except Exception as e:
            api.log(f"Video download error: {e}")
            return json.dumps({"status": "error", "error": str(e)[:200]})

    api.register_tool({
        "name": "video_download",
        "description": (
            "Download a video from X/Twitter, Instagram, TikTok, YouTube, or any yt-dlp-supported site. "
            "Returns the local file path. On macOS the video is auto-converted to H.264 MP4 for QuickTime; "
            "on other OSes (or when convert='no') the raw download is kept as-is. "
            "If you only need the video for transcription or analysis, set convert='no' to skip conversion and save time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL of the video to download",
                },
                "filename": {
                    "type": "string",
                    "description": "Optional output filename (default: auto-generated)",
                },
                "convert": {
                    "type": "string",
                    "enum": ["auto", "yes", "no"],
                    "description": (
                        "H.264 conversion mode. 'auto' = convert on macOS only (default). "
                        "'no' = skip conversion (faster, use when video is for transcription/analysis). "
                        "'yes' = always convert."
                    ),
                },
            },
            "required": ["url"],
        },
        "execute": execute_video_download,
    })
