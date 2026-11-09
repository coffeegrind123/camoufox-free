/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// Camoufox's per-window and startup work. It lives here rather than in
// browser-init.js because chrome://browser/content/ is content-accessible: a page
// can load that file and read its functions back, so it must stay byte-identical
// to stock. Registered by category entries in camoufox-window-module.patch.

const lazy = {};
ChromeUtils.defineESModuleGetters(lazy, {
  AddonManager: "resource://gre/modules/AddonManager.sys.mjs",
  FileUtils: "resource://gre/modules/FileUtils.sys.mjs",
});

// Default-branch prefs are never written to prefs.js, so they reset every launch.
const ADDONS_INSTALLED_PREF = "camoufox.addons.installed";
const CERTS_IMPORTED_PREF = "camoufox.certificates.imported";

function debug(msg) {
  ChromeUtils.camouDebug(msg);
}

function onceThisLaunch(pref) {
  const defaults = Services.prefs.getDefaultBranch("");
  if (defaults.getBoolPref(pref, false)) {
    return false;
  }
  defaults.setBoolPref(pref, true);
  return true;
}

function processRawCertificate(content) {
  return content.replace(/\-{5}[\w]+\s[\w]+\-{5}/g, "").replace(/\s/g, "");
}

function importCertificate(certdb, certData, source) {
  try {
    certdb.addCertFromBase64(certData, "C,C,C", "");
    debug("Successfully imported " + source + " certificate");
  } catch (e) {
    debug("Failed to import " + source + " certificate: " + e);
  }
}

async function readCertFile(path) {
  debug("Reading certificate file: " + path);
  const file = new lazy.FileUtils.File(path);
  const ioService = Cc["@mozilla.org/network/io-service;1"].getService(Ci.nsIIOService);
  const channel = ioService.newChannelFromURI(
    ioService.newFileURI(file),
    null,
    Services.scriptSecurityManager.getSystemPrincipal(),
    null,
    Ci.nsILoadInfo.SEC_ALLOW_CROSS_ORIGIN_SEC_CONTEXT_IS_NULL,
    Ci.nsIContentPolicy.TYPE_OTHER
  );
  const inputStream = Cc["@mozilla.org/scriptableinputstream;1"].createInstance(
    Ci.nsIScriptableInputStream
  );
  const input = channel.open();
  inputStream.init(input);
  const content = inputStream.read(input.available());
  inputStream.close();
  input.close();
  return processRawCertificate(content);
}

async function installTemporaryAddon(addonPath) {
  const addon = await lazy.AddonManager.installTemporaryAddon(new lazy.FileUtils.File(addonPath));
  Services.obs.notifyObservers(null, "devtools-installed-addon", addon.id);
  return addon;
}

function installAddons() {
  const addonPaths = ChromeUtils.camouGetStringList("addons");
  if (!addonPaths?.length || !onceThisLaunch(ADDONS_INSTALLED_PREF)) {
    return;
  }
  Promise.all(addonPaths.map(installTemporaryAddon))
    .then(addons => debug("Installed " + addons.length + " addon(s)"))
    .catch(e => debug("Failed to install addons: " + e));
}

function importCertificates() {
  const certsPaths = ChromeUtils.camouGetStringList("certificatePaths");
  const certsRaw = ChromeUtils.camouGetStringList("certificates");
  if (!(certsPaths?.length || certsRaw?.length) || !onceThisLaunch(CERTS_IMPORTED_PREF)) {
    return;
  }
  debug("Found certificates to import");
  let certdb = Cc["@mozilla.org/security/x509certdb;1"].getService(Ci.nsIX509CertDB);
  try {
    certdb = Cc["@mozilla.org/security/x509certdb;1"].getService(Ci.nsIX509CertDB2);
  } catch (e) {}
  if (certsPaths?.length) {
    debug("Processing " + certsPaths.length + " certificate files");
    Promise.all(certsPaths.map(readCertFile))
      .then(all => all.forEach(certData => importCertificate(certdb, certData, "from file")))
      .catch(e => debug("Failed to read certificate files: " + e));
  }
  for (const rawCert of certsRaw || []) {
    try {
      importCertificate(certdb, processRawCertificate(rawCert), "raw");
    } catch (e) {
      debug("Failed to process raw certificate: " + e);
    }
  }
}

// The claimed OS's window frame (window.frameLeft/Top/Right/Bottom), or null.
// With it a page reads its content area plus this frame as the window's outer
// size (window-sizing-claimed-os.patch), whatever the real window's chrome is.
function claimedFrame() {
  const sides = ["Left", "Top", "Right", "Bottom"].map(side =>
    ChromeUtils.camouGetInt("window.frame" + side)
  );
  if (!sides.some(Boolean)) {
    return null;
  }
  const [left, top, right, bottom] = sides.map(inset => inset || 0);
  return { left, top, right, bottom };
}

function applyWindowPosition(win) {
  // Each window the browser opens is moved to the identity's position, so it
  // really is there and reports it. Where the window manager puts it elsewhere
  // anyway, the page still reads the identity's position
  // (window-screen-origin.patch); a popup a page opened reports where it
  // really is, as in stock. 0 is a position, so an absent key reads as a
  // value no screen has (the WebIDL argument cannot be NaN).
  const UNSET = -1e9;
  const x = ChromeUtils.camouGetDouble("window.screenX", UNSET);
  const y = ChromeUtils.camouGetDouble("window.screenY", UNSET);
  if (x === UNSET && y === UNSET) {
    return;
  }
  // The window manager places a window when it maps it, after load, so the
  // position is held through startup as the size is. A move is only ever
  // made to a normal window: moving a fullscreen or maximized one restores it.
  const deadline = Date.now() + 5000;
  const place = () => {
    if (Date.now() > deadline) {
      win.removeEventListener("MozAfterPaint", place);
      return;
    }
    if (win.windowState !== win.STATE_NORMAL) {
      return;
    }
    const tx = x === UNSET ? win.screenX : x;
    const ty = y === UNSET ? win.screenY : y;
    if (win.screenX !== tx || win.screenY !== ty) {
      win.moveTo(tx, ty);
    }
  };
  place();
  win.addEventListener("MozAfterPaint", place);
}

function applyWindowSize(win) {
  // The real window is resized to the identity's size; pinning the document
  // instead deadlocks Juggler's viewport handshake (daijro/camoufox#666).
  // Without an identity size, stock's own startup sizing applies. So it does
  // for a window a page opened: stock gives it the size its window.open()
  // features ask for.
  const appWindow = win.docShell.treeOwner
    .QueryInterface(Ci.nsIInterfaceRequestor)
    .getInterface(Ci.nsIAppWindow);
  if (appWindow.initialOpenWindowInfo) {
    return;
  }
  applyWindowPosition(win);
  const outerWidth = ChromeUtils.camouGetInt("window.outerWidth");
  const outerHeight = ChromeUtils.camouGetInt("window.outerHeight");
  const innerWidth = ChromeUtils.camouGetInt("window.innerWidth");
  const innerHeight = ChromeUtils.camouGetInt("window.innerHeight");
  if (!(outerWidth || outerHeight || innerWidth || innerHeight)) {
    return;
  }
  const doc = win.document;
  const stack = win.gBrowser.selectedBrowser.closest(".browserStack");
  // An inner size is met by sizing the content area, so the window manager
  // adds its frame to it as it does for stock, and outerWidth/outerHeight and
  // the window's placement follow. Sizing to the outer size instead runs before
  // the frame exists, so the frame lands on top of it. Chrome reads the
  // identity's innerWidth/innerHeight too, so the window is measured: the
  // content area starts where the toolbars end and runs to the window's edge.
  // The bookmarks toolbar shown only on a new tab takes its own room from the
  // content area, as in stock; it is not part of the identity's outer chrome.
  const newTabToolbar = () => {
    const bar = doc.getElementById("PersonalToolbar");
    if (!bar || bar.collapsed ||
        Services.prefs.getCharPref("browser.toolbars.bookmarks.visibility", "newtab") !== "newtab") {
      return 0;
    }
    return bar.getBoundingClientRect().height;
  };
  // With a claimed frame (window-sizing-claimed-os.patch) a page reads its
  // content area plus that frame as the outer size, so an outer size alone is
  // met by sizing the content area to it less the frame. The real window ends
  // up as much larger as its own chrome is larger than the claimed OS's.
  const frame = claimedFrame();
  const contentWidth = innerWidth || (frame && outerWidth ? outerWidth - frame.left - frame.right : 0);
  const contentHeight = innerHeight || (frame && outerHeight ? outerHeight - frame.top - frame.bottom : 0);
  const misfit = () => {
    const client = doc.documentElement.getBoundingClientRect();
    const start = stack.getBoundingClientRect();
    return [
      contentWidth
        ? Math.round(contentWidth + start.left - client.width)
        : outerWidth ? outerWidth - win.outerWidth : 0,
      contentHeight
        ? Math.round(contentHeight + start.top - newTabToolbar() - client.height)
        : outerHeight ? outerHeight - win.outerHeight : 0,
    ];
  };
  // Hold that size through startup: mutter auto-maximizes a new window
  // covering >= 80% of the work area. After the deadline a change is the user's.
  // Where the window cannot grow to the identity's viewport, the content is
  // pinned to that size and still lays out at it. The pin comes off once the
  // real content area is the identity's: from then on the content area
  // follows the window, as in stock (fullscreen, the find bar).
  let pin = null;
  const unpin = () => {
    if (pin && !misfit().some(Boolean)) {
      pin.remove();
      pin = null;
      doc.getElementById("browser")?.style.removeProperty("box-sizing");
    }
  };
  if (innerWidth || innerHeight) {
    doc.getElementById("browser")?.style.setProperty("box-sizing", "content-box");
    pin = doc.createElement("style");
    pin.textContent = `
    .browserStack {
      ${innerWidth ? `width: ${innerWidth}px !important;` : ""}
      ${innerHeight ? `height: ${innerHeight}px !important;` : ""}
      ${innerHeight ? "flex: unset !important;" : ""}
      overflow: auto;
      contain: size;
      scrollbar-width: none;
    }
  `;
    doc.head.appendChild(pin);
  }

  // Only the window manager's changes are undone: a page entering fullscreen
  // or the find bar taking room from the content area leaves the outer size
  // or the size mode to the page and the user, as in stock.
  // An X11 window manager's frame (_NET_FRAME_EXTENTS) can arrive after the
  // window maps. It changes only the margins Firefox adds to the outer size,
  // and with the content area unchanged no resize event fires, so the hold
  // also checks on a timer.
  const deadline = Date.now() + 5000;
  let held = null;
  let holdTimer = null;
  const stopHold = () => {
    win.removeEventListener("sizemodechange", holdStartupSize);
    win.removeEventListener("resize", holdStartupSize);
    if (holdTimer !== null) {
      win.clearInterval(holdTimer);
      holdTimer = null;
    }
  };
  const holdStartupSize = () => {
    if (Date.now() > deadline || win.windowState === win.STATE_FULLSCREEN) {
      stopHold();
      return;
    }
    if (win.windowState === win.STATE_MAXIMIZED) {
      win.restore();
    } else if (held && held[0] === win.outerWidth && held[1] === win.outerHeight &&
               !misfit().some(Boolean)) {
      // The window being at the held size is not enough: the toolbars can
      // reflow after it got there (84px to 72px tall, a few hundred ms in, on
      // a loaded host) with no resize event, which left the content area
      // 12px too tall for the rest of the launch.
      unpin();
      return;
    }
    const [dw, dh] = misfit();
    if (dw || dh) {
      win.resizeBy(dw, dh);
    } else {
      unpin();
    }
    held = [win.outerWidth + dw, win.outerHeight + dh];
  };
  win.addEventListener("sizemodechange", holdStartupSize);
  win.addEventListener("resize", holdStartupSize);
  holdTimer = win.setInterval(holdStartupSize, 100);
  holdStartupSize();
  // After startup too, a maximized window would take the real display's size,
  // larger than the identity's screen, and outerWidth/innerWidth follow the
  // real window: a window bigger than its screen. It goes back to the
  // identity's size. An identity drawn maximized already fills its screen,
  // and a page reads it as maximized (zz-window-presentation.patch).
  win.addEventListener("sizemodechange", () => {
    if (Date.now() > deadline && win.windowState === win.STATE_MAXIMIZED) {
      win.restore();
    }
  });
  // A driver's viewport takes over from the identity's startup size at once.
  win.addEventListener(
    "CamoufoxViewportSized",
    () => {
      stopHold();
      if (pin) {
        pin.remove();
        pin = null;
        doc.getElementById("browser")?.style.removeProperty("box-sizing");
      }
    },
    { once: true }
  );
}

function addDebugListeners(win) {
  if (!ChromeUtils.isCamouDebug()) {
    return;
  }
  debug("Debug mode ON.");
  win.gBrowser.addTabsProgressListener({
    onLocationChange(aBrowser, aWebProgress, aRequest, aLocation) {
      if (aBrowser === win.gBrowser.selectedBrowser) {
        debug("URL changed to: " + aLocation.spec);
      }
    },
  });
  win.gURLBar?.addEventListener("change", () => debug("URL bar value changed to: " + win.gURLBar.value));
}

function addCursorFollower(win) {
  // Debugging aid only: a visible automation cue, so opt-in (showcursor=true).
  if (!ChromeUtils.camouGetBool("showcursor", false)) {
    return;
  }
  const doc = win.document;
  const dot = doc.createElement("div");
  dot.id = "cursor-highlighter";
  dot.style.cssText = `
    position: fixed; width: 10px; height: 10px; background-color: rgba(255,105,105,0.8);
    border-radius: 50%; pointer-events: none; z-index: 2147483647; transform: translate(-50%, -50%);
    box-shadow: 0 0 0 5px rgba(255,105,105,0.5), 0 0 0 10px rgba(255,105,105,0.3), 0 0 0 15px rgba(255,105,105,0.1);
  `;
  doc.documentElement.appendChild(dot);
  win.addEventListener("mousemove", e => {
    dot.style.left = `${e.clientX}px`;
    dot.style.top = `${e.clientY}px`;
  });
}

function applyAcceptLanguages() {
  let camouLocale =
    ChromeUtils.camouGetString("locale:all") || ChromeUtils.camouGetString("navigator.language");
  if (!camouLocale) {
    const language = ChromeUtils.camouGetString("locale:language");
    const region = ChromeUtils.camouGetString("locale:region");
    if (language && region) {
      camouLocale = language + "-" + region + ", " + language;
    }
  }
  if (camouLocale) {
    Services.prefs.setCharPref("intl.accept_languages", camouLocale);
  }
}

export const CamoufoxWindow = {
  onStartup() {
    applyAcceptLanguages();
  },

  // Called from gBrowserInit.onLoad() with the window. The category's jsGlobal
  // is consumed by BrowserUtils.callModulesFromCategory, not passed on.
  onWindowLoad(win) {
    for (const step of [applyWindowSize, addDebugListeners, addCursorFollower]) {
      try {
        step(win);
      } catch (e) {
        debug(`CamoufoxWindow ${step.name} failed: ${e}`);
      }
    }
    installAddons();
    importCertificates();
  },
};
