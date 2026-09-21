/**
 * Download Manager — Website Interactive Logic (app.js)
 */

document.addEventListener("DOMContentLoaded", () => {
  const mainDownloadBtn = document.getElementById("mainDownloadBtn");
  const downloadToast = document.getElementById("downloadToast");
  const heroVersionBadge = document.getElementById("heroVersionBadge");
  const downloadMetaSize = document.getElementById("downloadMetaSize");
  const downloadMetaVersion = document.getElementById("downloadMetaVersion");
  const footerDownloadLink = document.getElementById("footerDownloadLink");
  const toastDetails = document.getElementById("toastDetails");

  let toastTimeout = null;

  function showDownloadToast() {
    if (downloadToast) {
      downloadToast.classList.add("show");
      clearTimeout(toastTimeout);
      toastTimeout = setTimeout(() => {
        downloadToast.classList.remove("show");
      }, 4500);
    }
  }

  function handleDownloadClick(e) {
    const btn = e.currentTarget;
    const originalLabel = btn.querySelector(".btn-label") || btn.querySelector("span");
    const originalText = originalLabel ? originalLabel.textContent : "";

    if (originalLabel) {
      originalLabel.textContent = "Starting Download...";
      setTimeout(() => {
        originalLabel.textContent = originalText;
      }, 3000);
    }

    showDownloadToast();
  }

  if (mainDownloadBtn) {
    mainDownloadBtn.addEventListener("click", handleDownloadClick);
  }

  // --- Dynamic Latest Release Fetcher from GitHub Releases API ---
  const GITHUB_REPO = "sametburhan/download-manager";
  const GITHUB_API_URL = `https://api.github.com/repos/${GITHUB_REPO}/releases/latest`;

  function formatBytes(bytes) {
    if (!bytes || isNaN(bytes)) return "";
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(1)} MB`;
  }

  async function fetchLatestRelease() {
    try {
      const res = await fetch(GITHUB_API_URL);
      if (!res.ok) {
        console.warn("GitHub Releases API returned status:", res.status);
        return;
      }
      const data = await res.json();
      const tagName = data.tag_name || "v1.1.0";

      // Find the Windows installer (.exe)
      const exeAsset = data.assets && data.assets.find(
        (a) => a.name && a.name.toLowerCase().endsWith(".exe")
      );

      if (exeAsset) {
        const downloadUrl = exeAsset.browser_download_url;
        const fileSizeFormatted = formatBytes(exeAsset.size);

        // Update Main Download CTA
        if (mainDownloadBtn) {
          mainDownloadBtn.href = downloadUrl;
          mainDownloadBtn.setAttribute("download", exeAsset.name);
        }

        // Update Footer Download Link
        if (footerDownloadLink) {
          footerDownloadLink.href = downloadUrl;
          footerDownloadLink.textContent = `Download ${tagName} (.exe)`;
          footerDownloadLink.setAttribute("download", exeAsset.name);
        }

        // Update Hero Version Badge
        if (heroVersionBadge) {
          heroVersionBadge.textContent = `Engineered for Windows 10 & 11 • ${tagName}`;
        }

        // Update Metadata info
        if (downloadMetaSize && fileSizeFormatted) {
          downloadMetaSize.textContent = fileSizeFormatted;
        }
        if (downloadMetaVersion) {
          downloadMetaVersion.textContent = tagName;
        }

        // Update Toast text
        if (toastDetails) {
          toastDetails.textContent = `${exeAsset.name} ${fileSizeFormatted ? `(${fileSizeFormatted})` : ""} is downloading.`;
        }
      }
    } catch (err) {
      console.warn("Failed to query latest release:", err);
    }
  }

  // Fetch immediately on load
  fetchLatestRelease();

  // --- Contact / Feedback Modal Logic ---
  const navContactBtn = document.getElementById("navContactBtn");
  const footerContactBtn = document.getElementById("footerContactBtn");
  const contactModal = document.getElementById("contactModal");
  const modalOverlay = document.getElementById("modalOverlay");
  const modalCard = document.querySelector(".modal-card");
  const modalCloseBtn = document.getElementById("modalCloseBtn");
  const modalCancelBtn = document.getElementById("modalCancelBtn");
  const modalDoneBtn = document.getElementById("modalDoneBtn");
  const contactForm = document.getElementById("contactForm");
  const contactSuccess = document.getElementById("contactSuccess");
  const submitFeedbackBtn = document.getElementById("submitFeedbackBtn");

  function openContactModal() {
    if (!contactModal) return;
    contactModal.removeAttribute("hidden");
    if (modalCard) {
      modalCard.classList.remove("show-success");
    }
    // Force DOM reflow so transition plays nicely
    void contactModal.offsetWidth;
    contactModal.classList.add("is-open");
    document.body.style.overflow = "hidden";

    // Auto-focus name field
    const nameInput = document.getElementById("contactName");
    if (nameInput) {
      setTimeout(() => nameInput.focus(), 150);
    }
  }

  function closeContactModal() {
    if (!contactModal) return;
    contactModal.classList.remove("is-open");
    document.body.style.overflow = "";
    setTimeout(() => {
      if (!contactModal.classList.contains("is-open")) {
        contactModal.setAttribute("hidden", "true");
        if (modalCard) {
          modalCard.classList.remove("show-success");
        }
      }
    }, 280);
  }

  if (navContactBtn) {
    navContactBtn.addEventListener("click", openContactModal);
  }

  if (footerContactBtn) {
    footerContactBtn.addEventListener("click", openContactModal);
  }

  if (modalOverlay) {
    modalOverlay.addEventListener("click", closeContactModal);
  }

  if (modalCloseBtn) {
    modalCloseBtn.addEventListener("click", closeContactModal);
  }

  if (modalCancelBtn) {
    modalCancelBtn.addEventListener("click", closeContactModal);
  }

  if (modalDoneBtn) {
    modalDoneBtn.addEventListener("click", closeContactModal);
  }

  // Close on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && contactModal && contactModal.classList.contains("is-open")) {
      closeContactModal();
    }
  });

  // Handle Form Submission
  if (contactForm) {
    contactForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      if (submitFeedbackBtn) {
        submitFeedbackBtn.disabled = true;
        submitFeedbackBtn.innerHTML = `<span>Sending...</span>`;
      }

      const formData = new FormData(contactForm);
      const payload = {
        name: formData.get("name"),
        email: formData.get("email"),
        category: formData.get("category") || "Feedback",
        message: formData.get("message"),
        _subject: `Download Manager Feedback [${formData.get("category") || "Feedback"}] - ${formData.get("name")}`,
        _captcha: "false",
        _template: "table"
      };

      try {
        await fetch("https://formsubmit.co/ajax/samet26burhan2@gmail.com", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
          },
          body: JSON.stringify(payload)
        });
      } catch (err) {
        console.warn("Form dispatch error / offline fallback:", err);
      } finally {
        if (modalCard) {
          modalCard.classList.add("show-success");
        }
        contactForm.reset();

        if (submitFeedbackBtn) {
          submitFeedbackBtn.disabled = false;
          submitFeedbackBtn.innerHTML = `
            <span>Send Feedback</span>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          `;
        }
      }
    });
  }

  // --- Dynamic Live Speed Simulation in App Mockup ---
  const speedElement = document.querySelector(".window-badge-stat span:last-child");
  const taskSpeedElement = document.querySelector(".task-card.active-task .task-speed");

  if (speedElement && taskSpeedElement) {
    setInterval(() => {
      // Fluctuate total speed between 26.2 and 29.8 MB/s
      const totalSpeed = (26.0 + Math.random() * 3.8).toFixed(1);
      // Fluctuate task 1 speed between 17.5 and 20.2 MB/s
      const taskSpeed = (17.5 + Math.random() * 2.7).toFixed(1);

      speedElement.textContent = `Active • ${totalSpeed} MB/s`;
      taskSpeedElement.textContent = `${taskSpeed} MB/s`;
    }, 2400);
  }

  // --- Smooth scroll for dock items ---
  document.querySelectorAll('.dock-item[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", function (e) {
      const targetId = this.getAttribute("href");
      if (targetId && targetId !== "#") {
        const targetElement = document.querySelector(targetId);
        if (targetElement) {
          e.preventDefault();
          targetElement.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
    });
  });
});
