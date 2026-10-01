/**
 * Minimal browser runtime for Imperva sensor scripts.
 * Captures XHR/fetch POST payloads and document.cookie writes.
 * Used by imperva_bypass.py via Node (not a headless browser).
 */
"use strict";

const captured = {
  posts: [],
  cookies: {},
  errors: [],
  logs: [],
};

function log(msg) {
  captured.logs.push(String(msg));
}

const USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

class CookieJar {
  constructor() {
    this._map = {};
  }
  get cookie() {
    return Object.entries(this._map)
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");
  }
  set cookie(raw) {
    const pair = String(raw).split(";")[0];
    const eq = pair.indexOf("=");
    if (eq === -1) return;
    const name = pair.slice(0, eq).trim();
    const value = pair.slice(eq + 1).trim();
    if (name) {
      this._map[name] = value;
      captured.cookies[name] = value;
    }
  }
  getItem(name) {
    return this._map[name] || null;
  }
}

function hookSrc(el, label) {
  let _src = "";
  Object.defineProperty(el, "src", {
    get() {
      return _src;
    },
    set(v) {
      _src = String(v);
      captured.posts.push({
        method: "GET",
        url: _src,
        headers: {},
        body: "",
        via: label,
      });
    },
    configurable: true,
  });
}

function makeElement(tag) {
  const tagName = String(tag || "").toUpperCase();
  const el = {
    tagName,
    style: {},
    children: [],
    attributes: {},
    innerHTML: "",
    textContent: "",
    offsetWidth: 300,
    offsetHeight: 150,
    clientWidth: 300,
    clientHeight: 150,
    getContext() {
      return {
        fillRect() {},
        fillText() {},
        measureText(t) {
          return { width: String(t).length * 7 };
        },
        arc() {},
        stroke() {},
        fill() {},
        beginPath() {},
        closePath() {},
        moveTo() {},
        lineTo() {},
        rect() {},
        createLinearGradient() {
          return { addColorStop() {} };
        },
        getImageData() {
          return { data: new Uint8ClampedArray(16) };
        },
        canvas: { width: 300, height: 150 },
        font: "10px sans-serif",
      };
    },
    toDataURL() {
      return "data:image/png;base64,iVBORw0KGgo=";
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    removeChild(child) {
      this.children = this.children.filter((c) => c !== child);
      return child;
    },
    setAttribute(k, v) {
      this.attributes[k] = v;
    },
    getAttribute(k) {
      return this.attributes[k] || null;
    },
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return true;
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    getElementsByTagName() {
      return [];
    },
    click() {},
    focus() {},
    blur() {},
    submit() {
      captured.posts.push({
        method: (el.method || "GET").toUpperCase(),
        url: el.action || "",
        headers: {},
        body: el._body || "",
        via: "form.submit",
      });
    },
    _body: "",
  };
  if (tagName === "SCRIPT" || tagName === "IFRAME" || tagName === "IMG") {
    hookSrc(el, tagName.toLowerCase());
  }
  if (tagName === "FORM") {
    let _action = "";
    Object.defineProperty(el, "action", {
      get() {
        return _action;
      },
      set(v) {
        _action = String(v);
      },
      configurable: true,
    });
    Object.defineProperty(el, "method", {
      value: "POST",
      writable: true,
    });
  }
  return el;
}

const document = {
  cookie: "",
  _cookieJar: new CookieJar(),
  location: {
    href: "https://all.accor.com/a/en.html",
    hostname: "all.accor.com",
    host: "all.accor.com",
    protocol: "https:",
    origin: "https://all.accor.com",
    pathname: "/a/en.html",
    search: "",
    hash: "",
  },
  referrer: "https://all.accor.com/",
  documentElement: makeElement("html"),
  body: makeElement("body"),
  head: makeElement("head"),
  createElement(tag) {
    return makeElement(tag);
  },
  getElementById() {
    return null;
  },
  getElementsByTagName(tag) {
    if (String(tag).toLowerCase() === "script") return [];
    return [];
  },
  querySelector() {
    return null;
  },
  querySelectorAll() {
    return [];
  },
  addEventListener() {},
  removeEventListener() {},
  createEvent() {
    return { initEvent() {} };
  },
  currentScript: { src: "" },
};

Object.defineProperty(document, "cookie", {
  get() {
    return document._cookieJar.cookie;
  },
  set(v) {
    document._cookieJar.cookie = v;
  },
});

const navigator = {
  userAgent: USER_AGENT,
  language: "en-US",
  languages: ["en-US", "en"],
  platform: "Win32",
  hardwareConcurrency: 8,
  deviceMemory: 8,
  maxTouchPoints: 0,
  vendor: "Google Inc.",
  productSub: "20030107",
  cookieEnabled: true,
  doNotTrack: null,
  webdriver: false,
  plugins: { length: 5, item: () => null, namedItem: () => null },
  mimeTypes: { length: 2, item: () => null, namedItem: () => null },
  connection: { effectiveType: "4g", rtt: 50, downlink: 10 },
  permissions: {
    query: async () => ({ state: "prompt" }),
  },
  getBattery: async () => ({
    charging: true,
    chargingTime: 0,
    dischargingTime: Infinity,
    level: 1,
  }),
  mediaDevices: {
    enumerateDevices: async () => [],
  },
};

const screen = {
  width: 1920,
  height: 1080,
  availWidth: 1920,
  availHeight: 1040,
  colorDepth: 24,
  pixelDepth: 24,
  orientation: { type: "landscape-primary", angle: 0 },
};

const performance = {
  now: () => Date.now() % 1000000,
  timing: {
    navigationStart: Date.now() - 3000,
    loadEventEnd: Date.now() - 500,
    domContentLoadedEventEnd: Date.now() - 800,
  },
  memory: { jsHeapSizeLimit: 2172649472, totalJSHeapSize: 20000000, usedJSHeapSize: 10000000 },
};

function XMLHttpRequest() {
  this._headers = {};
  this.readyState = 0;
  this.status = 0;
  this.responseText = "";
  this.onreadystatechange = null;
  this.onload = null;
  this.onerror = null;
}
XMLHttpRequest.prototype.open = function (method, url) {
  this._method = method;
  this._url = url;
};
XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
  this._headers[k] = v;
};
XMLHttpRequest.prototype.send = function (body) {
  captured.posts.push({
    method: this._method,
    url: this._url,
    headers: { ...this._headers },
    body: body == null ? "" : String(body),
  });
  this.readyState = 4;
  this.status = 200;
  this.responseText = JSON.stringify({
    token: "mock-token-not-from-server",
    renewInSec: 3600,
    cookieDomain: "all.accor.com",
  });
  if (typeof this.onreadystatechange === "function") this.onreadystatechange();
  if (typeof this.onload === "function") this.onload();
};
XMLHttpRequest.DONE = 4;

async function fetch(url, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const body = opts.body == null ? "" : String(opts.body);
  captured.posts.push({
    method,
    url: String(url),
    headers: opts.headers || {},
    body,
  });
  return {
    ok: true,
    status: 200,
    json: async () => ({
      token: "mock-token-not-from-server",
      renewInSec: 3600,
      cookieDomain: "all.accor.com",
    }),
    text: async () =>
      JSON.stringify({
        token: "mock-token-not-from-server",
        renewInSec: 3600,
        cookieDomain: "all.accor.com",
      }),
  };
}

const timers = [];
function setTimeout(fn, ms) {
  const id = timers.length + 1;
  timers.push({ id, fn, ms: ms || 0, done: false });
  return id;
}
function clearTimeout() {}
function setInterval(fn, ms) {
  return setTimeout(fn, ms);
}
function clearInterval() {}

function atob(s) {
  return Buffer.from(String(s), "base64").toString("binary");
}
function btoa(s) {
  return Buffer.from(String(s), "binary").toString("base64");
}

const window = {
  document,
  navigator,
  screen,
  performance,
  location: document.location,
  history: { length: 1, pushState() {}, replaceState() {} },
  localStorage: {
    _d: {},
    getItem(k) {
      return this._d[k] || null;
    },
    setItem(k, v) {
      this._d[k] = String(v);
    },
    removeItem(k) {
      delete this._d[k];
    },
  },
  sessionStorage: {
    _d: {},
    getItem(k) {
      return this._d[k] || null;
    },
    setItem(k, v) {
      this._d[k] = String(v);
    },
    removeItem(k) {
      delete this._d[k];
    },
  },
  XMLHttpRequest,
  fetch,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
  atob,
  btoa,
  Date,
  Math,
  JSON,
  Array,
  Object,
  String,
  Number,
  Boolean,
  RegExp,
  Error,
  TypeError,
  Uint8Array,
  Uint8ClampedArray,
  ArrayBuffer,
  DataView,
  Promise,
  Map,
  Set,
  WeakMap,
  WeakSet,
  Symbol,
  Proxy,
  Reflect,
  parseInt,
  parseFloat,
  isNaN,
  isFinite,
  encodeURIComponent,
  decodeURIComponent,
  encodeURI,
  decodeURI,
  escape,
  unescape,
  console: {
    log: (...a) => log(a.join(" ")),
    warn: (...a) => log("warn:" + a.join(" ")),
    error: (...a) => captured.errors.push(a.join(" ")),
  },
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent() {
    return true;
  },
  getComputedStyle() {
    return {};
  },
  matchMedia() {
    return { matches: false, addListener() {}, removeListener() {} };
  },
  devicePixelRatio: 1,
  innerWidth: 1920,
  innerHeight: 969,
  outerWidth: 1920,
  outerHeight: 1080,
  screenX: 0,
  screenY: 0,
  pageXOffset: 0,
  pageYOffset: 0,
  scrollX: 0,
  scrollY: 0,
  chrome: { runtime: {} },
  crypto: {
    getRandomValues(arr) {
      for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256);
      return arr;
    },
    subtle: {},
  },
  requestAnimationFrame(fn) {
    return setTimeout(fn, 16);
  },
  cancelAnimationFrame() {},
  MutationObserver: class {
    observe() {}
    disconnect() {}
  },
  IntersectionObserver: class {
    observe() {}
    disconnect() {}
  },
  ResizeObserver: class {
    observe() {}
    disconnect() {}
  },
  Worker: class {
    constructor() {}
    postMessage() {}
    terminate() {}
  },
  Blob: class {
    constructor(parts) {
      this._parts = parts;
    }
  },
  URL: {
    createObjectURL() {
      return "blob:https://all.accor.com/mock";
    },
    revokeObjectURL() {},
  },
  Intl: global.Intl,
  Buffer: undefined,
};

window.window = window;
window.self = window;
window.top = window;
window.parent = window;
window.globalThis = window;

const vm = require("vm");

function buildSandbox() {
  timers.length = 0;
  return {
    window,
    document,
    navigator,
    screen,
    location: document.location,
    history: window.history,
    localStorage: window.localStorage,
    sessionStorage: window.sessionStorage,
    XMLHttpRequest,
    fetch,
    atob,
    btoa,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    performance,
    console: window.console,
    Date,
    Math,
    JSON,
    Array,
    Object,
    String,
    Number,
    Boolean,
    RegExp,
    Error,
    TypeError,
    Uint8Array,
    Uint8ClampedArray,
    ArrayBuffer,
    DataView,
    Promise,
    Map,
    Set,
    WeakMap,
    WeakSet,
    Symbol,
    Proxy,
    Reflect,
    parseInt,
    parseFloat,
    isNaN,
    isFinite,
    encodeURIComponent,
    decodeURIComponent,
    encodeURI,
    decodeURI,
    escape,
    unescape,
    Intl: global.Intl,
    MutationObserver: window.MutationObserver,
    IntersectionObserver: window.IntersectionObserver,
    ResizeObserver: window.ResizeObserver,
    Worker: window.Worker,
    Blob: window.Blob,
    URL: window.URL,
    devicePixelRatio: 1,
    innerWidth: 1920,
    innerHeight: 969,
    outerWidth: 1920,
    outerHeight: 1080,
    screenX: 0,
    screenY: 0,
    pageXOffset: 0,
    pageYOffset: 0,
    scrollX: 0,
    scrollY: 0,
    chrome: window.chrome,
    crypto: window.crypto,
    requestAnimationFrame: window.requestAnimationFrame,
    cancelAnimationFrame: window.cancelAnimationFrame,
    addEventListener: window.addEventListener,
    removeEventListener: window.removeEventListener,
    dispatchEvent: window.dispatchEvent,
    getComputedStyle: window.getComputedStyle,
    matchMedia: window.matchMedia,
  };
}

function runSensorScript(source, maxTicks = 200) {
  captured.posts.length = 0;
  captured.errors.length = 0;
  captured.logs.length = 0;
  const sandbox = buildSandbox();
  sandbox.self = window;
  sandbox.top = window;
  sandbox.parent = window;
  sandbox.globalThis = sandbox;
  const context = vm.createContext(sandbox);
  try {
    vm.runInContext(source, context, { timeout: 120000 });
  } catch (err) {
    captured.errors.push(String(err && err.stack ? err.stack : err));
  }
  let idle = 0;
  for (let tick = 0; tick < maxTicks && idle < 5; tick++) {
    const pending = timers.filter((t) => !t.done);
    if (!pending.length) {
      idle += 1;
      continue;
    }
    idle = 0;
    for (const t of pending) {
      t.done = true;
      try {
        if (typeof t.fn === "function") t.fn();
      } catch (err) {
        captured.errors.push(String(err && err.stack ? err.stack : err));
      }
    }
  }
  return captured;
}

if (require.main === module) {
  const fs = require("fs");
  const path = process.argv[2] || "_sensor.js";
  const maxTicks = Number(process.argv[3] || 200);
  const source = fs.readFileSync(path, "utf8");
  const result = runSensorScript(source, maxTicks);
  console.log(JSON.stringify(result, null, 2));
}

module.exports = { runSensorScript, captured };
