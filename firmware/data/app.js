// ============ i18n ============
//
// All user-facing strings live here. Bilingual: English + Italian.
// HTML uses the data-i18n="key" attribute for static text, data-i18n-attr
// for attributes like placeholder. JS uses t("key") at call sites.

const I18N = {
  en: {
    "brand.sub": "Status light",
    "topbar.online": "Online",
    "topbar.signout": "Sign out",

    "login.kicker": "Authenticate",
    "login.title": "Welcome back.",
    "login.lede":
      "This BusyLight is paired to your network. Enter the PIN you set during setup to take control.",
    "login.access_pin": "Access PIN",
    "login.placeholder": "4–8 digits",
    "login.unlock": "Unlock",
    "login.error.invalid_format": "PIN must be 4 to 8 digits.",

    "hero.kicker": "Currently",

    "states.AVAILABLE.name": "Available",
    "states.BUSY.name": "Busy",
    "states.IN_CALL.name": "In a call",
    "states.AWAY.name": "Away",
    "states.WIFI_ERROR.name": "No Wi-Fi",

    "states.AVAILABLE.tag": "Come on in — the light is on.",
    "states.BUSY.tag":
      "Solid red. People at the door will know to wait.",
    "states.IN_CALL.tag":
      "Blinking red. A call or meeting is in progress.",
    "states.AWAY.tag":
      "Blinking green. Stepped away, back soon.",
    "states.WIFI_ERROR.tag":
      "Can't reach the network — check Wi-Fi credentials.",

    "states.AVAILABLE.desc": "Solid green · door open",
    "states.BUSY.desc": "Solid red · focus mode",
    "states.IN_CALL.desc": "Red blink · meeting",
    "states.AWAY.desc": "Green blink · stepped out",

    "set_state.title": "Set state",
    "set_state.sub": "Tap to switch the desk light",
    "set_state.updating": "Updating…",

    "device.title": "Device",
    "device.sub": "Read-only",
    "device.hostname": "Hostname",
    "device.address": "Address",
    "device.local_ip": "Local IP",
    "device.wifi": "Wi-Fi",
    "device.firmware": "Firmware",
    "device.uptime": "Uptime",

    "access.title": "Access",
    "access.sub": "Change PIN",
    "access.current_pin": "Current PIN",
    "access.new_pin": "New PIN",
    "access.rotate": "Rotate PIN",
    "access.changed": "PIN rotated. The old PIN is no longer accepted.",
    "access.error.invalid_format": "New PIN must be 4 to 8 digits.",

    "ota.title": "Firmware",
    "ota.sub": "Optional",
    "ota.lede":
      "Upload a new .bin compiled for the ESP32-C6. It writes to the inactive slot and reboots into it. Bad images can always be recovered over USB.",
    "ota.no_file": "No file selected",
    "ota.choose": "Choose .bin",
    "ota.upload": "Upload & reboot",
    "ota.uploading": "Uploading…",
    "ota.complete":
      "Upload complete. Device rebooting. Reload the page in about 30 seconds.",
    "ota.no_bin": "Pick a firmware .bin file first.",
    "ota.network_error": "Network error during upload.",
    "ota.failed": "Upload failed:",

    "maint.title": "Maintenance",
    "maint.sub": "Use with care",
    "maint.restart.title": "Restart device",
    "maint.restart.desc": "Reboots without touching Wi-Fi or PIN.",
    "maint.restart.btn": "Restart",
    "maint.restart.confirm":
      "Reboot BusyLight now? You will lose the session.",
    "maint.restart.requested":
      "Reboot requested. Reload the page in about 15 seconds.",
    "maint.factory.title": "Factory reset",
    "maint.factory.desc":
      "Wipes Wi-Fi and PIN. A USB cable is required to provision the device again.",
    "maint.factory.btn": "Reset",
    "maint.factory.confirm":
      "Factory reset wipes Wi-Fi credentials AND the PIN. After this you can only reprovision over USB. Continue?",
    "maint.factory.rejected": "Factory reset rejected:",
    "maint.factory.requested":
      "Factory reset confirmed. Device rebooting.",

    "foot.source": "Source ↗",

    "errors.invalid_pin": "Wrong PIN.",
    "errors.locked_out":
      "Too many attempts. Try again in 60 seconds.",
    "errors.csrf_invalid": "Session expired. Sign in again.",
    "errors.unauthorized": "Session expired. Sign in again.",
    "errors.invalid_payload": "Malformed request.",
    "errors.invalid_state": "Unknown state value.",
    "errors.invalid_current_pin": "Current PIN does not match.",
    "errors.pin_length": "PIN must be 4–8 digits.",
    "errors.pin_digits_only": "PIN must be digits only.",
    "errors.confirm_required": "Confirmation header missing.",
    "errors.unauthorized_ota": "Authentication failed for OTA.",
    "errors.image_too_small": "Firmware too small to be valid.",
    "errors.update_begin_failed": "Could not allocate OTA slot.",
    "errors.update_end_failed": "Final write failed; reboot to recover.",
    "errors.write_failed": "Write failed mid-upload.",
  },

  it: {
    "brand.sub": "Luce di stato",
    "topbar.online": "Online",
    "topbar.signout": "Esci",

    "login.kicker": "Autenticazione",
    "login.title": "Bentornato.",
    "login.lede":
      "Questo BusyLight è associato alla tua rete. Inserisci il PIN impostato in fase di setup per prendere il controllo.",
    "login.access_pin": "PIN di accesso",
    "login.placeholder": "4–8 cifre",
    "login.unlock": "Sblocca",
    "login.error.invalid_format": "Il PIN deve avere da 4 a 8 cifre.",

    "hero.kicker": "Stato attuale",

    "states.AVAILABLE.name": "Disponibile",
    "states.BUSY.name": "Occupato",
    "states.IN_CALL.name": "In chiamata",
    "states.AWAY.name": "Assente",
    "states.WIFI_ERROR.name": "Senza Wi-Fi",

    "states.AVAILABLE.tag":
      "Vieni pure — la luce è verde.",
    "states.BUSY.tag":
      "Rosso fisso. Chi passa dalla porta saprà che è meglio attendere.",
    "states.IN_CALL.tag":
      "Rosso lampeggiante. Sei in una chiamata o riunione.",
    "states.AWAY.tag":
      "Verde lampeggiante. Sei via, torni a breve.",
    "states.WIFI_ERROR.tag":
      "Rete irraggiungibile — controlla le credenziali Wi-Fi.",

    "states.AVAILABLE.desc": "Verde fisso · porta aperta",
    "states.BUSY.desc": "Rosso fisso · modalità focus",
    "states.IN_CALL.desc": "Lampeggio rosso · riunione",
    "states.AWAY.desc": "Lampeggio verde · sono via",

    "set_state.title": "Imposta stato",
    "set_state.sub": "Tocca per cambiare la luce sulla scrivania",
    "set_state.updating": "Aggiorno…",

    "device.title": "Dispositivo",
    "device.sub": "Solo lettura",
    "device.hostname": "Hostname",
    "device.address": "Indirizzo",
    "device.local_ip": "IP locale",
    "device.wifi": "Wi-Fi",
    "device.firmware": "Firmware",
    "device.uptime": "Attivo da",

    "access.title": "Accesso",
    "access.sub": "Cambia PIN",
    "access.current_pin": "PIN attuale",
    "access.new_pin": "Nuovo PIN",
    "access.rotate": "Cambia PIN",
    "access.changed":
      "PIN aggiornato. Il vecchio PIN non è più valido.",
    "access.error.invalid_format":
      "Il nuovo PIN deve avere da 4 a 8 cifre.",

    "ota.title": "Firmware",
    "ota.sub": "Opzionale",
    "ota.lede":
      "Carica un nuovo .bin compilato per ESP32-C6. Viene scritto nello slot inattivo e il dispositivo riparte da quello. Una immagine difettosa si recupera sempre via USB.",
    "ota.no_file": "Nessun file selezionato",
    "ota.choose": "Scegli .bin",
    "ota.upload": "Carica e riavvia",
    "ota.uploading": "Carico…",
    "ota.complete":
      "Caricamento completato. Riavvio in corso. Ricarica la pagina tra circa 30 secondi.",
    "ota.no_bin": "Seleziona prima un file .bin.",
    "ota.network_error": "Errore di rete durante il caricamento.",
    "ota.failed": "Caricamento fallito:",

    "maint.title": "Manutenzione",
    "maint.sub": "Usare con attenzione",
    "maint.restart.title": "Riavvia il dispositivo",
    "maint.restart.desc":
      "Riavvia senza toccare le credenziali Wi-Fi o il PIN.",
    "maint.restart.btn": "Riavvia",
    "maint.restart.confirm":
      "Riavvio BusyLight ora? Perderai la sessione corrente.",
    "maint.restart.requested":
      "Riavvio richiesto. Ricarica la pagina tra circa 15 secondi.",
    "maint.factory.title": "Reset di fabbrica",
    "maint.factory.desc":
      "Cancella Wi-Fi e PIN. Per riprovvigionare il dispositivo serve il cavo USB.",
    "maint.factory.btn": "Reset",
    "maint.factory.confirm":
      "Il reset di fabbrica cancella le credenziali Wi-Fi E il PIN. Dopo questa operazione potrai riprovvigionare solo via USB. Continuare?",
    "maint.factory.rejected": "Reset di fabbrica rifiutato:",
    "maint.factory.requested":
      "Reset di fabbrica confermato. Dispositivo in riavvio.",

    "foot.source": "Sorgente ↗",

    "errors.invalid_pin": "PIN errato.",
    "errors.locked_out":
      "Troppi tentativi. Riprova fra 60 secondi.",
    "errors.csrf_invalid": "Sessione scaduta. Accedi di nuovo.",
    "errors.unauthorized": "Sessione scaduta. Accedi di nuovo.",
    "errors.invalid_payload": "Richiesta malformata.",
    "errors.invalid_state": "Stato non valido.",
    "errors.invalid_current_pin": "Il PIN attuale non corrisponde.",
    "errors.pin_length": "Il PIN deve avere da 4 a 8 cifre.",
    "errors.pin_digits_only": "Il PIN deve contenere solo cifre.",
    "errors.confirm_required": "Manca l'header di conferma.",
    "errors.unauthorized_ota": "Autenticazione OTA fallita.",
    "errors.image_too_small": "Firmware troppo piccolo per essere valido.",
    "errors.update_begin_failed": "Impossibile allocare lo slot OTA.",
    "errors.update_end_failed":
      "Scrittura finale fallita; riavvia per recuperare.",
    "errors.write_failed": "Scrittura fallita a metà upload.",
  },
};

const LANG_STORAGE_KEY = "busylight.lang";

function detectInitialLang() {
  try {
    const saved = localStorage.getItem(LANG_STORAGE_KEY);
    if (saved && I18N[saved]) return saved;
  } catch {
    // localStorage may be blocked
  }
  const nav = (navigator.language || "en").toLowerCase();
  if (nav.startsWith("it")) return "it";
  return "en";
}

let currentLang = detectInitialLang();

function t(key) {
  const bundle = I18N[currentLang] || I18N.en;
  return bundle[key] ?? I18N.en[key] ?? key;
}

function applyI18n(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  root.querySelectorAll("[data-i18n-attr]").forEach((el) => {
    el.dataset.i18nAttr.split(",").forEach((pair) => {
      const [attr, key] = pair.split(":").map((s) => s.trim());
      if (attr && key) el.setAttribute(attr, t(key));
    });
  });
  document.documentElement.lang = currentLang;
}

function setLang(lang) {
  if (!I18N[lang]) return;
  currentLang = lang;
  try {
    localStorage.setItem(LANG_STORAGE_KEY, lang);
  } catch {
    // ignore
  }
  applyI18n();
  document
    .querySelectorAll("[data-lang-btn]")
    .forEach((btn) =>
      btn.classList.toggle("active", btn.dataset.langBtn === lang)
    );
  // re-render dynamic strings
  refreshDynamicLabels();
}

function refreshDynamicLabels() {
  if (statusOrb && statusOrb.dataset.state) {
    setStateUi(statusOrb.dataset.state);
  }
  if (otaFilename && !otaFile.files?.length) {
    otaFilename.textContent = t("ota.no_file");
  }
}

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

function humanError(code) {
  if (!code) return null;
  const key = `errors.${code}`;
  // If we have a translation, use it; otherwise fall back to the raw code.
  return t(key) === key ? code : t(key);
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

function setStateUi(state) {
  if (!state) return;
  currentState.textContent = t(`states.${state}.name`);
  if (statusOrb) statusOrb.dataset.state = state;
  if (heroSub) heroSub.textContent = t(`states.${state}.tag`);
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
    loginMsg.textContent = t("login.error.invalid_format");
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
    if (stateMsg) stateMsg.textContent = t("set_state.updating");
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
    pinMsg.textContent = t("access.error.invalid_format");
    return;
  }
  try {
    await api("/api/settings/pin", {
      method: "POST",
      body: JSON.stringify({ current_pin, new_pin }),
    });
    currentPin.value = "";
    newPin.value = "";
    pinMsg.textContent = t("access.changed");
  } catch (err) {
    pinMsg.textContent = err.message;
  }
});

rebootBtn.addEventListener("click", async () => {
  if (!confirm(t("maint.restart.confirm"))) return;
  try {
    await api("/api/device/reboot", { method: "POST" });
    stateMsg.textContent = t("maint.restart.requested");
  } catch (err) {
    stateMsg.textContent = err.message;
  }
});

if (factoryResetBtn) {
  factoryResetBtn.addEventListener("click", async () => {
    if (!confirm(t("maint.factory.confirm"))) return;
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
        stateMsg.textContent = `${t("maint.factory.rejected")} ${detail}`;
        return;
      }
      stateMsg.textContent = t("maint.factory.requested");
    } catch (err) {
      stateMsg.textContent = err.message;
    }
  });
}

if (otaFile) {
  otaFile.addEventListener("change", () => {
    if (otaFile.files && otaFile.files.length > 0) {
      const f = otaFile.files[0];
      const size = (f.size / 1024).toFixed(1);
      otaFilename.textContent = `${f.name}  ·  ${size} KB`;
    } else {
      otaFilename.textContent = t("ota.no_file");
    }
  });
}

if (otaBtn) {
  otaBtn.addEventListener("click", () => {
    otaMsg.textContent = "";
    if (!otaFile.files || otaFile.files.length === 0) {
      otaMsg.textContent = t("ota.no_bin");
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
        otaMsg.textContent = `${t("ota.uploading")} ${pct}%`;
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        otaMsg.textContent = t("ota.complete");
      } else {
        let detail = xhr.responseText;
        try {
          const j = JSON.parse(xhr.responseText);
          detail = humanError(j.error) || j.error || detail;
        } catch {
          // ignore
        }
        otaMsg.textContent = `${t("ota.failed")} ${detail}`;
      }
    };
    xhr.onerror = () => {
      otaMsg.textContent = t("ota.network_error");
    };
    xhr.send(form);
  });
}

// ============ Language switcher ============

document.querySelectorAll("[data-lang-btn]").forEach((btn) => {
  btn.addEventListener("click", () => setLang(btn.dataset.langBtn));
});

// ============ Boot ============

applyI18n();
setLang(currentLang);  // marks the right button active

initSession().then(() => {
  if (!consoleGrid.classList.contains("hidden")) {
    startPeriodicRefresh();
  }
});
