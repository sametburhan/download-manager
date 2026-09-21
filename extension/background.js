/**
 * Download Manager - Browser Background Service (background.js)
 * 
 * Responsibilities:
 * 1. Maintains WebSocket link with desktop app (ws://127.0.0.1:6800).
 * 2. Intercepts standard browser downloads and delegates them to desktop app.
 * 3. Deep-sniffs network requests for HLS (.m3u8), DASH (.mpd), and direct video streams.
 * 4. Tracks detected media per-tab, updates extension badge, and enables 1-click downloads.
 */

const WS_URL = "ws://127.0.0.1:6800";
let socket = null;
let isConnected = false;
let autoCaptureEnabled = true;
let heartbeatInterval = null;
let reconnectTimeout = null;

// Immediately restore autoCapture preference upon service worker wake-up
chrome.storage.local.get(["autoCapture"], (res) => {
  if (res && res.autoCapture !== undefined) {
    autoCaptureEnabled = Boolean(res.autoCapture);
  }
});

// ==================== Browser Startup & Session Guard ====================
let isStartingUp = true;
const extensionStartTime = Date.now();
const STARTUP_GRACE_PERIOD_MS = 5000; // 5-second shield against session-restored downloads on browser launch

function endStartupGracePeriod() {
  setTimeout(() => {
    isStartingUp = false;
    console.log("[Download Manager] Startup grace period ended. Interception active.");
  }, STARTUP_GRACE_PERIOD_MS);
}

endStartupGracePeriod();

if (chrome.runtime && chrome.runtime.onStartup) {
  chrome.runtime.onStartup.addListener(() => {
    isStartingUp = true;
    console.log("[Download Manager] Browser onStartup detected. Startup guard armed for 5 seconds.");
    endStartupGracePeriod();
  });
}

// Per-tab detected media cache: tabId -> Array<{ url, page_url, referrer, title, mime_type, quality, timestamp }>
const tabMedia = {};

// Per-tab cleared media URLs cache: tabId -> Set<string>
// Suppresses re-detection of items that the user explicitly cleared until page navigation
const clearedMediaUrlsByTab = {};

// File extensions to automatically intercept
const DEFAULT_CAPTURED_EXTENSIONS = [
  "zip", "rar", "7z", "tar", "gz", "bz2", "xz",
  "iso", "dmg", "exe", "msi", "apk", "bin",
  "mp4", "mkv", "avi", "mov", "flv", "wmv", "webm",
  "mp3", "flac", "wav", "aac", "ogg",
  "pdf", "epub", "doc", "docx", "xls", "xlsx"
];

// Anti-flood cache for stream detection
const recentlyDetectedMedia = new Set();

// Ad and analytics blacklist patterns
const AD_PATTERNS = [
  "googleads", "doubleclick", "googlesyndication", "adnxs", "adservice",
  "pagead", "analytics", "facebook.com/tr", "taboola", "outbrain",
  "scorecardresearch", "advertising.com", "popads", "popcash", "adsterra",
  "smartadserver", "yandex.ru/ads", "adcolony", "applovin", "unity3d"
];

function isAdUrl(url) {
  if (!url) return true;
  const lower = url.toLowerCase();
  return AD_PATTERNS.some(pat => lower.includes(pat));
}

// Media stream matching patterns
const STREAM_URL_REGEX = /\.(m3u8|mpd|mp4|webm|mkv|mov|avi|flv|m4v)(\?.*)?$/i;
const HLS_KEYWORD_REGEX = /(\/hls\/|\/playlist\.m3u8|\/master\.m3u8|\/index\.m3u8|\/manifest\.mpd|\.m3u8\?)/i;

function isMediaUrl(url) {
  if (isAdUrl(url)) return false;
  if (isChunkSegment(url)) return false;
  return STREAM_URL_REGEX.test(url) || HLS_KEYWORD_REGEX.test(url);
}

function isMediaContentType(contentType) {
  if (!contentType) return false;
  const ct = contentType.toLowerCase();
  if (ct.includes("mp2t")) return false; // Raw TS segment chunk
  return ct.includes("video/") || 
         ct.includes("application/vnd.apple.mpegurl") || 
         ct.includes("application/x-mpegurl") || 
         ct.includes("application/mpegurl") || 
         ct.includes("audio/mpegurl") || 
         ct.includes("audio/x-mpegurl") || 
         ct.includes("application/dash+xml");
}

function isChunkSegment(url) {
  if (!url) return true;
  const lower = url.toLowerCase();

  // Exclude raw YouTube video buffer chunks (which cause badge to explode into hundreds)
  if (lower.includes("googlevideo.com") || lower.includes("/videoplayback")) {
    return true;
  }

  // Exclude byte range requests, sequence numbers, and buffer chunks
  if (/[?&](range|sq|rn|rbuf|byterange)=/i.test(url)) {
    return true;
  }

  // Exclude individual short chunk segments from polluting the video list
  return /\.(ts|m4s|aac|key)(\?.*)?$/i.test(url) || 
         /(seg|segment|chunk|frag|fragment|part)[-_]?\d+/i.test(lower) || 
         /frag\(\d+\)/i.test(lower) ||
         /seg-\d+-v\d+/i.test(lower) ||
         lower.includes("/seg-");
}

// ==================== 1. WebSocket Client & Lifecycle ====================

// Queue for pending messages while WebSocket is connecting
const pendingMessages = [];

function flushPendingMessages() {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  while (pendingMessages.length > 0) {
    const msg = pendingMessages.shift();
    console.log("[Download Manager] Flushing queued message to desktop:", msg.action);
    try {
      socket.send(JSON.stringify(msg));
    } catch (e) {
      console.error("[Download Manager] Error sending queued message:", e);
      break;
    }
  }
}

function connectWebSocket() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      console.log("[Download Manager] Connected to desktop WebSocket server.");
      isConnected = true;
      updateGlobalBadge();
      flushPendingMessages();

      clearInterval(heartbeatInterval);
      heartbeatInterval = setInterval(() => {
        if (isConnected && socket && socket.readyState === WebSocket.OPEN) {
          sendSocketMessage("PING", {});
        }
      }, 20000);
    };

    socket.onmessage = (event) => {
      try {
        const response = JSON.parse(event.data);
        console.log("[Download Manager] Server response:", response);
      } catch (e) {
        // Raw message
      }
    };

    socket.onclose = () => handleDisconnect();
    socket.onerror = () => handleDisconnect();

  } catch (err) {
    handleDisconnect();
  }
}

function handleDisconnect() {
  isConnected = false;
  socket = null;
  updateGlobalBadge();
  clearInterval(heartbeatInterval);

  clearTimeout(reconnectTimeout);
  reconnectTimeout = setTimeout(() => {
    connectWebSocket();
  }, 5000);
}

function sendSocketMessage(action, payload) {
  const message = {
    action: action,
    payload: payload,
    timestamp: Date.now() / 1000
  };

  if (socket && socket.readyState === WebSocket.OPEN) {
    try {
      socket.send(JSON.stringify(message));
      return true;
    } catch (err) {
      console.error("[Download Manager] Failed to send socket message immediately:", err);
    }
  }

  // Socket is closed or connecting: queue message so it is delivered upon connection
  console.log(`[Download Manager] Socket not open (state: ${socket ? socket.readyState : 'null'}). Enqueueing message:`, action);
  pendingMessages.push(message);

  if (pendingMessages.length > 50) {
    pendingMessages.shift();
  }

  connectWebSocket();
  return true;
}

function updateGlobalBadge() {
  if (!isConnected) {
    chrome.action.setBadgeText({ text: "" });
    chrome.action.setTitle({ title: "Download Manager: Waiting for Desktop App" });
  }
}

function updateTabBadge(tabId) {
  if (!autoCaptureEnabled) {
    chrome.action.setBadgeText({ tabId: tabId, text: "OFF" });
    chrome.action.setBadgeBackgroundColor({ tabId: tabId, color: "#475569" });
    chrome.action.setTitle({ tabId: tabId, title: "Download Manager: Automatic Interception is Disabled" });
    return;
  }

  const count = (tabMedia[tabId] || []).length;
  if (count > 0) {
    chrome.action.setBadgeText({ tabId: tabId, text: String(count) });
    chrome.action.setBadgeBackgroundColor({ tabId: tabId, color: "#0078d4" });
    chrome.action.setTitle({ tabId: tabId, title: `Download Manager: ${count} video(s) found on this page!` });
  } else if (isConnected) {
    chrome.action.setBadgeText({ tabId: tabId, text: "ON" });
    chrome.action.setBadgeBackgroundColor({ tabId: tabId, color: "#107c41" });
  } else {
    chrome.action.setBadgeText({ tabId: tabId, text: "" });
  }
}

// ==================== 2. Media Tracking Registry ====================

function parsePlatformMedia(url, title) {
  if (!url) return null;

  // 1. YouTube (Watch, Shorts, Embed, Live, youtu.be)
  const ytMatch = url.match(/(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?.*v=|shorts\/|embed\/|live\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/i);
  if (ytMatch) {
    const videoId = ytMatch[1];
    let cleanTitle = title || "YouTube Video";
    cleanTitle = cleanTitle.replace(/^\([0-9]+\)\s*/, "").replace(/\s*-\s*YouTube$/, "").trim();
    if (!cleanTitle || cleanTitle.toLowerCase() === "youtube") {
      cleanTitle = `YouTube Video (${videoId})`;
    }

    return {
      url: `https://www.youtube.com/watch?v=${videoId}`,
      page_url: url,
      referrer: url,
      title: cleanTitle,
      mime_type: "video/mp4",
      quality: "YouTube (UHD / MP3)",
      source_type: "youtube",
      timestamp: Date.now()
    };
  }

  // 2. Vimeo
  const vimeoMatch = url.match(/(?:https?:\/\/)?(?:www\.)?vimeo\.com\/(\d+)/i);
  if (vimeoMatch) {
    let cleanTitle = (title || "Vimeo Video").replace(/\s*on Vimeo$/, "").trim();
    return {
      url: url,
      page_url: url,
      referrer: url,
      title: cleanTitle || "Vimeo Video",
      mime_type: "video/mp4",
      quality: "Vimeo HD",
      source_type: "vimeo",
      timestamp: Date.now()
    };
  }

  return null;
}

function recordMediaForTab(tabId, mediaItem) {
  if (!tabId || tabId < 0 || !autoCaptureEnabled) return;

  const cleanItemUrl = (mediaItem.url || "").split("#")[0];

  // If user explicitly cleared this URL on this tab, ignore it
  if (clearedMediaUrlsByTab[tabId] && clearedMediaUrlsByTab[tabId].has(cleanItemUrl)) {
    return;
  }

  if (!tabMedia[tabId]) {
    tabMedia[tabId] = [];
  }

  // Deduplicate by clean stream URL
  const exists = tabMedia[tabId].some(item => item.url.split("#")[0] === cleanItemUrl);
  if (!exists) {
    tabMedia[tabId].push(mediaItem);
    updateTabBadge(tabId);
    console.log(`[Download Manager] Video recorded for tab #${tabId}:`, mediaItem.title, mediaItem.quality);
  }
}

// Clear state when tab is closed
chrome.tabs.onRemoved.addListener((tabId) => {
  delete tabMedia[tabId];
  delete clearedMediaUrlsByTab[tabId];
});

// Update or re-detect when navigation happens
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!autoCaptureEnabled) {
    tabMedia[tabId] = [];
    updateTabBadge(tabId);
    return;
  }

  const currentUrl = changeInfo.url || (tab && tab.url);
  const currentTitle = changeInfo.title || (tab && tab.title);

  if (changeInfo.url) {
    tabMedia[tabId] = [];
    delete clearedMediaUrlsByTab[tabId];
    const platformMedia = parsePlatformMedia(changeInfo.url, currentTitle);
    if (platformMedia) {
      recordMediaForTab(tabId, platformMedia);
    } else {
      updateTabBadge(tabId);
    }
  } else if (changeInfo.title && currentUrl) {
    const platformMedia = parsePlatformMedia(currentUrl, changeInfo.title);
    if (platformMedia) {
      if (!tabMedia[tabId] || tabMedia[tabId].length === 0) {
        recordMediaForTab(tabId, platformMedia);
      } else {
        const item = tabMedia[tabId].find(m => m.source_type === "youtube" || m.url === platformMedia.url);
        if (item) {
          item.title = platformMedia.title;
        }
      }
    }
  }
});

// Update badge when user switches active tab
chrome.tabs.onActivated.addListener((activeInfo) => {
  updateTabBadge(activeInfo.tabId);
});

// ==================== 3. Download Interception ====================

// Cache to prevent re-processing the same download item multiple times
const processedDownloadIds = new Set();

chrome.downloads.onCreated.addListener((downloadItem) => {
  if (!autoCaptureEnabled || !isConnected) return;

  // 1. Guard against browser startup tab/history restoration burst
  if (isStartingUp) {
    console.log("[Download Manager] Ignoring download during browser startup guard period:", downloadItem.filename || downloadItem.url);
    return;
  }

  // 2. Prevent duplicate processing of already intercepted or seen download IDs
  if (downloadItem.id !== undefined && downloadItem.id !== null) {
    if (processedDownloadIds.has(downloadItem.id)) {
      return;
    }
  }

  // 3. Only intercept active "in_progress" downloads (ignore complete, interrupted, or paused)
  if (downloadItem.state && downloadItem.state !== "in_progress") {
    console.log("[Download Manager] Ignoring non-in-progress download state:", downloadItem.state, downloadItem.filename);
    return;
  }

  // 4. Ignore downloads that have already transferred bytes (resumed/restored from previous session)
  if (downloadItem.bytesReceived && downloadItem.bytesReceived > 0) {
    console.log("[Download Manager] Ignoring restored download with existing bytes:", downloadItem.bytesReceived, downloadItem.filename);
    return;
  }

  // 5. Ignore paused or resumable downloads
  if (downloadItem.paused || downloadItem.canResume) {
    console.log("[Download Manager] Ignoring paused/resumable download item:", downloadItem.filename);
    return;
  }

  // 6. Check download initiation timestamp: Must be initiated during the current extension session
  // and must be fresh (within 5 seconds)
  if (downloadItem.startTime) {
    const startTimeMs = new Date(downloadItem.startTime).getTime();
    const ageMs = Date.now() - startTimeMs;
    if (startTimeMs < (extensionStartTime - 1000) || ageMs > 5000) {
      console.log("[Download Manager] Ignoring stale/restored download item (age:", ageMs, "ms):", downloadItem.filename);
      return;
    }
  }

  // 7. Ignore browser internal schemes
  const url = downloadItem.url || downloadItem.finalUrl;
  if (!url || url.startsWith("blob:") || url.startsWith("data:") || url.startsWith("chrome:") || url.startsWith("chrome-extension:")) return;

  const filename = downloadItem.filename || url.split("?")[0].split("/").pop() || "";
  const ext = filename.split(".").pop().toLowerCase();

  const shouldCapture = DEFAULT_CAPTURED_EXTENSIONS.includes(ext) || downloadItem.totalBytes > 10 * 1024 * 1024;

  if (shouldCapture) {
    if (downloadItem.id !== undefined && downloadItem.id !== null) {
      processedDownloadIds.add(downloadItem.id);
      if (processedDownloadIds.size > 1000) {
        const first = processedDownloadIds.values().next().value;
        processedDownloadIds.delete(first);
      }
    }

    console.log("[Download Manager] Intercepting user-initiated download:", filename, url);

    const sent = sendSocketMessage("DOWNLOAD_URL", {
      url: url,
      filename: filename,
      referrer: downloadItem.referrer || "",
      user_agent: navigator.userAgent
    });

    if (sent) {
      setTimeout(() => {
        chrome.downloads.cancel(downloadItem.id, () => {
          chrome.downloads.erase({ id: downloadItem.id });
        });
      }, 50);
    }
  }
});


// ==================== 4. Advanced Network Media Sniffer ====================

function processPotentialMediaRequest(details, contentType = "") {
  if (!autoCaptureEnabled) return;
  const url = details.url;
  if (!details.tabId || details.tabId < 0) return;
  if (isAdUrl(url)) return;
  if (isChunkSegment(url)) return;

  const matchedByUrl = isMediaUrl(url);
  const matchedByHeader = isMediaContentType(contentType);

  if (!matchedByUrl && !matchedByHeader) return;

  // Deduplicate rapid requests
  if (recentlyDetectedMedia.has(url)) return;
  recentlyDetectedMedia.add(url);
  setTimeout(() => recentlyDetectedMedia.delete(url), 30000);

  // Retrieve top-level tab title and main page context
  chrome.tabs.get(details.tabId, (tab) => {
    if (chrome.runtime.lastError || !tab) return;

    let rawTitle = tab.title || "Video Stream";
    let cleanTitle = rawTitle.replace(/^\([0-9]+\)\s*/, "").replace(/\s*-\s*YouTube$/, "").trim();

    let qualityLabel = "HLS Stream";
    if (url.includes(".mpd")) {
      qualityLabel = "DASH";
    } else if (url.includes(".m3u8") || contentType.includes("mpegurl")) {
      qualityLabel = "HLS (m3u8)";
    } else if (url.includes(".mp4") || contentType.includes("mp4")) {
      qualityLabel = "MP4";
    } else if (url.includes(".webm")) {
      qualityLabel = "WebM";
    }

    const referrer = details.initiator || details.documentUrl || tab.url || "";

    recordMediaForTab(details.tabId, {
      url: url,
      page_url: tab.url,
      referrer: referrer,
      title: cleanTitle || "Video Stream",
      mime_type: contentType || "video/mp4",
      quality: qualityLabel,
      timestamp: Date.now(),
      source_type: "stream"
    });
  });
}

if (chrome.webRequest && chrome.webRequest.onHeadersReceived) {
  chrome.webRequest.onHeadersReceived.addListener(
    (details) => {
      const headers = details.responseHeaders || [];
      let ct = "";
      for (const h of headers) {
        if (h.name.toLowerCase() === "content-type") {
          ct = (h.value || "").toLowerCase();
          break;
        }
      }
      processPotentialMediaRequest(details, ct);
    },
    { urls: ["<all_urls>"] },
    ["responseHeaders"]
  );
}

if (chrome.webRequest && chrome.webRequest.onBeforeRequest) {
  chrome.webRequest.onBeforeRequest.addListener(
    (details) => {
      if (isMediaUrl(details.url)) {
        processPotentialMediaRequest(details, "");
      }
    },
    { urls: ["<all_urls>"] }
  );
}

// ==================== 5. Context Menu ====================

function showExtensionNotification(title, message) {
  try {
    if (chrome.notifications && chrome.notifications.create) {
      chrome.notifications.create({
        type: "basic",
        iconUrl: "icons/icon48.png",
        title: title,
        message: message
      }, () => {
        if (chrome.runtime.lastError) {}
      });
    }
  } catch (e) {}
}

function setupContextMenu() {
  if (!chrome.contextMenus) return;
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "dm_download_link",
      title: "Download with Download Manager",
      contexts: ["link", "video", "audio", "image", "selection", "page"]
    }, () => {
      if (chrome.runtime.lastError) {}
    });
  });
}

chrome.runtime.onInstalled.addListener(() => {
  setupContextMenu();

  chrome.storage.local.get(["autoCapture"], (res) => {
    if (res && res.autoCapture !== undefined) autoCaptureEnabled = res.autoCapture;
  });

  connectWebSocket();
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "dm_download_link") {
    let targetUrl = info.linkUrl || info.srcUrl;
    if (!targetUrl && info.selectionText) {
      const trimmed = info.selectionText.trim();
      if (trimmed.startsWith("http://") || trimmed.startsWith("https://") || trimmed.startsWith("ftp://") || trimmed.startsWith("file://")) {
        targetUrl = trimmed;
      }
    }
    if (!targetUrl) {
      targetUrl = info.pageUrl;
    }

    if (targetUrl) {
      let filename = "";
      try {
        const u = new URL(targetUrl);
        const name = u.pathname.split("/").pop();
        if (name && name.includes(".")) {
          filename = decodeURIComponent(name);
        }
      } catch (e) {
        const clean = targetUrl.split("?")[0].split("#")[0];
        const name = clean.split("/").pop();
        if (name && name.includes(".")) {
          filename = name;
        }
      }

      console.log("[Download Manager] Context menu download requested:", targetUrl, "Filename:", filename);

      const payload = {
        url: targetUrl,
        filename: filename || undefined,
        referrer: tab ? tab.url : "",
        user_agent: navigator.userAgent
      };

      sendSocketMessage("DOWNLOAD_URL", payload);

      if (!isConnected) {
        setTimeout(() => {
          if (!isConnected) {
            console.warn("[Download Manager] Desktop application is not reachable at ws://127.0.0.1:6800");
            showExtensionNotification(
              "Download Manager",
              "Desktop application is not running. Please launch Download Manager to download."
            );
          }
        }, 2500);
      }
    }
  }
});

// ==================== 6. Extension Messaging ====================

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "GET_STATUS") {
    sendResponse({
      isConnected: isConnected,
      autoCapture: autoCaptureEnabled,
      serverUrl: WS_URL
    });
  } else if (request.type === "GET_TAB_MEDIA") {
    if (!autoCaptureEnabled) {
      sendResponse({ mediaList: [] });
      return;
    }

    const tabId = request.tabId;
    const existingList = tabMedia[tabId] || [];

    if (existingList.length === 0 && tabId) {
      chrome.tabs.get(tabId, (tab) => {
        if (!chrome.runtime.lastError && tab && tab.url) {
          const platformMedia = parsePlatformMedia(tab.url, tab.title);
          if (platformMedia) {
            const cleanUrl = platformMedia.url.split("#")[0];
            // Only auto-record if not previously cleared by user on this tab
            if (!clearedMediaUrlsByTab[tabId] || !clearedMediaUrlsByTab[tabId].has(cleanUrl)) {
              recordMediaForTab(tabId, platformMedia);
              sendResponse({ mediaList: [platformMedia] });
              return;
            }
          }
        }
        sendResponse({ mediaList: [] });
      });
      return true; // Keep message channel open for async response
    } else {
      sendResponse({
        mediaList: existingList
      });
    }
  } else if (request.type === "CLEAR_TAB_MEDIA") {
    const tabId = request.tabId;
    if (tabId) {
      if (!clearedMediaUrlsByTab[tabId]) {
        clearedMediaUrlsByTab[tabId] = new Set();
      }
      // Snapshot all current tab media URLs into cleared set
      if (tabMedia[tabId]) {
        tabMedia[tabId].forEach(item => {
          if (item && item.url) {
            clearedMediaUrlsByTab[tabId].add(item.url.split("#")[0]);
          }
        });
      }
      // Also add any URLs explicitly passed in request
      if (Array.isArray(request.clearedUrls)) {
        request.clearedUrls.forEach(u => {
          if (u) clearedMediaUrlsByTab[tabId].add(u.split("#")[0]);
        });
      }

      tabMedia[tabId] = [];
      updateTabBadge(tabId);
    }
    sendResponse({ success: true });
  } else if (request.type === "RESCAN_TAB_MEDIA") {
    const tabId = request.tabId;
    if (tabId) {
      delete clearedMediaUrlsByTab[tabId];
      tabMedia[tabId] = [];
      updateTabBadge(tabId);
    }
    sendResponse({ success: true });
  } else if (request.type === "MEDIA_FOUND") {
    if (!autoCaptureEnabled) {
      sendResponse({ success: false, reason: "AUTO_CAPTURE_DISABLED" });
      return;
    }

    // Media reported from content.js
    const targetTabId = (sender && sender.tab) ? sender.tab.id : request.tabId;
    if (targetTabId) {
      recordMediaForTab(targetTabId, {
        url: request.payload.url,
        page_url: request.payload.page_url,
        referrer: request.payload.referrer || (sender && sender.tab ? sender.tab.url : ""),
        title: request.payload.title,
        mime_type: request.payload.mime_type || "video/mp4",
        quality: request.payload.quality || "MP4",
        source_type: request.payload.source_type || "stream",
        timestamp: Date.now()
      });
    }
    sendResponse({ success: true });
  } else if (request.type === "DOWNLOAD_MEDIA_DIRECT") {
    if (!autoCaptureEnabled) {
      sendResponse({ success: false, reason: "AUTO_CAPTURE_DISABLED" });
      return;
    }

    // Download action triggered by user from popup or floating button
    if (!isConnected) connectWebSocket();
    const payload = {
      ...request.payload,
      user_agent: navigator.userAgent
    };
    const sent = sendSocketMessage("MEDIA_DETECTED", payload);
    sendResponse({ success: sent });
  } else if (request.type === "TOGGLE_AUTO_CAPTURE") {
    autoCaptureEnabled = Boolean(request.enabled);
    chrome.storage.local.set({ autoCapture: autoCaptureEnabled });
    if (!autoCaptureEnabled) {
      for (const tabId in tabMedia) {
        tabMedia[tabId] = [];
      }
      for (const tabId in clearedMediaUrlsByTab) {
        delete clearedMediaUrlsByTab[tabId];
      }
    }
    chrome.tabs.query({}, (tabs) => {
      tabs.forEach(t => updateTabBadge(t.id));
    });
    sendResponse({ success: true, autoCapture: autoCaptureEnabled });
  } else if (request.type === "SEND_MANUAL_URL") {
    const sent = sendSocketMessage("DOWNLOAD_URL", {
      url: request.url,
      user_agent: navigator.userAgent
    });
    sendResponse({ success: sent });
  } else if (request.type === "RECONNECT") {
    connectWebSocket();
    sendResponse({ success: true });
  }
  return true;
});

setupContextMenu();
connectWebSocket();
