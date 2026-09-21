/**
 * Download Manager - Popup Logic (popup.js)
 * 
 * Lists detected media on the page, communicates in real time with content.js,
 * and launches the download dialog on the desktop application upon user selection.
 */

document.addEventListener("DOMContentLoaded", () => {
  const statusBadge = document.getElementById("statusBadge");
  const statusText = document.getElementById("statusText");
  const autoCaptureToggle = document.getElementById("autoCaptureToggle");
  const manualUrlInput = document.getElementById("manualUrlInput");
  const sendUrlBtn = document.getElementById("sendUrlBtn");
  const reconnectBtn = document.getElementById("reconnectBtn");
  const feedbackMsg = document.getElementById("feedbackMsg");
  const mediaFeedbackMsg = document.getElementById("mediaFeedbackMsg");
  const mediaCountBadge = document.getElementById("mediaCountBadge");
  const mediaListContainer = document.getElementById("mediaListContainer");
  const rescanMediaBtn = document.getElementById("rescanMediaBtn");
  const clearMediaBtn = document.getElementById("clearMediaBtn");

  let currentTabId = null;
  let currentActiveTab = null;
  let isAppConnected = false;
  let currentDisplayedMedia = [];

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

  // 1. Find active tab and load media
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs && tabs.length > 0) {
      currentActiveTab = tabs[0];
      currentTabId = currentActiveTab.id;
      loadTabMedia(currentTabId, currentActiveTab);
    } else {
      chrome.tabs.query({ active: true, lastFocusedWindow: true }, (tabs2) => {
        if (tabs2 && tabs2.length > 0) {
          currentActiveTab = tabs2[0];
          currentTabId = currentActiveTab.id;
          loadTabMedia(currentTabId, currentActiveTab);
        }
      });
    }
  });

  // 2. Refresh connection status from background service
  function refreshStatus() {
    chrome.runtime.sendMessage({ type: "GET_STATUS" }, (response) => {
      if (chrome.runtime.lastError || !response) {
        updateStatusUI(false);
        return;
      }

      updateStatusUI(response.isConnected);
      if (response.autoCapture !== undefined) {
        autoCaptureToggle.checked = response.autoCapture;
      }
    });

    if (currentTabId) {
      loadTabMedia(currentTabId, currentActiveTab);
    }
  }

  function updateStatusUI(connected) {
    isAppConnected = Boolean(connected);
    if (connected) {
      statusBadge.className = "status-badge connected";
      statusText.textContent = "Connected";
    } else {
      statusBadge.className = "status-badge disconnected";
      statusText.textContent = "Disconnected";
    }
  }

  const autoCaptureCard = document.getElementById("autoCaptureCard");

  function highlightAutoCaptureRow() {
    if (autoCaptureCard) {
      autoCaptureCard.classList.remove("highlight-pulse");
      void autoCaptureCard.offsetWidth; // Force reflow to re-trigger CSS animation
      autoCaptureCard.classList.add("highlight-pulse");
      setTimeout(() => {
        autoCaptureCard.classList.remove("highlight-pulse");
      }, 2400);
    }
  }

  // 3. Multi-channel Media Scanning (Active Tab URL + Background cache + Live DOM scan)
  function loadTabMedia(tabId, tabObj, isRescan = false) {
    if (!tabId) return;

    if (!autoCaptureToggle.checked) {
      currentDisplayedMedia = [];
      mediaCountBadge.textContent = "0";
      mediaListContainer.innerHTML = `
        <div class="empty-media-msg">
          <p style="font-weight: 600; color: #f87171; margin-bottom: 4px;">⚠️ Interception is Disabled</p>
          <span style="color: #94a3b8; font-size: 11px;">Enable "Automatic Download Interception" above to detect and capture downloads.</span>
        </div>`;
      return;
    }

    // Stage 1: Get cached media from background.js
    chrome.runtime.sendMessage({ type: "GET_TAB_MEDIA", tabId: tabId }, (bgResponse) => {
      let combinedList = (bgResponse && bgResponse.mediaList) ? [...bgResponse.mediaList] : [];

      // Stage 2: Trigger live DOM scan from active tab's content.js
      chrome.tabs.sendMessage(tabId, { type: "SCAN_MEDIA", resetCleared: isRescan }, { frameId: 0 }, (contentResponse) => {
        if (!chrome.runtime.lastError && contentResponse && contentResponse.mediaList) {
          contentResponse.mediaList.forEach((item) => {
            const exists = combinedList.some(
              (m) => m.url === item.url || (m.page_url === item.page_url && m.title === item.title)
            );
            if (!exists) {
              combinedList.push(item);
              // Register in background service as well
              chrome.runtime.sendMessage({
                type: "MEDIA_FOUND",
                payload: item,
                tabId: tabId
              });
            }
          });
        }

        renderMediaList(combinedList);
      });
    });
  }

  function renderMediaList(mediaList) {
    currentDisplayedMedia = Array.isArray(mediaList) ? mediaList : [];
    mediaCountBadge.textContent = currentDisplayedMedia.length;

    if (!mediaList || mediaList.length === 0) {
      mediaListContainer.innerHTML = `
        <div class="empty-media-msg">
          <p style="font-weight: 500; color: #cbd5e1; margin-bottom: 4px;">No videos detected on this page yet.</p>
          <span style="color: #64748b; font-size: 11px;">Play a video on the page or click 🔄 above to rescan.</span>
        </div>`;
      return;
    }

    mediaListContainer.innerHTML = "";

    mediaList.forEach((item, index) => {
      const itemDiv = document.createElement("div");
      itemDiv.className = "media-item";
      itemDiv.style.cursor = "pointer";

      const titleText = item.title || `Video #${index + 1}`;
      const qualityText = item.quality || (item.mime_type ? item.mime_type.split("/")[1].toUpperCase() : "VIDEO");

      itemDiv.innerHTML = `
        <div class="media-item-info">
          <span class="media-item-title" title="${escapeHtml(titleText)}">${escapeHtml(titleText)}</span>
          <span class="media-item-badge">[${escapeHtml(qualityText)}]</span>
        </div>
        <button class="media-download-btn" title="Open download dialog on desktop">⬇️ Download</button>
      `;

      // Clicking the card or button opens the desktop download dialog
      const startDownloadAction = (e) => {
        e.stopPropagation();
        const btn = itemDiv.querySelector(".media-download-btn");

        // 1. If automatic interception is disabled, warn user in English and highlight switch
        if (!autoCaptureToggle.checked) {
          btn.textContent = "Enable Switch ⚠️";
          btn.style.backgroundColor = "#ef4444";
          showFeedback("Automatic Download Interception is disabled! Please enable it to download.", "error", "media");
          highlightAutoCaptureRow();

          setTimeout(() => {
            btn.textContent = "⬇️ Download";
            btn.style.backgroundColor = "#0078d4";
          }, 3000);
          return;
        }

        // 2. If currently disconnected, reject immediately with red feedback
        if (!isAppConnected) {
          btn.textContent = "No App ⚠️";
          btn.style.backgroundColor = "#ef4444";
          showFeedback("Desktop app is not connected! Please start Download Manager.", "error", "media");

          // Trigger background reconnect attempt
          chrome.runtime.sendMessage({ type: "RECONNECT" }, () => {
            setTimeout(refreshStatus, 800);
          });

          setTimeout(() => {
            btn.textContent = "⬇️ Download";
            btn.style.backgroundColor = "#0078d4";
          }, 3000);
          return;
        }

        btn.textContent = "⏳ Opening...";
        btn.style.backgroundColor = "#7c3aed";
        btn.disabled = true;

        chrome.runtime.sendMessage({
          type: "DOWNLOAD_MEDIA_DIRECT",
          payload: {
            url: item.url,
            page_url: item.page_url || item.url,
            referrer: item.referrer || item.page_url || "",
            media_src: item.url,
            title: item.title || "Video Stream"
          }
        }, (response) => {
          // Check if action blocked because interception is disabled
          if (response && response.reason === "AUTO_CAPTURE_DISABLED") {
            btn.textContent = "Enable Switch ⚠️";
            btn.style.backgroundColor = "#ef4444";
            showFeedback("Automatic Download Interception is disabled! Please enable it to download.", "error", "media");
            highlightAutoCaptureRow();

            setTimeout(() => {
              btn.textContent = "⬇️ Download";
              btn.style.backgroundColor = "#0078d4";
              btn.disabled = false;
            }, 3000);
            return;
          }

          // Check for actual success response from desktop WebSocket
          if (chrome.runtime.lastError || !response || !response.success) {
            updateStatusUI(false);
            btn.textContent = "Failed ❌";
            btn.style.backgroundColor = "#ef4444";
            showFeedback("Desktop app connection failed! Please check if Download Manager is running.", "error", "media");

            setTimeout(() => {
              btn.textContent = "⬇️ Download";
              btn.style.backgroundColor = "#0078d4";
              btn.disabled = false;
            }, 3000);
            return;
          }

          // Successful transmission to desktop app
          showFeedback("Download window opened on desktop! Please click 'Download'.", "success", "media");
          btn.textContent = "Opened ✅";
          btn.style.backgroundColor = "#16a34a";
          setTimeout(() => {
            btn.textContent = "⬇️ Download";
            btn.style.backgroundColor = "#0078d4";
            btn.disabled = false;
          }, 3500);
        });
      };

      const btn = itemDiv.querySelector(".media-download-btn");
      btn.addEventListener("click", startDownloadAction);
      itemDiv.addEventListener("click", startDownloadAction);

      mediaListContainer.appendChild(itemDiv);
    });
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // 4. Clear list button
  if (clearMediaBtn) {
    clearMediaBtn.addEventListener("click", () => {
      clearMediaBtn.style.transform = "scale(0.85)";
      setTimeout(() => { clearMediaBtn.style.transform = "scale(1)"; }, 200);

      const urlsToClear = currentDisplayedMedia.map(m => m.url).filter(Boolean);

      if (currentTabId) {
        // Clear background service worker cache and remember cleared URLs
        chrome.runtime.sendMessage({
          type: "CLEAR_TAB_MEDIA",
          tabId: currentTabId,
          clearedUrls: urlsToClear
        }, () => {
          // Clear content script in-page map and snapshot cleared keys
          chrome.tabs.sendMessage(currentTabId, {
            type: "CLEAR_PAGE_MEDIA",
            clearedUrls: urlsToClear
          }, () => {
            if (chrome.runtime.lastError) {
              // Content script might be absent on restricted scheme pages
            }
          });
        });
      }

      // Immediately clear UI and badge
      currentDisplayedMedia = [];
      renderMediaList([]);
      mediaCountBadge.textContent = "0";
      showFeedback("Media list cleared! 🗑️", "success", "media");
    });
  }

  // 5. Rescan button (Manual refresh)
  if (rescanMediaBtn) {
    rescanMediaBtn.addEventListener("click", () => {
      if (!autoCaptureToggle.checked) {
        showFeedback("Automatic Download Interception is disabled! Please enable it above.", "error", "media");
        highlightAutoCaptureRow();
        return;
      }

      rescanMediaBtn.style.transform = "rotate(180deg)";
      setTimeout(() => { rescanMediaBtn.style.transform = "rotate(0deg)"; }, 400);
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        const targetTab = (tabs && tabs.length > 0) ? tabs[0] : currentActiveTab;
        if (targetTab) {
          currentActiveTab = targetTab;
          currentTabId = targetTab.id;
          chrome.runtime.sendMessage({ type: "RESCAN_TAB_MEDIA", tabId: currentTabId }, () => {
            loadTabMedia(currentTabId, currentActiveTab, true);
          });
        }
      });
    });
  }

  // 5. Automatic capture toggle
  autoCaptureToggle.addEventListener("change", () => {
    const isEnabled = autoCaptureToggle.checked;
    chrome.runtime.sendMessage({
      type: "TOGGLE_AUTO_CAPTURE",
      enabled: isEnabled
    }, () => {
      if (!isEnabled) {
        mediaCountBadge.textContent = "0";
        mediaListContainer.innerHTML = `
          <div class="empty-media-msg">
            <p style="font-weight: 600; color: #f87171; margin-bottom: 4px;">⚠️ Interception is Disabled</p>
            <span style="color: #94a3b8; font-size: 11px;">Enable "Automatic Download Interception" above to detect and capture downloads.</span>
          </div>`;
        showFeedback("Automatic download interception disabled.", "error", "both");
      } else {
        showFeedback("Automatic download interception enabled.", "success", "both");
        if (currentTabId) {
          loadTabMedia(currentTabId, currentActiveTab);
        }
      }
    });
  });

  // 6. Manual URL submission
  sendUrlBtn.addEventListener("click", () => {
    if (!autoCaptureToggle.checked) {
      showFeedback("Automatic Download Interception is disabled! Please enable it above.", "error", "quick");
      highlightAutoCaptureRow();
      return;
    }

    const url = manualUrlInput.value.trim();
    if (!url) {
      showFeedback("Please enter a valid URL.", "error", "quick");
      return;
    }

    if (!url.startsWith("http://") && !url.startsWith("https://") && !url.startsWith("ftp://")) {
      showFeedback("URL must start with http:// or https://", "error", "quick");
      return;
    }

    if (!isAppConnected) {
      showFeedback("Desktop app is not connected! Please start Download Manager.", "error", "quick");
      return;
    }

    chrome.runtime.sendMessage({ type: "SEND_MANUAL_URL", url: url }, (response) => {
      if (response && response.reason === "AUTO_CAPTURE_DISABLED") {
        showFeedback("Automatic Download Interception is disabled! Please enable it above.", "error", "quick");
        highlightAutoCaptureRow();
        return;
      }
      if (response && response.success) {
        showFeedback("Download window opened on desktop! ✅", "success", "quick");
        manualUrlInput.value = "";
      } else {
        showFeedback("Failed to send! Is the desktop app running?", "error", "quick");
      }
    });
  });

  // 7. Reconnect button
  reconnectBtn.addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "RECONNECT" }, () => {
      setTimeout(refreshStatus, 800);
    });
  });

  function showFeedback(text, type, target = "both") {
    if ((target === "both" || target === "media") && mediaFeedbackMsg) {
      mediaFeedbackMsg.textContent = text;
      mediaFeedbackMsg.className = `feedback-msg ${type}`;
    }
    if ((target === "both" || target === "quick") && feedbackMsg) {
      feedbackMsg.textContent = text;
      feedbackMsg.className = `feedback-msg ${type}`;
    }
    setTimeout(() => {
      if (mediaFeedbackMsg) {
        mediaFeedbackMsg.textContent = "";
        mediaFeedbackMsg.className = "feedback-msg";
      }
      if (feedbackMsg) {
        feedbackMsg.textContent = "";
        feedbackMsg.className = "feedback-msg";
      }
    }, 4500);
  }

  // Initial load
  refreshStatus();
});
