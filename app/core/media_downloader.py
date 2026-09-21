"""
Download Manager - yt-dlp Medya İndirme ve Ayrıştırma Motoru (media_downloader.py)

Bu modül, YouTube ve diğer desteklenen video platformlarından medya bilgilerini
(başlık, küçük resim, çözünürlük seçenekleri) çeker ve seçilen kalitede video/ses
akışını QThread içinde izole olarak indirir.
"""

import os
import re
import shutil
import time
import urllib.parse
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import QThread, pyqtSignal
import yt_dlp
import yt_dlp.extractor.common

from app.core.models import DownloadTask, DownloadStatus, TaskType

# HLS Master Playlist -> Sublist & Segment query token propagation patch
_orig_parse_m3u8 = yt_dlp.extractor.common.InfoExtractor._parse_m3u8_formats_and_subtitles

def _patched_parse_m3u8(self, m3u8_doc, m3u8_url=None, *args, **kwargs):
    if m3u8_url and '?' in m3u8_url and isinstance(m3u8_doc, str):
        base_query = urllib.parse.urlparse(m3u8_url).query
        if base_query:
            new_lines = []
            for line in m3u8_doc.splitlines():
                trimmed = line.strip()
                if trimmed and not trimmed.startswith('#'):
                    if '?' not in trimmed:
                        line = f"{trimmed}?{base_query}"
                elif 'URI="' in line:
                    def repl(m):
                        u = m.group(1)
                        return f'URI="{u}?{base_query}"' if '?' not in u else m.group(0)
                    line = re.sub(r'URI="([^"]+)"', repl, line)
                new_lines.append(line)
            m3u8_doc = '\n'.join(new_lines)

    return _orig_parse_m3u8(self, m3u8_doc, m3u8_url, *args, **kwargs)

yt_dlp.extractor.common.InfoExtractor._parse_m3u8_formats_and_subtitles = _patched_parse_m3u8


def get_ffmpeg_path() -> Optional[str]:
    """Sistemde veya paketlenmiş sanal ortamda ffmpeg çalıştırılabilir dosyasını bulur."""
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            ffmpeg_dir = os.path.dirname(exe)
            standard_ffmpeg = os.path.join(ffmpeg_dir, "ffmpeg.exe")
            if not os.path.exists(standard_ffmpeg):
                try:
                    shutil.copy2(exe, standard_ffmpeg)
                except Exception:
                    pass
            if os.path.exists(standard_ffmpeg):
                return standard_ffmpeg
            return exe
    except Exception:
        pass
    return None


def get_js_runtimes() -> dict:
    """YouTube imza çözme ve player API'si için kullanılabilir JS motorlarını döndürür."""
    if shutil.which("node"):
        return {"node": {}}
    if shutil.which("deno"):
        return {"deno": {}}
    return {}


def get_ytdl_base_opts(headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Tüm yt-dlp işlemleri için optimize edilmiş temel seçenekleri hazırlar."""
    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "noplaylist": True,
    }
    ffmpeg = get_ffmpeg_path()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg

    runtimes = get_js_runtimes()
    if runtimes:
        opts["js_runtimes"] = runtimes

    # Proxy yapılandırması
    try:
        from app.core.config import load_network_settings
        net_settings = load_network_settings()
        if net_settings.proxy_mode == "manual" and net_settings.proxy_host:
            auth = f"{net_settings.proxy_user}:{net_settings.proxy_password}@" if net_settings.proxy_user else ""
            opts["proxy"] = f"http://{auth}{net_settings.proxy_host}:{net_settings.proxy_port}"
        elif net_settings.proxy_mode == "system":
            import urllib.request
            sys_proxies = urllib.request.getproxies()
            if "https" in sys_proxies:
                opts["proxy"] = sys_proxies["https"]
            elif "http" in sys_proxies:
                opts["proxy"] = sys_proxies["http"]
    except Exception:
        pass

    # Standart modern tarayıcı başlıkları (bot ve DPI engellemelerini aşmak için)
    merged_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
    }
    if headers:
        merged_headers.update(headers)
        if "Referer" in headers and "Origin" not in merged_headers:
            ref = headers["Referer"]
            parsed_ref = urllib.parse.urlparse(ref)
            if parsed_ref.scheme and parsed_ref.netloc:
                merged_headers["Origin"] = f"{parsed_ref.scheme}://{parsed_ref.netloc}"
                merged_headers["Sec-Fetch-Mode"] = "cors"
                merged_headers["Sec-Fetch-Dest"] = "empty"
                merged_headers["Sec-Fetch-Site"] = "cross-site"
    opts["http_headers"] = merged_headers

    return opts


class MediaInfoExtractor(QThread):
    """
    Belirtilen medya URL'sini analiz ederek indirmeden önce format,
    kalite, süre ve başlık bilgilerini çeken QThread sınıfı.
    """

    metadata_ready = pyqtSignal(dict)    # Çıkarılan meta veri sözlüğü
    error_occurred = pyqtSignal(str)     # Hata mesajı

    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None, parent=None):
        super().__init__(parent)
        self.url = url
        self.headers = headers or {}

    def run(self) -> None:
        """yt-dlp extract_info metodunu indirme yapmadan (download=False) çalıştırır."""
        ydl_opts = get_ytdl_base_opts(self.headers)
        ydl_opts.update({
            "skip_download": True,
            "extract_flat": False,
        })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if not info:
                    self.error_occurred.emit("Failed to retrieve media information.")
                    return

                # Önemli format seçeneklerini çözünürlüklere göre grupla ve sırala
                formats_summary: List[Dict[str, Any]] = []
                formats = info.get("formats", [])

                # 1. Video çözünürlüklerini topla (yüksekten düşüğe)
                seen_heights = set()
                video_candidates = []
                for fmt in formats:
                    height = fmt.get("height")
                    vcodec = fmt.get("vcodec", "none")
                    if height and vcodec != "none":
                        video_candidates.append(fmt)

                # Yüksekliğe ve dosya boyutuna göre sırala
                video_candidates.sort(
                    key=lambda f: (f.get("height", 0) or 0, f.get("filesize") or f.get("filesize_approx") or 0),
                    reverse=True
                )

                for fmt in video_candidates:
                    h = fmt.get("height")
                    if not h or h in seen_heights:
                        continue
                    seen_heights.add(h)

                    ext = fmt.get("ext", "mp4")
                    format_id = fmt.get("format_id", "")
                    filesize = fmt.get("filesize") or fmt.get("filesize_approx") or 0

                    if h >= 2160:
                        res_title = f"4K UHD ({h}p)"
                    elif h >= 1440:
                        res_title = f"2K QHD ({h}p)"
                    elif h >= 1080:
                        res_title = f"1080p Full HD"
                    elif h >= 720:
                        res_title = f"720p HD"
                    else:
                        res_title = f"{h}p"

                    size_str = ""
                    if filesize > 0:
                        size_mb = filesize / (1024 * 1024)
                        size_str = f" (~{size_mb:.1f} MB)"

                    label = f"{res_title} - {ext.upper()}{size_str}"

                    formats_summary.append({
                        "format_id": f"height_{h}",
                        "raw_format_id": format_id,
                        "label": label,
                        "height": h,
                        "ext": ext,
                        "filesize": filesize,
                        "is_video": True
                    })

                # 2. Ses seçeneklerini ekle
                audio_seen = set()
                for fmt in formats:
                    vcodec = fmt.get("vcodec", "none")
                    acodec = fmt.get("acodec", "none")
                    ext = fmt.get("ext", "m4a")
                    filesize = fmt.get("filesize") or fmt.get("filesize_approx") or 0
                    if vcodec == "none" and acodec != "none" and ext not in audio_seen:
                        audio_seen.add(ext)
                        size_str = f" (~{filesize / (1024 * 1024):.1f} MB)" if filesize > 0 else ""
                        formats_summary.append({
                            "format_id": fmt.get("format_id", ""),
                            "label": f"Audio Only ({ext.upper()}){size_str}",
                            "height": 0,
                            "ext": ext,
                            "filesize": filesize,
                            "is_video": False
                        })

                payload = {
                    "url": self.url,
                    "title": info.get("title", "Video Stream"),
                    "thumbnail": info.get("thumbnail"),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader", "Unknown"),
                    "formats": formats_summary
                }
                self.metadata_ready.emit(payload)

        except Exception as exc:
            err_str = str(exc)
            if "10054" in err_str or "Connection reset" in err_str or "TransportError" in err_str:
                msg = (
                    "Connection reset by remote host [WinError 10054].\n"
                    "This website or video CDN is blocked by your ISP or firewall.\n"
                    "Please enable a system VPN (or set a Proxy in Network Settings) to access this content."
                )
            elif "404" in err_str or "Not Found" in err_str:
                msg = (
                    "Stream URL returned HTTP 404: Not Found.\n"
                    "The temporary security token of this stream has expired or is invalid.\n"
                    "Tip: On the movie site, try selecting another player source (e.g. Vidmoly / Rapidrame / Filemoon), play the video, and click '⚡ Download This Video' again."
                )
            elif "seg-" in self.url or ".ts" in self.url:
                msg = "Invalid stream fragment URL. Please refresh the page and select the main video stream."
            else:
                msg = f"Media extraction error: {err_str}"
            self.error_occurred.emit(msg)


class MediaDownloader(QThread):
    """
    Seçilen medya formatını arka planda indiren ve yt-dlp progress_hook
    üzerinden PyQt6 arayüzüne anlık hız, yüzde ve durum aktaran motor.
    """

    progress_updated = pyqtSignal(dict)      # İlerleme, hız, ETA sözlüğü
    status_changed = pyqtSignal(str, str)    # task_id, yeni_durum
    finished = pyqtSignal(str, str)          # task_id, dosya_yolu
    error_occurred = pyqtSignal(str, str)    # task_id, hata_mesajı

    def __init__(
        self,
        task: DownloadTask,
        format_id: Optional[str] = None,
        audio_only: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.task = task
        self.format_id = format_id
        self.audio_only = audio_only
        self._is_cancelled = False
        self._final_filepath = ""

    def cancel(self) -> None:
        """İndirmeyi iptal eder."""
        self._is_cancelled = True
        self.task.status = DownloadStatus.CANCELLED
        self.status_changed.emit(self.task.task_id, DownloadStatus.CANCELLED.value)

    def run(self) -> None:
        """yt-dlp ile indirmeyi başlatan ana iş parçacığı fonksiyonu."""
        self.task.status = DownloadStatus.DOWNLOADING
        self.status_changed.emit(self.task.task_id, DownloadStatus.DOWNLOADING.value)

        # Hedef şablon ve indirme seçeneklerini hazırla
        base_name = os.path.splitext(self.task.filename)[0] if self.task.filename else "%(title)s"
        out_template = os.path.join(self.task.destination_folder, f"{base_name}.%(ext)s")

        ydl_opts: Dict[str, Any] = get_ytdl_base_opts(self.task.headers)
        ydl_opts.update({
            "outtmpl": out_template,
            "progress_hooks": [self._progress_hook],
            "merge_output_format": "mp4",
        })

        has_ffmpeg = bool(get_ffmpeg_path())

        # Format seçimi
        if self.audio_only:
            if has_ffmpeg:
                ydl_opts["format"] = "bestaudio/best"
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]
            else:
                ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        elif self.format_id:
            if self.format_id.startswith("height_"):
                h = self.format_id.replace("height_", "")
                if has_ffmpeg:
                    ydl_opts["format"] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
                else:
                    ydl_opts["format"] = f"best[height<={h}]/best"
            else:
                if has_ffmpeg:
                    ydl_opts["format"] = f"{self.format_id}+bestaudio/best"
                else:
                    ydl_opts["format"] = f"{self.format_id}/best"
        else:
            if has_ffmpeg:
                ydl_opts["format"] = "bestvideo+bestaudio/best"
            else:
                ydl_opts["format"] = "best[ext=mp4]/best"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.task.url, download=True)
                if info:
                    self._final_filepath = ydl.prepare_filename(info)

            if self._is_cancelled:
                return

            # İndirme ve dönüştürme tamamlandı: Diskte oluşan gerçek dosyayı tespit et
            real_file_path = self._final_filepath
            if real_file_path and not os.path.exists(real_file_path):
                base, _ = os.path.splitext(real_file_path)
                for ext in [".mp4", ".mkv", ".mp3", ".m4a", ".webm"]:
                    cand = base + ext
                    if os.path.exists(cand):
                        real_file_path = cand
                        break

            if not real_file_path or not os.path.exists(real_file_path):
                base_cand = os.path.splitext(self.task.filename)[0]
                for ext in [".mp4", ".mkv", ".mp3", ".m4a", ".webm"]:
                    cand = os.path.join(self.task.destination_folder, base_cand + ext)
                    if os.path.exists(cand):
                        real_file_path = cand
                        break

            if real_file_path and os.path.exists(real_file_path):
                actual_name = os.path.basename(real_file_path)
                self.task.filename = actual_name
                actual_size = os.path.getsize(real_file_path)
                self.task.total_size = actual_size
                self.task.downloaded_size = actual_size
                self._final_filepath = real_file_path
            elif self.task.downloaded_size > 0 and self.task.total_size <= 0:
                self.task.total_size = self.task.downloaded_size

            self.task.status = DownloadStatus.COMPLETED
            self.task.completed_at = time.time()
            self.status_changed.emit(self.task.task_id, DownloadStatus.COMPLETED.value)
            self.finished.emit(self.task.task_id, real_file_path or self.task.final_file_path)

        except yt_dlp.utils.DownloadCancelled:
            self.task.status = DownloadStatus.CANCELLED
            self.status_changed.emit(self.task.task_id, DownloadStatus.CANCELLED.value)
        except Exception as exc:
            err_str = str(exc)
            if "10054" in err_str or "Connection reset" in err_str or "TransportError" in err_str:
                err_msg = (
                    "Connection reset by remote host [WinError 10054].\n"
                    "This website or stream is blocked by your ISP or firewall.\n"
                    "Please enable a system-wide VPN (or set a Proxy in Network Settings)."
                )
            elif "404" in err_str or "Not Found" in err_str:
                err_msg = (
                    "Stream URL returned 404: Not Found (Token expired).\n"
                    "Please refresh the movie page, select a player (like Vidmoly or Filemoon), and re-download."
                )
            else:
                err_msg = str(exc)
            self.task.status = DownloadStatus.FAILED
            self.task.error_message = err_msg
            self.status_changed.emit(self.task.task_id, DownloadStatus.FAILED.value)
            self.error_occurred.emit(self.task.task_id, err_msg)

    def _progress_hook(self, d: Dict[str, Any]) -> None:
        """yt-dlp'den gelen anlık verileri PyQt sinyaline dönüştürür."""
        if self._is_cancelled:
            raise yt_dlp.utils.DownloadCancelled("Download cancelled by user.")

        status = d.get("status")

        if status == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta")

            self.task.downloaded_size = downloaded
            if total > 0:
                self.task.total_size = total
            self.task.speed_bytes_per_sec = speed
            self.task.eta_seconds = eta

            effective_total = self.task.total_size
            percent = (downloaded / effective_total * 100.0) if effective_total > 0 else 0.0

            self.progress_updated.emit({
                "task_id": self.task.task_id,
                "downloaded_bytes": downloaded,
                "total_bytes": effective_total,
                "percent": percent,
                "speed_str": self.task.formatted_speed,
                "eta_str": self.task.formatted_eta,
                "speed_bps": speed
            })

        elif status == "finished":
            # İndirme bitti, birleştirme / ses dönüştürme aşaması
            self.task.status = DownloadStatus.MERGING
            self.status_changed.emit(self.task.task_id, DownloadStatus.MERGING.value)
