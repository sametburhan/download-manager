/**
 * Download Manager - Enhanced Content Script (content.js)
 * 
 * Responsibilities:
 * 1. Deep DOM and iframe inspection for HTML5 <video>, YouTube, Vimeo, and streaming players.
 * 2. Parses inline script configurations for HLS (.m3u8) / MP4 streams in movie/series players.
 * 3. Injects modern floating "⚡ Download This Video" button over video players.
 * 4. Syncs detected media with background service and popup.
 */

const reportedMediaMap = new Map();
const clearedMediaKeys = new Set();
let autoCaptureEnabled = true;

// Restore persistent auto-capture state from chrome storage
chrome.storage.local.get(["autoCapture"], (res) => {
  if (res && res.autoCapture !== undefined) {
    autoCaptureEnabled = Boolean(res.autoCapture);
    if (!autoCaptureEnabled) {
      reportedMediaMap.clear();
      clearedMediaKeys.clear();
    }
  }
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.autoCapture !== undefined) {
    autoCaptureEnabled = Boolean(changes.autoCapture.newValue);
    if (!autoCaptureEnabled) {
      reportedMediaMap.clear();
      clearedMediaKeys.clear();
      document.querySelectorAll(".dm-floating-btn").forEach(btn => {
        btn.style.display = "none";
      });
    } else {
      syncDetectedMediaToBackground();
    }
  }
});

/**
 * Clean up page title removing notification numbers and platform suffixes.
 */
function getCleanPageTitle() {
  // 1. YouTube specific title selectors
  const ytTitleEl = document.querySelector("ytd-watch-metadata #title h1 yt-formatted-string") ||
                    document.querySelector("ytd-watch-metadata #title h1") ||
                    document.querySelector("h1.ytd-video-primary-info-renderer") ||
                    document.querySelector("#title.ytd-watch-flexy h1") ||
                    document.querySelector("#title.ytd-watch-metadata") ||
                    document.querySelector(".ytd-shorts-player-container h2") ||
                    document.querySelector("ytd-reel-player-header-renderer h2");
  if (ytTitleEl && ytTitleEl.textContent.trim()) {
    return ytTitleEl.textContent.trim();
  }

  // 2. OpenGraph / Twitter meta titles
  const ogTitle = document.querySelector('meta[property="og:title"]');
  if (ogTitle && ogTitle.content && ogTitle.content.trim()) {
    return ogTitle.content.trim();
  }

  const twTitle = document.querySelector('meta[name="twitter:title"]');
  if (twTitle && twTitle.content && twTitle.content.trim()) {
    return twTitle.content.trim();
  }

  // 3. Fallback to document title
  let title = document.title || "YouTube Video";
  title = title.replace(/^\([0-9]+\)\s*/, "");
  title = title.replace(/\s*-\s*YouTube$/, "");
  return title.trim() || "YouTube Video";
}

/**
 * Returns human-readable resolution badge for a video element.
 */
function getResolutionBadge(video) {
  if (video && video.videoHeight) {
    const h = video.videoHeight;
    if (h >= 2160) return "4K UHD";
    if (h >= 1440) return "2K QHD";
    if (h >= 1080) return "1080p FHD";
    if (h >= 720) return "720p HD";
    if (h >= 480) return "480p";
    if (h >= 360) return "360p";
    return `${h}p`;
  }
  return "HD";
}

/**
 * Scans page scripts for embedded player stream URLs (.m3u8 / .mp4).
 */
function scanScriptsForStreamUrls() {
  const streamUrls = [];
  const scriptTags = document.querySelectorAll("script");
  const regex = /["'](https?:\/\/[^"'\s]+\.(?:m3u8|mp4|webm)[^"'\s]*)["']/gi;

  scriptTags.forEach((script) => {
    const text = script.textContent;
    if (!text || (!text.includes(".m3u8") && !text.includes(".mp4"))) return;

    let match;
    while ((match = regex.exec(text)) !== null) {
      const foundUrl = match[1];
      if (!foundUrl.includes("googleads") && !foundUrl.includes("doubleclick")) {
        streamUrls.push(foundUrl);
      }
    }
  });

  return streamUrls;
}

/**
 * Detects all media elements on the current page / frame.
 */
function detectAllPageMedia() {
  if (!autoCaptureEnabled) return [];
  const mediaList = [];
  const pageUrl = window.location.href;
  const isYouTube = window.location.hostname.includes("youtube.com") || window.location.hostname.includes("youtu.be");
  const isVimeo = window.location.hostname.includes("vimeo.com");

  // 1. YouTube Specialized Detection (Highest Priority)
  const isYouTubeVideo = isYouTube && (
    window.location.pathname.startsWith("/watch") ||
    window.location.pathname.startsWith("/shorts/") ||
    window.location.pathname.startsWith("/embed/") ||
    window.location.pathname.startsWith("/live/")
  );

  if (isYouTubeVideo) {
    const ytTitle = getCleanPageTitle();
    const ytVideo = document.querySelector("video.html5-main-video") || document.querySelector("video");
    const resBadge = ytVideo ? getResolutionBadge(ytVideo) : "YouTube (UHD / MP3)";

    mediaList.push({
      url: pageUrl,
      page_url: pageUrl,
      referrer: document.referrer || pageUrl,
      title: ytTitle,
      mime_type: "video/mp4",
      quality: resBadge,
      source_type: "youtube"
    });
  }

  // 2. Vimeo Specialized Detection
  if (isVimeo && window.location.pathname.match(/\/\d+/)) {
    mediaList.push({
      url: pageUrl,
      page_url: pageUrl,
      referrer: document.referrer || pageUrl,
      title: getCleanPageTitle(),
      mime_type: "video/mp4",
      quality: "Vimeo HD",
      source_type: "vimeo"
    });
  }

  // 3. Scan Embedded Player Scripts for Direct HLS / MP4 Streams (Movie & Series Sites)
  const scriptStreams = scanScriptsForStreamUrls();
  scriptStreams.forEach((streamUrl, idx) => {
    const isM3U8 = streamUrl.includes(".m3u8");
    mediaList.push({
      url: streamUrl,
      page_url: pageUrl,
      referrer: pageUrl,
      title: getCleanPageTitle() || `Stream #${idx + 1}`,
      mime_type: isM3U8 ? "application/x-mpegurl" : "video/mp4",
      quality: isM3U8 ? "HLS (m3u8)" : "MP4 Stream",
      source_type: "stream"
    });
  });

  // 4. Standard HTML5 <video> Tags
  const videos = document.querySelectorAll("video");
  videos.forEach((video, idx) => {
    if (isYouTube && mediaList.some(m => m.source_type === "youtube")) {
      return;
    }

    let src = video.currentSrc || video.src;

    if (!src) {
      const sourceEl = video.querySelector("source[src]");
      if (sourceEl) src = sourceEl.src;
    }

    if (src && (src.startsWith("http://") || src.startsWith("https://") || src.startsWith("blob:"))) {
      const isBlob = src.startsWith("blob:");
      // For blob streams, pass pageUrl so background or yt-dlp can resolve the frame/page
      const finalUrl = isBlob ? pageUrl : src;
      const resBadge = getResolutionBadge(video);

      if (!mediaList.some(m => m.url === finalUrl)) {
        mediaList.push({
          url: finalUrl,
          page_url: pageUrl,
          referrer: document.referrer || pageUrl,
          title: getCleanPageTitle() || `Video #${idx + 1}`,
          mime_type: "video/mp4",
          quality: isBlob ? `Stream (${resBadge})` : resBadge,
          source_type: isBlob ? "stream" : "direct"
        });
      }
    }
  });

  return mediaList;
}

/**
 * Synchronizes detected media to the background service worker.
 */
function syncDetectedMediaToBackground() {
  if (!autoCaptureEnabled) return;
  const found = detectAllPageMedia();
  found.forEach(item => {
    const cleanUrl = (item.url || "").split("#")[0];
    const key = item.url + "|" + item.title;
    // Suppress videos that the user explicitly cleared on this page
    if (clearedMediaKeys.has(cleanUrl) || clearedMediaKeys.has(key)) {
      return;
    }
    if (!reportedMediaMap.has(key)) {
      reportedMediaMap.set(key, true);
      chrome.runtime.sendMessage({
        type: "MEDIA_FOUND",
        payload: item
      });
    }
  });
}

/**
 * Attaches listeners and floating download button to video players.
 */
function attachListenersToVideos() {
  const videos = document.querySelectorAll("video");

  videos.forEach((video) => {
    if (video.dataset.dmAttached) return;
    video.dataset.dmAttached = "true";

    const triggerSync = () => {
      syncDetectedMediaToBackground();
    };

    video.addEventListener("play", triggerSync);
    video.addEventListener("loadedmetadata", triggerSync);
    video.addEventListener("timeupdate", triggerSync, { once: true });

    attachFloatingDownloadButton(video);
  });
}

/**
 * Injects floating "⚡ Download This Video" button over video player container.
 */
function attachFloatingDownloadButton(video) {
  const isYouTube = window.location.hostname.includes("youtube.com");
  const container = isYouTube
    ? (document.querySelector("#movie_player") || document.querySelector(".html5-video-player") || video.parentElement)
    : (video.parentElement || video.parentNode);
  if (!container || container.querySelector(".dm-floating-btn")) return;

  const btn = document.createElement("div");
  btn.className = "dm-floating-btn";
  btn.innerHTML = "⚡ Download This Video";

  Object.assign(btn.style, {
    position: "absolute",
    top: "14px",
    right: "14px",
    zIndex: "2147483647",
    backgroundColor: "rgba(15, 17, 23, 0.90)",
    color: "#ffffff",
    padding: "7px 15px",
    borderRadius: "8px",
    fontSize: "12px",
    fontWeight: "bold",
    fontFamily: "Segoe UI, -apple-system, sans-serif",
    cursor: "pointer",
    display: "none",
    boxShadow: "0 4px 18px rgba(0,0,0,0.65)",
    border: "1px solid #3b82f6",
    backdropFilter: "blur(10px)",
    transition: "transform 0.15s ease, background-color 0.15s ease",
    pointerEvents: "auto",
    userSelect: "none"
  });

  const parentStyle = window.getComputedStyle(container);
  if (parentStyle.position === "static") {
    container.style.position = "relative";
  }

  container.addEventListener("mouseenter", () => {
    if (autoCaptureEnabled) {
      btn.style.display = "block";
    }
  });
  container.addEventListener("mouseleave", () => { btn.style.display = "none"; });

  btn.addEventListener("mouseenter", () => {
    btn.style.backgroundColor = "#2563eb";
    btn.style.transform = "scale(1.04)";
  });
  btn.addEventListener("mouseleave", () => {
    btn.style.backgroundColor = "rgba(15, 17, 23, 0.90)";
    btn.style.transform = "scale(1)";
  });

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    e.preventDefault();

    if (!autoCaptureEnabled) {
      btn.innerHTML = "⚠️ Please enable Interception!";
      btn.style.backgroundColor = "#dc2626";
      setTimeout(() => {
        btn.innerHTML = "⚡ Download This Video";
        btn.style.backgroundColor = "rgba(15, 17, 23, 0.90)";
      }, 3000);
      return;
    }

    btn.innerHTML = "⏳ Opening...";
    const src = video.currentSrc || video.src || window.location.href;

    chrome.runtime.sendMessage({
      type: "DOWNLOAD_MEDIA_DIRECT",
      payload: {
        url: window.location.href,
        page_url: window.location.href,
        referrer: document.referrer || window.location.href,
        media_src: src,
        title: getCleanPageTitle()
      }
    }, (response) => {
      if (response && response.reason === "AUTO_CAPTURE_DISABLED") {
        btn.innerHTML = "⚠️ Interception is Disabled!";
        btn.style.backgroundColor = "#dc2626";
        setTimeout(() => {
          btn.innerHTML = "⚡ Download This Video";
          btn.style.backgroundColor = "rgba(15, 17, 23, 0.90)";
        }, 3000);
        return;
      }

      if (chrome.runtime.lastError || !response || !response.success) {
        btn.innerHTML = "❌ App Not Running!";
        btn.style.backgroundColor = "#dc2626";
        setTimeout(() => {
          btn.innerHTML = "⚡ Download This Video";
          btn.style.backgroundColor = "rgba(15, 17, 23, 0.90)";
        }, 3000);
        return;
      }

      btn.innerHTML = "✅ Sent!";
      btn.style.backgroundColor = "#16a34a";
      setTimeout(() => {
        btn.innerHTML = "⚡ Download This Video";
        btn.style.backgroundColor = "rgba(15, 17, 23, 0.90)";
      }, 2500);
    });
  });

  container.appendChild(btn);
}

// ==================== Communication Listeners ====================

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "SCAN_MEDIA" || request.type === "GET_PAGE_VIDEOS") {
    if (request.resetCleared) {
      clearedMediaKeys.clear();
    }
    const all = detectAllPageMedia();
    const list = all.filter(item => {
      const cleanUrl = (item.url || "").split("#")[0];
      const key = item.url + "|" + item.title;
      return !clearedMediaKeys.has(cleanUrl) && !clearedMediaKeys.has(key);
    });
    sendResponse({ mediaList: list, isTop: window === window.top });
  } else if (request.type === "CLEAR_PAGE_MEDIA") {
    // Snapshot all currently detectable items as cleared
    const current = detectAllPageMedia();
    current.forEach(item => {
      if (item.url) clearedMediaKeys.add(item.url.split("#")[0]);
      clearedMediaKeys.add(item.url + "|" + item.title);
    });
    // Also include any explicitly passed URLs from popup
    if (Array.isArray(request.clearedUrls)) {
      request.clearedUrls.forEach(u => {
        if (u) clearedMediaKeys.add(u.split("#")[0]);
      });
    }
    // Retain reportedMediaMap keys in cleared set to prevent re-discovery
    for (const key of reportedMediaMap.keys()) {
      clearedMediaKeys.add(key);
    }
    sendResponse({ success: true });
  }
  return true;
});

// ==================== Initialization & Page Mutation Observers ====================

attachListenersToVideos();
syncDetectedMediaToBackground();

const observer = new MutationObserver(() => {
  attachListenersToVideos();
});
observer.observe(document.body || document.documentElement, { childList: true, subtree: true });

// YouTube and SPA Navigation Event Listeners
let lastRecordedHref = window.location.href;
function handleSpaNavigation() {
  if (window.location.href !== lastRecordedHref) {
    lastRecordedHref = window.location.href;
    clearedMediaKeys.clear();
    reportedMediaMap.clear();
    setTimeout(() => {
      attachListenersToVideos();
      syncDetectedMediaToBackground();
    }, 400);
  }
}

setInterval(handleSpaNavigation, 1200);
window.addEventListener("yt-navigate-finish", handleSpaNavigation);
window.addEventListener("yt-page-data-updated", handleSpaNavigation);
window.addEventListener("popstate", handleSpaNavigation);
