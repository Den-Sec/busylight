// ============ DOM refs ============
const loginCard = document.getElementById("login-card");
const consoleGrid = document.getElementById("console-grid");
const logoutBtn = document.getElementById("logout-btn");

const loginBtn = document.getElementById("login-btn");
const pinInput = document.getElementById("pin");
const loginMsg = document.getElementById("login-msg");

const statusOrb = document.getElementById("status-orb");
const currentState = document.getElementById("current-state");
const stateMsg = document.getElementById("state-msg");
const heroSub = document.getElementById("hero-sub");

const tHost = document.getElementById("t-host");
const tMdns = document.getElementById("t-mdns");
const tIp = document.getElementById("t-ip");
const tRssi = document.getElementById("t-rssi");
const tBars = document.getElementById("t-bars");
const tVer = document.getElementById("t-ver");
const tUptime = document.getElementById("t-uptime");

const brandVersion = document.getElementById("brand-version");
const hostchip = document.getElementById("hostchip");
const linkState = document.getElementById("link-state");

const currentPin = document.getElementById("current-pin");
const newPin = document.getElementById("new-pin");
const changePinBtn = document.getElementById("change-pin-btn");
const pinMsg = document.getElementById("pin-msg");

const otaFile = document.getElementById("ota-file");
const otaFilename = document.getElementById("ota-filename");
const otaBtn = document.getElementById("ota-btn");
const otaProgress = document.getElementById("ota-progress");
const otaMsg = document.getElementById("ota-msg");

const rebootBtn = document.getElementById("reboot-btn");
const factoryResetBtn = document.getElementById("factory-reset-btn");

// ============ Helpers ============
function readCookie(name) {
  const prefix = name + "=";
  for (const raw of document.cookie.split(";")) {
    const p = raw.trim();
    if (p.startsWith(prefix)) return p.substring(prefix.length);
  }
  return "";
}

function csrfToken() {
  return readCookie("BLCSRF");
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (options.method && options.method !== "GET") {
    const tok = csrfToken();
    if (tok) headers["X-CSRF-Token"] = tok;
  }

  const response = await fetch(path, {
    credentials: "include",
    headers,
    ...options,
  });

  const text = await response.text();
  let json = {};
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    json = { raw: text };
  }

  if (!response.ok) {
    const err = new Error(humanError(json.error) || `HTTP ${response.status}`);
    err.status = response.status;
    err.payload = json;
    throw err;
  }

  return json;
}

const ERROR_LABELS = {
  invalid_pin: "Wrong PIN.",
  locked_out: "Too many attempts. Try again in 60 seconds.",
  csrf_invalid: "Session expired. Sign in again.",
  unauthorized: "Session expired. Sign in again.",
  invalid_payload: "Malformed request.",
  invalid_state: "Unknown state value.",
  invalid_current_pin: "Current PIN does not match.",
  pin_length: "PIN must be 4-8 digits.",
  pin_digits_only: "PIN must be digits only.",
  confirm_required: "Confirmation header missing.",
  unauthorized_ota: "Authentication failed for OTA.",
  image_too_small: "Firmware too small to be valid.",
  update_begin_failed: "Could not allocate OTA slot.",
  update_end_failed: "Final write failed; reboot to recover.",
  write_failed: "Write failed mid-upload.",
};

function humanError(code) {
  if (!code) return null;
  return ERROR_LABELS[code] || code;
}

function formatUptime(ms) {
  if (typeof ms !== "number" || !isFinite(ms)) return "--";
  const s = Math.floor(ms / 1000);
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  if (days > 0) return `${days}d ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

function signalBars(rssi) {
  if (typeof rssi !== "number") return 0;
  if (rssi >= -55) return 4;
  if (rssi >= -65) return 3;
  if (rssi >= -75) return 2;
  if (rssi >= -85) return 1;
  return 0;
}

function showApp() {
  loginCard.classList.add("hidden");
  consoleGrid.classList.remove("hidden");
  logoutBtn.classList.remove("hidden");
}

function showLogin() {
  loginCard.classList.remove("hidden");
  consoleGrid.classList.add("hidden");
  logoutBtn.classList.add("hidden");
}

const STATE_LABEL = {
  AVAILABLE: "Available",
  BUSY: "Busy",
  IN_CALL: "In a call",
  AWAY: "Away",
  WIFI_ERROR: "No Wi-Fi",
};

const STATE_TAGLINE = {
  AVAILABLE: "Come on in — the light is on.",
  BUSY: "Solid red. People at the door will know to wait.",
  IN_CALL: "Blinking red. A call or meeting is in progress.",
  AWAY: "Blinking green. Stepped away, back soon.",
  WIFI_ERROR: "Can't reach the network — check Wi-Fi credentials.",
};

function setStateUi(state) {
  if (!state) return;
  currentState.textContent = STATE_LABEL[state] || state;
  if (statusOrb) statusOrb.dataset.state = state;
  if (heroSub) heroSub.textContent = STATE_TAGLINE[state] || "";
  document.querySelectorAll(".tile, .state").forEach((btn) => {
    if (btn.dataset.state === state) btn.classList.add("active");
    else btn.classList.remove("active");
  });
}

// ============ Refreshers ============

async function refreshState() {
  const data = await api("/api/state");
  setStateUi(data.state);
  if (typeof data.uptime_ms === "number") {
    tUptime.textContent = formatUptime(data.uptime_ms);
  }
}

async function refreshSettings() {
  const data = await api("/api/settings");
  tHost.textContent = data.hostname || "--";
  tMdns.textContent = data.mdns || "--";
  tIp.textContent = data.ip || "--";
  if (typeof data.rssi === "number") {
    tRssi.textContent = `${data.rssi} dBm`;
    tBars.dataset.strength = String(signalBars(data.rssi));
  }
  tVer.textContent = data.version ? `v${data.version}` : "--";
  if (brandVersion) brandVersion.textContent = data.version || "?.?.?";
  if (hostchip && data.hostname) hostchip.textContent = `${data.hostname}.local`;
}

async function initSession() {
  try {
    await refreshState();
    await refreshSettings();
    showApp();
  } catch (err) {
    if (err.status === 401) {
      showLogin();
      return;
    }
    loginMsg.textContent = err.message;
  }
}

// Periodically refresh uptime + state so the orb stays in sync.
let refreshTimer = null;
function startPeriodicRefresh() {
  if (refreshTimer) return;
  refreshTimer = setInterval(async () => {
    if (consoleGrid.classList.contains("hidden")) return;
    try {
      await refreshState();
    } catch {
      // ignore transient errors
    }
  }, 5000);
}

// ============ Handlers ============

loginBtn.addEventListener("click", async () => {
  loginMsg.textContent = "";
  const pin = pinInput.value.trim();
  if (!/^\d{4,8}$/.test(pin)) {
    loginMsg.textContent = "PIN must be 4 to 8 digits.";
    return;
  }
  try {
    await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ pin }),
    });
    pinInput.value = "";
    await initSession();
    startPeriodicRefresh();
  } catch (err) {
    loginMsg.textContent = err.message;
  }
});

pinInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") loginBtn.click();
});

document.querySelectorAll(".tile, .state").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const state = btn.dataset.state;
    if (stateMsg) stateMsg.textContent = "Updating…";
    try {
      await api("/api/state", {
        method: "POST",
        body: JSON.stringify({ state }),
      });
      await refreshState();
      if (stateMsg) stateMsg.textContent = "";
    } catch (err) {
      if (stateMsg) stateMsg.textContent = err.message;
    }
  });
});

logoutBtn.addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch {
    // ignore
  }
  showLogin();
});

changePinBtn.addEventListener("click", async () => {
  pinMsg.textContent = "";
  const current_pin = currentPin.value.trim();
  const new_pin = newPin.value.trim();
  if (!/^\d{4,8}$/.test(new_pin)) {
    pinMsg.textContent = "New PIN must be 4 to 8 digits.";
    return;
  }
  try {
    await api("/api/settings/pin", {
      method: "POST",
      body: JSON.stringify({ current_pin, new_pin }),
    });
    currentPin.value = "";
    newPin.value = "";
    pinMsg.textContent = "PIN rotated. The old PIN is no longer accepted.";
  } catch (err) {
    pinMsg.textContent = err.message;
  }
});

rebootBtn.addEventListener("click", async () => {
  if (!confirm("Reboot BusyLight now? You will lose the session.")) return;
  try {
    await api("/api/device/reboot", { method: "POST" });
    stateMsg.textContent = "Reboot requested. Reload the page in ~15 seconds.";
  } catch (err) {
    stateMsg.textContent = err.message;
  }
});

if (factoryResetBtn) {
  factoryResetBtn.addEventListener("click", async () => {
    const ok = confirm(
      "Factory reset wipes Wi-Fi credentials AND the PIN. After this you can only reprovision over USB. Continue?"
    );
    if (!ok) return;
    try {
      const response = await fetch("/api/device/factory_reset", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken(),
          "X-Confirm": "YES",
        },
      });
      if (!response.ok) {
        const text = await response.text();
        let detail = text;
        try {
          const j = JSON.parse(text);
          detail = humanError(j.error) || j.error || text;
        } catch {
          // ignore
        }
        stateMsg.textContent = `Factory reset rejected: ${detail}`;
        return;
      }
      stateMsg.textContent = "Factory reset confirmed. Device rebooting.";
    } catch (err) {
      stateMsg.textContent = err.message;
    }
  });
}

// ============ OTA ============

if (otaFile) {
  otaFile.addEventListener("change", () => {
    if (otaFile.files && otaFile.files.length > 0) {
      const f = otaFile.files[0];
      const size = (f.size / 1024).toFixed(1);
      otaFilename.textContent = `${f.name}  ·  ${size} KB`;
    } else {
      otaFilename.textContent = "Drop firmware here or click to browse";
    }
  });
}

if (otaBtn) {
  otaBtn.addEventListener("click", () => {
    otaMsg.textContent = "";
    if (!otaFile.files || otaFile.files.length === 0) {
      otaMsg.textContent = "Pick a firmware .bin file first.";
      return;
    }
    const file = otaFile.files[0];
    const form = new FormData();
    form.append("firmware", file, file.name);

    otaProgress.value = 0;
    otaProgress.classList.remove("hidden");

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/firmware/update");
    xhr.setRequestHeader("X-CSRF-Token", csrfToken());
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        otaProgress.value = pct;
        otaMsg.textContent = `Uploading... ${pct}%`;
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        otaMsg.textContent =
          "Upload complete. Device rebooting. Reload the page in about 30 seconds.";
      } else {
        let detail = xhr.responseText;
        try {
          const j = JSON.parse(xhr.responseText);
          detail = humanError(j.error) || j.error || detail;
        } catch {
          // ignore
        }
        otaMsg.textContent = `Upload failed: ${detail}`;
      }
    };
    xhr.onerror = () => {
      otaMsg.textContent = "Network error during upload.";
    };
    xhr.send(form);
  });
}

// ============ Boot ============

initSession().then(() => {
  if (!consoleGrid.classList.contains("hidden")) {
    startPeriodicRefresh();
  }
});
