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
    "errors.ssid_length": "SSID must be 1–32 characters.",
    "errors.password_length": "Password must be at most 63 characters.",
    "errors.wifi_list_full": "You already have the maximum number of saved networks.",
    "errors.wifi_in_use":
      "Can't remove the network you're connected to. Switch to another saved one first.",
    "errors.wifi_not_found": "That network is not in the list.",
    "errors.save_failed": "Could not save to flash.",

    "wifi.title": "Wi-Fi networks",
    "wifi.empty":
      "No saved networks yet. Add one to keep this BusyLight online when you move it around.",
    "wifi.ssid": "Network name (SSID)",
    "wifi.password": "Password",
    "wifi.password_placeholder": "Leave empty for open networks",
    "wifi.add": "Save network",
    "wifi.adding": "Saving…",
    "wifi.added": "Network saved.",
    "wifi.current": "Connected",
    "wifi.remove": "Remove",
    "wifi.confirm_remove":
      'Remove "{ssid}"? The device will fall back to another saved network if available.',
    "wifi.meta_count": "{n} of {max}",
    "wifi.no_ssid": "Type a network name first.",

    "mqtt.title": "MQTT / Home Assistant",
    "mqtt.lede":
      "Connect this BusyLight to an MQTT broker. Home Assistant auto-discovers it as a Select entity (busylight/<host>/state and /cmd/set).",
    "mqtt.disabled": "Disabled",
    "mqtt.enabled_off": "Disabled",
    "mqtt.enabled_on": "Enabled",
    "mqtt.enable": "Enable MQTT bridge",
    "mqtt.host": "Broker host",
    "mqtt.port": "Port",
    "mqtt.username": "Username",
    "mqtt.password": "Password",
    "mqtt.password_placeholder": "Leave empty to keep current",
    "mqtt.save": "Save MQTT settings",
    "mqtt.saved": "MQTT settings saved.",
    "errors.mqtt_host_required":
      "Broker host is required when MQTT is enabled.",
    "errors.port_invalid": "Port must be between 1 and 65535.",
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
    "errors.ssid_length": "Il nome rete deve avere da 1 a 32 caratteri.",
    "errors.password_length": "La password può avere al massimo 63 caratteri.",
    "errors.wifi_list_full":
      "Hai già raggiunto il numero massimo di reti salvate.",
    "errors.wifi_in_use":
      "Non puoi rimuovere la rete attualmente in uso. Passa prima a un'altra rete salvata.",
    "errors.wifi_not_found": "Questa rete non è nella lista.",
    "errors.save_failed": "Impossibile salvare nella flash.",

    "wifi.title": "Reti Wi-Fi",
    "wifi.empty":
      "Nessuna rete salvata. Aggiungine una per tenere il BusyLight online quando lo sposti.",
    "wifi.ssid": "Nome rete (SSID)",
    "wifi.password": "Password",
    "wifi.password_placeholder": "Lascia vuoto per reti aperte",
    "wifi.add": "Salva rete",
    "wifi.adding": "Salvo…",
    "wifi.added": "Rete salvata.",
    "wifi.current": "Connesso",
    "wifi.remove": "Rimuovi",
    "wifi.confirm_remove":
      'Rimuovo "{ssid}"? Il dispositivo passerà ad un\'altra rete salvata se disponibile.',
    "wifi.meta_count": "{n} di {max}",
    "wifi.no_ssid": "Inserisci prima un nome rete.",

    "mqtt.title": "MQTT / Home Assistant",
    "mqtt.lede":
      "Collega questo BusyLight a un broker MQTT. Home Assistant lo rileva automaticamente come entità Select (busylight/<host>/state e /cmd/set).",
    "mqtt.disabled": "Disattivato",
    "mqtt.enabled_off": "Disattivato",
    "mqtt.enabled_on": "Attivo",
    "mqtt.enable": "Attiva bridge MQTT",
    "mqtt.host": "Indirizzo broker",
    "mqtt.port": "Porta",
    "mqtt.username": "Username",
    "mqtt.password": "Password",
    "mqtt.password_placeholder": "Lascia vuoto per non cambiarla",
    "mqtt.save": "Salva impostazioni MQTT",
    "mqtt.saved": "Impostazioni MQTT salvate.",
    "errors.mqtt_host_required":
      "L'indirizzo del broker è obbligatorio quando MQTT è attivo.",
    "errors.port_invalid": "La porta deve essere tra 1 e 65535.",
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
  if (
    wifiList &&
    !consoleGrid.classList.contains("hidden")
  ) {
    // re-fetch so the "Connected" tag is rendered in the new language
    refreshWifiList();
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

const wifiList = document.getElementById("wifi-list");
const wifiEmpty = document.getElementById("wifi-empty");
const wifiMeta = document.getElementById("wifi-meta");
const wifiNewSsid = document.getElementById("wifi-new-ssid");
const wifiNewPassword = document.getElementById("wifi-new-password");
const wifiAddBtn = document.getElementById("wifi-add-btn");
const wifiMsg = document.getElementById("wifi-msg");

const mqttEnabled = document.getElementById("mqtt-enabled");
const mqttHost = document.getElementById("mqtt-host");
const mqttPort = document.getElementById("mqtt-port");
const mqttUser = document.getElementById("mqtt-user");
const mqttPass = document.getElementById("mqtt-pass");
const mqttSaveBtn = document.getElementById("mqtt-save");
const mqttMsg = document.getElementById("mqtt-msg");
const mqttStatus = document.getElementById("mqtt-status");

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

async function refreshWifiList() {
  if (!wifiList) return;
  try {
    const data = await api("/api/wifi");
    renderWifiList(data);
  } catch (err) {
    if (err.status === 401) showLogin();
    if (wifiMsg) wifiMsg.textContent = err.message;
  }
}

function renderWifiList(data) {
  if (!wifiList) return;
  const networks = Array.isArray(data.networks) ? data.networks : [];
  const max = typeof data.max === "number" ? data.max : 6;

  wifiList.innerHTML = "";
  for (const net of networks) {
    const li = document.createElement("li");
    li.className = "wifi-row" + (net.current ? " current" : "");

    const left = document.createElement("div");
    left.style.display = "flex";
    left.style.alignItems = "center";
    left.style.gap = "8px";

    const name = document.createElement("span");
    name.className = "wifi-row-name";
    name.textContent = net.ssid;
    left.appendChild(name);

    if (net.current) {
      const tag = document.createElement("span");
      tag.className = "wifi-row-tag";
      tag.textContent = t("wifi.current");
      left.appendChild(tag);
    }

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "wifi-row-remove";
    btn.setAttribute("aria-label", t("wifi.remove"));
    btn.textContent = "×";
    btn.addEventListener("click", () => removeWifi(net.ssid, !!net.current));

    li.appendChild(left);
    li.appendChild(btn);
    wifiList.appendChild(li);
  }

  if (wifiEmpty) wifiEmpty.hidden = networks.length > 0;
  if (wifiMeta) {
    wifiMeta.textContent = t("wifi.meta_count")
      .replace("{n}", String(networks.length))
      .replace("{max}", String(max));
  }
}

async function addWifi() {
  if (!wifiNewSsid) return;
  const ssid = wifiNewSsid.value.trim();
  const password = wifiNewPassword.value;
  if (!ssid) {
    wifiMsg.textContent = t("wifi.no_ssid");
    return;
  }
  wifiMsg.textContent = t("wifi.adding");
  try {
    await api("/api/wifi", {
      method: "POST",
      body: JSON.stringify({ ssid, password }),
    });
    wifiNewSsid.value = "";
    wifiNewPassword.value = "";
    wifiMsg.textContent = t("wifi.added");
    await refreshWifiList();
  } catch (err) {
    wifiMsg.textContent = err.message;
  }
}

async function removeWifi(ssid, isCurrent) {
  const prompt = t("wifi.confirm_remove").replace("{ssid}", ssid);
  if (!confirm(prompt)) return;
  try {
    const body = { ssid };
    if (isCurrent) body.force = true;
    const r = await fetch("/api/wifi", {
      method: "DELETE",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken(),
      },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const text = await r.text();
      let msg = text;
      try {
        const j = JSON.parse(text);
        msg = humanError(j.error) || j.error || text;
      } catch {}
      wifiMsg.textContent = msg;
      return;
    }
    await refreshWifiList();
  } catch (err) {
    wifiMsg.textContent = err.message;
  }
}

async function refreshMqtt() {
  if (!mqttHost) return;
  try {
    const data = await api("/api/mqtt");
    if (mqttEnabled) mqttEnabled.checked = !!data.enabled;
    if (mqttHost) mqttHost.value = data.host || "";
    if (mqttPort) mqttPort.value = data.port ? String(data.port) : "1883";
    if (mqttUser) mqttUser.value = data.username || "";
    // Never echo the stored password back; placeholder hints at it.
    if (mqttPass) mqttPass.value = "";
    if (mqttStatus) {
      mqttStatus.textContent = t(
        data.enabled ? "mqtt.enabled_on" : "mqtt.enabled_off"
      );
    }
  } catch (err) {
    if (err.status === 401) showLogin();
  }
}

async function saveMqtt() {
  if (!mqttSaveBtn) return;
  mqttMsg.textContent = "";
  const body = {
    enabled: !!mqttEnabled.checked,
    host: mqttHost.value.trim(),
    port: Number(mqttPort.value.trim() || "1883"),
    username: mqttUser.value,
  };
  // Only send the password if the user typed something. Empty input
  // means "leave whatever is stored alone".
  if (mqttPass.value) body.password = mqttPass.value;

  try {
    await api("/api/mqtt", {
      method: "POST",
      body: JSON.stringify(body),
    });
    mqttPass.value = "";
    mqttMsg.textContent = t("mqtt.saved");
    if (mqttStatus) {
      mqttStatus.textContent = t(
        body.enabled ? "mqtt.enabled_on" : "mqtt.enabled_off"
      );
    }
  } catch (err) {
    mqttMsg.textContent = err.message;
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
    await refreshWifiList();
    await refreshMqtt();
    showApp();
  } catch (err) {
    if (err.status === 401) {
      showLogin();
      return;
    }
    loginMsg.textContent = err.message;
  }
}

// Periodically refresh uptime + state so the orb stays in sync. With
// WebSockets connected the orb already updates in real-time, but we
// keep polling at a relaxed cadence to refresh uptime/RSSI and to
// recover the state if the socket is wedged.
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

// ============ WebSocket live state ============
//
// The firmware exposes a WebSocket server on port 81 and pushes a
// `{event:"state",state:"..."}` payload whenever the LED flips —
// triggered both by the local web API and (later) by external
// controllers like the presence helper. The page subscribes on login
// success and reconnects with backoff if the socket drops.

let ws = null;
let wsReconnectTimer = null;
let wsReconnectDelayMs = 1500;

function startWebSocket() {
  if (ws || consoleGrid.classList.contains("hidden")) return;
  const host = window.location.hostname || "busylight.local";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  try {
    ws = new WebSocket(`${proto}//${host}:81/`);
  } catch {
    scheduleWsReconnect();
    return;
  }

  ws.onopen = () => {
    wsReconnectDelayMs = 1500; // reset backoff on successful connect
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.event === "state" && msg.state) {
        setStateUi(msg.state);
      }
    } catch {
      // ignore non-JSON
    }
  };
  ws.onclose = () => {
    ws = null;
    scheduleWsReconnect();
  };
  ws.onerror = () => {
    // onclose will fire next; handled there.
  };
}

function scheduleWsReconnect() {
  if (wsReconnectTimer) return;
  if (consoleGrid.classList.contains("hidden")) return;
  wsReconnectTimer = setTimeout(() => {
    wsReconnectTimer = null;
    wsReconnectDelayMs = Math.min(wsReconnectDelayMs * 1.6, 15000);
    startWebSocket();
  }, wsReconnectDelayMs);
}

function stopWebSocket() {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }
  if (ws) {
    try { ws.close(); } catch {}
    ws = null;
  }
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
    startWebSocket();
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
  stopWebSocket();
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

if (wifiAddBtn) {
  wifiAddBtn.addEventListener("click", addWifi);
}
if (wifiNewPassword) {
  wifiNewPassword.addEventListener("keydown", (e) => {
    if (e.key === "Enter") addWifi();
  });
}

if (mqttSaveBtn) {
  mqttSaveBtn.addEventListener("click", saveMqtt);
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
    startWebSocket();
  }
});
