var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __commonJS = (cb, mod) => function __require() {
  return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// node_modules/canonicalize/lib/canonicalize.js
var require_canonicalize = __commonJS({
  "node_modules/canonicalize/lib/canonicalize.js"(exports, module) {
    "use strict";
    module.exports = function serialize(object) {
      if (typeof object === "number" && isNaN(object)) {
        throw new Error("NaN is not allowed");
      }
      if (typeof object === "number" && !isFinite(object)) {
        throw new Error("Infinity is not allowed");
      }
      if (object === null || typeof object !== "object") {
        return JSON.stringify(object);
      }
      if (object.toJSON instanceof Function) {
        return serialize(object.toJSON());
      }
      if (Array.isArray(object)) {
        const values2 = object.reduce((t, cv, ci) => {
          const comma = ci === 0 ? "" : ",";
          const value = cv === void 0 || typeof cv === "symbol" ? null : cv;
          return `${t}${comma}${serialize(value)}`;
        }, "");
        return `[${values2}]`;
      }
      const values = Object.keys(object).sort().reduce((t, cv) => {
        if (object[cv] === void 0 || typeof object[cv] === "symbol") {
          return t;
        }
        const comma = t.length === 0 ? "" : ",";
        return `${t}${comma}${serialize(cv)}:${serialize(object[cv])}`;
      }, "");
      return `{${values}}`;
    };
  }
});

// node_modules/@firebase/util/dist/postinstall.mjs
var getDefaultsFromPostinstall = () => void 0;

// node_modules/@firebase/util/dist/index.esm.js
var stringToByteArray$1 = function(str) {
  const out = [];
  let p2 = 0;
  for (let i = 0; i < str.length; i++) {
    let c = str.charCodeAt(i);
    if (c < 128) {
      out[p2++] = c;
    } else if (c < 2048) {
      out[p2++] = c >> 6 | 192;
      out[p2++] = c & 63 | 128;
    } else if ((c & 64512) === 55296 && i + 1 < str.length && (str.charCodeAt(i + 1) & 64512) === 56320) {
      c = 65536 + ((c & 1023) << 10) + (str.charCodeAt(++i) & 1023);
      out[p2++] = c >> 18 | 240;
      out[p2++] = c >> 12 & 63 | 128;
      out[p2++] = c >> 6 & 63 | 128;
      out[p2++] = c & 63 | 128;
    } else {
      out[p2++] = c >> 12 | 224;
      out[p2++] = c >> 6 & 63 | 128;
      out[p2++] = c & 63 | 128;
    }
  }
  return out;
};
var byteArrayToString = function(bytes) {
  const out = [];
  let pos = 0, c = 0;
  while (pos < bytes.length) {
    const c1 = bytes[pos++];
    if (c1 < 128) {
      out[c++] = String.fromCharCode(c1);
    } else if (c1 > 191 && c1 < 224) {
      const c2 = bytes[pos++];
      out[c++] = String.fromCharCode((c1 & 31) << 6 | c2 & 63);
    } else if (c1 > 239 && c1 < 365) {
      const c2 = bytes[pos++];
      const c3 = bytes[pos++];
      const c4 = bytes[pos++];
      const u = ((c1 & 7) << 18 | (c2 & 63) << 12 | (c3 & 63) << 6 | c4 & 63) - 65536;
      out[c++] = String.fromCharCode(55296 + (u >> 10));
      out[c++] = String.fromCharCode(56320 + (u & 1023));
    } else {
      const c2 = bytes[pos++];
      const c3 = bytes[pos++];
      out[c++] = String.fromCharCode((c1 & 15) << 12 | (c2 & 63) << 6 | c3 & 63);
    }
  }
  return out.join("");
};
var base64 = {
  /**
   * Maps bytes to characters.
   */
  byteToCharMap_: null,
  /**
   * Maps characters to bytes.
   */
  charToByteMap_: null,
  /**
   * Maps bytes to websafe characters.
   * @private
   */
  byteToCharMapWebSafe_: null,
  /**
   * Maps websafe characters to bytes.
   * @private
   */
  charToByteMapWebSafe_: null,
  /**
   * Our default alphabet, shared between
   * ENCODED_VALS and ENCODED_VALS_WEBSAFE
   */
  ENCODED_VALS_BASE: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
  /**
   * Our default alphabet. Value 64 (=) is special; it means "nothing."
   */
  get ENCODED_VALS() {
    return this.ENCODED_VALS_BASE + "+/=";
  },
  /**
   * Our websafe alphabet.
   */
  get ENCODED_VALS_WEBSAFE() {
    return this.ENCODED_VALS_BASE + "-_.";
  },
  /**
   * Whether this browser supports the atob and btoa functions. This extension
   * started at Mozilla but is now implemented by many browsers. We use the
   * ASSUME_* variables to avoid pulling in the full useragent detection library
   * but still allowing the standard per-browser compilations.
   *
   */
  HAS_NATIVE_SUPPORT: typeof atob === "function",
  /**
   * Base64-encode an array of bytes.
   *
   * @param input An array of bytes (numbers with
   *     value in [0, 255]) to encode.
   * @param webSafe Boolean indicating we should use the
   *     alternative alphabet.
   * @return The base64 encoded string.
   */
  encodeByteArray(input, webSafe) {
    if (!Array.isArray(input)) {
      throw Error("encodeByteArray takes an array as a parameter");
    }
    this.init_();
    const byteToCharMap = webSafe ? this.byteToCharMapWebSafe_ : this.byteToCharMap_;
    const output = [];
    for (let i = 0; i < input.length; i += 3) {
      const byte1 = input[i];
      const haveByte2 = i + 1 < input.length;
      const byte2 = haveByte2 ? input[i + 1] : 0;
      const haveByte3 = i + 2 < input.length;
      const byte3 = haveByte3 ? input[i + 2] : 0;
      const outByte1 = byte1 >> 2;
      const outByte2 = (byte1 & 3) << 4 | byte2 >> 4;
      let outByte3 = (byte2 & 15) << 2 | byte3 >> 6;
      let outByte4 = byte3 & 63;
      if (!haveByte3) {
        outByte4 = 64;
        if (!haveByte2) {
          outByte3 = 64;
        }
      }
      output.push(byteToCharMap[outByte1], byteToCharMap[outByte2], byteToCharMap[outByte3], byteToCharMap[outByte4]);
    }
    return output.join("");
  },
  /**
   * Base64-encode a string.
   *
   * @param input A string to encode.
   * @param webSafe If true, we should use the
   *     alternative alphabet.
   * @return The base64 encoded string.
   */
  encodeString(input, webSafe) {
    if (this.HAS_NATIVE_SUPPORT && !webSafe) {
      return btoa(input);
    }
    return this.encodeByteArray(stringToByteArray$1(input), webSafe);
  },
  /**
   * Base64-decode a string.
   *
   * @param input to decode.
   * @param webSafe True if we should use the
   *     alternative alphabet.
   * @return string representing the decoded value.
   */
  decodeString(input, webSafe) {
    if (this.HAS_NATIVE_SUPPORT && !webSafe) {
      return atob(input);
    }
    return byteArrayToString(this.decodeStringToByteArray(input, webSafe));
  },
  /**
   * Base64-decode a string.
   *
   * In base-64 decoding, groups of four characters are converted into three
   * bytes.  If the encoder did not apply padding, the input length may not
   * be a multiple of 4.
   *
   * In this case, the last group will have fewer than 4 characters, and
   * padding will be inferred.  If the group has one or two characters, it decodes
   * to one byte.  If the group has three characters, it decodes to two bytes.
   *
   * @param input Input to decode.
   * @param webSafe True if we should use the web-safe alphabet.
   * @return bytes representing the decoded value.
   */
  decodeStringToByteArray(input, webSafe) {
    this.init_();
    const charToByteMap = webSafe ? this.charToByteMapWebSafe_ : this.charToByteMap_;
    const output = [];
    for (let i = 0; i < input.length; ) {
      const byte1 = charToByteMap[input.charAt(i++)];
      const haveByte2 = i < input.length;
      const byte2 = haveByte2 ? charToByteMap[input.charAt(i)] : 0;
      ++i;
      const haveByte3 = i < input.length;
      const byte3 = haveByte3 ? charToByteMap[input.charAt(i)] : 64;
      ++i;
      const haveByte4 = i < input.length;
      const byte4 = haveByte4 ? charToByteMap[input.charAt(i)] : 64;
      ++i;
      if (byte1 == null || byte2 == null || byte3 == null || byte4 == null) {
        throw new DecodeBase64StringError();
      }
      const outByte1 = byte1 << 2 | byte2 >> 4;
      output.push(outByte1);
      if (byte3 !== 64) {
        const outByte2 = byte2 << 4 & 240 | byte3 >> 2;
        output.push(outByte2);
        if (byte4 !== 64) {
          const outByte3 = byte3 << 6 & 192 | byte4;
          output.push(outByte3);
        }
      }
    }
    return output;
  },
  /**
   * Lazy static initialization function. Called before
   * accessing any of the static map variables.
   * @private
   */
  init_() {
    if (!this.byteToCharMap_) {
      this.byteToCharMap_ = {};
      this.charToByteMap_ = {};
      this.byteToCharMapWebSafe_ = {};
      this.charToByteMapWebSafe_ = {};
      for (let i = 0; i < this.ENCODED_VALS.length; i++) {
        this.byteToCharMap_[i] = this.ENCODED_VALS.charAt(i);
        this.charToByteMap_[this.byteToCharMap_[i]] = i;
        this.byteToCharMapWebSafe_[i] = this.ENCODED_VALS_WEBSAFE.charAt(i);
        this.charToByteMapWebSafe_[this.byteToCharMapWebSafe_[i]] = i;
        if (i >= this.ENCODED_VALS_BASE.length) {
          this.charToByteMap_[this.ENCODED_VALS_WEBSAFE.charAt(i)] = i;
          this.charToByteMapWebSafe_[this.ENCODED_VALS.charAt(i)] = i;
        }
      }
    }
  }
};
var DecodeBase64StringError = class extends Error {
  constructor() {
    super(...arguments);
    this.name = "DecodeBase64StringError";
  }
};
var base64Encode = function(str) {
  const utf8Bytes = stringToByteArray$1(str);
  return base64.encodeByteArray(utf8Bytes, true);
};
var base64urlEncodeWithoutPadding = function(str) {
  return base64Encode(str).replace(/\./g, "");
};
var base64Decode = function(str) {
  try {
    return base64.decodeString(str, true);
  } catch (e) {
    console.error("base64Decode failed: ", e);
  }
  return null;
};
function getGlobal() {
  if (typeof self !== "undefined") {
    return self;
  }
  if (typeof window !== "undefined") {
    return window;
  }
  if (typeof global !== "undefined") {
    return global;
  }
  throw new Error("Unable to locate global object.");
}
var getDefaultsFromGlobal = () => getGlobal().__FIREBASE_DEFAULTS__;
var getDefaultsFromEnvVariable = () => {
  if (typeof process === "undefined" || typeof process.env === "undefined") {
    return;
  }
  const defaultsJsonString = process.env.__FIREBASE_DEFAULTS__;
  if (defaultsJsonString) {
    return JSON.parse(defaultsJsonString);
  }
};
var getDefaultsFromCookie = () => {
  if (typeof document === "undefined") {
    return;
  }
  let match;
  try {
    match = document.cookie.match(/__FIREBASE_DEFAULTS__=([^;]+)/);
  } catch (e) {
    return;
  }
  const decoded = match && base64Decode(match[1]);
  return decoded && JSON.parse(decoded);
};
var getDefaults = () => {
  try {
    return getDefaultsFromPostinstall() || getDefaultsFromGlobal() || getDefaultsFromEnvVariable() || getDefaultsFromCookie();
  } catch (e) {
    console.info(`Unable to get __FIREBASE_DEFAULTS__ due to: ${e}`);
    return;
  }
};
var getDefaultEmulatorHost = (productName) => getDefaults()?.emulatorHosts?.[productName];
var getDefaultEmulatorHostnameAndPort = (productName) => {
  const host = getDefaultEmulatorHost(productName);
  if (!host) {
    return void 0;
  }
  const separatorIndex = host.lastIndexOf(":");
  if (separatorIndex <= 0 || separatorIndex + 1 === host.length) {
    throw new Error(`Invalid host ${host} with no separate hostname and port!`);
  }
  const port = parseInt(host.substring(separatorIndex + 1), 10);
  if (host[0] === "[") {
    return [host.substring(1, separatorIndex - 1), port];
  } else {
    return [host.substring(0, separatorIndex), port];
  }
};
var getDefaultAppConfig = () => getDefaults()?.config;
var getExperimentalSetting = (name4) => getDefaults()?.[`_${name4}`];
var Deferred = class {
  constructor() {
    this.reject = () => {
    };
    this.resolve = () => {
    };
    this.promise = new Promise((resolve, reject) => {
      this.resolve = resolve;
      this.reject = reject;
    });
  }
  /**
   * Our API internals are not promisified and cannot because our callback APIs have subtle expectations around
   * invoking promises inline, which Promises are forbidden to do. This method accepts an optional node-style callback
   * and returns a node-style callback which will resolve or reject the Deferred's promise.
   */
  wrapCallback(callback) {
    return (error, value) => {
      if (error) {
        this.reject(error);
      } else {
        this.resolve(value);
      }
      if (typeof callback === "function") {
        this.promise.catch(() => {
        });
        if (callback.length === 1) {
          callback(error);
        } else {
          callback(error, value);
        }
      }
    };
  }
};
function isCloudWorkstation(url) {
  try {
    const host = url.startsWith("http://") || url.startsWith("https://") ? new URL(url).hostname : url;
    return host.endsWith(".cloudworkstations.dev");
  } catch {
    return false;
  }
}
async function pingServer(endpoint) {
  const result = await fetch(endpoint, {
    credentials: "include"
  });
  return result.ok;
}
function createMockUserToken(token, projectId) {
  if (token.uid) {
    throw new Error('The "uid" field is no longer supported by mockUserToken. Please use "sub" instead for Firebase Auth User ID.');
  }
  const header = {
    alg: "none",
    type: "JWT"
  };
  const project = projectId || "demo-project";
  const iat = token.iat || 0;
  const sub = token.sub || token.user_id;
  if (!sub) {
    throw new Error("mockUserToken must contain 'sub' or 'user_id' field!");
  }
  const payload = {
    // Set all required fields to decent defaults
    iss: `https://securetoken.google.com/${project}`,
    aud: project,
    iat,
    exp: iat + 3600,
    auth_time: iat,
    sub,
    user_id: sub,
    firebase: {
      sign_in_provider: "custom",
      identities: {}
    },
    // Override with user options
    ...token
  };
  const signature = "";
  return [
    base64urlEncodeWithoutPadding(JSON.stringify(header)),
    base64urlEncodeWithoutPadding(JSON.stringify(payload)),
    signature
  ].join(".");
}
var emulatorStatus = {};
function getEmulatorSummary() {
  const summary = {
    prod: [],
    emulator: []
  };
  for (const key of Object.keys(emulatorStatus)) {
    if (emulatorStatus[key]) {
      summary.emulator.push(key);
    } else {
      summary.prod.push(key);
    }
  }
  return summary;
}
function getOrCreateEl(id) {
  let parentDiv = document.getElementById(id);
  let created = false;
  if (!parentDiv) {
    parentDiv = document.createElement("div");
    parentDiv.setAttribute("id", id);
    created = true;
  }
  return { created, element: parentDiv };
}
var previouslyDismissed = false;
function updateEmulatorBanner(name4, isRunningEmulator) {
  if (typeof window === "undefined" || typeof document === "undefined" || !isCloudWorkstation(window.location.host) || emulatorStatus[name4] === isRunningEmulator || emulatorStatus[name4] || // If already set to use emulator, can't go back to prod.
  previouslyDismissed) {
    return;
  }
  emulatorStatus[name4] = isRunningEmulator;
  function prefixedId(id) {
    return `__firebase__banner__${id}`;
  }
  const bannerId = "__firebase__banner";
  const summary = getEmulatorSummary();
  const showError = summary.prod.length > 0;
  function tearDown() {
    const element = document.getElementById(bannerId);
    if (element) {
      element.remove();
    }
  }
  function setupBannerStyles(bannerEl) {
    bannerEl.style.display = "flex";
    bannerEl.style.background = "#7faaf0";
    bannerEl.style.position = "fixed";
    bannerEl.style.bottom = "5px";
    bannerEl.style.left = "5px";
    bannerEl.style.padding = ".5em";
    bannerEl.style.borderRadius = "5px";
    bannerEl.style.alignItems = "center";
  }
  function setupIconStyles(prependIcon, iconId) {
    prependIcon.setAttribute("width", "24");
    prependIcon.setAttribute("id", iconId);
    prependIcon.setAttribute("height", "24");
    prependIcon.setAttribute("viewBox", "0 0 24 24");
    prependIcon.setAttribute("fill", "none");
    prependIcon.style.marginLeft = "-6px";
  }
  function setupCloseBtn() {
    const closeBtn = document.createElement("span");
    closeBtn.style.cursor = "pointer";
    closeBtn.style.marginLeft = "16px";
    closeBtn.style.fontSize = "24px";
    closeBtn.innerHTML = " &times;";
    closeBtn.onclick = () => {
      previouslyDismissed = true;
      tearDown();
    };
    return closeBtn;
  }
  function setupLinkStyles(learnMoreLink, learnMoreId) {
    learnMoreLink.setAttribute("id", learnMoreId);
    learnMoreLink.innerText = "Learn more";
    learnMoreLink.href = "https://firebase.google.com/docs/studio/preview-apps#preview-backend";
    learnMoreLink.setAttribute("target", "__blank");
    learnMoreLink.style.paddingLeft = "5px";
    learnMoreLink.style.textDecoration = "underline";
  }
  function setupDom() {
    const banner = getOrCreateEl(bannerId);
    const firebaseTextId = prefixedId("text");
    const firebaseText = document.getElementById(firebaseTextId) || document.createElement("span");
    const learnMoreId = prefixedId("learnmore");
    const learnMoreLink = document.getElementById(learnMoreId) || document.createElement("a");
    const prependIconId = prefixedId("preprendIcon");
    const prependIcon = document.getElementById(prependIconId) || document.createElementNS("http://www.w3.org/2000/svg", "svg");
    if (banner.created) {
      const bannerEl = banner.element;
      setupBannerStyles(bannerEl);
      setupLinkStyles(learnMoreLink, learnMoreId);
      const closeBtn = setupCloseBtn();
      setupIconStyles(prependIcon, prependIconId);
      bannerEl.append(prependIcon, firebaseText, learnMoreLink, closeBtn);
      document.body.appendChild(bannerEl);
    }
    if (showError) {
      firebaseText.innerText = `Preview backend disconnected.`;
      prependIcon.innerHTML = `<g clip-path="url(#clip0_6013_33858)">
<path d="M4.8 17.6L12 5.6L19.2 17.6H4.8ZM6.91667 16.4H17.0833L12 7.93333L6.91667 16.4ZM12 15.6C12.1667 15.6 12.3056 15.5444 12.4167 15.4333C12.5389 15.3111 12.6 15.1667 12.6 15C12.6 14.8333 12.5389 14.6944 12.4167 14.5833C12.3056 14.4611 12.1667 14.4 12 14.4C11.8333 14.4 11.6889 14.4611 11.5667 14.5833C11.4556 14.6944 11.4 14.8333 11.4 15C11.4 15.1667 11.4556 15.3111 11.5667 15.4333C11.6889 15.5444 11.8333 15.6 12 15.6ZM11.4 13.6H12.6V10.4H11.4V13.6Z" fill="#212121"/>
</g>
<defs>
<clipPath id="clip0_6013_33858">
<rect width="24" height="24" fill="white"/>
</clipPath>
</defs>`;
    } else {
      prependIcon.innerHTML = `<g clip-path="url(#clip0_6083_34804)">
<path d="M11.4 15.2H12.6V11.2H11.4V15.2ZM12 10C12.1667 10 12.3056 9.94444 12.4167 9.83333C12.5389 9.71111 12.6 9.56667 12.6 9.4C12.6 9.23333 12.5389 9.09444 12.4167 8.98333C12.3056 8.86111 12.1667 8.8 12 8.8C11.8333 8.8 11.6889 8.86111 11.5667 8.98333C11.4556 9.09444 11.4 9.23333 11.4 9.4C11.4 9.56667 11.4556 9.71111 11.5667 9.83333C11.6889 9.94444 11.8333 10 12 10ZM12 18.4C11.1222 18.4 10.2944 18.2333 9.51667 17.9C8.73889 17.5667 8.05556 17.1111 7.46667 16.5333C6.88889 15.9444 6.43333 15.2611 6.1 14.4833C5.76667 13.7056 5.6 12.8778 5.6 12C5.6 11.1111 5.76667 10.2833 6.1 9.51667C6.43333 8.73889 6.88889 8.06111 7.46667 7.48333C8.05556 6.89444 8.73889 6.43333 9.51667 6.1C10.2944 5.76667 11.1222 5.6 12 5.6C12.8889 5.6 13.7167 5.76667 14.4833 6.1C15.2611 6.43333 15.9389 6.89444 16.5167 7.48333C17.1056 8.06111 17.5667 8.73889 17.9 9.51667C18.2333 10.2833 18.4 11.1111 18.4 12C18.4 12.8778 18.2333 13.7056 17.9 14.4833C17.5667 15.2611 17.1056 15.9444 16.5167 16.5333C15.9389 17.1111 15.2611 17.5667 14.4833 17.9C13.7167 18.2333 12.8889 18.4 12 18.4ZM12 17.2C13.4444 17.2 14.6722 16.6944 15.6833 15.6833C16.6944 14.6722 17.2 13.4444 17.2 12C17.2 10.5556 16.6944 9.32778 15.6833 8.31667C14.6722 7.30555 13.4444 6.8 12 6.8C10.5556 6.8 9.32778 7.30555 8.31667 8.31667C7.30556 9.32778 6.8 10.5556 6.8 12C6.8 13.4444 7.30556 14.6722 8.31667 15.6833C9.32778 16.6944 10.5556 17.2 12 17.2Z" fill="#212121"/>
</g>
<defs>
<clipPath id="clip0_6083_34804">
<rect width="24" height="24" fill="white"/>
</clipPath>
</defs>`;
      firebaseText.innerText = "Preview backend running in this workspace.";
    }
    firebaseText.setAttribute("id", firebaseTextId);
  }
  if (document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", setupDom);
  } else {
    setupDom();
  }
}
function getUA() {
  if (typeof navigator !== "undefined" && typeof navigator["userAgent"] === "string") {
    return navigator["userAgent"];
  } else {
    return "";
  }
}
function isMobileCordova() {
  return typeof window !== "undefined" && // @ts-ignore Setting up an broadly applicable index signature for Window
  // just to deal with this case would probably be a bad idea.
  !!(window["cordova"] || window["phonegap"] || window["PhoneGap"]) && /ios|iphone|ipod|ipad|android|blackberry|iemobile/i.test(getUA());
}
function isCloudflareWorker() {
  return typeof navigator !== "undefined" && navigator.userAgent === "Cloudflare-Workers";
}
function isBrowserExtension() {
  const runtime = typeof chrome === "object" ? chrome.runtime : typeof browser === "object" ? browser.runtime : void 0;
  return typeof runtime === "object" && runtime.id !== void 0;
}
function isReactNative() {
  return typeof navigator === "object" && navigator["product"] === "ReactNative";
}
function isIE() {
  const ua = getUA();
  return ua.indexOf("MSIE ") >= 0 || ua.indexOf("Trident/") >= 0;
}
function isIndexedDBAvailable() {
  try {
    return typeof indexedDB === "object";
  } catch (e) {
    return false;
  }
}
function validateIndexedDBOpenable() {
  return new Promise((resolve, reject) => {
    try {
      let preExist = true;
      const DB_CHECK_NAME = "validate-browser-context-for-indexeddb-analytics-module";
      const request = self.indexedDB.open(DB_CHECK_NAME);
      request.onsuccess = () => {
        request.result.close();
        if (!preExist) {
          self.indexedDB.deleteDatabase(DB_CHECK_NAME);
        }
        resolve(true);
      };
      request.onupgradeneeded = () => {
        preExist = false;
      };
      request.onerror = () => {
        reject(request.error?.message || "");
      };
    } catch (error) {
      reject(error);
    }
  });
}
var ERROR_NAME = "FirebaseError";
var FirebaseError = class _FirebaseError extends Error {
  constructor(code, message, customData) {
    super(message);
    this.code = code;
    this.customData = customData;
    this.name = ERROR_NAME;
    Object.setPrototypeOf(this, _FirebaseError.prototype);
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, ErrorFactory.prototype.create);
    }
  }
};
var ErrorFactory = class {
  constructor(service, serviceName, errors) {
    this.service = service;
    this.serviceName = serviceName;
    this.errors = errors;
  }
  create(code, ...data) {
    const customData = data[0] || {};
    const fullCode = `${this.service}/${code}`;
    const template = this.errors[code];
    const message = template ? replaceTemplate(template, customData) : "Error";
    const fullMessage = `${this.serviceName}: ${message} (${fullCode}).`;
    const error = new FirebaseError(fullCode, fullMessage, customData);
    return error;
  }
};
function replaceTemplate(template, data) {
  return template.replace(PATTERN, (_, key) => {
    const value = data[key];
    return value != null ? String(value) : `<${key}?>`;
  });
}
var PATTERN = /\{\$([^}]+)}/g;
function isEmpty(obj) {
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      return false;
    }
  }
  return true;
}
function deepEqual(a, b2) {
  if (a === b2) {
    return true;
  }
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b2);
  for (const k2 of aKeys) {
    if (!bKeys.includes(k2)) {
      return false;
    }
    const aProp = a[k2];
    const bProp = b2[k2];
    if (isObject(aProp) && isObject(bProp)) {
      if (!deepEqual(aProp, bProp)) {
        return false;
      }
    } else if (aProp !== bProp) {
      return false;
    }
  }
  for (const k2 of bKeys) {
    if (!aKeys.includes(k2)) {
      return false;
    }
  }
  return true;
}
function isObject(thing) {
  return thing !== null && typeof thing === "object";
}
function querystring(querystringParams) {
  const params = [];
  for (const [key, value] of Object.entries(querystringParams)) {
    if (Array.isArray(value)) {
      value.forEach((arrayVal) => {
        params.push(encodeURIComponent(key) + "=" + encodeURIComponent(arrayVal));
      });
    } else {
      params.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
    }
  }
  return params.length ? "&" + params.join("&") : "";
}
function querystringDecode(querystring2) {
  const obj = {};
  const tokens = querystring2.replace(/^\?/, "").split("&");
  tokens.forEach((token) => {
    if (token) {
      const [key, value] = token.split("=");
      obj[decodeURIComponent(key)] = decodeURIComponent(value);
    }
  });
  return obj;
}
function extractQuerystring(url) {
  const queryStart = url.indexOf("?");
  if (!queryStart) {
    return "";
  }
  const fragmentStart = url.indexOf("#", queryStart);
  return url.substring(queryStart, fragmentStart > 0 ? fragmentStart : void 0);
}
function createSubscribe(executor, onNoObservers) {
  const proxy = new ObserverProxy(executor, onNoObservers);
  return proxy.subscribe.bind(proxy);
}
var ObserverProxy = class {
  /**
   * @param executor Function which can make calls to a single Observer
   *     as a proxy.
   * @param onNoObservers Callback when count of Observers goes to zero.
   */
  constructor(executor, onNoObservers) {
    this.observers = [];
    this.unsubscribes = [];
    this.observerCount = 0;
    this.task = Promise.resolve();
    this.finalized = false;
    this.onNoObservers = onNoObservers;
    this.task.then(() => {
      executor(this);
    }).catch((e) => {
      this.error(e);
    });
  }
  next(value) {
    this.forEachObserver((observer) => {
      observer.next(value);
    });
  }
  error(error) {
    this.forEachObserver((observer) => {
      observer.error(error);
    });
    this.close(error);
  }
  complete() {
    this.forEachObserver((observer) => {
      observer.complete();
    });
    this.close();
  }
  /**
   * Subscribe function that can be used to add an Observer to the fan-out list.
   *
   * - We require that no event is sent to a subscriber synchronously to their
   *   call to subscribe().
   */
  subscribe(nextOrObserver, error, complete) {
    let observer;
    if (nextOrObserver === void 0 && error === void 0 && complete === void 0) {
      throw new Error("Missing Observer.");
    }
    if (implementsAnyMethods(nextOrObserver, [
      "next",
      "error",
      "complete"
    ])) {
      observer = nextOrObserver;
    } else {
      observer = {
        next: nextOrObserver,
        error,
        complete
      };
    }
    if (observer.next === void 0) {
      observer.next = noop;
    }
    if (observer.error === void 0) {
      observer.error = noop;
    }
    if (observer.complete === void 0) {
      observer.complete = noop;
    }
    const unsub = this.unsubscribeOne.bind(this, this.observers.length);
    if (this.finalized) {
      this.task.then(() => {
        try {
          if (this.finalError) {
            observer.error(this.finalError);
          } else {
            observer.complete();
          }
        } catch (e) {
        }
        return;
      });
    }
    this.observers.push(observer);
    return unsub;
  }
  // Unsubscribe is synchronous - we guarantee that no events are sent to
  // any unsubscribed Observer.
  unsubscribeOne(i) {
    if (this.observers === void 0 || this.observers[i] === void 0) {
      return;
    }
    delete this.observers[i];
    this.observerCount -= 1;
    if (this.observerCount === 0 && this.onNoObservers !== void 0) {
      this.onNoObservers(this);
    }
  }
  forEachObserver(fn) {
    if (this.finalized) {
      return;
    }
    for (let i = 0; i < this.observers.length; i++) {
      this.sendOne(i, fn);
    }
  }
  // Call the Observer via one of it's callback function. We are careful to
  // confirm that the observe has not been unsubscribed since this asynchronous
  // function had been queued.
  sendOne(i, fn) {
    this.task.then(() => {
      if (this.observers !== void 0 && this.observers[i] !== void 0) {
        try {
          fn(this.observers[i]);
        } catch (e) {
          if (typeof console !== "undefined" && console.error) {
            console.error(e);
          }
        }
      }
    });
  }
  close(err) {
    if (this.finalized) {
      return;
    }
    this.finalized = true;
    if (err !== void 0) {
      this.finalError = err;
    }
    this.task.then(() => {
      this.observers = void 0;
      this.onNoObservers = void 0;
    });
  }
};
function implementsAnyMethods(obj, methods) {
  if (typeof obj !== "object" || obj === null) {
    return false;
  }
  for (const method of methods) {
    if (method in obj && typeof obj[method] === "function") {
      return true;
    }
  }
  return false;
}
function noop() {
}
var MAX_VALUE_MILLIS = 4 * 60 * 60 * 1e3;
function getModularInstance(service) {
  if (service && service._delegate) {
    return service._delegate;
  } else {
    return service;
  }
}

// node_modules/@firebase/component/dist/esm/index.esm.js
var Component = class {
  /**
   *
   * @param name The public service name, e.g. app, auth, firestore, database
   * @param instanceFactory Service factory responsible for creating the public interface
   * @param type whether the service provided by the component is public or private
   */
  constructor(name4, instanceFactory, type) {
    this.name = name4;
    this.instanceFactory = instanceFactory;
    this.type = type;
    this.multipleInstances = false;
    this.serviceProps = {};
    this.instantiationMode = "LAZY";
    this.onInstanceCreated = null;
  }
  setInstantiationMode(mode) {
    this.instantiationMode = mode;
    return this;
  }
  setMultipleInstances(multipleInstances) {
    this.multipleInstances = multipleInstances;
    return this;
  }
  setServiceProps(props) {
    this.serviceProps = props;
    return this;
  }
  setInstanceCreatedCallback(callback) {
    this.onInstanceCreated = callback;
    return this;
  }
};
var DEFAULT_ENTRY_NAME = "[DEFAULT]";
var Provider = class {
  constructor(name4, container) {
    this.name = name4;
    this.container = container;
    this.component = null;
    this.instances = /* @__PURE__ */ new Map();
    this.instancesDeferred = /* @__PURE__ */ new Map();
    this.instancesOptions = /* @__PURE__ */ new Map();
    this.onInitCallbacks = /* @__PURE__ */ new Map();
  }
  /**
   * @param identifier A provider can provide multiple instances of a service
   * if this.component.multipleInstances is true.
   */
  get(identifier) {
    const normalizedIdentifier = this.normalizeInstanceIdentifier(identifier);
    if (!this.instancesDeferred.has(normalizedIdentifier)) {
      const deferred = new Deferred();
      this.instancesDeferred.set(normalizedIdentifier, deferred);
      if (this.isInitialized(normalizedIdentifier) || this.shouldAutoInitialize()) {
        try {
          const instance = this.getOrInitializeService({
            instanceIdentifier: normalizedIdentifier
          });
          if (instance) {
            deferred.resolve(instance);
          }
        } catch (e) {
        }
      }
    }
    return this.instancesDeferred.get(normalizedIdentifier).promise;
  }
  getImmediate(options) {
    const normalizedIdentifier = this.normalizeInstanceIdentifier(options?.identifier);
    const optional = options?.optional ?? false;
    if (this.isInitialized(normalizedIdentifier) || this.shouldAutoInitialize()) {
      try {
        return this.getOrInitializeService({
          instanceIdentifier: normalizedIdentifier
        });
      } catch (e) {
        if (optional) {
          return null;
        } else {
          throw e;
        }
      }
    } else {
      if (optional) {
        return null;
      } else {
        throw Error(`Service ${this.name} is not available`);
      }
    }
  }
  getComponent() {
    return this.component;
  }
  setComponent(component) {
    if (component.name !== this.name) {
      throw Error(`Mismatching Component ${component.name} for Provider ${this.name}.`);
    }
    if (this.component) {
      throw Error(`Component for ${this.name} has already been provided`);
    }
    this.component = component;
    if (!this.shouldAutoInitialize()) {
      return;
    }
    if (isComponentEager(component)) {
      try {
        this.getOrInitializeService({ instanceIdentifier: DEFAULT_ENTRY_NAME });
      } catch (e) {
      }
    }
    for (const [instanceIdentifier, instanceDeferred] of this.instancesDeferred.entries()) {
      const normalizedIdentifier = this.normalizeInstanceIdentifier(instanceIdentifier);
      try {
        const instance = this.getOrInitializeService({
          instanceIdentifier: normalizedIdentifier
        });
        instanceDeferred.resolve(instance);
      } catch (e) {
      }
    }
  }
  clearInstance(identifier = DEFAULT_ENTRY_NAME) {
    this.instancesDeferred.delete(identifier);
    this.instancesOptions.delete(identifier);
    this.instances.delete(identifier);
  }
  // app.delete() will call this method on every provider to delete the services
  // TODO: should we mark the provider as deleted?
  async delete() {
    const services = Array.from(this.instances.values());
    await Promise.all([
      ...services.filter((service) => "INTERNAL" in service).map((service) => service.INTERNAL.delete()),
      ...services.filter((service) => "_delete" in service).map((service) => service._delete())
    ]);
  }
  isComponentSet() {
    return this.component != null;
  }
  isInitialized(identifier = DEFAULT_ENTRY_NAME) {
    return this.instances.has(identifier);
  }
  getOptions(identifier = DEFAULT_ENTRY_NAME) {
    return this.instancesOptions.get(identifier) || {};
  }
  initialize(opts = {}) {
    const { options = {} } = opts;
    const normalizedIdentifier = this.normalizeInstanceIdentifier(opts.instanceIdentifier);
    if (this.isInitialized(normalizedIdentifier)) {
      throw Error(`${this.name}(${normalizedIdentifier}) has already been initialized`);
    }
    if (!this.isComponentSet()) {
      throw Error(`Component ${this.name} has not been registered yet`);
    }
    const instance = this.getOrInitializeService({
      instanceIdentifier: normalizedIdentifier,
      options
    });
    for (const [instanceIdentifier, instanceDeferred] of this.instancesDeferred.entries()) {
      const normalizedDeferredIdentifier = this.normalizeInstanceIdentifier(instanceIdentifier);
      if (normalizedIdentifier === normalizedDeferredIdentifier) {
        instanceDeferred.resolve(instance);
      }
    }
    return instance;
  }
  /**
   *
   * @param callback - a function that will be invoked  after the provider has been initialized by calling provider.initialize().
   * The function is invoked SYNCHRONOUSLY, so it should not execute any longrunning tasks in order to not block the program.
   *
   * @param identifier An optional instance identifier
   * @returns a function to unregister the callback
   */
  onInit(callback, identifier) {
    const normalizedIdentifier = this.normalizeInstanceIdentifier(identifier);
    const existingCallbacks = this.onInitCallbacks.get(normalizedIdentifier) ?? /* @__PURE__ */ new Set();
    existingCallbacks.add(callback);
    this.onInitCallbacks.set(normalizedIdentifier, existingCallbacks);
    const existingInstance = this.instances.get(normalizedIdentifier);
    if (existingInstance) {
      callback(existingInstance, normalizedIdentifier);
    }
    return () => {
      existingCallbacks.delete(callback);
    };
  }
  /**
   * Invoke onInit callbacks synchronously
   * @param instance the service instance`
   */
  invokeOnInitCallbacks(instance, identifier) {
    const callbacks = this.onInitCallbacks.get(identifier);
    if (!callbacks) {
      return;
    }
    for (const callback of callbacks) {
      try {
        callback(instance, identifier);
      } catch {
      }
    }
  }
  getOrInitializeService({ instanceIdentifier, options = {} }) {
    let instance = this.instances.get(instanceIdentifier);
    if (!instance && this.component) {
      instance = this.component.instanceFactory(this.container, {
        instanceIdentifier: normalizeIdentifierForFactory(instanceIdentifier),
        options
      });
      this.instances.set(instanceIdentifier, instance);
      this.instancesOptions.set(instanceIdentifier, options);
      this.invokeOnInitCallbacks(instance, instanceIdentifier);
      if (this.component.onInstanceCreated) {
        try {
          this.component.onInstanceCreated(this.container, instanceIdentifier, instance);
        } catch {
        }
      }
    }
    return instance || null;
  }
  normalizeInstanceIdentifier(identifier = DEFAULT_ENTRY_NAME) {
    if (this.component) {
      return this.component.multipleInstances ? identifier : DEFAULT_ENTRY_NAME;
    } else {
      return identifier;
    }
  }
  shouldAutoInitialize() {
    return !!this.component && this.component.instantiationMode !== "EXPLICIT";
  }
};
function normalizeIdentifierForFactory(identifier) {
  return identifier === DEFAULT_ENTRY_NAME ? void 0 : identifier;
}
function isComponentEager(component) {
  return component.instantiationMode === "EAGER";
}
var ComponentContainer = class {
  constructor(name4) {
    this.name = name4;
    this.providers = /* @__PURE__ */ new Map();
  }
  /**
   *
   * @param component Component being added
   * @param overwrite When a component with the same name has already been registered,
   * if overwrite is true: overwrite the existing component with the new component and create a new
   * provider with the new component. It can be useful in tests where you want to use different mocks
   * for different tests.
   * if overwrite is false: throw an exception
   */
  addComponent(component) {
    const provider = this.getProvider(component.name);
    if (provider.isComponentSet()) {
      throw new Error(`Component ${component.name} has already been registered with ${this.name}`);
    }
    provider.setComponent(component);
  }
  addOrOverwriteComponent(component) {
    const provider = this.getProvider(component.name);
    if (provider.isComponentSet()) {
      this.providers.delete(component.name);
    }
    this.addComponent(component);
  }
  /**
   * getProvider provides a type safe interface where it can only be called with a field name
   * present in NameServiceMapping interface.
   *
   * Firebase SDKs providing services should extend NameServiceMapping interface to register
   * themselves.
   */
  getProvider(name4) {
    if (this.providers.has(name4)) {
      return this.providers.get(name4);
    }
    const provider = new Provider(name4, this);
    this.providers.set(name4, provider);
    return provider;
  }
  getProviders() {
    return Array.from(this.providers.values());
  }
};

// node_modules/@firebase/logger/dist/esm/index.esm.js
var instances = [];
var LogLevel;
(function(LogLevel2) {
  LogLevel2[LogLevel2["DEBUG"] = 0] = "DEBUG";
  LogLevel2[LogLevel2["VERBOSE"] = 1] = "VERBOSE";
  LogLevel2[LogLevel2["INFO"] = 2] = "INFO";
  LogLevel2[LogLevel2["WARN"] = 3] = "WARN";
  LogLevel2[LogLevel2["ERROR"] = 4] = "ERROR";
  LogLevel2[LogLevel2["SILENT"] = 5] = "SILENT";
})(LogLevel || (LogLevel = {}));
var levelStringToEnum = {
  "debug": LogLevel.DEBUG,
  "verbose": LogLevel.VERBOSE,
  "info": LogLevel.INFO,
  "warn": LogLevel.WARN,
  "error": LogLevel.ERROR,
  "silent": LogLevel.SILENT
};
var defaultLogLevel = LogLevel.INFO;
var ConsoleMethod = {
  [LogLevel.DEBUG]: "log",
  [LogLevel.VERBOSE]: "log",
  [LogLevel.INFO]: "info",
  [LogLevel.WARN]: "warn",
  [LogLevel.ERROR]: "error"
};
var defaultLogHandler = (instance, logType, ...args) => {
  if (logType < instance.logLevel) {
    return;
  }
  const now = (/* @__PURE__ */ new Date()).toISOString();
  const method = ConsoleMethod[logType];
  if (method) {
    console[method](`[${now}]  ${instance.name}:`, ...args);
  } else {
    throw new Error(`Attempted to log a message with an invalid logType (value: ${logType})`);
  }
};
var Logger = class {
  /**
   * Gives you an instance of a Logger to capture messages according to
   * Firebase's logging scheme.
   *
   * @param name The name that the logs will be associated with
   */
  constructor(name4) {
    this.name = name4;
    this._logLevel = defaultLogLevel;
    this._logHandler = defaultLogHandler;
    this._userLogHandler = null;
    instances.push(this);
  }
  get logLevel() {
    return this._logLevel;
  }
  set logLevel(val) {
    if (!(val in LogLevel)) {
      throw new TypeError(`Invalid value "${val}" assigned to \`logLevel\``);
    }
    this._logLevel = val;
  }
  // Workaround for setter/getter having to be the same type.
  setLogLevel(val) {
    this._logLevel = typeof val === "string" ? levelStringToEnum[val] : val;
  }
  get logHandler() {
    return this._logHandler;
  }
  set logHandler(val) {
    if (typeof val !== "function") {
      throw new TypeError("Value assigned to `logHandler` must be a function");
    }
    this._logHandler = val;
  }
  get userLogHandler() {
    return this._userLogHandler;
  }
  set userLogHandler(val) {
    this._userLogHandler = val;
  }
  /**
   * The functions below are all based on the `console` interface
   */
  debug(...args) {
    this._userLogHandler && this._userLogHandler(this, LogLevel.DEBUG, ...args);
    this._logHandler(this, LogLevel.DEBUG, ...args);
  }
  log(...args) {
    this._userLogHandler && this._userLogHandler(this, LogLevel.VERBOSE, ...args);
    this._logHandler(this, LogLevel.VERBOSE, ...args);
  }
  info(...args) {
    this._userLogHandler && this._userLogHandler(this, LogLevel.INFO, ...args);
    this._logHandler(this, LogLevel.INFO, ...args);
  }
  warn(...args) {
    this._userLogHandler && this._userLogHandler(this, LogLevel.WARN, ...args);
    this._logHandler(this, LogLevel.WARN, ...args);
  }
  error(...args) {
    this._userLogHandler && this._userLogHandler(this, LogLevel.ERROR, ...args);
    this._logHandler(this, LogLevel.ERROR, ...args);
  }
};

// node_modules/idb/build/wrap-idb-value.js
var instanceOfAny = (object, constructors) => constructors.some((c) => object instanceof c);
var idbProxyableTypes;
var cursorAdvanceMethods;
function getIdbProxyableTypes() {
  return idbProxyableTypes || (idbProxyableTypes = [
    IDBDatabase,
    IDBObjectStore,
    IDBIndex,
    IDBCursor,
    IDBTransaction
  ]);
}
function getCursorAdvanceMethods() {
  return cursorAdvanceMethods || (cursorAdvanceMethods = [
    IDBCursor.prototype.advance,
    IDBCursor.prototype.continue,
    IDBCursor.prototype.continuePrimaryKey
  ]);
}
var cursorRequestMap = /* @__PURE__ */ new WeakMap();
var transactionDoneMap = /* @__PURE__ */ new WeakMap();
var transactionStoreNamesMap = /* @__PURE__ */ new WeakMap();
var transformCache = /* @__PURE__ */ new WeakMap();
var reverseTransformCache = /* @__PURE__ */ new WeakMap();
function promisifyRequest(request) {
  const promise = new Promise((resolve, reject) => {
    const unlisten = () => {
      request.removeEventListener("success", success);
      request.removeEventListener("error", error);
    };
    const success = () => {
      resolve(wrap(request.result));
      unlisten();
    };
    const error = () => {
      reject(request.error);
      unlisten();
    };
    request.addEventListener("success", success);
    request.addEventListener("error", error);
  });
  promise.then((value) => {
    if (value instanceof IDBCursor) {
      cursorRequestMap.set(value, request);
    }
  }).catch(() => {
  });
  reverseTransformCache.set(promise, request);
  return promise;
}
function cacheDonePromiseForTransaction(tx) {
  if (transactionDoneMap.has(tx))
    return;
  const done = new Promise((resolve, reject) => {
    const unlisten = () => {
      tx.removeEventListener("complete", complete);
      tx.removeEventListener("error", error);
      tx.removeEventListener("abort", error);
    };
    const complete = () => {
      resolve();
      unlisten();
    };
    const error = () => {
      reject(tx.error || new DOMException("AbortError", "AbortError"));
      unlisten();
    };
    tx.addEventListener("complete", complete);
    tx.addEventListener("error", error);
    tx.addEventListener("abort", error);
  });
  transactionDoneMap.set(tx, done);
}
var idbProxyTraps = {
  get(target, prop, receiver) {
    if (target instanceof IDBTransaction) {
      if (prop === "done")
        return transactionDoneMap.get(target);
      if (prop === "objectStoreNames") {
        return target.objectStoreNames || transactionStoreNamesMap.get(target);
      }
      if (prop === "store") {
        return receiver.objectStoreNames[1] ? void 0 : receiver.objectStore(receiver.objectStoreNames[0]);
      }
    }
    return wrap(target[prop]);
  },
  set(target, prop, value) {
    target[prop] = value;
    return true;
  },
  has(target, prop) {
    if (target instanceof IDBTransaction && (prop === "done" || prop === "store")) {
      return true;
    }
    return prop in target;
  }
};
function replaceTraps(callback) {
  idbProxyTraps = callback(idbProxyTraps);
}
function wrapFunction(func) {
  if (func === IDBDatabase.prototype.transaction && !("objectStoreNames" in IDBTransaction.prototype)) {
    return function(storeNames, ...args) {
      const tx = func.call(unwrap(this), storeNames, ...args);
      transactionStoreNamesMap.set(tx, storeNames.sort ? storeNames.sort() : [storeNames]);
      return wrap(tx);
    };
  }
  if (getCursorAdvanceMethods().includes(func)) {
    return function(...args) {
      func.apply(unwrap(this), args);
      return wrap(cursorRequestMap.get(this));
    };
  }
  return function(...args) {
    return wrap(func.apply(unwrap(this), args));
  };
}
function transformCachableValue(value) {
  if (typeof value === "function")
    return wrapFunction(value);
  if (value instanceof IDBTransaction)
    cacheDonePromiseForTransaction(value);
  if (instanceOfAny(value, getIdbProxyableTypes()))
    return new Proxy(value, idbProxyTraps);
  return value;
}
function wrap(value) {
  if (value instanceof IDBRequest)
    return promisifyRequest(value);
  if (transformCache.has(value))
    return transformCache.get(value);
  const newValue = transformCachableValue(value);
  if (newValue !== value) {
    transformCache.set(value, newValue);
    reverseTransformCache.set(newValue, value);
  }
  return newValue;
}
var unwrap = (value) => reverseTransformCache.get(value);

// node_modules/idb/build/index.js
function openDB(name4, version4, { blocked, upgrade, blocking, terminated } = {}) {
  const request = indexedDB.open(name4, version4);
  const openPromise = wrap(request);
  if (upgrade) {
    request.addEventListener("upgradeneeded", (event) => {
      upgrade(wrap(request.result), event.oldVersion, event.newVersion, wrap(request.transaction), event);
    });
  }
  if (blocked) {
    request.addEventListener("blocked", (event) => blocked(
      // Casting due to https://github.com/microsoft/TypeScript-DOM-lib-generator/pull/1405
      event.oldVersion,
      event.newVersion,
      event
    ));
  }
  openPromise.then((db) => {
    if (terminated)
      db.addEventListener("close", () => terminated());
    if (blocking) {
      db.addEventListener("versionchange", (event) => blocking(event.oldVersion, event.newVersion, event));
    }
  }).catch(() => {
  });
  return openPromise;
}
var readMethods = ["get", "getKey", "getAll", "getAllKeys", "count"];
var writeMethods = ["put", "add", "delete", "clear"];
var cachedMethods = /* @__PURE__ */ new Map();
function getMethod(target, prop) {
  if (!(target instanceof IDBDatabase && !(prop in target) && typeof prop === "string")) {
    return;
  }
  if (cachedMethods.get(prop))
    return cachedMethods.get(prop);
  const targetFuncName = prop.replace(/FromIndex$/, "");
  const useIndex = prop !== targetFuncName;
  const isWrite = writeMethods.includes(targetFuncName);
  if (
    // Bail if the target doesn't exist on the target. Eg, getAll isn't in Edge.
    !(targetFuncName in (useIndex ? IDBIndex : IDBObjectStore).prototype) || !(isWrite || readMethods.includes(targetFuncName))
  ) {
    return;
  }
  const method = async function(storeName, ...args) {
    const tx = this.transaction(storeName, isWrite ? "readwrite" : "readonly");
    let target2 = tx.store;
    if (useIndex)
      target2 = target2.index(args.shift());
    return (await Promise.all([
      target2[targetFuncName](...args),
      isWrite && tx.done
    ]))[0];
  };
  cachedMethods.set(prop, method);
  return method;
}
replaceTraps((oldTraps) => ({
  ...oldTraps,
  get: (target, prop, receiver) => getMethod(target, prop) || oldTraps.get(target, prop, receiver),
  has: (target, prop) => !!getMethod(target, prop) || oldTraps.has(target, prop)
}));

// node_modules/@firebase/app/dist/esm/index.esm.js
var PlatformLoggerServiceImpl = class {
  constructor(container) {
    this.container = container;
  }
  // In initial implementation, this will be called by installations on
  // auth token refresh, and installations will send this string.
  getPlatformInfoString() {
    const providers = this.container.getProviders();
    return providers.map((provider) => {
      if (isVersionServiceProvider(provider)) {
        const service = provider.getImmediate();
        return `${service.library}/${service.version}`;
      } else {
        return null;
      }
    }).filter((logString) => logString).join(" ");
  }
};
function isVersionServiceProvider(provider) {
  const component = provider.getComponent();
  return component?.type === "VERSION";
}
var name$q = "@firebase/app";
var version$1 = "0.14.1";
var logger = new Logger("@firebase/app");
var name$p = "@firebase/app-compat";
var name$o = "@firebase/analytics-compat";
var name$n = "@firebase/analytics";
var name$m = "@firebase/app-check-compat";
var name$l = "@firebase/app-check";
var name$k = "@firebase/auth";
var name$j = "@firebase/auth-compat";
var name$i = "@firebase/database";
var name$h = "@firebase/data-connect";
var name$g = "@firebase/database-compat";
var name$f = "@firebase/functions";
var name$e = "@firebase/functions-compat";
var name$d = "@firebase/installations";
var name$c = "@firebase/installations-compat";
var name$b = "@firebase/messaging";
var name$a = "@firebase/messaging-compat";
var name$9 = "@firebase/performance";
var name$8 = "@firebase/performance-compat";
var name$7 = "@firebase/remote-config";
var name$6 = "@firebase/remote-config-compat";
var name$5 = "@firebase/storage";
var name$4 = "@firebase/storage-compat";
var name$3 = "@firebase/firestore";
var name$2 = "@firebase/ai";
var name$1 = "@firebase/firestore-compat";
var name = "firebase";
var version = "12.1.0";
var DEFAULT_ENTRY_NAME2 = "[DEFAULT]";
var PLATFORM_LOG_STRING = {
  [name$q]: "fire-core",
  [name$p]: "fire-core-compat",
  [name$n]: "fire-analytics",
  [name$o]: "fire-analytics-compat",
  [name$l]: "fire-app-check",
  [name$m]: "fire-app-check-compat",
  [name$k]: "fire-auth",
  [name$j]: "fire-auth-compat",
  [name$i]: "fire-rtdb",
  [name$h]: "fire-data-connect",
  [name$g]: "fire-rtdb-compat",
  [name$f]: "fire-fn",
  [name$e]: "fire-fn-compat",
  [name$d]: "fire-iid",
  [name$c]: "fire-iid-compat",
  [name$b]: "fire-fcm",
  [name$a]: "fire-fcm-compat",
  [name$9]: "fire-perf",
  [name$8]: "fire-perf-compat",
  [name$7]: "fire-rc",
  [name$6]: "fire-rc-compat",
  [name$5]: "fire-gcs",
  [name$4]: "fire-gcs-compat",
  [name$3]: "fire-fst",
  [name$1]: "fire-fst-compat",
  [name$2]: "fire-vertex",
  "fire-js": "fire-js",
  // Platform identifier for JS SDK.
  [name]: "fire-js-all"
};
var _apps = /* @__PURE__ */ new Map();
var _serverApps = /* @__PURE__ */ new Map();
var _components = /* @__PURE__ */ new Map();
function _addComponent(app, component) {
  try {
    app.container.addComponent(component);
  } catch (e) {
    logger.debug(`Component ${component.name} failed to register with FirebaseApp ${app.name}`, e);
  }
}
function _registerComponent(component) {
  const componentName = component.name;
  if (_components.has(componentName)) {
    logger.debug(`There were multiple attempts to register component ${componentName}.`);
    return false;
  }
  _components.set(componentName, component);
  for (const app of _apps.values()) {
    _addComponent(app, component);
  }
  for (const serverApp of _serverApps.values()) {
    _addComponent(serverApp, component);
  }
  return true;
}
function _getProvider(app, name4) {
  const heartbeatController = app.container.getProvider("heartbeat").getImmediate({ optional: true });
  if (heartbeatController) {
    void heartbeatController.triggerHeartbeat();
  }
  return app.container.getProvider(name4);
}
function _isFirebaseServerApp(obj) {
  if (obj === null || obj === void 0) {
    return false;
  }
  return obj.settings !== void 0;
}
var ERRORS = {
  [
    "no-app"
    /* AppError.NO_APP */
  ]: "No Firebase App '{$appName}' has been created - call initializeApp() first",
  [
    "bad-app-name"
    /* AppError.BAD_APP_NAME */
  ]: "Illegal App name: '{$appName}'",
  [
    "duplicate-app"
    /* AppError.DUPLICATE_APP */
  ]: "Firebase App named '{$appName}' already exists with different options or config",
  [
    "app-deleted"
    /* AppError.APP_DELETED */
  ]: "Firebase App named '{$appName}' already deleted",
  [
    "server-app-deleted"
    /* AppError.SERVER_APP_DELETED */
  ]: "Firebase Server App has been deleted",
  [
    "no-options"
    /* AppError.NO_OPTIONS */
  ]: "Need to provide options, when not being deployed to hosting via source.",
  [
    "invalid-app-argument"
    /* AppError.INVALID_APP_ARGUMENT */
  ]: "firebase.{$appName}() takes either no argument or a Firebase App instance.",
  [
    "invalid-log-argument"
    /* AppError.INVALID_LOG_ARGUMENT */
  ]: "First argument to `onLog` must be null or a function.",
  [
    "idb-open"
    /* AppError.IDB_OPEN */
  ]: "Error thrown when opening IndexedDB. Original error: {$originalErrorMessage}.",
  [
    "idb-get"
    /* AppError.IDB_GET */
  ]: "Error thrown when reading from IndexedDB. Original error: {$originalErrorMessage}.",
  [
    "idb-set"
    /* AppError.IDB_WRITE */
  ]: "Error thrown when writing to IndexedDB. Original error: {$originalErrorMessage}.",
  [
    "idb-delete"
    /* AppError.IDB_DELETE */
  ]: "Error thrown when deleting from IndexedDB. Original error: {$originalErrorMessage}.",
  [
    "finalization-registry-not-supported"
    /* AppError.FINALIZATION_REGISTRY_NOT_SUPPORTED */
  ]: "FirebaseServerApp deleteOnDeref field defined but the JS runtime does not support FinalizationRegistry.",
  [
    "invalid-server-app-environment"
    /* AppError.INVALID_SERVER_APP_ENVIRONMENT */
  ]: "FirebaseServerApp is not for use in browser environments."
};
var ERROR_FACTORY = new ErrorFactory("app", "Firebase", ERRORS);
var FirebaseAppImpl = class {
  constructor(options, config, container) {
    this._isDeleted = false;
    this._options = { ...options };
    this._config = { ...config };
    this._name = config.name;
    this._automaticDataCollectionEnabled = config.automaticDataCollectionEnabled;
    this._container = container;
    this.container.addComponent(new Component(
      "app",
      () => this,
      "PUBLIC"
      /* ComponentType.PUBLIC */
    ));
  }
  get automaticDataCollectionEnabled() {
    this.checkDestroyed();
    return this._automaticDataCollectionEnabled;
  }
  set automaticDataCollectionEnabled(val) {
    this.checkDestroyed();
    this._automaticDataCollectionEnabled = val;
  }
  get name() {
    this.checkDestroyed();
    return this._name;
  }
  get options() {
    this.checkDestroyed();
    return this._options;
  }
  get config() {
    this.checkDestroyed();
    return this._config;
  }
  get container() {
    return this._container;
  }
  get isDeleted() {
    return this._isDeleted;
  }
  set isDeleted(val) {
    this._isDeleted = val;
  }
  /**
   * This function will throw an Error if the App has already been deleted -
   * use before performing API actions on the App.
   */
  checkDestroyed() {
    if (this.isDeleted) {
      throw ERROR_FACTORY.create("app-deleted", { appName: this._name });
    }
  }
};
var SDK_VERSION = version;
function initializeApp(_options, rawConfig = {}) {
  let options = _options;
  if (typeof rawConfig !== "object") {
    const name5 = rawConfig;
    rawConfig = { name: name5 };
  }
  const config = {
    name: DEFAULT_ENTRY_NAME2,
    automaticDataCollectionEnabled: true,
    ...rawConfig
  };
  const name4 = config.name;
  if (typeof name4 !== "string" || !name4) {
    throw ERROR_FACTORY.create("bad-app-name", {
      appName: String(name4)
    });
  }
  options || (options = getDefaultAppConfig());
  if (!options) {
    throw ERROR_FACTORY.create(
      "no-options"
      /* AppError.NO_OPTIONS */
    );
  }
  const existingApp = _apps.get(name4);
  if (existingApp) {
    if (deepEqual(options, existingApp.options) && deepEqual(config, existingApp.config)) {
      return existingApp;
    } else {
      throw ERROR_FACTORY.create("duplicate-app", { appName: name4 });
    }
  }
  const container = new ComponentContainer(name4);
  for (const component of _components.values()) {
    container.addComponent(component);
  }
  const newApp = new FirebaseAppImpl(options, config, container);
  _apps.set(name4, newApp);
  return newApp;
}
function getApp(name4 = DEFAULT_ENTRY_NAME2) {
  const app = _apps.get(name4);
  if (!app && name4 === DEFAULT_ENTRY_NAME2 && getDefaultAppConfig()) {
    return initializeApp();
  }
  if (!app) {
    throw ERROR_FACTORY.create("no-app", { appName: name4 });
  }
  return app;
}
function registerVersion(libraryKeyOrName, version4, variant) {
  let library = PLATFORM_LOG_STRING[libraryKeyOrName] ?? libraryKeyOrName;
  if (variant) {
    library += `-${variant}`;
  }
  const libraryMismatch = library.match(/\s|\//);
  const versionMismatch = version4.match(/\s|\//);
  if (libraryMismatch || versionMismatch) {
    const warning = [
      `Unable to register library "${library}" with version "${version4}":`
    ];
    if (libraryMismatch) {
      warning.push(`library name "${library}" contains illegal characters (whitespace or "/")`);
    }
    if (libraryMismatch && versionMismatch) {
      warning.push("and");
    }
    if (versionMismatch) {
      warning.push(`version name "${version4}" contains illegal characters (whitespace or "/")`);
    }
    logger.warn(warning.join(" "));
    return;
  }
  _registerComponent(new Component(
    `${library}-version`,
    () => ({ library, version: version4 }),
    "VERSION"
    /* ComponentType.VERSION */
  ));
}
var DB_NAME = "firebase-heartbeat-database";
var DB_VERSION = 1;
var STORE_NAME = "firebase-heartbeat-store";
var dbPromise = null;
function getDbPromise() {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade: (db, oldVersion) => {
        switch (oldVersion) {
          case 0:
            try {
              db.createObjectStore(STORE_NAME);
            } catch (e) {
              console.warn(e);
            }
        }
      }
    }).catch((e) => {
      throw ERROR_FACTORY.create("idb-open", {
        originalErrorMessage: e.message
      });
    });
  }
  return dbPromise;
}
async function readHeartbeatsFromIndexedDB(app) {
  try {
    const db = await getDbPromise();
    const tx = db.transaction(STORE_NAME);
    const result = await tx.objectStore(STORE_NAME).get(computeKey(app));
    await tx.done;
    return result;
  } catch (e) {
    if (e instanceof FirebaseError) {
      logger.warn(e.message);
    } else {
      const idbGetError = ERROR_FACTORY.create("idb-get", {
        originalErrorMessage: e?.message
      });
      logger.warn(idbGetError.message);
    }
  }
}
async function writeHeartbeatsToIndexedDB(app, heartbeatObject) {
  try {
    const db = await getDbPromise();
    const tx = db.transaction(STORE_NAME, "readwrite");
    const objectStore = tx.objectStore(STORE_NAME);
    await objectStore.put(heartbeatObject, computeKey(app));
    await tx.done;
  } catch (e) {
    if (e instanceof FirebaseError) {
      logger.warn(e.message);
    } else {
      const idbGetError = ERROR_FACTORY.create("idb-set", {
        originalErrorMessage: e?.message
      });
      logger.warn(idbGetError.message);
    }
  }
}
function computeKey(app) {
  return `${app.name}!${app.options.appId}`;
}
var MAX_HEADER_BYTES = 1024;
var MAX_NUM_STORED_HEARTBEATS = 30;
var HeartbeatServiceImpl = class {
  constructor(container) {
    this.container = container;
    this._heartbeatsCache = null;
    const app = this.container.getProvider("app").getImmediate();
    this._storage = new HeartbeatStorageImpl(app);
    this._heartbeatsCachePromise = this._storage.read().then((result) => {
      this._heartbeatsCache = result;
      return result;
    });
  }
  /**
   * Called to report a heartbeat. The function will generate
   * a HeartbeatsByUserAgent object, update heartbeatsCache, and persist it
   * to IndexedDB.
   * Note that we only store one heartbeat per day. So if a heartbeat for today is
   * already logged, subsequent calls to this function in the same day will be ignored.
   */
  async triggerHeartbeat() {
    try {
      const platformLogger = this.container.getProvider("platform-logger").getImmediate();
      const agent = platformLogger.getPlatformInfoString();
      const date = getUTCDateString();
      if (this._heartbeatsCache?.heartbeats == null) {
        this._heartbeatsCache = await this._heartbeatsCachePromise;
        if (this._heartbeatsCache?.heartbeats == null) {
          return;
        }
      }
      if (this._heartbeatsCache.lastSentHeartbeatDate === date || this._heartbeatsCache.heartbeats.some((singleDateHeartbeat) => singleDateHeartbeat.date === date)) {
        return;
      } else {
        this._heartbeatsCache.heartbeats.push({ date, agent });
        if (this._heartbeatsCache.heartbeats.length > MAX_NUM_STORED_HEARTBEATS) {
          const earliestHeartbeatIdx = getEarliestHeartbeatIdx(this._heartbeatsCache.heartbeats);
          this._heartbeatsCache.heartbeats.splice(earliestHeartbeatIdx, 1);
        }
      }
      return this._storage.overwrite(this._heartbeatsCache);
    } catch (e) {
      logger.warn(e);
    }
  }
  /**
   * Returns a base64 encoded string which can be attached to the heartbeat-specific header directly.
   * It also clears all heartbeats from memory as well as in IndexedDB.
   *
   * NOTE: Consuming product SDKs should not send the header if this method
   * returns an empty string.
   */
  async getHeartbeatsHeader() {
    try {
      if (this._heartbeatsCache === null) {
        await this._heartbeatsCachePromise;
      }
      if (this._heartbeatsCache?.heartbeats == null || this._heartbeatsCache.heartbeats.length === 0) {
        return "";
      }
      const date = getUTCDateString();
      const { heartbeatsToSend, unsentEntries } = extractHeartbeatsForHeader(this._heartbeatsCache.heartbeats);
      const headerString = base64urlEncodeWithoutPadding(JSON.stringify({ version: 2, heartbeats: heartbeatsToSend }));
      this._heartbeatsCache.lastSentHeartbeatDate = date;
      if (unsentEntries.length > 0) {
        this._heartbeatsCache.heartbeats = unsentEntries;
        await this._storage.overwrite(this._heartbeatsCache);
      } else {
        this._heartbeatsCache.heartbeats = [];
        void this._storage.overwrite(this._heartbeatsCache);
      }
      return headerString;
    } catch (e) {
      logger.warn(e);
      return "";
    }
  }
};
function getUTCDateString() {
  const today = /* @__PURE__ */ new Date();
  return today.toISOString().substring(0, 10);
}
function extractHeartbeatsForHeader(heartbeatsCache, maxSize = MAX_HEADER_BYTES) {
  const heartbeatsToSend = [];
  let unsentEntries = heartbeatsCache.slice();
  for (const singleDateHeartbeat of heartbeatsCache) {
    const heartbeatEntry = heartbeatsToSend.find((hb) => hb.agent === singleDateHeartbeat.agent);
    if (!heartbeatEntry) {
      heartbeatsToSend.push({
        agent: singleDateHeartbeat.agent,
        dates: [singleDateHeartbeat.date]
      });
      if (countBytes(heartbeatsToSend) > maxSize) {
        heartbeatsToSend.pop();
        break;
      }
    } else {
      heartbeatEntry.dates.push(singleDateHeartbeat.date);
      if (countBytes(heartbeatsToSend) > maxSize) {
        heartbeatEntry.dates.pop();
        break;
      }
    }
    unsentEntries = unsentEntries.slice(1);
  }
  return {
    heartbeatsToSend,
    unsentEntries
  };
}
var HeartbeatStorageImpl = class {
  constructor(app) {
    this.app = app;
    this._canUseIndexedDBPromise = this.runIndexedDBEnvironmentCheck();
  }
  async runIndexedDBEnvironmentCheck() {
    if (!isIndexedDBAvailable()) {
      return false;
    } else {
      return validateIndexedDBOpenable().then(() => true).catch(() => false);
    }
  }
  /**
   * Read all heartbeats.
   */
  async read() {
    const canUseIndexedDB = await this._canUseIndexedDBPromise;
    if (!canUseIndexedDB) {
      return { heartbeats: [] };
    } else {
      const idbHeartbeatObject = await readHeartbeatsFromIndexedDB(this.app);
      if (idbHeartbeatObject?.heartbeats) {
        return idbHeartbeatObject;
      } else {
        return { heartbeats: [] };
      }
    }
  }
  // overwrite the storage with the provided heartbeats
  async overwrite(heartbeatsObject) {
    const canUseIndexedDB = await this._canUseIndexedDBPromise;
    if (!canUseIndexedDB) {
      return;
    } else {
      const existingHeartbeatsObject = await this.read();
      return writeHeartbeatsToIndexedDB(this.app, {
        lastSentHeartbeatDate: heartbeatsObject.lastSentHeartbeatDate ?? existingHeartbeatsObject.lastSentHeartbeatDate,
        heartbeats: heartbeatsObject.heartbeats
      });
    }
  }
  // add heartbeats
  async add(heartbeatsObject) {
    const canUseIndexedDB = await this._canUseIndexedDBPromise;
    if (!canUseIndexedDB) {
      return;
    } else {
      const existingHeartbeatsObject = await this.read();
      return writeHeartbeatsToIndexedDB(this.app, {
        lastSentHeartbeatDate: heartbeatsObject.lastSentHeartbeatDate ?? existingHeartbeatsObject.lastSentHeartbeatDate,
        heartbeats: [
          ...existingHeartbeatsObject.heartbeats,
          ...heartbeatsObject.heartbeats
        ]
      });
    }
  }
};
function countBytes(heartbeatsCache) {
  return base64urlEncodeWithoutPadding(
    // heartbeatsCache wrapper properties
    JSON.stringify({ version: 2, heartbeats: heartbeatsCache })
  ).length;
}
function getEarliestHeartbeatIdx(heartbeats) {
  if (heartbeats.length === 0) {
    return -1;
  }
  let earliestHeartbeatIdx = 0;
  let earliestHeartbeatDate = heartbeats[0].date;
  for (let i = 1; i < heartbeats.length; i++) {
    if (heartbeats[i].date < earliestHeartbeatDate) {
      earliestHeartbeatDate = heartbeats[i].date;
      earliestHeartbeatIdx = i;
    }
  }
  return earliestHeartbeatIdx;
}
function registerCoreComponents(variant) {
  _registerComponent(new Component(
    "platform-logger",
    (container) => new PlatformLoggerServiceImpl(container),
    "PRIVATE"
    /* ComponentType.PRIVATE */
  ));
  _registerComponent(new Component(
    "heartbeat",
    (container) => new HeartbeatServiceImpl(container),
    "PRIVATE"
    /* ComponentType.PRIVATE */
  ));
  registerVersion(name$q, version$1, variant);
  registerVersion(name$q, version$1, "esm2020");
  registerVersion("fire-js", "");
}
registerCoreComponents("");

// node_modules/firebase/app/dist/esm/index.esm.js
var name2 = "firebase";
var version2 = "12.1.0";
registerVersion(name2, version2, "app");

// node_modules/@firebase/auth/dist/esm/index-9ccb475d.js
function _prodErrorMap() {
  return {
    [
      "dependent-sdk-initialized-before-auth"
      /* AuthErrorCode.DEPENDENT_SDK_INIT_BEFORE_AUTH */
    ]: "Another Firebase SDK was initialized and is trying to use Auth before Auth is initialized. Please be sure to call `initializeAuth` or `getAuth` before starting any other Firebase SDK."
  };
}
var prodErrorMap = _prodErrorMap;
var _DEFAULT_AUTH_ERROR_FACTORY = new ErrorFactory("auth", "Firebase", _prodErrorMap());
var logClient = new Logger("@firebase/auth");
function _logWarn(msg, ...args) {
  if (logClient.logLevel <= LogLevel.WARN) {
    logClient.warn(`Auth (${SDK_VERSION}): ${msg}`, ...args);
  }
}
function _logError(msg, ...args) {
  if (logClient.logLevel <= LogLevel.ERROR) {
    logClient.error(`Auth (${SDK_VERSION}): ${msg}`, ...args);
  }
}
function _fail(authOrCode, ...rest) {
  throw createErrorInternal(authOrCode, ...rest);
}
function _createError(authOrCode, ...rest) {
  return createErrorInternal(authOrCode, ...rest);
}
function _errorWithCustomMessage(auth, code, message) {
  const errorMap = {
    ...prodErrorMap(),
    [code]: message
  };
  const factory = new ErrorFactory("auth", "Firebase", errorMap);
  return factory.create(code, {
    appName: auth.name
  });
}
function _serverAppCurrentUserOperationNotSupportedError(auth) {
  return _errorWithCustomMessage(auth, "operation-not-supported-in-this-environment", "Operations that alter the current user are not supported in conjunction with FirebaseServerApp");
}
function _assertInstanceOf(auth, object, instance) {
  const constructorInstance = instance;
  if (!(object instanceof constructorInstance)) {
    if (constructorInstance.name !== object.constructor.name) {
      _fail(
        auth,
        "argument-error"
        /* AuthErrorCode.ARGUMENT_ERROR */
      );
    }
    throw _errorWithCustomMessage(auth, "argument-error", `Type of ${object.constructor.name} does not match expected instance.Did you pass a reference from a different Auth SDK?`);
  }
}
function createErrorInternal(authOrCode, ...rest) {
  if (typeof authOrCode !== "string") {
    const code = rest[0];
    const fullParams = [...rest.slice(1)];
    if (fullParams[0]) {
      fullParams[0].appName = authOrCode.name;
    }
    return authOrCode._errorFactory.create(code, ...fullParams);
  }
  return _DEFAULT_AUTH_ERROR_FACTORY.create(authOrCode, ...rest);
}
function _assert(assertion, authOrCode, ...rest) {
  if (!assertion) {
    throw createErrorInternal(authOrCode, ...rest);
  }
}
function debugFail(failure) {
  const message = `INTERNAL ASSERTION FAILED: ` + failure;
  _logError(message);
  throw new Error(message);
}
function debugAssert(assertion, message) {
  if (!assertion) {
    debugFail(message);
  }
}
function _getCurrentUrl() {
  return typeof self !== "undefined" && self.location?.href || "";
}
function _isHttpOrHttps() {
  return _getCurrentScheme() === "http:" || _getCurrentScheme() === "https:";
}
function _getCurrentScheme() {
  return typeof self !== "undefined" && self.location?.protocol || null;
}
function _isOnline() {
  if (typeof navigator !== "undefined" && navigator && "onLine" in navigator && typeof navigator.onLine === "boolean" && // Apply only for traditional web apps and Chrome extensions.
  // This is especially true for Cordova apps which have unreliable
  // navigator.onLine behavior unless cordova-plugin-network-information is
  // installed which overwrites the native navigator.onLine value and
  // defines navigator.connection.
  (_isHttpOrHttps() || isBrowserExtension() || "connection" in navigator)) {
    return navigator.onLine;
  }
  return true;
}
function _getUserLanguage() {
  if (typeof navigator === "undefined") {
    return null;
  }
  const navigatorLanguage = navigator;
  return (
    // Most reliable, but only supported in Chrome/Firefox.
    navigatorLanguage.languages && navigatorLanguage.languages[0] || // Supported in most browsers, but returns the language of the browser
    // UI, not the language set in browser settings.
    navigatorLanguage.language || // Couldn't determine language.
    null
  );
}
var Delay = class {
  constructor(shortDelay, longDelay) {
    this.shortDelay = shortDelay;
    this.longDelay = longDelay;
    debugAssert(longDelay > shortDelay, "Short delay should be less than long delay!");
    this.isMobile = isMobileCordova() || isReactNative();
  }
  get() {
    if (!_isOnline()) {
      return Math.min(5e3, this.shortDelay);
    }
    return this.isMobile ? this.longDelay : this.shortDelay;
  }
};
function _emulatorUrl(config, path) {
  debugAssert(config.emulator, "Emulator should always be set here");
  const { url } = config.emulator;
  if (!path) {
    return url;
  }
  return `${url}${path.startsWith("/") ? path.slice(1) : path}`;
}
var FetchProvider = class {
  static initialize(fetchImpl, headersImpl, responseImpl) {
    this.fetchImpl = fetchImpl;
    if (headersImpl) {
      this.headersImpl = headersImpl;
    }
    if (responseImpl) {
      this.responseImpl = responseImpl;
    }
  }
  static fetch() {
    if (this.fetchImpl) {
      return this.fetchImpl;
    }
    if (typeof self !== "undefined" && "fetch" in self) {
      return self.fetch;
    }
    if (typeof globalThis !== "undefined" && globalThis.fetch) {
      return globalThis.fetch;
    }
    if (typeof fetch !== "undefined") {
      return fetch;
    }
    debugFail("Could not find fetch implementation, make sure you call FetchProvider.initialize() with an appropriate polyfill");
  }
  static headers() {
    if (this.headersImpl) {
      return this.headersImpl;
    }
    if (typeof self !== "undefined" && "Headers" in self) {
      return self.Headers;
    }
    if (typeof globalThis !== "undefined" && globalThis.Headers) {
      return globalThis.Headers;
    }
    if (typeof Headers !== "undefined") {
      return Headers;
    }
    debugFail("Could not find Headers implementation, make sure you call FetchProvider.initialize() with an appropriate polyfill");
  }
  static response() {
    if (this.responseImpl) {
      return this.responseImpl;
    }
    if (typeof self !== "undefined" && "Response" in self) {
      return self.Response;
    }
    if (typeof globalThis !== "undefined" && globalThis.Response) {
      return globalThis.Response;
    }
    if (typeof Response !== "undefined") {
      return Response;
    }
    debugFail("Could not find Response implementation, make sure you call FetchProvider.initialize() with an appropriate polyfill");
  }
};
var SERVER_ERROR_MAP = {
  // Custom token errors.
  [
    "CREDENTIAL_MISMATCH"
    /* ServerError.CREDENTIAL_MISMATCH */
  ]: "custom-token-mismatch",
  // This can only happen if the SDK sends a bad request.
  [
    "MISSING_CUSTOM_TOKEN"
    /* ServerError.MISSING_CUSTOM_TOKEN */
  ]: "internal-error",
  // Create Auth URI errors.
  [
    "INVALID_IDENTIFIER"
    /* ServerError.INVALID_IDENTIFIER */
  ]: "invalid-email",
  // This can only happen if the SDK sends a bad request.
  [
    "MISSING_CONTINUE_URI"
    /* ServerError.MISSING_CONTINUE_URI */
  ]: "internal-error",
  // Sign in with email and password errors (some apply to sign up too).
  [
    "INVALID_PASSWORD"
    /* ServerError.INVALID_PASSWORD */
  ]: "wrong-password",
  // This can only happen if the SDK sends a bad request.
  [
    "MISSING_PASSWORD"
    /* ServerError.MISSING_PASSWORD */
  ]: "missing-password",
  // Thrown if Email Enumeration Protection is enabled in the project and the email or password is
  // invalid.
  [
    "INVALID_LOGIN_CREDENTIALS"
    /* ServerError.INVALID_LOGIN_CREDENTIALS */
  ]: "invalid-credential",
  // Sign up with email and password errors.
  [
    "EMAIL_EXISTS"
    /* ServerError.EMAIL_EXISTS */
  ]: "email-already-in-use",
  [
    "PASSWORD_LOGIN_DISABLED"
    /* ServerError.PASSWORD_LOGIN_DISABLED */
  ]: "operation-not-allowed",
  // Verify assertion for sign in with credential errors:
  [
    "INVALID_IDP_RESPONSE"
    /* ServerError.INVALID_IDP_RESPONSE */
  ]: "invalid-credential",
  [
    "INVALID_PENDING_TOKEN"
    /* ServerError.INVALID_PENDING_TOKEN */
  ]: "invalid-credential",
  [
    "FEDERATED_USER_ID_ALREADY_LINKED"
    /* ServerError.FEDERATED_USER_ID_ALREADY_LINKED */
  ]: "credential-already-in-use",
  // This can only happen if the SDK sends a bad request.
  [
    "MISSING_REQ_TYPE"
    /* ServerError.MISSING_REQ_TYPE */
  ]: "internal-error",
  // Send Password reset email errors:
  [
    "EMAIL_NOT_FOUND"
    /* ServerError.EMAIL_NOT_FOUND */
  ]: "user-not-found",
  [
    "RESET_PASSWORD_EXCEED_LIMIT"
    /* ServerError.RESET_PASSWORD_EXCEED_LIMIT */
  ]: "too-many-requests",
  [
    "EXPIRED_OOB_CODE"
    /* ServerError.EXPIRED_OOB_CODE */
  ]: "expired-action-code",
  [
    "INVALID_OOB_CODE"
    /* ServerError.INVALID_OOB_CODE */
  ]: "invalid-action-code",
  // This can only happen if the SDK sends a bad request.
  [
    "MISSING_OOB_CODE"
    /* ServerError.MISSING_OOB_CODE */
  ]: "internal-error",
  // Operations that require ID token in request:
  [
    "CREDENTIAL_TOO_OLD_LOGIN_AGAIN"
    /* ServerError.CREDENTIAL_TOO_OLD_LOGIN_AGAIN */
  ]: "requires-recent-login",
  [
    "INVALID_ID_TOKEN"
    /* ServerError.INVALID_ID_TOKEN */
  ]: "invalid-user-token",
  [
    "TOKEN_EXPIRED"
    /* ServerError.TOKEN_EXPIRED */
  ]: "user-token-expired",
  [
    "USER_NOT_FOUND"
    /* ServerError.USER_NOT_FOUND */
  ]: "user-token-expired",
  // Other errors.
  [
    "TOO_MANY_ATTEMPTS_TRY_LATER"
    /* ServerError.TOO_MANY_ATTEMPTS_TRY_LATER */
  ]: "too-many-requests",
  [
    "PASSWORD_DOES_NOT_MEET_REQUIREMENTS"
    /* ServerError.PASSWORD_DOES_NOT_MEET_REQUIREMENTS */
  ]: "password-does-not-meet-requirements",
  // Phone Auth related errors.
  [
    "INVALID_CODE"
    /* ServerError.INVALID_CODE */
  ]: "invalid-verification-code",
  [
    "INVALID_SESSION_INFO"
    /* ServerError.INVALID_SESSION_INFO */
  ]: "invalid-verification-id",
  [
    "INVALID_TEMPORARY_PROOF"
    /* ServerError.INVALID_TEMPORARY_PROOF */
  ]: "invalid-credential",
  [
    "MISSING_SESSION_INFO"
    /* ServerError.MISSING_SESSION_INFO */
  ]: "missing-verification-id",
  [
    "SESSION_EXPIRED"
    /* ServerError.SESSION_EXPIRED */
  ]: "code-expired",
  // Other action code errors when additional settings passed.
  // MISSING_CONTINUE_URI is getting mapped to INTERNAL_ERROR above.
  // This is OK as this error will be caught by client side validation.
  [
    "MISSING_ANDROID_PACKAGE_NAME"
    /* ServerError.MISSING_ANDROID_PACKAGE_NAME */
  ]: "missing-android-pkg-name",
  [
    "UNAUTHORIZED_DOMAIN"
    /* ServerError.UNAUTHORIZED_DOMAIN */
  ]: "unauthorized-continue-uri",
  // getProjectConfig errors when clientId is passed.
  [
    "INVALID_OAUTH_CLIENT_ID"
    /* ServerError.INVALID_OAUTH_CLIENT_ID */
  ]: "invalid-oauth-client-id",
  // User actions (sign-up or deletion) disabled errors.
  [
    "ADMIN_ONLY_OPERATION"
    /* ServerError.ADMIN_ONLY_OPERATION */
  ]: "admin-restricted-operation",
  // Multi factor related errors.
  [
    "INVALID_MFA_PENDING_CREDENTIAL"
    /* ServerError.INVALID_MFA_PENDING_CREDENTIAL */
  ]: "invalid-multi-factor-session",
  [
    "MFA_ENROLLMENT_NOT_FOUND"
    /* ServerError.MFA_ENROLLMENT_NOT_FOUND */
  ]: "multi-factor-info-not-found",
  [
    "MISSING_MFA_ENROLLMENT_ID"
    /* ServerError.MISSING_MFA_ENROLLMENT_ID */
  ]: "missing-multi-factor-info",
  [
    "MISSING_MFA_PENDING_CREDENTIAL"
    /* ServerError.MISSING_MFA_PENDING_CREDENTIAL */
  ]: "missing-multi-factor-session",
  [
    "SECOND_FACTOR_EXISTS"
    /* ServerError.SECOND_FACTOR_EXISTS */
  ]: "second-factor-already-in-use",
  [
    "SECOND_FACTOR_LIMIT_EXCEEDED"
    /* ServerError.SECOND_FACTOR_LIMIT_EXCEEDED */
  ]: "maximum-second-factor-count-exceeded",
  // Blocking functions related errors.
  [
    "BLOCKING_FUNCTION_ERROR_RESPONSE"
    /* ServerError.BLOCKING_FUNCTION_ERROR_RESPONSE */
  ]: "internal-error",
  // Recaptcha related errors.
  [
    "RECAPTCHA_NOT_ENABLED"
    /* ServerError.RECAPTCHA_NOT_ENABLED */
  ]: "recaptcha-not-enabled",
  [
    "MISSING_RECAPTCHA_TOKEN"
    /* ServerError.MISSING_RECAPTCHA_TOKEN */
  ]: "missing-recaptcha-token",
  [
    "INVALID_RECAPTCHA_TOKEN"
    /* ServerError.INVALID_RECAPTCHA_TOKEN */
  ]: "invalid-recaptcha-token",
  [
    "INVALID_RECAPTCHA_ACTION"
    /* ServerError.INVALID_RECAPTCHA_ACTION */
  ]: "invalid-recaptcha-action",
  [
    "MISSING_CLIENT_TYPE"
    /* ServerError.MISSING_CLIENT_TYPE */
  ]: "missing-client-type",
  [
    "MISSING_RECAPTCHA_VERSION"
    /* ServerError.MISSING_RECAPTCHA_VERSION */
  ]: "missing-recaptcha-version",
  [
    "INVALID_RECAPTCHA_VERSION"
    /* ServerError.INVALID_RECAPTCHA_VERSION */
  ]: "invalid-recaptcha-version",
  [
    "INVALID_REQ_TYPE"
    /* ServerError.INVALID_REQ_TYPE */
  ]: "invalid-req-type"
  /* AuthErrorCode.INVALID_REQ_TYPE */
};
var CookieAuthProxiedEndpoints = [
  "/v1/accounts:signInWithCustomToken",
  "/v1/accounts:signInWithEmailLink",
  "/v1/accounts:signInWithIdp",
  "/v1/accounts:signInWithPassword",
  "/v1/accounts:signInWithPhoneNumber",
  "/v1/token"
  /* Endpoint.TOKEN */
];
var DEFAULT_API_TIMEOUT_MS = new Delay(3e4, 6e4);
function _addTidIfNecessary(auth, request) {
  if (auth.tenantId && !request.tenantId) {
    return {
      ...request,
      tenantId: auth.tenantId
    };
  }
  return request;
}
async function _performApiRequest(auth, method, path, request, customErrorMap = {}) {
  return _performFetchWithErrorHandling(auth, customErrorMap, async () => {
    let body = {};
    let params = {};
    if (request) {
      if (method === "GET") {
        params = request;
      } else {
        body = {
          body: JSON.stringify(request)
        };
      }
    }
    const query = querystring({
      key: auth.config.apiKey,
      ...params
    }).slice(1);
    const headers = await auth._getAdditionalHeaders();
    headers[
      "Content-Type"
      /* HttpHeader.CONTENT_TYPE */
    ] = "application/json";
    if (auth.languageCode) {
      headers[
        "X-Firebase-Locale"
        /* HttpHeader.X_FIREBASE_LOCALE */
      ] = auth.languageCode;
    }
    const fetchArgs = {
      method,
      headers,
      ...body
    };
    if (!isCloudflareWorker()) {
      fetchArgs.referrerPolicy = "no-referrer";
    }
    if (auth.emulatorConfig && isCloudWorkstation(auth.emulatorConfig.host)) {
      fetchArgs.credentials = "include";
    }
    return FetchProvider.fetch()(await _getFinalTarget(auth, auth.config.apiHost, path, query), fetchArgs);
  });
}
async function _performFetchWithErrorHandling(auth, customErrorMap, fetchFn) {
  auth._canInitEmulator = false;
  const errorMap = { ...SERVER_ERROR_MAP, ...customErrorMap };
  try {
    const networkTimeout = new NetworkTimeout(auth);
    const response = await Promise.race([
      fetchFn(),
      networkTimeout.promise
    ]);
    networkTimeout.clearNetworkTimeout();
    const json = await response.json();
    if ("needConfirmation" in json) {
      throw _makeTaggedError(auth, "account-exists-with-different-credential", json);
    }
    if (response.ok && !("errorMessage" in json)) {
      return json;
    } else {
      const errorMessage = response.ok ? json.errorMessage : json.error.message;
      const [serverErrorCode, serverErrorMessage] = errorMessage.split(" : ");
      if (serverErrorCode === "FEDERATED_USER_ID_ALREADY_LINKED") {
        throw _makeTaggedError(auth, "credential-already-in-use", json);
      } else if (serverErrorCode === "EMAIL_EXISTS") {
        throw _makeTaggedError(auth, "email-already-in-use", json);
      } else if (serverErrorCode === "USER_DISABLED") {
        throw _makeTaggedError(auth, "user-disabled", json);
      }
      const authError = errorMap[serverErrorCode] || serverErrorCode.toLowerCase().replace(/[_\s]+/g, "-");
      if (serverErrorMessage) {
        throw _errorWithCustomMessage(auth, authError, serverErrorMessage);
      } else {
        _fail(auth, authError);
      }
    }
  } catch (e) {
    if (e instanceof FirebaseError) {
      throw e;
    }
    _fail(auth, "network-request-failed", { "message": String(e) });
  }
}
async function _performSignInRequest(auth, method, path, request, customErrorMap = {}) {
  const serverResponse = await _performApiRequest(auth, method, path, request, customErrorMap);
  if ("mfaPendingCredential" in serverResponse) {
    _fail(auth, "multi-factor-auth-required", {
      _serverResponse: serverResponse
    });
  }
  return serverResponse;
}
async function _getFinalTarget(auth, host, path, query) {
  const base = `${host}${path}?${query}`;
  const authInternal = auth;
  const finalTarget = authInternal.config.emulator ? _emulatorUrl(auth.config, base) : `${auth.config.apiScheme}://${base}`;
  if (CookieAuthProxiedEndpoints.includes(path)) {
    await authInternal._persistenceManagerAvailable;
    if (authInternal._getPersistenceType() === "COOKIE") {
      const cookiePersistence = authInternal._getPersistence();
      return cookiePersistence._getFinalTarget(finalTarget).toString();
    }
  }
  return finalTarget;
}
function _parseEnforcementState(enforcementStateStr) {
  switch (enforcementStateStr) {
    case "ENFORCE":
      return "ENFORCE";
    case "AUDIT":
      return "AUDIT";
    case "OFF":
      return "OFF";
    default:
      return "ENFORCEMENT_STATE_UNSPECIFIED";
  }
}
var NetworkTimeout = class {
  clearNetworkTimeout() {
    clearTimeout(this.timer);
  }
  constructor(auth) {
    this.auth = auth;
    this.timer = null;
    this.promise = new Promise((_, reject) => {
      this.timer = setTimeout(() => {
        return reject(_createError(
          this.auth,
          "network-request-failed"
          /* AuthErrorCode.NETWORK_REQUEST_FAILED */
        ));
      }, DEFAULT_API_TIMEOUT_MS.get());
    });
  }
};
function _makeTaggedError(auth, code, response) {
  const errorParams = {
    appName: auth.name
  };
  if (response.email) {
    errorParams.email = response.email;
  }
  if (response.phoneNumber) {
    errorParams.phoneNumber = response.phoneNumber;
  }
  const error = _createError(auth, code, errorParams);
  error.customData._tokenResponse = response;
  return error;
}
function isEnterprise(grecaptcha) {
  return grecaptcha !== void 0 && grecaptcha.enterprise !== void 0;
}
var RecaptchaConfig = class {
  constructor(response) {
    this.siteKey = "";
    this.recaptchaEnforcementState = [];
    if (response.recaptchaKey === void 0) {
      throw new Error("recaptchaKey undefined");
    }
    this.siteKey = response.recaptchaKey.split("/")[3];
    this.recaptchaEnforcementState = response.recaptchaEnforcementState;
  }
  /**
   * Returns the reCAPTCHA Enterprise enforcement state for the given provider.
   *
   * @param providerStr - The provider whose enforcement state is to be returned.
   * @returns The reCAPTCHA Enterprise enforcement state for the given provider.
   */
  getProviderEnforcementState(providerStr) {
    if (!this.recaptchaEnforcementState || this.recaptchaEnforcementState.length === 0) {
      return null;
    }
    for (const recaptchaEnforcementState of this.recaptchaEnforcementState) {
      if (recaptchaEnforcementState.provider && recaptchaEnforcementState.provider === providerStr) {
        return _parseEnforcementState(recaptchaEnforcementState.enforcementState);
      }
    }
    return null;
  }
  /**
   * Returns true if the reCAPTCHA Enterprise enforcement state for the provider is set to ENFORCE or AUDIT.
   *
   * @param providerStr - The provider whose enablement state is to be returned.
   * @returns Whether or not reCAPTCHA Enterprise protection is enabled for the given provider.
   */
  isProviderEnabled(providerStr) {
    return this.getProviderEnforcementState(providerStr) === "ENFORCE" || this.getProviderEnforcementState(providerStr) === "AUDIT";
  }
  /**
   * Returns true if reCAPTCHA Enterprise protection is enabled in at least one provider, otherwise
   * returns false.
   *
   * @returns Whether or not reCAPTCHA Enterprise protection is enabled for at least one provider.
   */
  isAnyProviderEnabled() {
    return this.isProviderEnabled(
      "EMAIL_PASSWORD_PROVIDER"
      /* RecaptchaAuthProvider.EMAIL_PASSWORD_PROVIDER */
    ) || this.isProviderEnabled(
      "PHONE_PROVIDER"
      /* RecaptchaAuthProvider.PHONE_PROVIDER */
    );
  }
};
async function getRecaptchaConfig(auth, request) {
  return _performApiRequest(auth, "GET", "/v2/recaptchaConfig", _addTidIfNecessary(auth, request));
}
async function deleteAccount(auth, request) {
  return _performApiRequest(auth, "POST", "/v1/accounts:delete", request);
}
async function getAccountInfo(auth, request) {
  return _performApiRequest(auth, "POST", "/v1/accounts:lookup", request);
}
function utcTimestampToDateString(utcTimestamp) {
  if (!utcTimestamp) {
    return void 0;
  }
  try {
    const date = new Date(Number(utcTimestamp));
    if (!isNaN(date.getTime())) {
      return date.toUTCString();
    }
  } catch (e) {
  }
  return void 0;
}
async function getIdTokenResult(user, forceRefresh = false) {
  const userInternal = getModularInstance(user);
  const token = await userInternal.getIdToken(forceRefresh);
  const claims = _parseToken(token);
  _assert(
    claims && claims.exp && claims.auth_time && claims.iat,
    userInternal.auth,
    "internal-error"
    /* AuthErrorCode.INTERNAL_ERROR */
  );
  const firebase = typeof claims.firebase === "object" ? claims.firebase : void 0;
  const signInProvider = firebase?.["sign_in_provider"];
  return {
    claims,
    token,
    authTime: utcTimestampToDateString(secondsStringToMilliseconds(claims.auth_time)),
    issuedAtTime: utcTimestampToDateString(secondsStringToMilliseconds(claims.iat)),
    expirationTime: utcTimestampToDateString(secondsStringToMilliseconds(claims.exp)),
    signInProvider: signInProvider || null,
    signInSecondFactor: firebase?.["sign_in_second_factor"] || null
  };
}
function secondsStringToMilliseconds(seconds) {
  return Number(seconds) * 1e3;
}
function _parseToken(token) {
  const [algorithm, payload, signature] = token.split(".");
  if (algorithm === void 0 || payload === void 0 || signature === void 0) {
    _logError("JWT malformed, contained fewer than 3 sections");
    return null;
  }
  try {
    const decoded = base64Decode(payload);
    if (!decoded) {
      _logError("Failed to decode base64 JWT payload");
      return null;
    }
    return JSON.parse(decoded);
  } catch (e) {
    _logError("Caught error parsing JWT payload as JSON", e?.toString());
    return null;
  }
}
function _tokenExpiresIn(token) {
  const parsedToken = _parseToken(token);
  _assert(
    parsedToken,
    "internal-error"
    /* AuthErrorCode.INTERNAL_ERROR */
  );
  _assert(
    typeof parsedToken.exp !== "undefined",
    "internal-error"
    /* AuthErrorCode.INTERNAL_ERROR */
  );
  _assert(
    typeof parsedToken.iat !== "undefined",
    "internal-error"
    /* AuthErrorCode.INTERNAL_ERROR */
  );
  return Number(parsedToken.exp) - Number(parsedToken.iat);
}
async function _logoutIfInvalidated(user, promise, bypassAuthState = false) {
  if (bypassAuthState) {
    return promise;
  }
  try {
    return await promise;
  } catch (e) {
    if (e instanceof FirebaseError && isUserInvalidated(e)) {
      if (user.auth.currentUser === user) {
        await user.auth.signOut();
      }
    }
    throw e;
  }
}
function isUserInvalidated({ code }) {
  return code === `auth/${"user-disabled"}` || code === `auth/${"user-token-expired"}`;
}
var ProactiveRefresh = class {
  constructor(user) {
    this.user = user;
    this.isRunning = false;
    this.timerId = null;
    this.errorBackoff = 3e4;
  }
  _start() {
    if (this.isRunning) {
      return;
    }
    this.isRunning = true;
    this.schedule();
  }
  _stop() {
    if (!this.isRunning) {
      return;
    }
    this.isRunning = false;
    if (this.timerId !== null) {
      clearTimeout(this.timerId);
    }
  }
  getInterval(wasError) {
    if (wasError) {
      const interval = this.errorBackoff;
      this.errorBackoff = Math.min(
        this.errorBackoff * 2,
        96e4
        /* Duration.RETRY_BACKOFF_MAX */
      );
      return interval;
    } else {
      this.errorBackoff = 3e4;
      const expTime = this.user.stsTokenManager.expirationTime ?? 0;
      const interval = expTime - Date.now() - 3e5;
      return Math.max(0, interval);
    }
  }
  schedule(wasError = false) {
    if (!this.isRunning) {
      return;
    }
    const interval = this.getInterval(wasError);
    this.timerId = setTimeout(async () => {
      await this.iteration();
    }, interval);
  }
  async iteration() {
    try {
      await this.user.getIdToken(true);
    } catch (e) {
      if (e?.code === `auth/${"network-request-failed"}`) {
        this.schedule(
          /* wasError */
          true
        );
      }
      return;
    }
    this.schedule();
  }
};
var UserMetadata = class {
  constructor(createdAt, lastLoginAt) {
    this.createdAt = createdAt;
    this.lastLoginAt = lastLoginAt;
    this._initializeTime();
  }
  _initializeTime() {
    this.lastSignInTime = utcTimestampToDateString(this.lastLoginAt);
    this.creationTime = utcTimestampToDateString(this.createdAt);
  }
  _copy(metadata) {
    this.createdAt = metadata.createdAt;
    this.lastLoginAt = metadata.lastLoginAt;
    this._initializeTime();
  }
  toJSON() {
    return {
      createdAt: this.createdAt,
      lastLoginAt: this.lastLoginAt
    };
  }
};
async function _reloadWithoutSaving(user) {
  const auth = user.auth;
  const idToken = await user.getIdToken();
  const response = await _logoutIfInvalidated(user, getAccountInfo(auth, { idToken }));
  _assert(
    response?.users.length,
    auth,
    "internal-error"
    /* AuthErrorCode.INTERNAL_ERROR */
  );
  const coreAccount = response.users[0];
  user._notifyReloadListener(coreAccount);
  const newProviderData = coreAccount.providerUserInfo?.length ? extractProviderData(coreAccount.providerUserInfo) : [];
  const providerData = mergeProviderData(user.providerData, newProviderData);
  const oldIsAnonymous = user.isAnonymous;
  const newIsAnonymous = !(user.email && coreAccount.passwordHash) && !providerData?.length;
  const isAnonymous = !oldIsAnonymous ? false : newIsAnonymous;
  const updates = {
    uid: coreAccount.localId,
    displayName: coreAccount.displayName || null,
    photoURL: coreAccount.photoUrl || null,
    email: coreAccount.email || null,
    emailVerified: coreAccount.emailVerified || false,
    phoneNumber: coreAccount.phoneNumber || null,
    tenantId: coreAccount.tenantId || null,
    providerData,
    metadata: new UserMetadata(coreAccount.createdAt, coreAccount.lastLoginAt),
    isAnonymous
  };
  Object.assign(user, updates);
}
async function reload(user) {
  const userInternal = getModularInstance(user);
  await _reloadWithoutSaving(userInternal);
  await userInternal.auth._persistUserIfCurrent(userInternal);
  userInternal.auth._notifyListenersIfCurrent(userInternal);
}
function mergeProviderData(original, newData) {
  const deduped = original.filter((o) => !newData.some((n) => n.providerId === o.providerId));
  return [...deduped, ...newData];
}
function extractProviderData(providers) {
  return providers.map(({ providerId, ...provider }) => {
    return {
      providerId,
      uid: provider.rawId || "",
      displayName: provider.displayName || null,
      email: provider.email || null,
      phoneNumber: provider.phoneNumber || null,
      photoURL: provider.photoUrl || null
    };
  });
}
async function requestStsToken(auth, refreshToken) {
  const response = await _performFetchWithErrorHandling(auth, {}, async () => {
    const body = querystring({
      "grant_type": "refresh_token",
      "refresh_token": refreshToken
    }).slice(1);
    const { tokenApiHost, apiKey } = auth.config;
    const url = await _getFinalTarget(auth, tokenApiHost, "/v1/token", `key=${apiKey}`);
    const headers = await auth._getAdditionalHeaders();
    headers[
      "Content-Type"
      /* HttpHeader.CONTENT_TYPE */
    ] = "application/x-www-form-urlencoded";
    const options = {
      method: "POST",
      headers,
      body
    };
    if (auth.emulatorConfig && isCloudWorkstation(auth.emulatorConfig.host)) {
      options.credentials = "include";
    }
    return FetchProvider.fetch()(url, options);
  });
  return {
    accessToken: response.access_token,
    expiresIn: response.expires_in,
    refreshToken: response.refresh_token
  };
}
async function revokeToken(auth, request) {
  return _performApiRequest(auth, "POST", "/v2/accounts:revokeToken", _addTidIfNecessary(auth, request));
}
var StsTokenManager = class _StsTokenManager {
  constructor() {
    this.refreshToken = null;
    this.accessToken = null;
    this.expirationTime = null;
  }
  get isExpired() {
    return !this.expirationTime || Date.now() > this.expirationTime - 3e4;
  }
  updateFromServerResponse(response) {
    _assert(
      response.idToken,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    _assert(
      typeof response.idToken !== "undefined",
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    _assert(
      typeof response.refreshToken !== "undefined",
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    const expiresIn = "expiresIn" in response && typeof response.expiresIn !== "undefined" ? Number(response.expiresIn) : _tokenExpiresIn(response.idToken);
    this.updateTokensAndExpiration(response.idToken, response.refreshToken, expiresIn);
  }
  updateFromIdToken(idToken) {
    _assert(
      idToken.length !== 0,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    const expiresIn = _tokenExpiresIn(idToken);
    this.updateTokensAndExpiration(idToken, null, expiresIn);
  }
  async getToken(auth, forceRefresh = false) {
    if (!forceRefresh && this.accessToken && !this.isExpired) {
      return this.accessToken;
    }
    _assert(
      this.refreshToken,
      auth,
      "user-token-expired"
      /* AuthErrorCode.TOKEN_EXPIRED */
    );
    if (this.refreshToken) {
      await this.refresh(auth, this.refreshToken);
      return this.accessToken;
    }
    return null;
  }
  clearRefreshToken() {
    this.refreshToken = null;
  }
  async refresh(auth, oldToken) {
    const { accessToken, refreshToken, expiresIn } = await requestStsToken(auth, oldToken);
    this.updateTokensAndExpiration(accessToken, refreshToken, Number(expiresIn));
  }
  updateTokensAndExpiration(accessToken, refreshToken, expiresInSec) {
    this.refreshToken = refreshToken || null;
    this.accessToken = accessToken || null;
    this.expirationTime = Date.now() + expiresInSec * 1e3;
  }
  static fromJSON(appName, object) {
    const { refreshToken, accessToken, expirationTime } = object;
    const manager = new _StsTokenManager();
    if (refreshToken) {
      _assert(typeof refreshToken === "string", "internal-error", {
        appName
      });
      manager.refreshToken = refreshToken;
    }
    if (accessToken) {
      _assert(typeof accessToken === "string", "internal-error", {
        appName
      });
      manager.accessToken = accessToken;
    }
    if (expirationTime) {
      _assert(typeof expirationTime === "number", "internal-error", {
        appName
      });
      manager.expirationTime = expirationTime;
    }
    return manager;
  }
  toJSON() {
    return {
      refreshToken: this.refreshToken,
      accessToken: this.accessToken,
      expirationTime: this.expirationTime
    };
  }
  _assign(stsTokenManager) {
    this.accessToken = stsTokenManager.accessToken;
    this.refreshToken = stsTokenManager.refreshToken;
    this.expirationTime = stsTokenManager.expirationTime;
  }
  _clone() {
    return Object.assign(new _StsTokenManager(), this.toJSON());
  }
  _performRefresh() {
    return debugFail("not implemented");
  }
};
function assertStringOrUndefined(assertion, appName) {
  _assert(typeof assertion === "string" || typeof assertion === "undefined", "internal-error", { appName });
}
var UserImpl = class _UserImpl {
  constructor({ uid, auth, stsTokenManager, ...opt }) {
    this.providerId = "firebase";
    this.proactiveRefresh = new ProactiveRefresh(this);
    this.reloadUserInfo = null;
    this.reloadListener = null;
    this.uid = uid;
    this.auth = auth;
    this.stsTokenManager = stsTokenManager;
    this.accessToken = stsTokenManager.accessToken;
    this.displayName = opt.displayName || null;
    this.email = opt.email || null;
    this.emailVerified = opt.emailVerified || false;
    this.phoneNumber = opt.phoneNumber || null;
    this.photoURL = opt.photoURL || null;
    this.isAnonymous = opt.isAnonymous || false;
    this.tenantId = opt.tenantId || null;
    this.providerData = opt.providerData ? [...opt.providerData] : [];
    this.metadata = new UserMetadata(opt.createdAt || void 0, opt.lastLoginAt || void 0);
  }
  async getIdToken(forceRefresh) {
    const accessToken = await _logoutIfInvalidated(this, this.stsTokenManager.getToken(this.auth, forceRefresh));
    _assert(
      accessToken,
      this.auth,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    if (this.accessToken !== accessToken) {
      this.accessToken = accessToken;
      await this.auth._persistUserIfCurrent(this);
      this.auth._notifyListenersIfCurrent(this);
    }
    return accessToken;
  }
  getIdTokenResult(forceRefresh) {
    return getIdTokenResult(this, forceRefresh);
  }
  reload() {
    return reload(this);
  }
  _assign(user) {
    if (this === user) {
      return;
    }
    _assert(
      this.uid === user.uid,
      this.auth,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    this.displayName = user.displayName;
    this.photoURL = user.photoURL;
    this.email = user.email;
    this.emailVerified = user.emailVerified;
    this.phoneNumber = user.phoneNumber;
    this.isAnonymous = user.isAnonymous;
    this.tenantId = user.tenantId;
    this.providerData = user.providerData.map((userInfo) => ({ ...userInfo }));
    this.metadata._copy(user.metadata);
    this.stsTokenManager._assign(user.stsTokenManager);
  }
  _clone(auth) {
    const newUser = new _UserImpl({
      ...this,
      auth,
      stsTokenManager: this.stsTokenManager._clone()
    });
    newUser.metadata._copy(this.metadata);
    return newUser;
  }
  _onReload(callback) {
    _assert(
      !this.reloadListener,
      this.auth,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    this.reloadListener = callback;
    if (this.reloadUserInfo) {
      this._notifyReloadListener(this.reloadUserInfo);
      this.reloadUserInfo = null;
    }
  }
  _notifyReloadListener(userInfo) {
    if (this.reloadListener) {
      this.reloadListener(userInfo);
    } else {
      this.reloadUserInfo = userInfo;
    }
  }
  _startProactiveRefresh() {
    this.proactiveRefresh._start();
  }
  _stopProactiveRefresh() {
    this.proactiveRefresh._stop();
  }
  async _updateTokensIfNecessary(response, reload2 = false) {
    let tokensRefreshed = false;
    if (response.idToken && response.idToken !== this.stsTokenManager.accessToken) {
      this.stsTokenManager.updateFromServerResponse(response);
      tokensRefreshed = true;
    }
    if (reload2) {
      await _reloadWithoutSaving(this);
    }
    await this.auth._persistUserIfCurrent(this);
    if (tokensRefreshed) {
      this.auth._notifyListenersIfCurrent(this);
    }
  }
  async delete() {
    if (_isFirebaseServerApp(this.auth.app)) {
      return Promise.reject(_serverAppCurrentUserOperationNotSupportedError(this.auth));
    }
    const idToken = await this.getIdToken();
    await _logoutIfInvalidated(this, deleteAccount(this.auth, { idToken }));
    this.stsTokenManager.clearRefreshToken();
    return this.auth.signOut();
  }
  toJSON() {
    return {
      uid: this.uid,
      email: this.email || void 0,
      emailVerified: this.emailVerified,
      displayName: this.displayName || void 0,
      isAnonymous: this.isAnonymous,
      photoURL: this.photoURL || void 0,
      phoneNumber: this.phoneNumber || void 0,
      tenantId: this.tenantId || void 0,
      providerData: this.providerData.map((userInfo) => ({ ...userInfo })),
      stsTokenManager: this.stsTokenManager.toJSON(),
      // Redirect event ID must be maintained in case there is a pending
      // redirect event.
      _redirectEventId: this._redirectEventId,
      ...this.metadata.toJSON(),
      // Required for compatibility with the legacy SDK (go/firebase-auth-sdk-persistence-parsing):
      apiKey: this.auth.config.apiKey,
      appName: this.auth.name
      // Missing authDomain will be tolerated by the legacy SDK.
      // stsTokenManager.apiKey isn't actually required (despite the legacy SDK persisting it).
    };
  }
  get refreshToken() {
    return this.stsTokenManager.refreshToken || "";
  }
  static _fromJSON(auth, object) {
    const displayName = object.displayName ?? void 0;
    const email = object.email ?? void 0;
    const phoneNumber = object.phoneNumber ?? void 0;
    const photoURL = object.photoURL ?? void 0;
    const tenantId = object.tenantId ?? void 0;
    const _redirectEventId = object._redirectEventId ?? void 0;
    const createdAt = object.createdAt ?? void 0;
    const lastLoginAt = object.lastLoginAt ?? void 0;
    const { uid, emailVerified, isAnonymous, providerData, stsTokenManager: plainObjectTokenManager } = object;
    _assert(
      uid && plainObjectTokenManager,
      auth,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    const stsTokenManager = StsTokenManager.fromJSON(this.name, plainObjectTokenManager);
    _assert(
      typeof uid === "string",
      auth,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    assertStringOrUndefined(displayName, auth.name);
    assertStringOrUndefined(email, auth.name);
    _assert(
      typeof emailVerified === "boolean",
      auth,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    _assert(
      typeof isAnonymous === "boolean",
      auth,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    assertStringOrUndefined(phoneNumber, auth.name);
    assertStringOrUndefined(photoURL, auth.name);
    assertStringOrUndefined(tenantId, auth.name);
    assertStringOrUndefined(_redirectEventId, auth.name);
    assertStringOrUndefined(createdAt, auth.name);
    assertStringOrUndefined(lastLoginAt, auth.name);
    const user = new _UserImpl({
      uid,
      auth,
      email,
      emailVerified,
      displayName,
      isAnonymous,
      photoURL,
      phoneNumber,
      tenantId,
      stsTokenManager,
      createdAt,
      lastLoginAt
    });
    if (providerData && Array.isArray(providerData)) {
      user.providerData = providerData.map((userInfo) => ({ ...userInfo }));
    }
    if (_redirectEventId) {
      user._redirectEventId = _redirectEventId;
    }
    return user;
  }
  /**
   * Initialize a User from an idToken server response
   * @param auth
   * @param idTokenResponse
   */
  static async _fromIdTokenResponse(auth, idTokenResponse, isAnonymous = false) {
    const stsTokenManager = new StsTokenManager();
    stsTokenManager.updateFromServerResponse(idTokenResponse);
    const user = new _UserImpl({
      uid: idTokenResponse.localId,
      auth,
      stsTokenManager,
      isAnonymous
    });
    await _reloadWithoutSaving(user);
    return user;
  }
  /**
   * Initialize a User from an idToken server response
   * @param auth
   * @param idTokenResponse
   */
  static async _fromGetAccountInfoResponse(auth, response, idToken) {
    const coreAccount = response.users[0];
    _assert(
      coreAccount.localId !== void 0,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    const providerData = coreAccount.providerUserInfo !== void 0 ? extractProviderData(coreAccount.providerUserInfo) : [];
    const isAnonymous = !(coreAccount.email && coreAccount.passwordHash) && !providerData?.length;
    const stsTokenManager = new StsTokenManager();
    stsTokenManager.updateFromIdToken(idToken);
    const user = new _UserImpl({
      uid: coreAccount.localId,
      auth,
      stsTokenManager,
      isAnonymous
    });
    const updates = {
      uid: coreAccount.localId,
      displayName: coreAccount.displayName || null,
      photoURL: coreAccount.photoUrl || null,
      email: coreAccount.email || null,
      emailVerified: coreAccount.emailVerified || false,
      phoneNumber: coreAccount.phoneNumber || null,
      tenantId: coreAccount.tenantId || null,
      providerData,
      metadata: new UserMetadata(coreAccount.createdAt, coreAccount.lastLoginAt),
      isAnonymous: !(coreAccount.email && coreAccount.passwordHash) && !providerData?.length
    };
    Object.assign(user, updates);
    return user;
  }
};
var instanceCache = /* @__PURE__ */ new Map();
function _getInstance(cls) {
  debugAssert(cls instanceof Function, "Expected a class definition");
  let instance = instanceCache.get(cls);
  if (instance) {
    debugAssert(instance instanceof cls, "Instance stored in cache mismatched with class");
    return instance;
  }
  instance = new cls();
  instanceCache.set(cls, instance);
  return instance;
}
var InMemoryPersistence = class {
  constructor() {
    this.type = "NONE";
    this.storage = {};
  }
  async _isAvailable() {
    return true;
  }
  async _set(key, value) {
    this.storage[key] = value;
  }
  async _get(key) {
    const value = this.storage[key];
    return value === void 0 ? null : value;
  }
  async _remove(key) {
    delete this.storage[key];
  }
  _addListener(_key, _listener) {
    return;
  }
  _removeListener(_key, _listener) {
    return;
  }
};
InMemoryPersistence.type = "NONE";
var inMemoryPersistence = InMemoryPersistence;
function _persistenceKeyName(key, apiKey, appName) {
  return `${"firebase"}:${key}:${apiKey}:${appName}`;
}
var PersistenceUserManager = class _PersistenceUserManager {
  constructor(persistence, auth, userKey) {
    this.persistence = persistence;
    this.auth = auth;
    this.userKey = userKey;
    const { config, name: name4 } = this.auth;
    this.fullUserKey = _persistenceKeyName(this.userKey, config.apiKey, name4);
    this.fullPersistenceKey = _persistenceKeyName("persistence", config.apiKey, name4);
    this.boundEventHandler = auth._onStorageEvent.bind(auth);
    this.persistence._addListener(this.fullUserKey, this.boundEventHandler);
  }
  setCurrentUser(user) {
    return this.persistence._set(this.fullUserKey, user.toJSON());
  }
  async getCurrentUser() {
    const blob = await this.persistence._get(this.fullUserKey);
    if (!blob) {
      return null;
    }
    if (typeof blob === "string") {
      const response = await getAccountInfo(this.auth, { idToken: blob }).catch(() => void 0);
      if (!response) {
        return null;
      }
      return UserImpl._fromGetAccountInfoResponse(this.auth, response, blob);
    }
    return UserImpl._fromJSON(this.auth, blob);
  }
  removeCurrentUser() {
    return this.persistence._remove(this.fullUserKey);
  }
  savePersistenceForRedirect() {
    return this.persistence._set(this.fullPersistenceKey, this.persistence.type);
  }
  async setPersistence(newPersistence) {
    if (this.persistence === newPersistence) {
      return;
    }
    const currentUser = await this.getCurrentUser();
    await this.removeCurrentUser();
    this.persistence = newPersistence;
    if (currentUser) {
      return this.setCurrentUser(currentUser);
    }
  }
  delete() {
    this.persistence._removeListener(this.fullUserKey, this.boundEventHandler);
  }
  static async create(auth, persistenceHierarchy, userKey = "authUser") {
    if (!persistenceHierarchy.length) {
      return new _PersistenceUserManager(_getInstance(inMemoryPersistence), auth, userKey);
    }
    const availablePersistences = (await Promise.all(persistenceHierarchy.map(async (persistence) => {
      if (await persistence._isAvailable()) {
        return persistence;
      }
      return void 0;
    }))).filter((persistence) => persistence);
    let selectedPersistence = availablePersistences[0] || _getInstance(inMemoryPersistence);
    const key = _persistenceKeyName(userKey, auth.config.apiKey, auth.name);
    let userToMigrate = null;
    for (const persistence of persistenceHierarchy) {
      try {
        const blob = await persistence._get(key);
        if (blob) {
          let user;
          if (typeof blob === "string") {
            const response = await getAccountInfo(auth, {
              idToken: blob
            }).catch(() => void 0);
            if (!response) {
              break;
            }
            user = await UserImpl._fromGetAccountInfoResponse(auth, response, blob);
          } else {
            user = UserImpl._fromJSON(auth, blob);
          }
          if (persistence !== selectedPersistence) {
            userToMigrate = user;
          }
          selectedPersistence = persistence;
          break;
        }
      } catch {
      }
    }
    const migrationHierarchy = availablePersistences.filter((p2) => p2._shouldAllowMigration);
    if (!selectedPersistence._shouldAllowMigration || !migrationHierarchy.length) {
      return new _PersistenceUserManager(selectedPersistence, auth, userKey);
    }
    selectedPersistence = migrationHierarchy[0];
    if (userToMigrate) {
      await selectedPersistence._set(key, userToMigrate.toJSON());
    }
    await Promise.all(persistenceHierarchy.map(async (persistence) => {
      if (persistence !== selectedPersistence) {
        try {
          await persistence._remove(key);
        } catch {
        }
      }
    }));
    return new _PersistenceUserManager(selectedPersistence, auth, userKey);
  }
};
function _getBrowserName(userAgent) {
  const ua = userAgent.toLowerCase();
  if (ua.includes("opera/") || ua.includes("opr/") || ua.includes("opios/")) {
    return "Opera";
  } else if (_isIEMobile(ua)) {
    return "IEMobile";
  } else if (ua.includes("msie") || ua.includes("trident/")) {
    return "IE";
  } else if (ua.includes("edge/")) {
    return "Edge";
  } else if (_isFirefox(ua)) {
    return "Firefox";
  } else if (ua.includes("silk/")) {
    return "Silk";
  } else if (_isBlackBerry(ua)) {
    return "Blackberry";
  } else if (_isWebOS(ua)) {
    return "Webos";
  } else if (_isSafari(ua)) {
    return "Safari";
  } else if ((ua.includes("chrome/") || _isChromeIOS(ua)) && !ua.includes("edge/")) {
    return "Chrome";
  } else if (_isAndroid(ua)) {
    return "Android";
  } else {
    const re = /([a-zA-Z\d\.]+)\/[a-zA-Z\d\.]*$/;
    const matches = userAgent.match(re);
    if (matches?.length === 2) {
      return matches[1];
    }
  }
  return "Other";
}
function _isFirefox(ua = getUA()) {
  return /firefox\//i.test(ua);
}
function _isSafari(userAgent = getUA()) {
  const ua = userAgent.toLowerCase();
  return ua.includes("safari/") && !ua.includes("chrome/") && !ua.includes("crios/") && !ua.includes("android");
}
function _isChromeIOS(ua = getUA()) {
  return /crios\//i.test(ua);
}
function _isIEMobile(ua = getUA()) {
  return /iemobile/i.test(ua);
}
function _isAndroid(ua = getUA()) {
  return /android/i.test(ua);
}
function _isBlackBerry(ua = getUA()) {
  return /blackberry/i.test(ua);
}
function _isWebOS(ua = getUA()) {
  return /webos/i.test(ua);
}
function _isIOS(ua = getUA()) {
  return /iphone|ipad|ipod/i.test(ua) || /macintosh/i.test(ua) && /mobile/i.test(ua);
}
function _isIOSStandalone(ua = getUA()) {
  return _isIOS(ua) && !!window.navigator?.standalone;
}
function _isIE10() {
  return isIE() && document.documentMode === 10;
}
function _isMobileBrowser(ua = getUA()) {
  return _isIOS(ua) || _isAndroid(ua) || _isWebOS(ua) || _isBlackBerry(ua) || /windows phone/i.test(ua) || _isIEMobile(ua);
}
function _getClientVersion(clientPlatform, frameworks = []) {
  let reportedPlatform;
  switch (clientPlatform) {
    case "Browser":
      reportedPlatform = _getBrowserName(getUA());
      break;
    case "Worker":
      reportedPlatform = `${_getBrowserName(getUA())}-${clientPlatform}`;
      break;
    default:
      reportedPlatform = clientPlatform;
  }
  const reportedFrameworks = frameworks.length ? frameworks.join(",") : "FirebaseCore-web";
  return `${reportedPlatform}/${"JsCore"}/${SDK_VERSION}/${reportedFrameworks}`;
}
var AuthMiddlewareQueue = class {
  constructor(auth) {
    this.auth = auth;
    this.queue = [];
  }
  pushCallback(callback, onAbort) {
    const wrappedCallback = (user) => new Promise((resolve, reject) => {
      try {
        const result = callback(user);
        resolve(result);
      } catch (e) {
        reject(e);
      }
    });
    wrappedCallback.onAbort = onAbort;
    this.queue.push(wrappedCallback);
    const index = this.queue.length - 1;
    return () => {
      this.queue[index] = () => Promise.resolve();
    };
  }
  async runMiddleware(nextUser) {
    if (this.auth.currentUser === nextUser) {
      return;
    }
    const onAbortStack = [];
    try {
      for (const beforeStateCallback of this.queue) {
        await beforeStateCallback(nextUser);
        if (beforeStateCallback.onAbort) {
          onAbortStack.push(beforeStateCallback.onAbort);
        }
      }
    } catch (e) {
      onAbortStack.reverse();
      for (const onAbort of onAbortStack) {
        try {
          onAbort();
        } catch (_) {
        }
      }
      throw this.auth._errorFactory.create("login-blocked", {
        originalMessage: e?.message
      });
    }
  }
};
async function _getPasswordPolicy(auth, request = {}) {
  return _performApiRequest(auth, "GET", "/v2/passwordPolicy", _addTidIfNecessary(auth, request));
}
var MINIMUM_MIN_PASSWORD_LENGTH = 6;
var PasswordPolicyImpl = class {
  constructor(response) {
    const responseOptions = response.customStrengthOptions;
    this.customStrengthOptions = {};
    this.customStrengthOptions.minPasswordLength = responseOptions.minPasswordLength ?? MINIMUM_MIN_PASSWORD_LENGTH;
    if (responseOptions.maxPasswordLength) {
      this.customStrengthOptions.maxPasswordLength = responseOptions.maxPasswordLength;
    }
    if (responseOptions.containsLowercaseCharacter !== void 0) {
      this.customStrengthOptions.containsLowercaseLetter = responseOptions.containsLowercaseCharacter;
    }
    if (responseOptions.containsUppercaseCharacter !== void 0) {
      this.customStrengthOptions.containsUppercaseLetter = responseOptions.containsUppercaseCharacter;
    }
    if (responseOptions.containsNumericCharacter !== void 0) {
      this.customStrengthOptions.containsNumericCharacter = responseOptions.containsNumericCharacter;
    }
    if (responseOptions.containsNonAlphanumericCharacter !== void 0) {
      this.customStrengthOptions.containsNonAlphanumericCharacter = responseOptions.containsNonAlphanumericCharacter;
    }
    this.enforcementState = response.enforcementState;
    if (this.enforcementState === "ENFORCEMENT_STATE_UNSPECIFIED") {
      this.enforcementState = "OFF";
    }
    this.allowedNonAlphanumericCharacters = response.allowedNonAlphanumericCharacters?.join("") ?? "";
    this.forceUpgradeOnSignin = response.forceUpgradeOnSignin ?? false;
    this.schemaVersion = response.schemaVersion;
  }
  validatePassword(password) {
    const status = {
      isValid: true,
      passwordPolicy: this
    };
    this.validatePasswordLengthOptions(password, status);
    this.validatePasswordCharacterOptions(password, status);
    status.isValid && (status.isValid = status.meetsMinPasswordLength ?? true);
    status.isValid && (status.isValid = status.meetsMaxPasswordLength ?? true);
    status.isValid && (status.isValid = status.containsLowercaseLetter ?? true);
    status.isValid && (status.isValid = status.containsUppercaseLetter ?? true);
    status.isValid && (status.isValid = status.containsNumericCharacter ?? true);
    status.isValid && (status.isValid = status.containsNonAlphanumericCharacter ?? true);
    return status;
  }
  /**
   * Validates that the password meets the length options for the policy.
   *
   * @param password Password to validate.
   * @param status Validation status.
   */
  validatePasswordLengthOptions(password, status) {
    const minPasswordLength = this.customStrengthOptions.minPasswordLength;
    const maxPasswordLength = this.customStrengthOptions.maxPasswordLength;
    if (minPasswordLength) {
      status.meetsMinPasswordLength = password.length >= minPasswordLength;
    }
    if (maxPasswordLength) {
      status.meetsMaxPasswordLength = password.length <= maxPasswordLength;
    }
  }
  /**
   * Validates that the password meets the character options for the policy.
   *
   * @param password Password to validate.
   * @param status Validation status.
   */
  validatePasswordCharacterOptions(password, status) {
    this.updatePasswordCharacterOptionsStatuses(
      status,
      /* containsLowercaseCharacter= */
      false,
      /* containsUppercaseCharacter= */
      false,
      /* containsNumericCharacter= */
      false,
      /* containsNonAlphanumericCharacter= */
      false
    );
    let passwordChar;
    for (let i = 0; i < password.length; i++) {
      passwordChar = password.charAt(i);
      this.updatePasswordCharacterOptionsStatuses(
        status,
        /* containsLowercaseCharacter= */
        passwordChar >= "a" && passwordChar <= "z",
        /* containsUppercaseCharacter= */
        passwordChar >= "A" && passwordChar <= "Z",
        /* containsNumericCharacter= */
        passwordChar >= "0" && passwordChar <= "9",
        /* containsNonAlphanumericCharacter= */
        this.allowedNonAlphanumericCharacters.includes(passwordChar)
      );
    }
  }
  /**
   * Updates the running validation status with the statuses for the character options.
   * Expected to be called each time a character is processed to update each option status
   * based on the current character.
   *
   * @param status Validation status.
   * @param containsLowercaseCharacter Whether the character is a lowercase letter.
   * @param containsUppercaseCharacter Whether the character is an uppercase letter.
   * @param containsNumericCharacter Whether the character is a numeric character.
   * @param containsNonAlphanumericCharacter Whether the character is a non-alphanumeric character.
   */
  updatePasswordCharacterOptionsStatuses(status, containsLowercaseCharacter, containsUppercaseCharacter, containsNumericCharacter, containsNonAlphanumericCharacter) {
    if (this.customStrengthOptions.containsLowercaseLetter) {
      status.containsLowercaseLetter || (status.containsLowercaseLetter = containsLowercaseCharacter);
    }
    if (this.customStrengthOptions.containsUppercaseLetter) {
      status.containsUppercaseLetter || (status.containsUppercaseLetter = containsUppercaseCharacter);
    }
    if (this.customStrengthOptions.containsNumericCharacter) {
      status.containsNumericCharacter || (status.containsNumericCharacter = containsNumericCharacter);
    }
    if (this.customStrengthOptions.containsNonAlphanumericCharacter) {
      status.containsNonAlphanumericCharacter || (status.containsNonAlphanumericCharacter = containsNonAlphanumericCharacter);
    }
  }
};
var AuthImpl = class {
  constructor(app, heartbeatServiceProvider, appCheckServiceProvider, config) {
    this.app = app;
    this.heartbeatServiceProvider = heartbeatServiceProvider;
    this.appCheckServiceProvider = appCheckServiceProvider;
    this.config = config;
    this.currentUser = null;
    this.emulatorConfig = null;
    this.operations = Promise.resolve();
    this.authStateSubscription = new Subscription(this);
    this.idTokenSubscription = new Subscription(this);
    this.beforeStateQueue = new AuthMiddlewareQueue(this);
    this.redirectUser = null;
    this.isProactiveRefreshEnabled = false;
    this.EXPECTED_PASSWORD_POLICY_SCHEMA_VERSION = 1;
    this._canInitEmulator = true;
    this._isInitialized = false;
    this._deleted = false;
    this._initializationPromise = null;
    this._popupRedirectResolver = null;
    this._errorFactory = _DEFAULT_AUTH_ERROR_FACTORY;
    this._agentRecaptchaConfig = null;
    this._tenantRecaptchaConfigs = {};
    this._projectPasswordPolicy = null;
    this._tenantPasswordPolicies = {};
    this._resolvePersistenceManagerAvailable = void 0;
    this.lastNotifiedUid = void 0;
    this.languageCode = null;
    this.tenantId = null;
    this.settings = { appVerificationDisabledForTesting: false };
    this.frameworks = [];
    this.name = app.name;
    this.clientVersion = config.sdkClientVersion;
    this._persistenceManagerAvailable = new Promise((resolve) => this._resolvePersistenceManagerAvailable = resolve);
  }
  _initializeWithPersistence(persistenceHierarchy, popupRedirectResolver) {
    if (popupRedirectResolver) {
      this._popupRedirectResolver = _getInstance(popupRedirectResolver);
    }
    this._initializationPromise = this.queue(async () => {
      if (this._deleted) {
        return;
      }
      this.persistenceManager = await PersistenceUserManager.create(this, persistenceHierarchy);
      this._resolvePersistenceManagerAvailable?.();
      if (this._deleted) {
        return;
      }
      if (this._popupRedirectResolver?._shouldInitProactively) {
        try {
          await this._popupRedirectResolver._initialize(this);
        } catch (e) {
        }
      }
      await this.initializeCurrentUser(popupRedirectResolver);
      this.lastNotifiedUid = this.currentUser?.uid || null;
      if (this._deleted) {
        return;
      }
      this._isInitialized = true;
    });
    return this._initializationPromise;
  }
  /**
   * If the persistence is changed in another window, the user manager will let us know
   */
  async _onStorageEvent() {
    if (this._deleted) {
      return;
    }
    const user = await this.assertedPersistence.getCurrentUser();
    if (!this.currentUser && !user) {
      return;
    }
    if (this.currentUser && user && this.currentUser.uid === user.uid) {
      this._currentUser._assign(user);
      await this.currentUser.getIdToken();
      return;
    }
    await this._updateCurrentUser(
      user,
      /* skipBeforeStateCallbacks */
      true
    );
  }
  async initializeCurrentUserFromIdToken(idToken) {
    try {
      const response = await getAccountInfo(this, { idToken });
      const user = await UserImpl._fromGetAccountInfoResponse(this, response, idToken);
      await this.directlySetCurrentUser(user);
    } catch (err) {
      console.warn("FirebaseServerApp could not login user with provided authIdToken: ", err);
      await this.directlySetCurrentUser(null);
    }
  }
  async initializeCurrentUser(popupRedirectResolver) {
    if (_isFirebaseServerApp(this.app)) {
      const idToken = this.app.settings.authIdToken;
      if (idToken) {
        return new Promise((resolve) => {
          setTimeout(() => this.initializeCurrentUserFromIdToken(idToken).then(resolve, resolve));
        });
      } else {
        return this.directlySetCurrentUser(null);
      }
    }
    const previouslyStoredUser = await this.assertedPersistence.getCurrentUser();
    let futureCurrentUser = previouslyStoredUser;
    let needsTocheckMiddleware = false;
    if (popupRedirectResolver && this.config.authDomain) {
      await this.getOrInitRedirectPersistenceManager();
      const redirectUserEventId = this.redirectUser?._redirectEventId;
      const storedUserEventId = futureCurrentUser?._redirectEventId;
      const result = await this.tryRedirectSignIn(popupRedirectResolver);
      if ((!redirectUserEventId || redirectUserEventId === storedUserEventId) && result?.user) {
        futureCurrentUser = result.user;
        needsTocheckMiddleware = true;
      }
    }
    if (!futureCurrentUser) {
      return this.directlySetCurrentUser(null);
    }
    if (!futureCurrentUser._redirectEventId) {
      if (needsTocheckMiddleware) {
        try {
          await this.beforeStateQueue.runMiddleware(futureCurrentUser);
        } catch (e) {
          futureCurrentUser = previouslyStoredUser;
          this._popupRedirectResolver._overrideRedirectResult(this, () => Promise.reject(e));
        }
      }
      if (futureCurrentUser) {
        return this.reloadAndSetCurrentUserOrClear(futureCurrentUser);
      } else {
        return this.directlySetCurrentUser(null);
      }
    }
    _assert(
      this._popupRedirectResolver,
      this,
      "argument-error"
      /* AuthErrorCode.ARGUMENT_ERROR */
    );
    await this.getOrInitRedirectPersistenceManager();
    if (this.redirectUser && this.redirectUser._redirectEventId === futureCurrentUser._redirectEventId) {
      return this.directlySetCurrentUser(futureCurrentUser);
    }
    return this.reloadAndSetCurrentUserOrClear(futureCurrentUser);
  }
  async tryRedirectSignIn(redirectResolver) {
    let result = null;
    try {
      result = await this._popupRedirectResolver._completeRedirectFn(this, redirectResolver, true);
    } catch (e) {
      await this._setRedirectUser(null);
    }
    return result;
  }
  async reloadAndSetCurrentUserOrClear(user) {
    try {
      await _reloadWithoutSaving(user);
    } catch (e) {
      if (e?.code !== `auth/${"network-request-failed"}`) {
        return this.directlySetCurrentUser(null);
      }
    }
    return this.directlySetCurrentUser(user);
  }
  useDeviceLanguage() {
    this.languageCode = _getUserLanguage();
  }
  async _delete() {
    this._deleted = true;
  }
  async updateCurrentUser(userExtern) {
    if (_isFirebaseServerApp(this.app)) {
      return Promise.reject(_serverAppCurrentUserOperationNotSupportedError(this));
    }
    const user = userExtern ? getModularInstance(userExtern) : null;
    if (user) {
      _assert(
        user.auth.config.apiKey === this.config.apiKey,
        this,
        "invalid-user-token"
        /* AuthErrorCode.INVALID_AUTH */
      );
    }
    return this._updateCurrentUser(user && user._clone(this));
  }
  async _updateCurrentUser(user, skipBeforeStateCallbacks = false) {
    if (this._deleted) {
      return;
    }
    if (user) {
      _assert(
        this.tenantId === user.tenantId,
        this,
        "tenant-id-mismatch"
        /* AuthErrorCode.TENANT_ID_MISMATCH */
      );
    }
    if (!skipBeforeStateCallbacks) {
      await this.beforeStateQueue.runMiddleware(user);
    }
    return this.queue(async () => {
      await this.directlySetCurrentUser(user);
      this.notifyAuthListeners();
    });
  }
  async signOut() {
    if (_isFirebaseServerApp(this.app)) {
      return Promise.reject(_serverAppCurrentUserOperationNotSupportedError(this));
    }
    await this.beforeStateQueue.runMiddleware(null);
    if (this.redirectPersistenceManager || this._popupRedirectResolver) {
      await this._setRedirectUser(null);
    }
    return this._updateCurrentUser(
      null,
      /* skipBeforeStateCallbacks */
      true
    );
  }
  setPersistence(persistence) {
    if (_isFirebaseServerApp(this.app)) {
      return Promise.reject(_serverAppCurrentUserOperationNotSupportedError(this));
    }
    return this.queue(async () => {
      await this.assertedPersistence.setPersistence(_getInstance(persistence));
    });
  }
  _getRecaptchaConfig() {
    if (this.tenantId == null) {
      return this._agentRecaptchaConfig;
    } else {
      return this._tenantRecaptchaConfigs[this.tenantId];
    }
  }
  async validatePassword(password) {
    if (!this._getPasswordPolicyInternal()) {
      await this._updatePasswordPolicy();
    }
    const passwordPolicy = this._getPasswordPolicyInternal();
    if (passwordPolicy.schemaVersion !== this.EXPECTED_PASSWORD_POLICY_SCHEMA_VERSION) {
      return Promise.reject(this._errorFactory.create("unsupported-password-policy-schema-version", {}));
    }
    return passwordPolicy.validatePassword(password);
  }
  _getPasswordPolicyInternal() {
    if (this.tenantId === null) {
      return this._projectPasswordPolicy;
    } else {
      return this._tenantPasswordPolicies[this.tenantId];
    }
  }
  async _updatePasswordPolicy() {
    const response = await _getPasswordPolicy(this);
    const passwordPolicy = new PasswordPolicyImpl(response);
    if (this.tenantId === null) {
      this._projectPasswordPolicy = passwordPolicy;
    } else {
      this._tenantPasswordPolicies[this.tenantId] = passwordPolicy;
    }
  }
  _getPersistenceType() {
    return this.assertedPersistence.persistence.type;
  }
  _getPersistence() {
    return this.assertedPersistence.persistence;
  }
  _updateErrorMap(errorMap) {
    this._errorFactory = new ErrorFactory("auth", "Firebase", errorMap());
  }
  onAuthStateChanged(nextOrObserver, error, completed) {
    return this.registerStateListener(this.authStateSubscription, nextOrObserver, error, completed);
  }
  beforeAuthStateChanged(callback, onAbort) {
    return this.beforeStateQueue.pushCallback(callback, onAbort);
  }
  onIdTokenChanged(nextOrObserver, error, completed) {
    return this.registerStateListener(this.idTokenSubscription, nextOrObserver, error, completed);
  }
  authStateReady() {
    return new Promise((resolve, reject) => {
      if (this.currentUser) {
        resolve();
      } else {
        const unsubscribe = this.onAuthStateChanged(() => {
          unsubscribe();
          resolve();
        }, reject);
      }
    });
  }
  /**
   * Revokes the given access token. Currently only supports Apple OAuth access tokens.
   */
  async revokeAccessToken(token) {
    if (this.currentUser) {
      const idToken = await this.currentUser.getIdToken();
      const request = {
        providerId: "apple.com",
        tokenType: "ACCESS_TOKEN",
        token,
        idToken
      };
      if (this.tenantId != null) {
        request.tenantId = this.tenantId;
      }
      await revokeToken(this, request);
    }
  }
  toJSON() {
    return {
      apiKey: this.config.apiKey,
      authDomain: this.config.authDomain,
      appName: this.name,
      currentUser: this._currentUser?.toJSON()
    };
  }
  async _setRedirectUser(user, popupRedirectResolver) {
    const redirectManager = await this.getOrInitRedirectPersistenceManager(popupRedirectResolver);
    return user === null ? redirectManager.removeCurrentUser() : redirectManager.setCurrentUser(user);
  }
  async getOrInitRedirectPersistenceManager(popupRedirectResolver) {
    if (!this.redirectPersistenceManager) {
      const resolver = popupRedirectResolver && _getInstance(popupRedirectResolver) || this._popupRedirectResolver;
      _assert(
        resolver,
        this,
        "argument-error"
        /* AuthErrorCode.ARGUMENT_ERROR */
      );
      this.redirectPersistenceManager = await PersistenceUserManager.create(
        this,
        [_getInstance(resolver._redirectPersistence)],
        "redirectUser"
        /* KeyName.REDIRECT_USER */
      );
      this.redirectUser = await this.redirectPersistenceManager.getCurrentUser();
    }
    return this.redirectPersistenceManager;
  }
  async _redirectUserForId(id) {
    if (this._isInitialized) {
      await this.queue(async () => {
      });
    }
    if (this._currentUser?._redirectEventId === id) {
      return this._currentUser;
    }
    if (this.redirectUser?._redirectEventId === id) {
      return this.redirectUser;
    }
    return null;
  }
  async _persistUserIfCurrent(user) {
    if (user === this.currentUser) {
      return this.queue(async () => this.directlySetCurrentUser(user));
    }
  }
  /** Notifies listeners only if the user is current */
  _notifyListenersIfCurrent(user) {
    if (user === this.currentUser) {
      this.notifyAuthListeners();
    }
  }
  _key() {
    return `${this.config.authDomain}:${this.config.apiKey}:${this.name}`;
  }
  _startProactiveRefresh() {
    this.isProactiveRefreshEnabled = true;
    if (this.currentUser) {
      this._currentUser._startProactiveRefresh();
    }
  }
  _stopProactiveRefresh() {
    this.isProactiveRefreshEnabled = false;
    if (this.currentUser) {
      this._currentUser._stopProactiveRefresh();
    }
  }
  /** Returns the current user cast as the internal type */
  get _currentUser() {
    return this.currentUser;
  }
  notifyAuthListeners() {
    if (!this._isInitialized) {
      return;
    }
    this.idTokenSubscription.next(this.currentUser);
    const currentUid = this.currentUser?.uid ?? null;
    if (this.lastNotifiedUid !== currentUid) {
      this.lastNotifiedUid = currentUid;
      this.authStateSubscription.next(this.currentUser);
    }
  }
  registerStateListener(subscription, nextOrObserver, error, completed) {
    if (this._deleted) {
      return () => {
      };
    }
    const cb = typeof nextOrObserver === "function" ? nextOrObserver : nextOrObserver.next.bind(nextOrObserver);
    let isUnsubscribed = false;
    const promise = this._isInitialized ? Promise.resolve() : this._initializationPromise;
    _assert(
      promise,
      this,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    promise.then(() => {
      if (isUnsubscribed) {
        return;
      }
      cb(this.currentUser);
    });
    if (typeof nextOrObserver === "function") {
      const unsubscribe = subscription.addObserver(nextOrObserver, error, completed);
      return () => {
        isUnsubscribed = true;
        unsubscribe();
      };
    } else {
      const unsubscribe = subscription.addObserver(nextOrObserver);
      return () => {
        isUnsubscribed = true;
        unsubscribe();
      };
    }
  }
  /**
   * Unprotected (from race conditions) method to set the current user. This
   * should only be called from within a queued callback. This is necessary
   * because the queue shouldn't rely on another queued callback.
   */
  async directlySetCurrentUser(user) {
    if (this.currentUser && this.currentUser !== user) {
      this._currentUser._stopProactiveRefresh();
    }
    if (user && this.isProactiveRefreshEnabled) {
      user._startProactiveRefresh();
    }
    this.currentUser = user;
    if (user) {
      await this.assertedPersistence.setCurrentUser(user);
    } else {
      await this.assertedPersistence.removeCurrentUser();
    }
  }
  queue(action) {
    this.operations = this.operations.then(action, action);
    return this.operations;
  }
  get assertedPersistence() {
    _assert(
      this.persistenceManager,
      this,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    return this.persistenceManager;
  }
  _logFramework(framework) {
    if (!framework || this.frameworks.includes(framework)) {
      return;
    }
    this.frameworks.push(framework);
    this.frameworks.sort();
    this.clientVersion = _getClientVersion(this.config.clientPlatform, this._getFrameworks());
  }
  _getFrameworks() {
    return this.frameworks;
  }
  async _getAdditionalHeaders() {
    const headers = {
      [
        "X-Client-Version"
        /* HttpHeader.X_CLIENT_VERSION */
      ]: this.clientVersion
    };
    if (this.app.options.appId) {
      headers[
        "X-Firebase-gmpid"
        /* HttpHeader.X_FIREBASE_GMPID */
      ] = this.app.options.appId;
    }
    const heartbeatsHeader = await this.heartbeatServiceProvider.getImmediate({
      optional: true
    })?.getHeartbeatsHeader();
    if (heartbeatsHeader) {
      headers[
        "X-Firebase-Client"
        /* HttpHeader.X_FIREBASE_CLIENT */
      ] = heartbeatsHeader;
    }
    const appCheckToken = await this._getAppCheckToken();
    if (appCheckToken) {
      headers[
        "X-Firebase-AppCheck"
        /* HttpHeader.X_FIREBASE_APP_CHECK */
      ] = appCheckToken;
    }
    return headers;
  }
  async _getAppCheckToken() {
    if (_isFirebaseServerApp(this.app) && this.app.settings.appCheckToken) {
      return this.app.settings.appCheckToken;
    }
    const appCheckTokenResult = await this.appCheckServiceProvider.getImmediate({ optional: true })?.getToken();
    if (appCheckTokenResult?.error) {
      _logWarn(`Error while retrieving App Check token: ${appCheckTokenResult.error}`);
    }
    return appCheckTokenResult?.token;
  }
};
function _castAuth(auth) {
  return getModularInstance(auth);
}
var Subscription = class {
  constructor(auth) {
    this.auth = auth;
    this.observer = null;
    this.addObserver = createSubscribe((observer) => this.observer = observer);
  }
  get next() {
    _assert(
      this.observer,
      this.auth,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    return this.observer.next.bind(this.observer);
  }
};
var externalJSProvider = {
  async loadJS() {
    throw new Error("Unable to load external scripts");
  },
  recaptchaV2Script: "",
  recaptchaEnterpriseScript: "",
  gapiScript: ""
};
function _setExternalJSProvider(p2) {
  externalJSProvider = p2;
}
function _loadJS(url) {
  return externalJSProvider.loadJS(url);
}
function _recaptchaEnterpriseScriptUrl() {
  return externalJSProvider.recaptchaEnterpriseScript;
}
function _gapiScriptUrl() {
  return externalJSProvider.gapiScript;
}
function _generateCallbackName(prefix) {
  return `__${prefix}${Math.floor(Math.random() * 1e6)}`;
}
var MockGreCAPTCHATopLevel = class {
  constructor() {
    this.enterprise = new MockGreCAPTCHA();
  }
  ready(callback) {
    callback();
  }
  execute(_siteKey, _options) {
    return Promise.resolve("token");
  }
  render(_container, _parameters) {
    return "";
  }
};
var MockGreCAPTCHA = class {
  ready(callback) {
    callback();
  }
  execute(_siteKey, _options) {
    return Promise.resolve("token");
  }
  render(_container, _parameters) {
    return "";
  }
};
var RECAPTCHA_ENTERPRISE_VERIFIER_TYPE = "recaptcha-enterprise";
var FAKE_TOKEN = "NO_RECAPTCHA";
var RecaptchaEnterpriseVerifier = class {
  /**
   *
   * @param authExtern - The corresponding Firebase {@link Auth} instance.
   *
   */
  constructor(authExtern) {
    this.type = RECAPTCHA_ENTERPRISE_VERIFIER_TYPE;
    this.auth = _castAuth(authExtern);
  }
  /**
   * Executes the verification process.
   *
   * @returns A Promise for a token that can be used to assert the validity of a request.
   */
  async verify(action = "verify", forceRefresh = false) {
    async function retrieveSiteKey(auth) {
      if (!forceRefresh) {
        if (auth.tenantId == null && auth._agentRecaptchaConfig != null) {
          return auth._agentRecaptchaConfig.siteKey;
        }
        if (auth.tenantId != null && auth._tenantRecaptchaConfigs[auth.tenantId] !== void 0) {
          return auth._tenantRecaptchaConfigs[auth.tenantId].siteKey;
        }
      }
      return new Promise(async (resolve, reject) => {
        getRecaptchaConfig(auth, {
          clientType: "CLIENT_TYPE_WEB",
          version: "RECAPTCHA_ENTERPRISE"
          /* RecaptchaVersion.ENTERPRISE */
        }).then((response) => {
          if (response.recaptchaKey === void 0) {
            reject(new Error("recaptcha Enterprise site key undefined"));
          } else {
            const config = new RecaptchaConfig(response);
            if (auth.tenantId == null) {
              auth._agentRecaptchaConfig = config;
            } else {
              auth._tenantRecaptchaConfigs[auth.tenantId] = config;
            }
            return resolve(config.siteKey);
          }
        }).catch((error) => {
          reject(error);
        });
      });
    }
    function retrieveRecaptchaToken(siteKey, resolve, reject) {
      const grecaptcha = window.grecaptcha;
      if (isEnterprise(grecaptcha)) {
        grecaptcha.enterprise.ready(() => {
          grecaptcha.enterprise.execute(siteKey, { action }).then((token) => {
            resolve(token);
          }).catch(() => {
            resolve(FAKE_TOKEN);
          });
        });
      } else {
        reject(Error("No reCAPTCHA enterprise script loaded."));
      }
    }
    if (this.auth.settings.appVerificationDisabledForTesting) {
      const mockRecaptcha = new MockGreCAPTCHATopLevel();
      return mockRecaptcha.execute("siteKey", { action: "verify" });
    }
    return new Promise((resolve, reject) => {
      retrieveSiteKey(this.auth).then((siteKey) => {
        if (!forceRefresh && isEnterprise(window.grecaptcha)) {
          retrieveRecaptchaToken(siteKey, resolve, reject);
        } else {
          if (typeof window === "undefined") {
            reject(new Error("RecaptchaVerifier is only supported in browser"));
            return;
          }
          let url = _recaptchaEnterpriseScriptUrl();
          if (url.length !== 0) {
            url += siteKey;
          }
          _loadJS(url).then(() => {
            retrieveRecaptchaToken(siteKey, resolve, reject);
          }).catch((error) => {
            reject(error);
          });
        }
      }).catch((error) => {
        reject(error);
      });
    });
  }
};
async function injectRecaptchaFields(auth, request, action, isCaptchaResp = false, isFakeToken = false) {
  const verifier = new RecaptchaEnterpriseVerifier(auth);
  let captchaResponse;
  if (isFakeToken) {
    captchaResponse = FAKE_TOKEN;
  } else {
    try {
      captchaResponse = await verifier.verify(action);
    } catch (error) {
      captchaResponse = await verifier.verify(action, true);
    }
  }
  const newRequest = { ...request };
  if (action === "mfaSmsEnrollment" || action === "mfaSmsSignIn") {
    if ("phoneEnrollmentInfo" in newRequest) {
      const phoneNumber = newRequest.phoneEnrollmentInfo.phoneNumber;
      const recaptchaToken = newRequest.phoneEnrollmentInfo.recaptchaToken;
      Object.assign(newRequest, {
        "phoneEnrollmentInfo": {
          phoneNumber,
          recaptchaToken,
          captchaResponse,
          "clientType": "CLIENT_TYPE_WEB",
          "recaptchaVersion": "RECAPTCHA_ENTERPRISE"
          /* RecaptchaVersion.ENTERPRISE */
        }
      });
    } else if ("phoneSignInInfo" in newRequest) {
      const recaptchaToken = newRequest.phoneSignInInfo.recaptchaToken;
      Object.assign(newRequest, {
        "phoneSignInInfo": {
          recaptchaToken,
          captchaResponse,
          "clientType": "CLIENT_TYPE_WEB",
          "recaptchaVersion": "RECAPTCHA_ENTERPRISE"
          /* RecaptchaVersion.ENTERPRISE */
        }
      });
    }
    return newRequest;
  }
  if (!isCaptchaResp) {
    Object.assign(newRequest, { captchaResponse });
  } else {
    Object.assign(newRequest, { "captchaResp": captchaResponse });
  }
  Object.assign(newRequest, {
    "clientType": "CLIENT_TYPE_WEB"
    /* RecaptchaClientType.WEB */
  });
  Object.assign(newRequest, {
    "recaptchaVersion": "RECAPTCHA_ENTERPRISE"
    /* RecaptchaVersion.ENTERPRISE */
  });
  return newRequest;
}
async function handleRecaptchaFlow(authInstance, request, actionName, actionMethod, recaptchaAuthProvider) {
  if (recaptchaAuthProvider === "EMAIL_PASSWORD_PROVIDER") {
    if (authInstance._getRecaptchaConfig()?.isProviderEnabled(
      "EMAIL_PASSWORD_PROVIDER"
      /* RecaptchaAuthProvider.EMAIL_PASSWORD_PROVIDER */
    )) {
      const requestWithRecaptcha = await injectRecaptchaFields(
        authInstance,
        request,
        actionName,
        actionName === "getOobCode"
        /* RecaptchaActionName.GET_OOB_CODE */
      );
      return actionMethod(authInstance, requestWithRecaptcha);
    } else {
      return actionMethod(authInstance, request).catch(async (error) => {
        if (error.code === `auth/${"missing-recaptcha-token"}`) {
          console.log(`${actionName} is protected by reCAPTCHA Enterprise for this project. Automatically triggering the reCAPTCHA flow and restarting the flow.`);
          const requestWithRecaptcha = await injectRecaptchaFields(
            authInstance,
            request,
            actionName,
            actionName === "getOobCode"
            /* RecaptchaActionName.GET_OOB_CODE */
          );
          return actionMethod(authInstance, requestWithRecaptcha);
        } else {
          return Promise.reject(error);
        }
      });
    }
  } else if (recaptchaAuthProvider === "PHONE_PROVIDER") {
    if (authInstance._getRecaptchaConfig()?.isProviderEnabled(
      "PHONE_PROVIDER"
      /* RecaptchaAuthProvider.PHONE_PROVIDER */
    )) {
      const requestWithRecaptcha = await injectRecaptchaFields(authInstance, request, actionName);
      return actionMethod(authInstance, requestWithRecaptcha).catch(async (error) => {
        if (authInstance._getRecaptchaConfig()?.getProviderEnforcementState(
          "PHONE_PROVIDER"
          /* RecaptchaAuthProvider.PHONE_PROVIDER */
        ) === "AUDIT") {
          if (error.code === `auth/${"missing-recaptcha-token"}` || error.code === `auth/${"invalid-app-credential"}`) {
            console.log(`Failed to verify with reCAPTCHA Enterprise. Automatically triggering the reCAPTCHA v2 flow to complete the ${actionName} flow.`);
            const requestWithRecaptchaFields = await injectRecaptchaFields(
              authInstance,
              request,
              actionName,
              false,
              // isCaptchaResp
              true
              // isFakeToken
            );
            return actionMethod(authInstance, requestWithRecaptchaFields);
          }
        }
        return Promise.reject(error);
      });
    } else {
      const requestWithRecaptchaFields = await injectRecaptchaFields(
        authInstance,
        request,
        actionName,
        false,
        // isCaptchaResp
        true
        // isFakeToken
      );
      return actionMethod(authInstance, requestWithRecaptchaFields);
    }
  } else {
    return Promise.reject(recaptchaAuthProvider + " provider is not supported.");
  }
}
async function _initializeRecaptchaConfig(auth) {
  const authInternal = _castAuth(auth);
  const response = await getRecaptchaConfig(authInternal, {
    clientType: "CLIENT_TYPE_WEB",
    version: "RECAPTCHA_ENTERPRISE"
    /* RecaptchaVersion.ENTERPRISE */
  });
  const config = new RecaptchaConfig(response);
  if (authInternal.tenantId == null) {
    authInternal._agentRecaptchaConfig = config;
  } else {
    authInternal._tenantRecaptchaConfigs[authInternal.tenantId] = config;
  }
  if (config.isAnyProviderEnabled()) {
    const verifier = new RecaptchaEnterpriseVerifier(authInternal);
    void verifier.verify();
  }
}
function initializeAuth(app, deps) {
  const provider = _getProvider(app, "auth");
  if (provider.isInitialized()) {
    const auth2 = provider.getImmediate();
    const initialOptions = provider.getOptions();
    if (deepEqual(initialOptions, deps ?? {})) {
      return auth2;
    } else {
      _fail(
        auth2,
        "already-initialized"
        /* AuthErrorCode.ALREADY_INITIALIZED */
      );
    }
  }
  const auth = provider.initialize({ options: deps });
  return auth;
}
function _initializeAuthInstance(auth, deps) {
  const persistence = deps?.persistence || [];
  const hierarchy = (Array.isArray(persistence) ? persistence : [persistence]).map(_getInstance);
  if (deps?.errorMap) {
    auth._updateErrorMap(deps.errorMap);
  }
  auth._initializeWithPersistence(hierarchy, deps?.popupRedirectResolver);
}
function connectAuthEmulator(auth, url, options) {
  const authInternal = _castAuth(auth);
  _assert(
    /^https?:\/\//.test(url),
    authInternal,
    "invalid-emulator-scheme"
    /* AuthErrorCode.INVALID_EMULATOR_SCHEME */
  );
  const disableWarnings = !!options?.disableWarnings;
  const protocol = extractProtocol(url);
  const { host, port } = extractHostAndPort(url);
  const portStr = port === null ? "" : `:${port}`;
  const emulator = { url: `${protocol}//${host}${portStr}/` };
  const emulatorConfig = Object.freeze({
    host,
    port,
    protocol: protocol.replace(":", ""),
    options: Object.freeze({ disableWarnings })
  });
  if (!authInternal._canInitEmulator) {
    _assert(
      authInternal.config.emulator && authInternal.emulatorConfig,
      authInternal,
      "emulator-config-failed"
      /* AuthErrorCode.EMULATOR_CONFIG_FAILED */
    );
    _assert(
      deepEqual(emulator, authInternal.config.emulator) && deepEqual(emulatorConfig, authInternal.emulatorConfig),
      authInternal,
      "emulator-config-failed"
      /* AuthErrorCode.EMULATOR_CONFIG_FAILED */
    );
    return;
  }
  authInternal.config.emulator = emulator;
  authInternal.emulatorConfig = emulatorConfig;
  authInternal.settings.appVerificationDisabledForTesting = true;
  if (isCloudWorkstation(host)) {
    void pingServer(`${protocol}//${host}${portStr}`);
    updateEmulatorBanner("Auth", true);
  } else if (!disableWarnings) {
    emitEmulatorWarning();
  }
}
function extractProtocol(url) {
  const protocolEnd = url.indexOf(":");
  return protocolEnd < 0 ? "" : url.substr(0, protocolEnd + 1);
}
function extractHostAndPort(url) {
  const protocol = extractProtocol(url);
  const authority = /(\/\/)?([^?#/]+)/.exec(url.substr(protocol.length));
  if (!authority) {
    return { host: "", port: null };
  }
  const hostAndPort = authority[2].split("@").pop() || "";
  const bracketedIPv6 = /^(\[[^\]]+\])(:|$)/.exec(hostAndPort);
  if (bracketedIPv6) {
    const host = bracketedIPv6[1];
    return { host, port: parsePort(hostAndPort.substr(host.length + 1)) };
  } else {
    const [host, port] = hostAndPort.split(":");
    return { host, port: parsePort(port) };
  }
}
function parsePort(portStr) {
  if (!portStr) {
    return null;
  }
  const port = Number(portStr);
  if (isNaN(port)) {
    return null;
  }
  return port;
}
function emitEmulatorWarning() {
  function attachBanner() {
    const el = document.createElement("p");
    const sty = el.style;
    el.innerText = "Running in emulator mode. Do not use with production credentials.";
    sty.position = "fixed";
    sty.width = "100%";
    sty.backgroundColor = "#ffffff";
    sty.border = ".1em solid #000000";
    sty.color = "#b50000";
    sty.bottom = "0px";
    sty.left = "0px";
    sty.margin = "0px";
    sty.zIndex = "10000";
    sty.textAlign = "center";
    el.classList.add("firebase-emulator-warning");
    document.body.appendChild(el);
  }
  if (typeof console !== "undefined" && typeof console.info === "function") {
    console.info("WARNING: You are using the Auth Emulator, which is intended for local testing only.  Do not use with production credentials.");
  }
  if (typeof window !== "undefined" && typeof document !== "undefined") {
    if (document.readyState === "loading") {
      window.addEventListener("DOMContentLoaded", attachBanner);
    } else {
      attachBanner();
    }
  }
}
var AuthCredential = class {
  /** @internal */
  constructor(providerId, signInMethod) {
    this.providerId = providerId;
    this.signInMethod = signInMethod;
  }
  /**
   * Returns a JSON-serializable representation of this object.
   *
   * @returns a JSON-serializable representation of this object.
   */
  toJSON() {
    return debugFail("not implemented");
  }
  /** @internal */
  _getIdTokenResponse(_auth) {
    return debugFail("not implemented");
  }
  /** @internal */
  _linkToIdToken(_auth, _idToken) {
    return debugFail("not implemented");
  }
  /** @internal */
  _getReauthenticationResolver(_auth) {
    return debugFail("not implemented");
  }
};
async function linkEmailPassword(auth, request) {
  return _performApiRequest(auth, "POST", "/v1/accounts:signUp", request);
}
async function signInWithPassword(auth, request) {
  return _performSignInRequest(auth, "POST", "/v1/accounts:signInWithPassword", _addTidIfNecessary(auth, request));
}
async function signInWithEmailLink$1(auth, request) {
  return _performSignInRequest(auth, "POST", "/v1/accounts:signInWithEmailLink", _addTidIfNecessary(auth, request));
}
async function signInWithEmailLinkForLinking(auth, request) {
  return _performSignInRequest(auth, "POST", "/v1/accounts:signInWithEmailLink", _addTidIfNecessary(auth, request));
}
var EmailAuthCredential = class _EmailAuthCredential extends AuthCredential {
  /** @internal */
  constructor(_email, _password, signInMethod, _tenantId = null) {
    super("password", signInMethod);
    this._email = _email;
    this._password = _password;
    this._tenantId = _tenantId;
  }
  /** @internal */
  static _fromEmailAndPassword(email, password) {
    return new _EmailAuthCredential(
      email,
      password,
      "password"
      /* SignInMethod.EMAIL_PASSWORD */
    );
  }
  /** @internal */
  static _fromEmailAndCode(email, oobCode, tenantId = null) {
    return new _EmailAuthCredential(email, oobCode, "emailLink", tenantId);
  }
  /** {@inheritdoc AuthCredential.toJSON} */
  toJSON() {
    return {
      email: this._email,
      password: this._password,
      signInMethod: this.signInMethod,
      tenantId: this._tenantId
    };
  }
  /**
   * Static method to deserialize a JSON representation of an object into an {@link  AuthCredential}.
   *
   * @param json - Either `object` or the stringified representation of the object. When string is
   * provided, `JSON.parse` would be called first.
   *
   * @returns If the JSON input does not represent an {@link AuthCredential}, null is returned.
   */
  static fromJSON(json) {
    const obj = typeof json === "string" ? JSON.parse(json) : json;
    if (obj?.email && obj?.password) {
      if (obj.signInMethod === "password") {
        return this._fromEmailAndPassword(obj.email, obj.password);
      } else if (obj.signInMethod === "emailLink") {
        return this._fromEmailAndCode(obj.email, obj.password, obj.tenantId);
      }
    }
    return null;
  }
  /** @internal */
  async _getIdTokenResponse(auth) {
    switch (this.signInMethod) {
      case "password":
        const request = {
          returnSecureToken: true,
          email: this._email,
          password: this._password,
          clientType: "CLIENT_TYPE_WEB"
          /* RecaptchaClientType.WEB */
        };
        return handleRecaptchaFlow(
          auth,
          request,
          "signInWithPassword",
          signInWithPassword,
          "EMAIL_PASSWORD_PROVIDER"
          /* RecaptchaAuthProvider.EMAIL_PASSWORD_PROVIDER */
        );
      case "emailLink":
        return signInWithEmailLink$1(auth, {
          email: this._email,
          oobCode: this._password
        });
      default:
        _fail(
          auth,
          "internal-error"
          /* AuthErrorCode.INTERNAL_ERROR */
        );
    }
  }
  /** @internal */
  async _linkToIdToken(auth, idToken) {
    switch (this.signInMethod) {
      case "password":
        const request = {
          idToken,
          returnSecureToken: true,
          email: this._email,
          password: this._password,
          clientType: "CLIENT_TYPE_WEB"
          /* RecaptchaClientType.WEB */
        };
        return handleRecaptchaFlow(
          auth,
          request,
          "signUpPassword",
          linkEmailPassword,
          "EMAIL_PASSWORD_PROVIDER"
          /* RecaptchaAuthProvider.EMAIL_PASSWORD_PROVIDER */
        );
      case "emailLink":
        return signInWithEmailLinkForLinking(auth, {
          idToken,
          email: this._email,
          oobCode: this._password
        });
      default:
        _fail(
          auth,
          "internal-error"
          /* AuthErrorCode.INTERNAL_ERROR */
        );
    }
  }
  /** @internal */
  _getReauthenticationResolver(auth) {
    return this._getIdTokenResponse(auth);
  }
};
async function signInWithIdp(auth, request) {
  return _performSignInRequest(auth, "POST", "/v1/accounts:signInWithIdp", _addTidIfNecessary(auth, request));
}
var IDP_REQUEST_URI$1 = "http://localhost";
var OAuthCredential = class _OAuthCredential extends AuthCredential {
  constructor() {
    super(...arguments);
    this.pendingToken = null;
  }
  /** @internal */
  static _fromParams(params) {
    const cred = new _OAuthCredential(params.providerId, params.signInMethod);
    if (params.idToken || params.accessToken) {
      if (params.idToken) {
        cred.idToken = params.idToken;
      }
      if (params.accessToken) {
        cred.accessToken = params.accessToken;
      }
      if (params.nonce && !params.pendingToken) {
        cred.nonce = params.nonce;
      }
      if (params.pendingToken) {
        cred.pendingToken = params.pendingToken;
      }
    } else if (params.oauthToken && params.oauthTokenSecret) {
      cred.accessToken = params.oauthToken;
      cred.secret = params.oauthTokenSecret;
    } else {
      _fail(
        "argument-error"
        /* AuthErrorCode.ARGUMENT_ERROR */
      );
    }
    return cred;
  }
  /** {@inheritdoc AuthCredential.toJSON}  */
  toJSON() {
    return {
      idToken: this.idToken,
      accessToken: this.accessToken,
      secret: this.secret,
      nonce: this.nonce,
      pendingToken: this.pendingToken,
      providerId: this.providerId,
      signInMethod: this.signInMethod
    };
  }
  /**
   * Static method to deserialize a JSON representation of an object into an
   * {@link  AuthCredential}.
   *
   * @param json - Input can be either Object or the stringified representation of the object.
   * When string is provided, JSON.parse would be called first.
   *
   * @returns If the JSON input does not represent an {@link  AuthCredential}, null is returned.
   */
  static fromJSON(json) {
    const obj = typeof json === "string" ? JSON.parse(json) : json;
    const { providerId, signInMethod, ...rest } = obj;
    if (!providerId || !signInMethod) {
      return null;
    }
    const cred = new _OAuthCredential(providerId, signInMethod);
    cred.idToken = rest.idToken || void 0;
    cred.accessToken = rest.accessToken || void 0;
    cred.secret = rest.secret;
    cred.nonce = rest.nonce;
    cred.pendingToken = rest.pendingToken || null;
    return cred;
  }
  /** @internal */
  _getIdTokenResponse(auth) {
    const request = this.buildRequest();
    return signInWithIdp(auth, request);
  }
  /** @internal */
  _linkToIdToken(auth, idToken) {
    const request = this.buildRequest();
    request.idToken = idToken;
    return signInWithIdp(auth, request);
  }
  /** @internal */
  _getReauthenticationResolver(auth) {
    const request = this.buildRequest();
    request.autoCreate = false;
    return signInWithIdp(auth, request);
  }
  buildRequest() {
    const request = {
      requestUri: IDP_REQUEST_URI$1,
      returnSecureToken: true
    };
    if (this.pendingToken) {
      request.pendingToken = this.pendingToken;
    } else {
      const postBody = {};
      if (this.idToken) {
        postBody["id_token"] = this.idToken;
      }
      if (this.accessToken) {
        postBody["access_token"] = this.accessToken;
      }
      if (this.secret) {
        postBody["oauth_token_secret"] = this.secret;
      }
      postBody["providerId"] = this.providerId;
      if (this.nonce && !this.pendingToken) {
        postBody["nonce"] = this.nonce;
      }
      request.postBody = querystring(postBody);
    }
    return request;
  }
};
async function sendPhoneVerificationCode(auth, request) {
  return _performApiRequest(auth, "POST", "/v1/accounts:sendVerificationCode", _addTidIfNecessary(auth, request));
}
async function signInWithPhoneNumber$1(auth, request) {
  return _performSignInRequest(auth, "POST", "/v1/accounts:signInWithPhoneNumber", _addTidIfNecessary(auth, request));
}
async function linkWithPhoneNumber$1(auth, request) {
  const response = await _performSignInRequest(auth, "POST", "/v1/accounts:signInWithPhoneNumber", _addTidIfNecessary(auth, request));
  if (response.temporaryProof) {
    throw _makeTaggedError(auth, "account-exists-with-different-credential", response);
  }
  return response;
}
var VERIFY_PHONE_NUMBER_FOR_EXISTING_ERROR_MAP_ = {
  [
    "USER_NOT_FOUND"
    /* ServerError.USER_NOT_FOUND */
  ]: "user-not-found"
  /* AuthErrorCode.USER_DELETED */
};
async function verifyPhoneNumberForExisting(auth, request) {
  const apiRequest = {
    ...request,
    operation: "REAUTH"
  };
  return _performSignInRequest(auth, "POST", "/v1/accounts:signInWithPhoneNumber", _addTidIfNecessary(auth, apiRequest), VERIFY_PHONE_NUMBER_FOR_EXISTING_ERROR_MAP_);
}
var PhoneAuthCredential = class _PhoneAuthCredential extends AuthCredential {
  constructor(params) {
    super(
      "phone",
      "phone"
      /* SignInMethod.PHONE */
    );
    this.params = params;
  }
  /** @internal */
  static _fromVerification(verificationId, verificationCode) {
    return new _PhoneAuthCredential({ verificationId, verificationCode });
  }
  /** @internal */
  static _fromTokenResponse(phoneNumber, temporaryProof) {
    return new _PhoneAuthCredential({ phoneNumber, temporaryProof });
  }
  /** @internal */
  _getIdTokenResponse(auth) {
    return signInWithPhoneNumber$1(auth, this._makeVerificationRequest());
  }
  /** @internal */
  _linkToIdToken(auth, idToken) {
    return linkWithPhoneNumber$1(auth, {
      idToken,
      ...this._makeVerificationRequest()
    });
  }
  /** @internal */
  _getReauthenticationResolver(auth) {
    return verifyPhoneNumberForExisting(auth, this._makeVerificationRequest());
  }
  /** @internal */
  _makeVerificationRequest() {
    const { temporaryProof, phoneNumber, verificationId, verificationCode } = this.params;
    if (temporaryProof && phoneNumber) {
      return { temporaryProof, phoneNumber };
    }
    return {
      sessionInfo: verificationId,
      code: verificationCode
    };
  }
  /** {@inheritdoc AuthCredential.toJSON} */
  toJSON() {
    const obj = {
      providerId: this.providerId
    };
    if (this.params.phoneNumber) {
      obj.phoneNumber = this.params.phoneNumber;
    }
    if (this.params.temporaryProof) {
      obj.temporaryProof = this.params.temporaryProof;
    }
    if (this.params.verificationCode) {
      obj.verificationCode = this.params.verificationCode;
    }
    if (this.params.verificationId) {
      obj.verificationId = this.params.verificationId;
    }
    return obj;
  }
  /** Generates a phone credential based on a plain object or a JSON string. */
  static fromJSON(json) {
    if (typeof json === "string") {
      json = JSON.parse(json);
    }
    const { verificationId, verificationCode, phoneNumber, temporaryProof } = json;
    if (!verificationCode && !verificationId && !phoneNumber && !temporaryProof) {
      return null;
    }
    return new _PhoneAuthCredential({
      verificationId,
      verificationCode,
      phoneNumber,
      temporaryProof
    });
  }
};
function parseMode(mode) {
  switch (mode) {
    case "recoverEmail":
      return "RECOVER_EMAIL";
    case "resetPassword":
      return "PASSWORD_RESET";
    case "signIn":
      return "EMAIL_SIGNIN";
    case "verifyEmail":
      return "VERIFY_EMAIL";
    case "verifyAndChangeEmail":
      return "VERIFY_AND_CHANGE_EMAIL";
    case "revertSecondFactorAddition":
      return "REVERT_SECOND_FACTOR_ADDITION";
    default:
      return null;
  }
}
function parseDeepLink(url) {
  const link = querystringDecode(extractQuerystring(url))["link"];
  const doubleDeepLink = link ? querystringDecode(extractQuerystring(link))["deep_link_id"] : null;
  const iOSDeepLink = querystringDecode(extractQuerystring(url))["deep_link_id"];
  const iOSDoubleDeepLink = iOSDeepLink ? querystringDecode(extractQuerystring(iOSDeepLink))["link"] : null;
  return iOSDoubleDeepLink || iOSDeepLink || doubleDeepLink || link || url;
}
var ActionCodeURL = class _ActionCodeURL {
  /**
   * @param actionLink - The link from which to extract the URL.
   * @returns The {@link ActionCodeURL} object, or null if the link is invalid.
   *
   * @internal
   */
  constructor(actionLink) {
    const searchParams = querystringDecode(extractQuerystring(actionLink));
    const apiKey = searchParams[
      "apiKey"
      /* QueryField.API_KEY */
    ] ?? null;
    const code = searchParams[
      "oobCode"
      /* QueryField.CODE */
    ] ?? null;
    const operation = parseMode(searchParams[
      "mode"
      /* QueryField.MODE */
    ] ?? null);
    _assert(
      apiKey && code && operation,
      "argument-error"
      /* AuthErrorCode.ARGUMENT_ERROR */
    );
    this.apiKey = apiKey;
    this.operation = operation;
    this.code = code;
    this.continueUrl = searchParams[
      "continueUrl"
      /* QueryField.CONTINUE_URL */
    ] ?? null;
    this.languageCode = searchParams[
      "lang"
      /* QueryField.LANGUAGE_CODE */
    ] ?? null;
    this.tenantId = searchParams[
      "tenantId"
      /* QueryField.TENANT_ID */
    ] ?? null;
  }
  /**
   * Parses the email action link string and returns an {@link ActionCodeURL} if the link is valid,
   * otherwise returns null.
   *
   * @param link  - The email action link string.
   * @returns The {@link ActionCodeURL} object, or null if the link is invalid.
   *
   * @public
   */
  static parseLink(link) {
    const actionLink = parseDeepLink(link);
    try {
      return new _ActionCodeURL(actionLink);
    } catch {
      return null;
    }
  }
};
var EmailAuthProvider = class _EmailAuthProvider {
  constructor() {
    this.providerId = _EmailAuthProvider.PROVIDER_ID;
  }
  /**
   * Initialize an {@link AuthCredential} using an email and password.
   *
   * @example
   * ```javascript
   * const authCredential = EmailAuthProvider.credential(email, password);
   * const userCredential = await signInWithCredential(auth, authCredential);
   * ```
   *
   * @example
   * ```javascript
   * const userCredential = await signInWithEmailAndPassword(auth, email, password);
   * ```
   *
   * @param email - Email address.
   * @param password - User account password.
   * @returns The auth provider credential.
   */
  static credential(email, password) {
    return EmailAuthCredential._fromEmailAndPassword(email, password);
  }
  /**
   * Initialize an {@link AuthCredential} using an email and an email link after a sign in with
   * email link operation.
   *
   * @example
   * ```javascript
   * const authCredential = EmailAuthProvider.credentialWithLink(auth, email, emailLink);
   * const userCredential = await signInWithCredential(auth, authCredential);
   * ```
   *
   * @example
   * ```javascript
   * await sendSignInLinkToEmail(auth, email);
   * // Obtain emailLink from user.
   * const userCredential = await signInWithEmailLink(auth, email, emailLink);
   * ```
   *
   * @param auth - The {@link Auth} instance used to verify the link.
   * @param email - Email address.
   * @param emailLink - Sign-in email link.
   * @returns - The auth provider credential.
   */
  static credentialWithLink(email, emailLink) {
    const actionCodeUrl = ActionCodeURL.parseLink(emailLink);
    _assert(
      actionCodeUrl,
      "argument-error"
      /* AuthErrorCode.ARGUMENT_ERROR */
    );
    return EmailAuthCredential._fromEmailAndCode(email, actionCodeUrl.code, actionCodeUrl.tenantId);
  }
};
EmailAuthProvider.PROVIDER_ID = "password";
EmailAuthProvider.EMAIL_PASSWORD_SIGN_IN_METHOD = "password";
EmailAuthProvider.EMAIL_LINK_SIGN_IN_METHOD = "emailLink";
var FederatedAuthProvider = class {
  /**
   * Constructor for generic OAuth providers.
   *
   * @param providerId - Provider for which credentials should be generated.
   */
  constructor(providerId) {
    this.providerId = providerId;
    this.defaultLanguageCode = null;
    this.customParameters = {};
  }
  /**
   * Set the language gode.
   *
   * @param languageCode - language code
   */
  setDefaultLanguage(languageCode) {
    this.defaultLanguageCode = languageCode;
  }
  /**
   * Sets the OAuth custom parameters to pass in an OAuth request for popup and redirect sign-in
   * operations.
   *
   * @remarks
   * For a detailed list, check the reserved required OAuth 2.0 parameters such as `client_id`,
   * `redirect_uri`, `scope`, `response_type`, and `state` are not allowed and will be ignored.
   *
   * @param customOAuthParameters - The custom OAuth parameters to pass in the OAuth request.
   */
  setCustomParameters(customOAuthParameters) {
    this.customParameters = customOAuthParameters;
    return this;
  }
  /**
   * Retrieve the current list of {@link CustomParameters}.
   */
  getCustomParameters() {
    return this.customParameters;
  }
};
var BaseOAuthProvider = class extends FederatedAuthProvider {
  constructor() {
    super(...arguments);
    this.scopes = [];
  }
  /**
   * Add an OAuth scope to the credential.
   *
   * @param scope - Provider OAuth scope to add.
   */
  addScope(scope) {
    if (!this.scopes.includes(scope)) {
      this.scopes.push(scope);
    }
    return this;
  }
  /**
   * Retrieve the current list of OAuth scopes.
   */
  getScopes() {
    return [...this.scopes];
  }
};
var FacebookAuthProvider = class _FacebookAuthProvider extends BaseOAuthProvider {
  constructor() {
    super(
      "facebook.com"
      /* ProviderId.FACEBOOK */
    );
  }
  /**
   * Creates a credential for Facebook.
   *
   * @example
   * ```javascript
   * // `event` from the Facebook auth.authResponseChange callback.
   * const credential = FacebookAuthProvider.credential(event.authResponse.accessToken);
   * const result = await signInWithCredential(credential);
   * ```
   *
   * @param accessToken - Facebook access token.
   */
  static credential(accessToken) {
    return OAuthCredential._fromParams({
      providerId: _FacebookAuthProvider.PROVIDER_ID,
      signInMethod: _FacebookAuthProvider.FACEBOOK_SIGN_IN_METHOD,
      accessToken
    });
  }
  /**
   * Used to extract the underlying {@link OAuthCredential} from a {@link UserCredential}.
   *
   * @param userCredential - The user credential.
   */
  static credentialFromResult(userCredential) {
    return _FacebookAuthProvider.credentialFromTaggedObject(userCredential);
  }
  /**
   * Used to extract the underlying {@link OAuthCredential} from a {@link AuthError} which was
   * thrown during a sign-in, link, or reauthenticate operation.
   *
   * @param userCredential - The user credential.
   */
  static credentialFromError(error) {
    return _FacebookAuthProvider.credentialFromTaggedObject(error.customData || {});
  }
  static credentialFromTaggedObject({ _tokenResponse: tokenResponse }) {
    if (!tokenResponse || !("oauthAccessToken" in tokenResponse)) {
      return null;
    }
    if (!tokenResponse.oauthAccessToken) {
      return null;
    }
    try {
      return _FacebookAuthProvider.credential(tokenResponse.oauthAccessToken);
    } catch {
      return null;
    }
  }
};
FacebookAuthProvider.FACEBOOK_SIGN_IN_METHOD = "facebook.com";
FacebookAuthProvider.PROVIDER_ID = "facebook.com";
var GoogleAuthProvider = class _GoogleAuthProvider extends BaseOAuthProvider {
  constructor() {
    super(
      "google.com"
      /* ProviderId.GOOGLE */
    );
    this.addScope("profile");
  }
  /**
   * Creates a credential for Google. At least one of ID token and access token is required.
   *
   * @example
   * ```javascript
   * // \`googleUser\` from the onsuccess Google Sign In callback.
   * const credential = GoogleAuthProvider.credential(googleUser.getAuthResponse().id_token);
   * const result = await signInWithCredential(credential);
   * ```
   *
   * @param idToken - Google ID token.
   * @param accessToken - Google access token.
   */
  static credential(idToken, accessToken) {
    return OAuthCredential._fromParams({
      providerId: _GoogleAuthProvider.PROVIDER_ID,
      signInMethod: _GoogleAuthProvider.GOOGLE_SIGN_IN_METHOD,
      idToken,
      accessToken
    });
  }
  /**
   * Used to extract the underlying {@link OAuthCredential} from a {@link UserCredential}.
   *
   * @param userCredential - The user credential.
   */
  static credentialFromResult(userCredential) {
    return _GoogleAuthProvider.credentialFromTaggedObject(userCredential);
  }
  /**
   * Used to extract the underlying {@link OAuthCredential} from a {@link AuthError} which was
   * thrown during a sign-in, link, or reauthenticate operation.
   *
   * @param userCredential - The user credential.
   */
  static credentialFromError(error) {
    return _GoogleAuthProvider.credentialFromTaggedObject(error.customData || {});
  }
  static credentialFromTaggedObject({ _tokenResponse: tokenResponse }) {
    if (!tokenResponse) {
      return null;
    }
    const { oauthIdToken, oauthAccessToken } = tokenResponse;
    if (!oauthIdToken && !oauthAccessToken) {
      return null;
    }
    try {
      return _GoogleAuthProvider.credential(oauthIdToken, oauthAccessToken);
    } catch {
      return null;
    }
  }
};
GoogleAuthProvider.GOOGLE_SIGN_IN_METHOD = "google.com";
GoogleAuthProvider.PROVIDER_ID = "google.com";
var GithubAuthProvider = class _GithubAuthProvider extends BaseOAuthProvider {
  constructor() {
    super(
      "github.com"
      /* ProviderId.GITHUB */
    );
  }
  /**
   * Creates a credential for GitHub.
   *
   * @param accessToken - GitHub access token.
   */
  static credential(accessToken) {
    return OAuthCredential._fromParams({
      providerId: _GithubAuthProvider.PROVIDER_ID,
      signInMethod: _GithubAuthProvider.GITHUB_SIGN_IN_METHOD,
      accessToken
    });
  }
  /**
   * Used to extract the underlying {@link OAuthCredential} from a {@link UserCredential}.
   *
   * @param userCredential - The user credential.
   */
  static credentialFromResult(userCredential) {
    return _GithubAuthProvider.credentialFromTaggedObject(userCredential);
  }
  /**
   * Used to extract the underlying {@link OAuthCredential} from a {@link AuthError} which was
   * thrown during a sign-in, link, or reauthenticate operation.
   *
   * @param userCredential - The user credential.
   */
  static credentialFromError(error) {
    return _GithubAuthProvider.credentialFromTaggedObject(error.customData || {});
  }
  static credentialFromTaggedObject({ _tokenResponse: tokenResponse }) {
    if (!tokenResponse || !("oauthAccessToken" in tokenResponse)) {
      return null;
    }
    if (!tokenResponse.oauthAccessToken) {
      return null;
    }
    try {
      return _GithubAuthProvider.credential(tokenResponse.oauthAccessToken);
    } catch {
      return null;
    }
  }
};
GithubAuthProvider.GITHUB_SIGN_IN_METHOD = "github.com";
GithubAuthProvider.PROVIDER_ID = "github.com";
var TwitterAuthProvider = class _TwitterAuthProvider extends BaseOAuthProvider {
  constructor() {
    super(
      "twitter.com"
      /* ProviderId.TWITTER */
    );
  }
  /**
   * Creates a credential for Twitter.
   *
   * @param token - Twitter access token.
   * @param secret - Twitter secret.
   */
  static credential(token, secret) {
    return OAuthCredential._fromParams({
      providerId: _TwitterAuthProvider.PROVIDER_ID,
      signInMethod: _TwitterAuthProvider.TWITTER_SIGN_IN_METHOD,
      oauthToken: token,
      oauthTokenSecret: secret
    });
  }
  /**
   * Used to extract the underlying {@link OAuthCredential} from a {@link UserCredential}.
   *
   * @param userCredential - The user credential.
   */
  static credentialFromResult(userCredential) {
    return _TwitterAuthProvider.credentialFromTaggedObject(userCredential);
  }
  /**
   * Used to extract the underlying {@link OAuthCredential} from a {@link AuthError} which was
   * thrown during a sign-in, link, or reauthenticate operation.
   *
   * @param userCredential - The user credential.
   */
  static credentialFromError(error) {
    return _TwitterAuthProvider.credentialFromTaggedObject(error.customData || {});
  }
  static credentialFromTaggedObject({ _tokenResponse: tokenResponse }) {
    if (!tokenResponse) {
      return null;
    }
    const { oauthAccessToken, oauthTokenSecret } = tokenResponse;
    if (!oauthAccessToken || !oauthTokenSecret) {
      return null;
    }
    try {
      return _TwitterAuthProvider.credential(oauthAccessToken, oauthTokenSecret);
    } catch {
      return null;
    }
  }
};
TwitterAuthProvider.TWITTER_SIGN_IN_METHOD = "twitter.com";
TwitterAuthProvider.PROVIDER_ID = "twitter.com";
var UserCredentialImpl = class _UserCredentialImpl {
  constructor(params) {
    this.user = params.user;
    this.providerId = params.providerId;
    this._tokenResponse = params._tokenResponse;
    this.operationType = params.operationType;
  }
  static async _fromIdTokenResponse(auth, operationType, idTokenResponse, isAnonymous = false) {
    const user = await UserImpl._fromIdTokenResponse(auth, idTokenResponse, isAnonymous);
    const providerId = providerIdForResponse(idTokenResponse);
    const userCred = new _UserCredentialImpl({
      user,
      providerId,
      _tokenResponse: idTokenResponse,
      operationType
    });
    return userCred;
  }
  static async _forOperation(user, operationType, response) {
    await user._updateTokensIfNecessary(
      response,
      /* reload */
      true
    );
    const providerId = providerIdForResponse(response);
    return new _UserCredentialImpl({
      user,
      providerId,
      _tokenResponse: response,
      operationType
    });
  }
};
function providerIdForResponse(response) {
  if (response.providerId) {
    return response.providerId;
  }
  if ("phoneNumber" in response) {
    return "phone";
  }
  return null;
}
var MultiFactorError = class _MultiFactorError extends FirebaseError {
  constructor(auth, error, operationType, user) {
    super(error.code, error.message);
    this.operationType = operationType;
    this.user = user;
    Object.setPrototypeOf(this, _MultiFactorError.prototype);
    this.customData = {
      appName: auth.name,
      tenantId: auth.tenantId ?? void 0,
      _serverResponse: error.customData._serverResponse,
      operationType
    };
  }
  static _fromErrorAndOperation(auth, error, operationType, user) {
    return new _MultiFactorError(auth, error, operationType, user);
  }
};
function _processCredentialSavingMfaContextIfNecessary(auth, operationType, credential, user) {
  const idTokenProvider = operationType === "reauthenticate" ? credential._getReauthenticationResolver(auth) : credential._getIdTokenResponse(auth);
  return idTokenProvider.catch((error) => {
    if (error.code === `auth/${"multi-factor-auth-required"}`) {
      throw MultiFactorError._fromErrorAndOperation(auth, error, operationType, user);
    }
    throw error;
  });
}
async function _link$1(user, credential, bypassAuthState = false) {
  const response = await _logoutIfInvalidated(user, credential._linkToIdToken(user.auth, await user.getIdToken()), bypassAuthState);
  return UserCredentialImpl._forOperation(user, "link", response);
}
async function _reauthenticate(user, credential, bypassAuthState = false) {
  const { auth } = user;
  if (_isFirebaseServerApp(auth.app)) {
    return Promise.reject(_serverAppCurrentUserOperationNotSupportedError(auth));
  }
  const operationType = "reauthenticate";
  try {
    const response = await _logoutIfInvalidated(user, _processCredentialSavingMfaContextIfNecessary(auth, operationType, credential, user), bypassAuthState);
    _assert(
      response.idToken,
      auth,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    const parsed = _parseToken(response.idToken);
    _assert(
      parsed,
      auth,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    const { sub: localId } = parsed;
    _assert(
      user.uid === localId,
      auth,
      "user-mismatch"
      /* AuthErrorCode.USER_MISMATCH */
    );
    return UserCredentialImpl._forOperation(user, operationType, response);
  } catch (e) {
    if (e?.code === `auth/${"user-not-found"}`) {
      _fail(
        auth,
        "user-mismatch"
        /* AuthErrorCode.USER_MISMATCH */
      );
    }
    throw e;
  }
}
async function _signInWithCredential(auth, credential, bypassAuthState = false) {
  if (_isFirebaseServerApp(auth.app)) {
    return Promise.reject(_serverAppCurrentUserOperationNotSupportedError(auth));
  }
  const operationType = "signIn";
  const response = await _processCredentialSavingMfaContextIfNecessary(auth, operationType, credential);
  const userCredential = await UserCredentialImpl._fromIdTokenResponse(auth, operationType, response);
  if (!bypassAuthState) {
    await auth._updateCurrentUser(userCredential.user);
  }
  return userCredential;
}
function setPersistence(auth, persistence) {
  return getModularInstance(auth).setPersistence(persistence);
}
function onIdTokenChanged(auth, nextOrObserver, error, completed) {
  return getModularInstance(auth).onIdTokenChanged(nextOrObserver, error, completed);
}
function beforeAuthStateChanged(auth, callback, onAbort) {
  return getModularInstance(auth).beforeAuthStateChanged(callback, onAbort);
}
function onAuthStateChanged(auth, nextOrObserver, error, completed) {
  return getModularInstance(auth).onAuthStateChanged(nextOrObserver, error, completed);
}
function signOut(auth) {
  return getModularInstance(auth).signOut();
}
function startEnrollPhoneMfa(auth, request) {
  return _performApiRequest(auth, "POST", "/v2/accounts/mfaEnrollment:start", _addTidIfNecessary(auth, request));
}
function finalizeEnrollPhoneMfa(auth, request) {
  return _performApiRequest(auth, "POST", "/v2/accounts/mfaEnrollment:finalize", _addTidIfNecessary(auth, request));
}
function startEnrollTotpMfa(auth, request) {
  return _performApiRequest(auth, "POST", "/v2/accounts/mfaEnrollment:start", _addTidIfNecessary(auth, request));
}
function finalizeEnrollTotpMfa(auth, request) {
  return _performApiRequest(auth, "POST", "/v2/accounts/mfaEnrollment:finalize", _addTidIfNecessary(auth, request));
}
var STORAGE_AVAILABLE_KEY = "__sak";
var BrowserPersistenceClass = class {
  constructor(storageRetriever, type) {
    this.storageRetriever = storageRetriever;
    this.type = type;
  }
  _isAvailable() {
    try {
      if (!this.storage) {
        return Promise.resolve(false);
      }
      this.storage.setItem(STORAGE_AVAILABLE_KEY, "1");
      this.storage.removeItem(STORAGE_AVAILABLE_KEY);
      return Promise.resolve(true);
    } catch {
      return Promise.resolve(false);
    }
  }
  _set(key, value) {
    this.storage.setItem(key, JSON.stringify(value));
    return Promise.resolve();
  }
  _get(key) {
    const json = this.storage.getItem(key);
    return Promise.resolve(json ? JSON.parse(json) : null);
  }
  _remove(key) {
    this.storage.removeItem(key);
    return Promise.resolve();
  }
  get storage() {
    return this.storageRetriever();
  }
};
var _POLLING_INTERVAL_MS$1 = 1e3;
var IE10_LOCAL_STORAGE_SYNC_DELAY = 10;
var BrowserLocalPersistence = class extends BrowserPersistenceClass {
  constructor() {
    super(
      () => window.localStorage,
      "LOCAL"
      /* PersistenceType.LOCAL */
    );
    this.boundEventHandler = (event, poll) => this.onStorageEvent(event, poll);
    this.listeners = {};
    this.localCache = {};
    this.pollTimer = null;
    this.fallbackToPolling = _isMobileBrowser();
    this._shouldAllowMigration = true;
  }
  forAllChangedKeys(cb) {
    for (const key of Object.keys(this.listeners)) {
      const newValue = this.storage.getItem(key);
      const oldValue = this.localCache[key];
      if (newValue !== oldValue) {
        cb(key, oldValue, newValue);
      }
    }
  }
  onStorageEvent(event, poll = false) {
    if (!event.key) {
      this.forAllChangedKeys((key2, _oldValue, newValue) => {
        this.notifyListeners(key2, newValue);
      });
      return;
    }
    const key = event.key;
    if (poll) {
      this.detachListener();
    } else {
      this.stopPolling();
    }
    const triggerListeners = () => {
      const storedValue2 = this.storage.getItem(key);
      if (!poll && this.localCache[key] === storedValue2) {
        return;
      }
      this.notifyListeners(key, storedValue2);
    };
    const storedValue = this.storage.getItem(key);
    if (_isIE10() && storedValue !== event.newValue && event.newValue !== event.oldValue) {
      setTimeout(triggerListeners, IE10_LOCAL_STORAGE_SYNC_DELAY);
    } else {
      triggerListeners();
    }
  }
  notifyListeners(key, value) {
    this.localCache[key] = value;
    const listeners = this.listeners[key];
    if (listeners) {
      for (const listener of Array.from(listeners)) {
        listener(value ? JSON.parse(value) : value);
      }
    }
  }
  startPolling() {
    this.stopPolling();
    this.pollTimer = setInterval(() => {
      this.forAllChangedKeys((key, oldValue, newValue) => {
        this.onStorageEvent(
          new StorageEvent("storage", {
            key,
            oldValue,
            newValue
          }),
          /* poll */
          true
        );
      });
    }, _POLLING_INTERVAL_MS$1);
  }
  stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }
  attachListener() {
    window.addEventListener("storage", this.boundEventHandler);
  }
  detachListener() {
    window.removeEventListener("storage", this.boundEventHandler);
  }
  _addListener(key, listener) {
    if (Object.keys(this.listeners).length === 0) {
      if (this.fallbackToPolling) {
        this.startPolling();
      } else {
        this.attachListener();
      }
    }
    if (!this.listeners[key]) {
      this.listeners[key] = /* @__PURE__ */ new Set();
      this.localCache[key] = this.storage.getItem(key);
    }
    this.listeners[key].add(listener);
  }
  _removeListener(key, listener) {
    if (this.listeners[key]) {
      this.listeners[key].delete(listener);
      if (this.listeners[key].size === 0) {
        delete this.listeners[key];
      }
    }
    if (Object.keys(this.listeners).length === 0) {
      this.detachListener();
      this.stopPolling();
    }
  }
  // Update local cache on base operations:
  async _set(key, value) {
    await super._set(key, value);
    this.localCache[key] = JSON.stringify(value);
  }
  async _get(key) {
    const value = await super._get(key);
    this.localCache[key] = JSON.stringify(value);
    return value;
  }
  async _remove(key) {
    await super._remove(key);
    delete this.localCache[key];
  }
};
BrowserLocalPersistence.type = "LOCAL";
var browserLocalPersistence = BrowserLocalPersistence;
var POLLING_INTERVAL_MS = 1e3;
function getDocumentCookie(name4) {
  const escapedName = name4.replace(/[\\^$.*+?()[\]{}|]/g, "\\$&");
  const matcher = RegExp(`${escapedName}=([^;]+)`);
  return document.cookie.match(matcher)?.[1] ?? null;
}
function getCookieName(key) {
  const isDevMode = window.location.protocol === "http:";
  return `${isDevMode ? "__dev_" : "__HOST-"}FIREBASE_${key.split(":")[3]}`;
}
var CookiePersistence = class {
  constructor() {
    this.type = "COOKIE";
    this.listenerUnsubscribes = /* @__PURE__ */ new Map();
  }
  // used to get the URL to the backend to proxy to
  _getFinalTarget(originalUrl) {
    if (typeof window === void 0) {
      return originalUrl;
    }
    const url = new URL(`${window.location.origin}/__cookies__`);
    url.searchParams.set("finalTarget", originalUrl);
    return url;
  }
  // To be a usable persistence method in a chain browserCookiePersistence ensures that
  // prerequisites have been met, namely that we're in a secureContext, navigator and document are
  // available and cookies are enabled. Not all UAs support these method, so fallback accordingly.
  async _isAvailable() {
    if (typeof isSecureContext === "boolean" && !isSecureContext) {
      return false;
    }
    if (typeof navigator === "undefined" || typeof document === "undefined") {
      return false;
    }
    return navigator.cookieEnabled ?? true;
  }
  // Set should be a noop as we expect middleware to handle this
  async _set(_key, _value) {
    return;
  }
  // Attempt to get the cookie from cookieStore, fallback to document.cookie
  async _get(key) {
    if (!this._isAvailable()) {
      return null;
    }
    const name4 = getCookieName(key);
    if (window.cookieStore) {
      const cookie = await window.cookieStore.get(name4);
      return cookie?.value;
    }
    return getDocumentCookie(name4);
  }
  // Log out by overriding the idToken with a sentinel value of ""
  async _remove(key) {
    if (!this._isAvailable()) {
      return;
    }
    const existingValue = await this._get(key);
    if (!existingValue) {
      return;
    }
    const name4 = getCookieName(key);
    document.cookie = `${name4}=;Max-Age=34560000;Partitioned;Secure;SameSite=Strict;Path=/;Priority=High`;
    await fetch(`/__cookies__`, { method: "DELETE" }).catch(() => void 0);
  }
  // Listen for cookie changes, both cookieStore and fallback to polling document.cookie
  _addListener(key, listener) {
    if (!this._isAvailable()) {
      return;
    }
    const name4 = getCookieName(key);
    if (window.cookieStore) {
      const cb = ((event) => {
        const changedCookie = event.changed.find((change) => change.name === name4);
        if (changedCookie) {
          listener(changedCookie.value);
        }
        const deletedCookie = event.deleted.find((change) => change.name === name4);
        if (deletedCookie) {
          listener(null);
        }
      });
      const unsubscribe2 = () => window.cookieStore.removeEventListener("change", cb);
      this.listenerUnsubscribes.set(listener, unsubscribe2);
      return window.cookieStore.addEventListener("change", cb);
    }
    let lastValue = getDocumentCookie(name4);
    const interval = setInterval(() => {
      const currentValue = getDocumentCookie(name4);
      if (currentValue !== lastValue) {
        listener(currentValue);
        lastValue = currentValue;
      }
    }, POLLING_INTERVAL_MS);
    const unsubscribe = () => clearInterval(interval);
    this.listenerUnsubscribes.set(listener, unsubscribe);
  }
  _removeListener(_key, listener) {
    const unsubscribe = this.listenerUnsubscribes.get(listener);
    if (!unsubscribe) {
      return;
    }
    unsubscribe();
    this.listenerUnsubscribes.delete(listener);
  }
};
CookiePersistence.type = "COOKIE";
var BrowserSessionPersistence = class extends BrowserPersistenceClass {
  constructor() {
    super(
      () => window.sessionStorage,
      "SESSION"
      /* PersistenceType.SESSION */
    );
  }
  _addListener(_key, _listener) {
    return;
  }
  _removeListener(_key, _listener) {
    return;
  }
};
BrowserSessionPersistence.type = "SESSION";
var browserSessionPersistence = BrowserSessionPersistence;
function _allSettled(promises) {
  return Promise.all(promises.map(async (promise) => {
    try {
      const value = await promise;
      return {
        fulfilled: true,
        value
      };
    } catch (reason) {
      return {
        fulfilled: false,
        reason
      };
    }
  }));
}
var Receiver = class _Receiver {
  constructor(eventTarget) {
    this.eventTarget = eventTarget;
    this.handlersMap = {};
    this.boundEventHandler = this.handleEvent.bind(this);
  }
  /**
   * Obtain an instance of a Receiver for a given event target, if none exists it will be created.
   *
   * @param eventTarget - An event target (such as window or self) through which the underlying
   * messages will be received.
   */
  static _getInstance(eventTarget) {
    const existingInstance = this.receivers.find((receiver) => receiver.isListeningto(eventTarget));
    if (existingInstance) {
      return existingInstance;
    }
    const newInstance = new _Receiver(eventTarget);
    this.receivers.push(newInstance);
    return newInstance;
  }
  isListeningto(eventTarget) {
    return this.eventTarget === eventTarget;
  }
  /**
   * Fans out a MessageEvent to the appropriate listeners.
   *
   * @remarks
   * Sends an {@link Status.ACK} upon receipt and a {@link Status.DONE} once all handlers have
   * finished processing.
   *
   * @param event - The MessageEvent.
   *
   */
  async handleEvent(event) {
    const messageEvent = event;
    const { eventId, eventType, data } = messageEvent.data;
    const handlers = this.handlersMap[eventType];
    if (!handlers?.size) {
      return;
    }
    messageEvent.ports[0].postMessage({
      status: "ack",
      eventId,
      eventType
    });
    const promises = Array.from(handlers).map(async (handler) => handler(messageEvent.origin, data));
    const response = await _allSettled(promises);
    messageEvent.ports[0].postMessage({
      status: "done",
      eventId,
      eventType,
      response
    });
  }
  /**
   * Subscribe an event handler for a particular event.
   *
   * @param eventType - Event name to subscribe to.
   * @param eventHandler - The event handler which should receive the events.
   *
   */
  _subscribe(eventType, eventHandler) {
    if (Object.keys(this.handlersMap).length === 0) {
      this.eventTarget.addEventListener("message", this.boundEventHandler);
    }
    if (!this.handlersMap[eventType]) {
      this.handlersMap[eventType] = /* @__PURE__ */ new Set();
    }
    this.handlersMap[eventType].add(eventHandler);
  }
  /**
   * Unsubscribe an event handler from a particular event.
   *
   * @param eventType - Event name to unsubscribe from.
   * @param eventHandler - Optional event handler, if none provided, unsubscribe all handlers on this event.
   *
   */
  _unsubscribe(eventType, eventHandler) {
    if (this.handlersMap[eventType] && eventHandler) {
      this.handlersMap[eventType].delete(eventHandler);
    }
    if (!eventHandler || this.handlersMap[eventType].size === 0) {
      delete this.handlersMap[eventType];
    }
    if (Object.keys(this.handlersMap).length === 0) {
      this.eventTarget.removeEventListener("message", this.boundEventHandler);
    }
  }
};
Receiver.receivers = [];
function _generateEventId(prefix = "", digits = 10) {
  let random = "";
  for (let i = 0; i < digits; i++) {
    random += Math.floor(Math.random() * 10);
  }
  return prefix + random;
}
var Sender = class {
  constructor(target) {
    this.target = target;
    this.handlers = /* @__PURE__ */ new Set();
  }
  /**
   * Unsubscribe the handler and remove it from our tracking Set.
   *
   * @param handler - The handler to unsubscribe.
   */
  removeMessageHandler(handler) {
    if (handler.messageChannel) {
      handler.messageChannel.port1.removeEventListener("message", handler.onMessage);
      handler.messageChannel.port1.close();
    }
    this.handlers.delete(handler);
  }
  /**
   * Send a message to the Receiver located at {@link target}.
   *
   * @remarks
   * We'll first wait a bit for an ACK , if we get one we will wait significantly longer until the
   * receiver has had a chance to fully process the event.
   *
   * @param eventType - Type of event to send.
   * @param data - The payload of the event.
   * @param timeout - Timeout for waiting on an ACK from the receiver.
   *
   * @returns An array of settled promises from all the handlers that were listening on the receiver.
   */
  async _send(eventType, data, timeout = 50) {
    const messageChannel = typeof MessageChannel !== "undefined" ? new MessageChannel() : null;
    if (!messageChannel) {
      throw new Error(
        "connection_unavailable"
        /* _MessageError.CONNECTION_UNAVAILABLE */
      );
    }
    let completionTimer;
    let handler;
    return new Promise((resolve, reject) => {
      const eventId = _generateEventId("", 20);
      messageChannel.port1.start();
      const ackTimer = setTimeout(() => {
        reject(new Error(
          "unsupported_event"
          /* _MessageError.UNSUPPORTED_EVENT */
        ));
      }, timeout);
      handler = {
        messageChannel,
        onMessage(event) {
          const messageEvent = event;
          if (messageEvent.data.eventId !== eventId) {
            return;
          }
          switch (messageEvent.data.status) {
            case "ack":
              clearTimeout(ackTimer);
              completionTimer = setTimeout(
                () => {
                  reject(new Error(
                    "timeout"
                    /* _MessageError.TIMEOUT */
                  ));
                },
                3e3
                /* _TimeoutDuration.COMPLETION */
              );
              break;
            case "done":
              clearTimeout(completionTimer);
              resolve(messageEvent.data.response);
              break;
            default:
              clearTimeout(ackTimer);
              clearTimeout(completionTimer);
              reject(new Error(
                "invalid_response"
                /* _MessageError.INVALID_RESPONSE */
              ));
              break;
          }
        }
      };
      this.handlers.add(handler);
      messageChannel.port1.addEventListener("message", handler.onMessage);
      this.target.postMessage({
        eventType,
        eventId,
        data
      }, [messageChannel.port2]);
    }).finally(() => {
      if (handler) {
        this.removeMessageHandler(handler);
      }
    });
  }
};
function _window() {
  return window;
}
function _setWindowLocation(url) {
  _window().location.href = url;
}
function _isWorker() {
  return typeof _window()["WorkerGlobalScope"] !== "undefined" && typeof _window()["importScripts"] === "function";
}
async function _getActiveServiceWorker() {
  if (!navigator?.serviceWorker) {
    return null;
  }
  try {
    const registration = await navigator.serviceWorker.ready;
    return registration.active;
  } catch {
    return null;
  }
}
function _getServiceWorkerController() {
  return navigator?.serviceWorker?.controller || null;
}
function _getWorkerGlobalScope() {
  return _isWorker() ? self : null;
}
var DB_NAME2 = "firebaseLocalStorageDb";
var DB_VERSION2 = 1;
var DB_OBJECTSTORE_NAME = "firebaseLocalStorage";
var DB_DATA_KEYPATH = "fbase_key";
var DBPromise = class {
  constructor(request) {
    this.request = request;
  }
  toPromise() {
    return new Promise((resolve, reject) => {
      this.request.addEventListener("success", () => {
        resolve(this.request.result);
      });
      this.request.addEventListener("error", () => {
        reject(this.request.error);
      });
    });
  }
};
function getObjectStore(db, isReadWrite) {
  return db.transaction([DB_OBJECTSTORE_NAME], isReadWrite ? "readwrite" : "readonly").objectStore(DB_OBJECTSTORE_NAME);
}
function _deleteDatabase() {
  const request = indexedDB.deleteDatabase(DB_NAME2);
  return new DBPromise(request).toPromise();
}
function _openDatabase() {
  const request = indexedDB.open(DB_NAME2, DB_VERSION2);
  return new Promise((resolve, reject) => {
    request.addEventListener("error", () => {
      reject(request.error);
    });
    request.addEventListener("upgradeneeded", () => {
      const db = request.result;
      try {
        db.createObjectStore(DB_OBJECTSTORE_NAME, { keyPath: DB_DATA_KEYPATH });
      } catch (e) {
        reject(e);
      }
    });
    request.addEventListener("success", async () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(DB_OBJECTSTORE_NAME)) {
        db.close();
        await _deleteDatabase();
        resolve(await _openDatabase());
      } else {
        resolve(db);
      }
    });
  });
}
async function _putObject(db, key, value) {
  const request = getObjectStore(db, true).put({
    [DB_DATA_KEYPATH]: key,
    value
  });
  return new DBPromise(request).toPromise();
}
async function getObject(db, key) {
  const request = getObjectStore(db, false).get(key);
  const data = await new DBPromise(request).toPromise();
  return data === void 0 ? null : data.value;
}
function _deleteObject(db, key) {
  const request = getObjectStore(db, true).delete(key);
  return new DBPromise(request).toPromise();
}
var _POLLING_INTERVAL_MS = 800;
var _TRANSACTION_RETRY_COUNT = 3;
var IndexedDBLocalPersistence = class {
  constructor() {
    this.type = "LOCAL";
    this._shouldAllowMigration = true;
    this.listeners = {};
    this.localCache = {};
    this.pollTimer = null;
    this.pendingWrites = 0;
    this.receiver = null;
    this.sender = null;
    this.serviceWorkerReceiverAvailable = false;
    this.activeServiceWorker = null;
    this._workerInitializationPromise = this.initializeServiceWorkerMessaging().then(() => {
    }, () => {
    });
  }
  async _openDb() {
    if (this.db) {
      return this.db;
    }
    this.db = await _openDatabase();
    return this.db;
  }
  async _withRetries(op) {
    let numAttempts = 0;
    while (true) {
      try {
        const db = await this._openDb();
        return await op(db);
      } catch (e) {
        if (numAttempts++ > _TRANSACTION_RETRY_COUNT) {
          throw e;
        }
        if (this.db) {
          this.db.close();
          this.db = void 0;
        }
      }
    }
  }
  /**
   * IndexedDB events do not propagate from the main window to the worker context.  We rely on a
   * postMessage interface to send these events to the worker ourselves.
   */
  async initializeServiceWorkerMessaging() {
    return _isWorker() ? this.initializeReceiver() : this.initializeSender();
  }
  /**
   * As the worker we should listen to events from the main window.
   */
  async initializeReceiver() {
    this.receiver = Receiver._getInstance(_getWorkerGlobalScope());
    this.receiver._subscribe("keyChanged", async (_origin, data) => {
      const keys = await this._poll();
      return {
        keyProcessed: keys.includes(data.key)
      };
    });
    this.receiver._subscribe("ping", async (_origin, _data) => {
      return [
        "keyChanged"
        /* _EventType.KEY_CHANGED */
      ];
    });
  }
  /**
   * As the main window, we should let the worker know when keys change (set and remove).
   *
   * @remarks
   * {@link https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerContainer/ready | ServiceWorkerContainer.ready}
   * may not resolve.
   */
  async initializeSender() {
    this.activeServiceWorker = await _getActiveServiceWorker();
    if (!this.activeServiceWorker) {
      return;
    }
    this.sender = new Sender(this.activeServiceWorker);
    const results = await this.sender._send(
      "ping",
      {},
      800
      /* _TimeoutDuration.LONG_ACK */
    );
    if (!results) {
      return;
    }
    if (results[0]?.fulfilled && results[0]?.value.includes(
      "keyChanged"
      /* _EventType.KEY_CHANGED */
    )) {
      this.serviceWorkerReceiverAvailable = true;
    }
  }
  /**
   * Let the worker know about a changed key, the exact key doesn't technically matter since the
   * worker will just trigger a full sync anyway.
   *
   * @remarks
   * For now, we only support one service worker per page.
   *
   * @param key - Storage key which changed.
   */
  async notifyServiceWorker(key) {
    if (!this.sender || !this.activeServiceWorker || _getServiceWorkerController() !== this.activeServiceWorker) {
      return;
    }
    try {
      await this.sender._send(
        "keyChanged",
        { key },
        // Use long timeout if receiver has previously responded to a ping from us.
        this.serviceWorkerReceiverAvailable ? 800 : 50
        /* _TimeoutDuration.ACK */
      );
    } catch {
    }
  }
  async _isAvailable() {
    try {
      if (!indexedDB) {
        return false;
      }
      const db = await _openDatabase();
      await _putObject(db, STORAGE_AVAILABLE_KEY, "1");
      await _deleteObject(db, STORAGE_AVAILABLE_KEY);
      return true;
    } catch {
    }
    return false;
  }
  async _withPendingWrite(write) {
    this.pendingWrites++;
    try {
      await write();
    } finally {
      this.pendingWrites--;
    }
  }
  async _set(key, value) {
    return this._withPendingWrite(async () => {
      await this._withRetries((db) => _putObject(db, key, value));
      this.localCache[key] = value;
      return this.notifyServiceWorker(key);
    });
  }
  async _get(key) {
    const obj = await this._withRetries((db) => getObject(db, key));
    this.localCache[key] = obj;
    return obj;
  }
  async _remove(key) {
    return this._withPendingWrite(async () => {
      await this._withRetries((db) => _deleteObject(db, key));
      delete this.localCache[key];
      return this.notifyServiceWorker(key);
    });
  }
  async _poll() {
    const result = await this._withRetries((db) => {
      const getAllRequest = getObjectStore(db, false).getAll();
      return new DBPromise(getAllRequest).toPromise();
    });
    if (!result) {
      return [];
    }
    if (this.pendingWrites !== 0) {
      return [];
    }
    const keys = [];
    const keysInResult = /* @__PURE__ */ new Set();
    if (result.length !== 0) {
      for (const { fbase_key: key, value } of result) {
        keysInResult.add(key);
        if (JSON.stringify(this.localCache[key]) !== JSON.stringify(value)) {
          this.notifyListeners(key, value);
          keys.push(key);
        }
      }
    }
    for (const localKey of Object.keys(this.localCache)) {
      if (this.localCache[localKey] && !keysInResult.has(localKey)) {
        this.notifyListeners(localKey, null);
        keys.push(localKey);
      }
    }
    return keys;
  }
  notifyListeners(key, newValue) {
    this.localCache[key] = newValue;
    const listeners = this.listeners[key];
    if (listeners) {
      for (const listener of Array.from(listeners)) {
        listener(newValue);
      }
    }
  }
  startPolling() {
    this.stopPolling();
    this.pollTimer = setInterval(async () => this._poll(), _POLLING_INTERVAL_MS);
  }
  stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }
  _addListener(key, listener) {
    if (Object.keys(this.listeners).length === 0) {
      this.startPolling();
    }
    if (!this.listeners[key]) {
      this.listeners[key] = /* @__PURE__ */ new Set();
      void this._get(key);
    }
    this.listeners[key].add(listener);
  }
  _removeListener(key, listener) {
    if (this.listeners[key]) {
      this.listeners[key].delete(listener);
      if (this.listeners[key].size === 0) {
        delete this.listeners[key];
      }
    }
    if (Object.keys(this.listeners).length === 0) {
      this.stopPolling();
    }
  }
};
IndexedDBLocalPersistence.type = "LOCAL";
var indexedDBLocalPersistence = IndexedDBLocalPersistence;
function startSignInPhoneMfa(auth, request) {
  return _performApiRequest(auth, "POST", "/v2/accounts/mfaSignIn:start", _addTidIfNecessary(auth, request));
}
function finalizeSignInPhoneMfa(auth, request) {
  return _performApiRequest(auth, "POST", "/v2/accounts/mfaSignIn:finalize", _addTidIfNecessary(auth, request));
}
function finalizeSignInTotpMfa(auth, request) {
  return _performApiRequest(auth, "POST", "/v2/accounts/mfaSignIn:finalize", _addTidIfNecessary(auth, request));
}
var _JSLOAD_CALLBACK = _generateCallbackName("rcb");
var NETWORK_TIMEOUT_DELAY = new Delay(3e4, 6e4);
var RECAPTCHA_VERIFIER_TYPE = "recaptcha";
async function _verifyPhoneNumber(auth, options, verifier) {
  if (!auth._getRecaptchaConfig()) {
    try {
      await _initializeRecaptchaConfig(auth);
    } catch (error) {
      console.log("Failed to initialize reCAPTCHA Enterprise config. Triggering the reCAPTCHA v2 verification.");
    }
  }
  try {
    let phoneInfoOptions;
    if (typeof options === "string") {
      phoneInfoOptions = {
        phoneNumber: options
      };
    } else {
      phoneInfoOptions = options;
    }
    if ("session" in phoneInfoOptions) {
      const session = phoneInfoOptions.session;
      if ("phoneNumber" in phoneInfoOptions) {
        _assert(
          session.type === "enroll",
          auth,
          "internal-error"
          /* AuthErrorCode.INTERNAL_ERROR */
        );
        const startPhoneMfaEnrollmentRequest = {
          idToken: session.credential,
          phoneEnrollmentInfo: {
            phoneNumber: phoneInfoOptions.phoneNumber,
            clientType: "CLIENT_TYPE_WEB"
            /* RecaptchaClientType.WEB */
          }
        };
        const startEnrollPhoneMfaActionCallback = async (authInstance, request) => {
          if (request.phoneEnrollmentInfo.captchaResponse === FAKE_TOKEN) {
            _assert(
              verifier?.type === RECAPTCHA_VERIFIER_TYPE,
              authInstance,
              "argument-error"
              /* AuthErrorCode.ARGUMENT_ERROR */
            );
            const requestWithRecaptchaV2 = await injectRecaptchaV2Token(authInstance, request, verifier);
            return startEnrollPhoneMfa(authInstance, requestWithRecaptchaV2);
          }
          return startEnrollPhoneMfa(authInstance, request);
        };
        const startPhoneMfaEnrollmentResponse = handleRecaptchaFlow(
          auth,
          startPhoneMfaEnrollmentRequest,
          "mfaSmsEnrollment",
          startEnrollPhoneMfaActionCallback,
          "PHONE_PROVIDER"
          /* RecaptchaAuthProvider.PHONE_PROVIDER */
        );
        const response = await startPhoneMfaEnrollmentResponse.catch((error) => {
          return Promise.reject(error);
        });
        return response.phoneSessionInfo.sessionInfo;
      } else {
        _assert(
          session.type === "signin",
          auth,
          "internal-error"
          /* AuthErrorCode.INTERNAL_ERROR */
        );
        const mfaEnrollmentId = phoneInfoOptions.multiFactorHint?.uid || phoneInfoOptions.multiFactorUid;
        _assert(
          mfaEnrollmentId,
          auth,
          "missing-multi-factor-info"
          /* AuthErrorCode.MISSING_MFA_INFO */
        );
        const startPhoneMfaSignInRequest = {
          mfaPendingCredential: session.credential,
          mfaEnrollmentId,
          phoneSignInInfo: {
            clientType: "CLIENT_TYPE_WEB"
            /* RecaptchaClientType.WEB */
          }
        };
        const startSignInPhoneMfaActionCallback = async (authInstance, request) => {
          if (request.phoneSignInInfo.captchaResponse === FAKE_TOKEN) {
            _assert(
              verifier?.type === RECAPTCHA_VERIFIER_TYPE,
              authInstance,
              "argument-error"
              /* AuthErrorCode.ARGUMENT_ERROR */
            );
            const requestWithRecaptchaV2 = await injectRecaptchaV2Token(authInstance, request, verifier);
            return startSignInPhoneMfa(authInstance, requestWithRecaptchaV2);
          }
          return startSignInPhoneMfa(authInstance, request);
        };
        const startPhoneMfaSignInResponse = handleRecaptchaFlow(
          auth,
          startPhoneMfaSignInRequest,
          "mfaSmsSignIn",
          startSignInPhoneMfaActionCallback,
          "PHONE_PROVIDER"
          /* RecaptchaAuthProvider.PHONE_PROVIDER */
        );
        const response = await startPhoneMfaSignInResponse.catch((error) => {
          return Promise.reject(error);
        });
        return response.phoneResponseInfo.sessionInfo;
      }
    } else {
      const sendPhoneVerificationCodeRequest = {
        phoneNumber: phoneInfoOptions.phoneNumber,
        clientType: "CLIENT_TYPE_WEB"
        /* RecaptchaClientType.WEB */
      };
      const sendPhoneVerificationCodeActionCallback = async (authInstance, request) => {
        if (request.captchaResponse === FAKE_TOKEN) {
          _assert(
            verifier?.type === RECAPTCHA_VERIFIER_TYPE,
            authInstance,
            "argument-error"
            /* AuthErrorCode.ARGUMENT_ERROR */
          );
          const requestWithRecaptchaV2 = await injectRecaptchaV2Token(authInstance, request, verifier);
          return sendPhoneVerificationCode(authInstance, requestWithRecaptchaV2);
        }
        return sendPhoneVerificationCode(authInstance, request);
      };
      const sendPhoneVerificationCodeResponse = handleRecaptchaFlow(
        auth,
        sendPhoneVerificationCodeRequest,
        "sendVerificationCode",
        sendPhoneVerificationCodeActionCallback,
        "PHONE_PROVIDER"
        /* RecaptchaAuthProvider.PHONE_PROVIDER */
      );
      const response = await sendPhoneVerificationCodeResponse.catch((error) => {
        return Promise.reject(error);
      });
      return response.sessionInfo;
    }
  } finally {
    verifier?._reset();
  }
}
async function injectRecaptchaV2Token(auth, request, recaptchaV2Verifier) {
  _assert(
    recaptchaV2Verifier.type === RECAPTCHA_VERIFIER_TYPE,
    auth,
    "argument-error"
    /* AuthErrorCode.ARGUMENT_ERROR */
  );
  const recaptchaV2Token = await recaptchaV2Verifier.verify();
  _assert(
    typeof recaptchaV2Token === "string",
    auth,
    "argument-error"
    /* AuthErrorCode.ARGUMENT_ERROR */
  );
  const newRequest = { ...request };
  if ("phoneEnrollmentInfo" in newRequest) {
    const phoneNumber = newRequest.phoneEnrollmentInfo.phoneNumber;
    const captchaResponse = newRequest.phoneEnrollmentInfo.captchaResponse;
    const clientType = newRequest.phoneEnrollmentInfo.clientType;
    const recaptchaVersion = newRequest.phoneEnrollmentInfo.recaptchaVersion;
    Object.assign(newRequest, {
      "phoneEnrollmentInfo": {
        phoneNumber,
        recaptchaToken: recaptchaV2Token,
        captchaResponse,
        clientType,
        recaptchaVersion
      }
    });
    return newRequest;
  } else if ("phoneSignInInfo" in newRequest) {
    const captchaResponse = newRequest.phoneSignInInfo.captchaResponse;
    const clientType = newRequest.phoneSignInInfo.clientType;
    const recaptchaVersion = newRequest.phoneSignInInfo.recaptchaVersion;
    Object.assign(newRequest, {
      "phoneSignInInfo": {
        recaptchaToken: recaptchaV2Token,
        captchaResponse,
        clientType,
        recaptchaVersion
      }
    });
    return newRequest;
  } else {
    Object.assign(newRequest, { "recaptchaToken": recaptchaV2Token });
    return newRequest;
  }
}
var PhoneAuthProvider = class _PhoneAuthProvider {
  /**
   * @param auth - The Firebase {@link Auth} instance in which sign-ins should occur.
   *
   */
  constructor(auth) {
    this.providerId = _PhoneAuthProvider.PROVIDER_ID;
    this.auth = _castAuth(auth);
  }
  /**
   *
   * Starts a phone number authentication flow by sending a verification code to the given phone
   * number.
   *
   * @example
   * ```javascript
   * const provider = new PhoneAuthProvider(auth);
   * const verificationId = await provider.verifyPhoneNumber(phoneNumber, applicationVerifier);
   * // Obtain verificationCode from the user.
   * const authCredential = PhoneAuthProvider.credential(verificationId, verificationCode);
   * const userCredential = await signInWithCredential(auth, authCredential);
   * ```
   *
   * @example
   * An alternative flow is provided using the `signInWithPhoneNumber` method.
   * ```javascript
   * const confirmationResult = signInWithPhoneNumber(auth, phoneNumber, applicationVerifier);
   * // Obtain verificationCode from the user.
   * const userCredential = confirmationResult.confirm(verificationCode);
   * ```
   *
   * @param phoneInfoOptions - The user's {@link PhoneInfoOptions}. The phone number should be in
   * E.164 format (e.g. +16505550101).
   * @param applicationVerifier - An {@link ApplicationVerifier}, which prevents
   * requests from unauthorized clients. This SDK includes an implementation
   * based on reCAPTCHA v2, {@link RecaptchaVerifier}. If you've enabled
   * reCAPTCHA Enterprise bot protection in Enforce mode, this parameter is
   * optional; in all other configurations, the parameter is required.
   *
   * @returns A Promise for a verification ID that can be passed to
   * {@link PhoneAuthProvider.credential} to identify this flow.
   */
  verifyPhoneNumber(phoneOptions, applicationVerifier) {
    return _verifyPhoneNumber(this.auth, phoneOptions, getModularInstance(applicationVerifier));
  }
  /**
   * Creates a phone auth credential, given the verification ID from
   * {@link PhoneAuthProvider.verifyPhoneNumber} and the code that was sent to the user's
   * mobile device.
   *
   * @example
   * ```javascript
   * const provider = new PhoneAuthProvider(auth);
   * const verificationId = provider.verifyPhoneNumber(phoneNumber, applicationVerifier);
   * // Obtain verificationCode from the user.
   * const authCredential = PhoneAuthProvider.credential(verificationId, verificationCode);
   * const userCredential = signInWithCredential(auth, authCredential);
   * ```
   *
   * @example
   * An alternative flow is provided using the `signInWithPhoneNumber` method.
   * ```javascript
   * const confirmationResult = await signInWithPhoneNumber(auth, phoneNumber, applicationVerifier);
   * // Obtain verificationCode from the user.
   * const userCredential = await confirmationResult.confirm(verificationCode);
   * ```
   *
   * @param verificationId - The verification ID returned from {@link PhoneAuthProvider.verifyPhoneNumber}.
   * @param verificationCode - The verification code sent to the user's mobile device.
   *
   * @returns The auth provider credential.
   */
  static credential(verificationId, verificationCode) {
    return PhoneAuthCredential._fromVerification(verificationId, verificationCode);
  }
  /**
   * Generates an {@link AuthCredential} from a {@link UserCredential}.
   * @param userCredential - The user credential.
   */
  static credentialFromResult(userCredential) {
    const credential = userCredential;
    return _PhoneAuthProvider.credentialFromTaggedObject(credential);
  }
  /**
   * Returns an {@link AuthCredential} when passed an error.
   *
   * @remarks
   *
   * This method works for errors like
   * `auth/account-exists-with-different-credentials`. This is useful for
   * recovering when attempting to set a user's phone number but the number
   * in question is already tied to another account. For example, the following
   * code tries to update the current user's phone number, and if that
   * fails, links the user with the account associated with that number:
   *
   * ```js
   * const provider = new PhoneAuthProvider(auth);
   * const verificationId = await provider.verifyPhoneNumber(number, verifier);
   * try {
   *   const code = ''; // Prompt the user for the verification code
   *   await updatePhoneNumber(
   *       auth.currentUser,
   *       PhoneAuthProvider.credential(verificationId, code));
   * } catch (e) {
   *   if ((e as FirebaseError)?.code === 'auth/account-exists-with-different-credential') {
   *     const cred = PhoneAuthProvider.credentialFromError(e);
   *     await linkWithCredential(auth.currentUser, cred);
   *   }
   * }
   *
   * // At this point, auth.currentUser.phoneNumber === number.
   * ```
   *
   * @param error - The error to generate a credential from.
   */
  static credentialFromError(error) {
    return _PhoneAuthProvider.credentialFromTaggedObject(error.customData || {});
  }
  static credentialFromTaggedObject({ _tokenResponse: tokenResponse }) {
    if (!tokenResponse) {
      return null;
    }
    const { phoneNumber, temporaryProof } = tokenResponse;
    if (phoneNumber && temporaryProof) {
      return PhoneAuthCredential._fromTokenResponse(phoneNumber, temporaryProof);
    }
    return null;
  }
};
PhoneAuthProvider.PROVIDER_ID = "phone";
PhoneAuthProvider.PHONE_SIGN_IN_METHOD = "phone";
function _withDefaultResolver(auth, resolverOverride) {
  if (resolverOverride) {
    return _getInstance(resolverOverride);
  }
  _assert(
    auth._popupRedirectResolver,
    auth,
    "argument-error"
    /* AuthErrorCode.ARGUMENT_ERROR */
  );
  return auth._popupRedirectResolver;
}
var IdpCredential = class extends AuthCredential {
  constructor(params) {
    super(
      "custom",
      "custom"
      /* ProviderId.CUSTOM */
    );
    this.params = params;
  }
  _getIdTokenResponse(auth) {
    return signInWithIdp(auth, this._buildIdpRequest());
  }
  _linkToIdToken(auth, idToken) {
    return signInWithIdp(auth, this._buildIdpRequest(idToken));
  }
  _getReauthenticationResolver(auth) {
    return signInWithIdp(auth, this._buildIdpRequest());
  }
  _buildIdpRequest(idToken) {
    const request = {
      requestUri: this.params.requestUri,
      sessionId: this.params.sessionId,
      postBody: this.params.postBody,
      tenantId: this.params.tenantId,
      pendingToken: this.params.pendingToken,
      returnSecureToken: true,
      returnIdpCredential: true
    };
    if (idToken) {
      request.idToken = idToken;
    }
    return request;
  }
};
function _signIn(params) {
  return _signInWithCredential(params.auth, new IdpCredential(params), params.bypassAuthState);
}
function _reauth(params) {
  const { auth, user } = params;
  _assert(
    user,
    auth,
    "internal-error"
    /* AuthErrorCode.INTERNAL_ERROR */
  );
  return _reauthenticate(user, new IdpCredential(params), params.bypassAuthState);
}
async function _link(params) {
  const { auth, user } = params;
  _assert(
    user,
    auth,
    "internal-error"
    /* AuthErrorCode.INTERNAL_ERROR */
  );
  return _link$1(user, new IdpCredential(params), params.bypassAuthState);
}
var AbstractPopupRedirectOperation = class {
  constructor(auth, filter, resolver, user, bypassAuthState = false) {
    this.auth = auth;
    this.resolver = resolver;
    this.user = user;
    this.bypassAuthState = bypassAuthState;
    this.pendingPromise = null;
    this.eventManager = null;
    this.filter = Array.isArray(filter) ? filter : [filter];
  }
  execute() {
    return new Promise(async (resolve, reject) => {
      this.pendingPromise = { resolve, reject };
      try {
        this.eventManager = await this.resolver._initialize(this.auth);
        await this.onExecution();
        this.eventManager.registerConsumer(this);
      } catch (e) {
        this.reject(e);
      }
    });
  }
  async onAuthEvent(event) {
    const { urlResponse, sessionId, postBody, tenantId, error, type } = event;
    if (error) {
      this.reject(error);
      return;
    }
    const params = {
      auth: this.auth,
      requestUri: urlResponse,
      sessionId,
      tenantId: tenantId || void 0,
      postBody: postBody || void 0,
      user: this.user,
      bypassAuthState: this.bypassAuthState
    };
    try {
      this.resolve(await this.getIdpTask(type)(params));
    } catch (e) {
      this.reject(e);
    }
  }
  onError(error) {
    this.reject(error);
  }
  getIdpTask(type) {
    switch (type) {
      case "signInViaPopup":
      case "signInViaRedirect":
        return _signIn;
      case "linkViaPopup":
      case "linkViaRedirect":
        return _link;
      case "reauthViaPopup":
      case "reauthViaRedirect":
        return _reauth;
      default:
        _fail(
          this.auth,
          "internal-error"
          /* AuthErrorCode.INTERNAL_ERROR */
        );
    }
  }
  resolve(cred) {
    debugAssert(this.pendingPromise, "Pending promise was never set");
    this.pendingPromise.resolve(cred);
    this.unregisterAndCleanUp();
  }
  reject(error) {
    debugAssert(this.pendingPromise, "Pending promise was never set");
    this.pendingPromise.reject(error);
    this.unregisterAndCleanUp();
  }
  unregisterAndCleanUp() {
    if (this.eventManager) {
      this.eventManager.unregisterConsumer(this);
    }
    this.pendingPromise = null;
    this.cleanUp();
  }
};
var _POLL_WINDOW_CLOSE_TIMEOUT = new Delay(2e3, 1e4);
async function signInWithPopup(auth, provider, resolver) {
  if (_isFirebaseServerApp(auth.app)) {
    return Promise.reject(_createError(
      auth,
      "operation-not-supported-in-this-environment"
      /* AuthErrorCode.OPERATION_NOT_SUPPORTED */
    ));
  }
  const authInternal = _castAuth(auth);
  _assertInstanceOf(auth, provider, FederatedAuthProvider);
  const resolverInternal = _withDefaultResolver(authInternal, resolver);
  const action = new PopupOperation(authInternal, "signInViaPopup", provider, resolverInternal);
  return action.executeNotNull();
}
var PopupOperation = class _PopupOperation extends AbstractPopupRedirectOperation {
  constructor(auth, filter, provider, resolver, user) {
    super(auth, filter, resolver, user);
    this.provider = provider;
    this.authWindow = null;
    this.pollId = null;
    if (_PopupOperation.currentPopupAction) {
      _PopupOperation.currentPopupAction.cancel();
    }
    _PopupOperation.currentPopupAction = this;
  }
  async executeNotNull() {
    const result = await this.execute();
    _assert(
      result,
      this.auth,
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    return result;
  }
  async onExecution() {
    debugAssert(this.filter.length === 1, "Popup operations only handle one event");
    const eventId = _generateEventId();
    this.authWindow = await this.resolver._openPopup(
      this.auth,
      this.provider,
      this.filter[0],
      // There's always one, see constructor
      eventId
    );
    this.authWindow.associatedEvent = eventId;
    this.resolver._originValidation(this.auth).catch((e) => {
      this.reject(e);
    });
    this.resolver._isIframeWebStorageSupported(this.auth, (isSupported) => {
      if (!isSupported) {
        this.reject(_createError(
          this.auth,
          "web-storage-unsupported"
          /* AuthErrorCode.WEB_STORAGE_UNSUPPORTED */
        ));
      }
    });
    this.pollUserCancellation();
  }
  get eventId() {
    return this.authWindow?.associatedEvent || null;
  }
  cancel() {
    this.reject(_createError(
      this.auth,
      "cancelled-popup-request"
      /* AuthErrorCode.EXPIRED_POPUP_REQUEST */
    ));
  }
  cleanUp() {
    if (this.authWindow) {
      this.authWindow.close();
    }
    if (this.pollId) {
      window.clearTimeout(this.pollId);
    }
    this.authWindow = null;
    this.pollId = null;
    _PopupOperation.currentPopupAction = null;
  }
  pollUserCancellation() {
    const poll = () => {
      if (this.authWindow?.window?.closed) {
        this.pollId = window.setTimeout(
          () => {
            this.pollId = null;
            this.reject(_createError(
              this.auth,
              "popup-closed-by-user"
              /* AuthErrorCode.POPUP_CLOSED_BY_USER */
            ));
          },
          8e3
          /* _Timeout.AUTH_EVENT */
        );
        return;
      }
      this.pollId = window.setTimeout(poll, _POLL_WINDOW_CLOSE_TIMEOUT.get());
    };
    poll();
  }
};
PopupOperation.currentPopupAction = null;
var PENDING_REDIRECT_KEY = "pendingRedirect";
var redirectOutcomeMap = /* @__PURE__ */ new Map();
var RedirectAction = class extends AbstractPopupRedirectOperation {
  constructor(auth, resolver, bypassAuthState = false) {
    super(auth, [
      "signInViaRedirect",
      "linkViaRedirect",
      "reauthViaRedirect",
      "unknown"
      /* AuthEventType.UNKNOWN */
    ], resolver, void 0, bypassAuthState);
    this.eventId = null;
  }
  /**
   * Override the execute function; if we already have a redirect result, then
   * just return it.
   */
  async execute() {
    let readyOutcome = redirectOutcomeMap.get(this.auth._key());
    if (!readyOutcome) {
      try {
        const hasPendingRedirect = await _getAndClearPendingRedirectStatus(this.resolver, this.auth);
        const result = hasPendingRedirect ? await super.execute() : null;
        readyOutcome = () => Promise.resolve(result);
      } catch (e) {
        readyOutcome = () => Promise.reject(e);
      }
      redirectOutcomeMap.set(this.auth._key(), readyOutcome);
    }
    if (!this.bypassAuthState) {
      redirectOutcomeMap.set(this.auth._key(), () => Promise.resolve(null));
    }
    return readyOutcome();
  }
  async onAuthEvent(event) {
    if (event.type === "signInViaRedirect") {
      return super.onAuthEvent(event);
    } else if (event.type === "unknown") {
      this.resolve(null);
      return;
    }
    if (event.eventId) {
      const user = await this.auth._redirectUserForId(event.eventId);
      if (user) {
        this.user = user;
        return super.onAuthEvent(event);
      } else {
        this.resolve(null);
      }
    }
  }
  async onExecution() {
  }
  cleanUp() {
  }
};
async function _getAndClearPendingRedirectStatus(resolver, auth) {
  const key = pendingRedirectKey(auth);
  const persistence = resolverPersistence(resolver);
  if (!await persistence._isAvailable()) {
    return false;
  }
  const hasPendingRedirect = await persistence._get(key) === "true";
  await persistence._remove(key);
  return hasPendingRedirect;
}
function _overrideRedirectResult(auth, result) {
  redirectOutcomeMap.set(auth._key(), result);
}
function resolverPersistence(resolver) {
  return _getInstance(resolver._redirectPersistence);
}
function pendingRedirectKey(auth) {
  return _persistenceKeyName(PENDING_REDIRECT_KEY, auth.config.apiKey, auth.name);
}
async function _getRedirectResult(auth, resolverExtern, bypassAuthState = false) {
  if (_isFirebaseServerApp(auth.app)) {
    return Promise.reject(_serverAppCurrentUserOperationNotSupportedError(auth));
  }
  const authInternal = _castAuth(auth);
  const resolver = _withDefaultResolver(authInternal, resolverExtern);
  const action = new RedirectAction(authInternal, resolver, bypassAuthState);
  const result = await action.execute();
  if (result && !bypassAuthState) {
    delete result.user._redirectEventId;
    await authInternal._persistUserIfCurrent(result.user);
    await authInternal._setRedirectUser(null, resolverExtern);
  }
  return result;
}
var EVENT_DUPLICATION_CACHE_DURATION_MS = 10 * 60 * 1e3;
var AuthEventManager = class {
  constructor(auth) {
    this.auth = auth;
    this.cachedEventUids = /* @__PURE__ */ new Set();
    this.consumers = /* @__PURE__ */ new Set();
    this.queuedRedirectEvent = null;
    this.hasHandledPotentialRedirect = false;
    this.lastProcessedEventTime = Date.now();
  }
  registerConsumer(authEventConsumer) {
    this.consumers.add(authEventConsumer);
    if (this.queuedRedirectEvent && this.isEventForConsumer(this.queuedRedirectEvent, authEventConsumer)) {
      this.sendToConsumer(this.queuedRedirectEvent, authEventConsumer);
      this.saveEventToCache(this.queuedRedirectEvent);
      this.queuedRedirectEvent = null;
    }
  }
  unregisterConsumer(authEventConsumer) {
    this.consumers.delete(authEventConsumer);
  }
  onEvent(event) {
    if (this.hasEventBeenHandled(event)) {
      return false;
    }
    let handled = false;
    this.consumers.forEach((consumer) => {
      if (this.isEventForConsumer(event, consumer)) {
        handled = true;
        this.sendToConsumer(event, consumer);
        this.saveEventToCache(event);
      }
    });
    if (this.hasHandledPotentialRedirect || !isRedirectEvent(event)) {
      return handled;
    }
    this.hasHandledPotentialRedirect = true;
    if (!handled) {
      this.queuedRedirectEvent = event;
      handled = true;
    }
    return handled;
  }
  sendToConsumer(event, consumer) {
    if (event.error && !isNullRedirectEvent(event)) {
      const code = event.error.code?.split("auth/")[1] || "internal-error";
      consumer.onError(_createError(this.auth, code));
    } else {
      consumer.onAuthEvent(event);
    }
  }
  isEventForConsumer(event, consumer) {
    const eventIdMatches = consumer.eventId === null || !!event.eventId && event.eventId === consumer.eventId;
    return consumer.filter.includes(event.type) && eventIdMatches;
  }
  hasEventBeenHandled(event) {
    if (Date.now() - this.lastProcessedEventTime >= EVENT_DUPLICATION_CACHE_DURATION_MS) {
      this.cachedEventUids.clear();
    }
    return this.cachedEventUids.has(eventUid(event));
  }
  saveEventToCache(event) {
    this.cachedEventUids.add(eventUid(event));
    this.lastProcessedEventTime = Date.now();
  }
};
function eventUid(e) {
  return [e.type, e.eventId, e.sessionId, e.tenantId].filter((v2) => v2).join("-");
}
function isNullRedirectEvent({ type, error }) {
  return type === "unknown" && error?.code === `auth/${"no-auth-event"}`;
}
function isRedirectEvent(event) {
  switch (event.type) {
    case "signInViaRedirect":
    case "linkViaRedirect":
    case "reauthViaRedirect":
      return true;
    case "unknown":
      return isNullRedirectEvent(event);
    default:
      return false;
  }
}
async function _getProjectConfig(auth, request = {}) {
  return _performApiRequest(auth, "GET", "/v1/projects", request);
}
var IP_ADDRESS_REGEX = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/;
var HTTP_REGEX = /^https?/;
async function _validateOrigin(auth) {
  if (auth.config.emulator) {
    return;
  }
  const { authorizedDomains } = await _getProjectConfig(auth);
  for (const domain of authorizedDomains) {
    try {
      if (matchDomain(domain)) {
        return;
      }
    } catch {
    }
  }
  _fail(
    auth,
    "unauthorized-domain"
    /* AuthErrorCode.INVALID_ORIGIN */
  );
}
function matchDomain(expected) {
  const currentUrl = _getCurrentUrl();
  const { protocol, hostname } = new URL(currentUrl);
  if (expected.startsWith("chrome-extension://")) {
    const ceUrl = new URL(expected);
    if (ceUrl.hostname === "" && hostname === "") {
      return protocol === "chrome-extension:" && expected.replace("chrome-extension://", "") === currentUrl.replace("chrome-extension://", "");
    }
    return protocol === "chrome-extension:" && ceUrl.hostname === hostname;
  }
  if (!HTTP_REGEX.test(protocol)) {
    return false;
  }
  if (IP_ADDRESS_REGEX.test(expected)) {
    return hostname === expected;
  }
  const escapedDomainPattern = expected.replace(/\./g, "\\.");
  const re = new RegExp("^(.+\\." + escapedDomainPattern + "|" + escapedDomainPattern + ")$", "i");
  return re.test(hostname);
}
var NETWORK_TIMEOUT = new Delay(3e4, 6e4);
function resetUnloadedGapiModules() {
  const beacon = _window().___jsl;
  if (beacon?.H) {
    for (const hint of Object.keys(beacon.H)) {
      beacon.H[hint].r = beacon.H[hint].r || [];
      beacon.H[hint].L = beacon.H[hint].L || [];
      beacon.H[hint].r = [...beacon.H[hint].L];
      if (beacon.CP) {
        for (let i = 0; i < beacon.CP.length; i++) {
          beacon.CP[i] = null;
        }
      }
    }
  }
}
function loadGapi(auth) {
  return new Promise((resolve, reject) => {
    function loadGapiIframe() {
      resetUnloadedGapiModules();
      gapi.load("gapi.iframes", {
        callback: () => {
          resolve(gapi.iframes.getContext());
        },
        ontimeout: () => {
          resetUnloadedGapiModules();
          reject(_createError(
            auth,
            "network-request-failed"
            /* AuthErrorCode.NETWORK_REQUEST_FAILED */
          ));
        },
        timeout: NETWORK_TIMEOUT.get()
      });
    }
    if (_window().gapi?.iframes?.Iframe) {
      resolve(gapi.iframes.getContext());
    } else if (!!_window().gapi?.load) {
      loadGapiIframe();
    } else {
      const cbName = _generateCallbackName("iframefcb");
      _window()[cbName] = () => {
        if (!!gapi.load) {
          loadGapiIframe();
        } else {
          reject(_createError(
            auth,
            "network-request-failed"
            /* AuthErrorCode.NETWORK_REQUEST_FAILED */
          ));
        }
      };
      return _loadJS(`${_gapiScriptUrl()}?onload=${cbName}`).catch((e) => reject(e));
    }
  }).catch((error) => {
    cachedGApiLoader = null;
    throw error;
  });
}
var cachedGApiLoader = null;
function _loadGapi(auth) {
  cachedGApiLoader = cachedGApiLoader || loadGapi(auth);
  return cachedGApiLoader;
}
var PING_TIMEOUT = new Delay(5e3, 15e3);
var IFRAME_PATH = "__/auth/iframe";
var EMULATED_IFRAME_PATH = "emulator/auth/iframe";
var IFRAME_ATTRIBUTES = {
  style: {
    position: "absolute",
    top: "-100px",
    width: "1px",
    height: "1px"
  },
  "aria-hidden": "true",
  tabindex: "-1"
};
var EID_FROM_APIHOST = /* @__PURE__ */ new Map([
  ["identitytoolkit.googleapis.com", "p"],
  // production
  ["staging-identitytoolkit.sandbox.googleapis.com", "s"],
  // staging
  ["test-identitytoolkit.sandbox.googleapis.com", "t"]
  // test
]);
function getIframeUrl(auth) {
  const config = auth.config;
  _assert(
    config.authDomain,
    auth,
    "auth-domain-config-required"
    /* AuthErrorCode.MISSING_AUTH_DOMAIN */
  );
  const url = config.emulator ? _emulatorUrl(config, EMULATED_IFRAME_PATH) : `https://${auth.config.authDomain}/${IFRAME_PATH}`;
  const params = {
    apiKey: config.apiKey,
    appName: auth.name,
    v: SDK_VERSION
  };
  const eid = EID_FROM_APIHOST.get(auth.config.apiHost);
  if (eid) {
    params.eid = eid;
  }
  const frameworks = auth._getFrameworks();
  if (frameworks.length) {
    params.fw = frameworks.join(",");
  }
  return `${url}?${querystring(params).slice(1)}`;
}
async function _openIframe(auth) {
  const context = await _loadGapi(auth);
  const gapi2 = _window().gapi;
  _assert(
    gapi2,
    auth,
    "internal-error"
    /* AuthErrorCode.INTERNAL_ERROR */
  );
  return context.open({
    where: document.body,
    url: getIframeUrl(auth),
    messageHandlersFilter: gapi2.iframes.CROSS_ORIGIN_IFRAMES_FILTER,
    attributes: IFRAME_ATTRIBUTES,
    dontclear: true
  }, (iframe) => new Promise(async (resolve, reject) => {
    await iframe.restyle({
      // Prevent iframe from closing on mouse out.
      setHideOnLeave: false
    });
    const networkError = _createError(
      auth,
      "network-request-failed"
      /* AuthErrorCode.NETWORK_REQUEST_FAILED */
    );
    const networkErrorTimer = _window().setTimeout(() => {
      reject(networkError);
    }, PING_TIMEOUT.get());
    function clearTimerAndResolve() {
      _window().clearTimeout(networkErrorTimer);
      resolve(iframe);
    }
    iframe.ping(clearTimerAndResolve).then(clearTimerAndResolve, () => {
      reject(networkError);
    });
  }));
}
var BASE_POPUP_OPTIONS = {
  location: "yes",
  resizable: "yes",
  statusbar: "yes",
  toolbar: "no"
};
var DEFAULT_WIDTH = 500;
var DEFAULT_HEIGHT = 600;
var TARGET_BLANK = "_blank";
var FIREFOX_EMPTY_URL = "http://localhost";
var AuthPopup = class {
  constructor(window2) {
    this.window = window2;
    this.associatedEvent = null;
  }
  close() {
    if (this.window) {
      try {
        this.window.close();
      } catch (e) {
      }
    }
  }
};
function _open(auth, url, name4, width = DEFAULT_WIDTH, height = DEFAULT_HEIGHT) {
  const top = Math.max((window.screen.availHeight - height) / 2, 0).toString();
  const left = Math.max((window.screen.availWidth - width) / 2, 0).toString();
  let target = "";
  const options = {
    ...BASE_POPUP_OPTIONS,
    width: width.toString(),
    height: height.toString(),
    top,
    left
  };
  const ua = getUA().toLowerCase();
  if (name4) {
    target = _isChromeIOS(ua) ? TARGET_BLANK : name4;
  }
  if (_isFirefox(ua)) {
    url = url || FIREFOX_EMPTY_URL;
    options.scrollbars = "yes";
  }
  const optionsString = Object.entries(options).reduce((accum, [key, value]) => `${accum}${key}=${value},`, "");
  if (_isIOSStandalone(ua) && target !== "_self") {
    openAsNewWindowIOS(url || "", target);
    return new AuthPopup(null);
  }
  const newWin = window.open(url || "", target, optionsString);
  _assert(
    newWin,
    auth,
    "popup-blocked"
    /* AuthErrorCode.POPUP_BLOCKED */
  );
  try {
    newWin.focus();
  } catch (e) {
  }
  return new AuthPopup(newWin);
}
function openAsNewWindowIOS(url, target) {
  const el = document.createElement("a");
  el.href = url;
  el.target = target;
  const click = document.createEvent("MouseEvent");
  click.initMouseEvent("click", true, true, window, 1, 0, 0, 0, 0, false, false, false, false, 1, null);
  el.dispatchEvent(click);
}
var WIDGET_PATH = "__/auth/handler";
var EMULATOR_WIDGET_PATH = "emulator/auth/handler";
var FIREBASE_APP_CHECK_FRAGMENT_ID = encodeURIComponent("fac");
async function _getRedirectUrl(auth, provider, authType, redirectUrl, eventId, additionalParams) {
  _assert(
    auth.config.authDomain,
    auth,
    "auth-domain-config-required"
    /* AuthErrorCode.MISSING_AUTH_DOMAIN */
  );
  _assert(
    auth.config.apiKey,
    auth,
    "invalid-api-key"
    /* AuthErrorCode.INVALID_API_KEY */
  );
  const params = {
    apiKey: auth.config.apiKey,
    appName: auth.name,
    authType,
    redirectUrl,
    v: SDK_VERSION,
    eventId
  };
  if (provider instanceof FederatedAuthProvider) {
    provider.setDefaultLanguage(auth.languageCode);
    params.providerId = provider.providerId || "";
    if (!isEmpty(provider.getCustomParameters())) {
      params.customParameters = JSON.stringify(provider.getCustomParameters());
    }
    for (const [key, value] of Object.entries(additionalParams || {})) {
      params[key] = value;
    }
  }
  if (provider instanceof BaseOAuthProvider) {
    const scopes = provider.getScopes().filter((scope) => scope !== "");
    if (scopes.length > 0) {
      params.scopes = scopes.join(",");
    }
  }
  if (auth.tenantId) {
    params.tid = auth.tenantId;
  }
  const paramsDict = params;
  for (const key of Object.keys(paramsDict)) {
    if (paramsDict[key] === void 0) {
      delete paramsDict[key];
    }
  }
  const appCheckToken = await auth._getAppCheckToken();
  const appCheckTokenFragment = appCheckToken ? `#${FIREBASE_APP_CHECK_FRAGMENT_ID}=${encodeURIComponent(appCheckToken)}` : "";
  return `${getHandlerBase(auth)}?${querystring(paramsDict).slice(1)}${appCheckTokenFragment}`;
}
function getHandlerBase({ config }) {
  if (!config.emulator) {
    return `https://${config.authDomain}/${WIDGET_PATH}`;
  }
  return _emulatorUrl(config, EMULATOR_WIDGET_PATH);
}
var WEB_STORAGE_SUPPORT_KEY = "webStorageSupport";
var BrowserPopupRedirectResolver = class {
  constructor() {
    this.eventManagers = {};
    this.iframes = {};
    this.originValidationPromises = {};
    this._redirectPersistence = browserSessionPersistence;
    this._completeRedirectFn = _getRedirectResult;
    this._overrideRedirectResult = _overrideRedirectResult;
  }
  // Wrapping in async even though we don't await anywhere in order
  // to make sure errors are raised as promise rejections
  async _openPopup(auth, provider, authType, eventId) {
    debugAssert(this.eventManagers[auth._key()]?.manager, "_initialize() not called before _openPopup()");
    const url = await _getRedirectUrl(auth, provider, authType, _getCurrentUrl(), eventId);
    return _open(auth, url, _generateEventId());
  }
  async _openRedirect(auth, provider, authType, eventId) {
    await this._originValidation(auth);
    const url = await _getRedirectUrl(auth, provider, authType, _getCurrentUrl(), eventId);
    _setWindowLocation(url);
    return new Promise(() => {
    });
  }
  _initialize(auth) {
    const key = auth._key();
    if (this.eventManagers[key]) {
      const { manager, promise: promise2 } = this.eventManagers[key];
      if (manager) {
        return Promise.resolve(manager);
      } else {
        debugAssert(promise2, "If manager is not set, promise should be");
        return promise2;
      }
    }
    const promise = this.initAndGetManager(auth);
    this.eventManagers[key] = { promise };
    promise.catch(() => {
      delete this.eventManagers[key];
    });
    return promise;
  }
  async initAndGetManager(auth) {
    const iframe = await _openIframe(auth);
    const manager = new AuthEventManager(auth);
    iframe.register("authEvent", (iframeEvent) => {
      _assert(
        iframeEvent?.authEvent,
        auth,
        "invalid-auth-event"
        /* AuthErrorCode.INVALID_AUTH_EVENT */
      );
      const handled = manager.onEvent(iframeEvent.authEvent);
      return {
        status: handled ? "ACK" : "ERROR"
        /* GapiOutcome.ERROR */
      };
    }, gapi.iframes.CROSS_ORIGIN_IFRAMES_FILTER);
    this.eventManagers[auth._key()] = { manager };
    this.iframes[auth._key()] = iframe;
    return manager;
  }
  _isIframeWebStorageSupported(auth, cb) {
    const iframe = this.iframes[auth._key()];
    iframe.send(WEB_STORAGE_SUPPORT_KEY, { type: WEB_STORAGE_SUPPORT_KEY }, (result) => {
      const isSupported = result?.[0]?.[WEB_STORAGE_SUPPORT_KEY];
      if (isSupported !== void 0) {
        cb(!!isSupported);
      }
      _fail(
        auth,
        "internal-error"
        /* AuthErrorCode.INTERNAL_ERROR */
      );
    }, gapi.iframes.CROSS_ORIGIN_IFRAMES_FILTER);
  }
  _originValidation(auth) {
    const key = auth._key();
    if (!this.originValidationPromises[key]) {
      this.originValidationPromises[key] = _validateOrigin(auth);
    }
    return this.originValidationPromises[key];
  }
  get _shouldInitProactively() {
    return _isMobileBrowser() || _isSafari() || _isIOS();
  }
};
var browserPopupRedirectResolver = BrowserPopupRedirectResolver;
var MultiFactorAssertionImpl = class {
  constructor(factorId) {
    this.factorId = factorId;
  }
  _process(auth, session, displayName) {
    switch (session.type) {
      case "enroll":
        return this._finalizeEnroll(auth, session.credential, displayName);
      case "signin":
        return this._finalizeSignIn(auth, session.credential);
      default:
        return debugFail("unexpected MultiFactorSessionType");
    }
  }
};
var PhoneMultiFactorAssertionImpl = class _PhoneMultiFactorAssertionImpl extends MultiFactorAssertionImpl {
  constructor(credential) {
    super(
      "phone"
      /* FactorId.PHONE */
    );
    this.credential = credential;
  }
  /** @internal */
  static _fromCredential(credential) {
    return new _PhoneMultiFactorAssertionImpl(credential);
  }
  /** @internal */
  _finalizeEnroll(auth, idToken, displayName) {
    return finalizeEnrollPhoneMfa(auth, {
      idToken,
      displayName,
      phoneVerificationInfo: this.credential._makeVerificationRequest()
    });
  }
  /** @internal */
  _finalizeSignIn(auth, mfaPendingCredential) {
    return finalizeSignInPhoneMfa(auth, {
      mfaPendingCredential,
      phoneVerificationInfo: this.credential._makeVerificationRequest()
    });
  }
};
var PhoneMultiFactorGenerator = class {
  constructor() {
  }
  /**
   * Provides a {@link PhoneMultiFactorAssertion} to confirm ownership of the phone second factor.
   *
   * @remarks
   * This method does not work in a Node.js environment.
   *
   * @param phoneAuthCredential - A credential provided by {@link PhoneAuthProvider.credential}.
   * @returns A {@link PhoneMultiFactorAssertion} which can be used with
   * {@link MultiFactorResolver.resolveSignIn}
   */
  static assertion(credential) {
    return PhoneMultiFactorAssertionImpl._fromCredential(credential);
  }
};
PhoneMultiFactorGenerator.FACTOR_ID = "phone";
var TotpMultiFactorGenerator = class {
  /**
   * Provides a {@link TotpMultiFactorAssertion} to confirm ownership of
   * the TOTP (time-based one-time password) second factor.
   * This assertion is used to complete enrollment in TOTP second factor.
   *
   * @param secret A {@link TotpSecret} containing the shared secret key and other TOTP parameters.
   * @param oneTimePassword One-time password from TOTP App.
   * @returns A {@link TotpMultiFactorAssertion} which can be used with
   * {@link MultiFactorUser.enroll}.
   */
  static assertionForEnrollment(secret, oneTimePassword) {
    return TotpMultiFactorAssertionImpl._fromSecret(secret, oneTimePassword);
  }
  /**
   * Provides a {@link TotpMultiFactorAssertion} to confirm ownership of the TOTP second factor.
   * This assertion is used to complete signIn with TOTP as the second factor.
   *
   * @param enrollmentId identifies the enrolled TOTP second factor.
   * @param oneTimePassword One-time password from TOTP App.
   * @returns A {@link TotpMultiFactorAssertion} which can be used with
   * {@link MultiFactorResolver.resolveSignIn}.
   */
  static assertionForSignIn(enrollmentId, oneTimePassword) {
    return TotpMultiFactorAssertionImpl._fromEnrollmentId(enrollmentId, oneTimePassword);
  }
  /**
   * Returns a promise to {@link TotpSecret} which contains the TOTP shared secret key and other parameters.
   * Creates a TOTP secret as part of enrolling a TOTP second factor.
   * Used for generating a QR code URL or inputting into a TOTP app.
   * This method uses the auth instance corresponding to the user in the multiFactorSession.
   *
   * @param session The {@link MultiFactorSession} that the user is part of.
   * @returns A promise to {@link TotpSecret}.
   */
  static async generateSecret(session) {
    const mfaSession = session;
    _assert(
      typeof mfaSession.user?.auth !== "undefined",
      "internal-error"
      /* AuthErrorCode.INTERNAL_ERROR */
    );
    const response = await startEnrollTotpMfa(mfaSession.user.auth, {
      idToken: mfaSession.credential,
      totpEnrollmentInfo: {}
    });
    return TotpSecret._fromStartTotpMfaEnrollmentResponse(response, mfaSession.user.auth);
  }
};
TotpMultiFactorGenerator.FACTOR_ID = "totp";
var TotpMultiFactorAssertionImpl = class _TotpMultiFactorAssertionImpl extends MultiFactorAssertionImpl {
  constructor(otp, enrollmentId, secret) {
    super(
      "totp"
      /* FactorId.TOTP */
    );
    this.otp = otp;
    this.enrollmentId = enrollmentId;
    this.secret = secret;
  }
  /** @internal */
  static _fromSecret(secret, otp) {
    return new _TotpMultiFactorAssertionImpl(otp, void 0, secret);
  }
  /** @internal */
  static _fromEnrollmentId(enrollmentId, otp) {
    return new _TotpMultiFactorAssertionImpl(otp, enrollmentId);
  }
  /** @internal */
  async _finalizeEnroll(auth, idToken, displayName) {
    _assert(
      typeof this.secret !== "undefined",
      auth,
      "argument-error"
      /* AuthErrorCode.ARGUMENT_ERROR */
    );
    return finalizeEnrollTotpMfa(auth, {
      idToken,
      displayName,
      totpVerificationInfo: this.secret._makeTotpVerificationInfo(this.otp)
    });
  }
  /** @internal */
  async _finalizeSignIn(auth, mfaPendingCredential) {
    _assert(
      this.enrollmentId !== void 0 && this.otp !== void 0,
      auth,
      "argument-error"
      /* AuthErrorCode.ARGUMENT_ERROR */
    );
    const totpVerificationInfo = { verificationCode: this.otp };
    return finalizeSignInTotpMfa(auth, {
      mfaPendingCredential,
      mfaEnrollmentId: this.enrollmentId,
      totpVerificationInfo
    });
  }
};
var TotpSecret = class _TotpSecret {
  // The public members are declared outside the constructor so the docs can be generated.
  constructor(secretKey, hashingAlgorithm, codeLength, codeIntervalSeconds, enrollmentCompletionDeadline, sessionInfo, auth) {
    this.sessionInfo = sessionInfo;
    this.auth = auth;
    this.secretKey = secretKey;
    this.hashingAlgorithm = hashingAlgorithm;
    this.codeLength = codeLength;
    this.codeIntervalSeconds = codeIntervalSeconds;
    this.enrollmentCompletionDeadline = enrollmentCompletionDeadline;
  }
  /** @internal */
  static _fromStartTotpMfaEnrollmentResponse(response, auth) {
    return new _TotpSecret(response.totpSessionInfo.sharedSecretKey, response.totpSessionInfo.hashingAlgorithm, response.totpSessionInfo.verificationCodeLength, response.totpSessionInfo.periodSec, new Date(response.totpSessionInfo.finalizeEnrollmentTime).toUTCString(), response.totpSessionInfo.sessionInfo, auth);
  }
  /** @internal */
  _makeTotpVerificationInfo(otp) {
    return { sessionInfo: this.sessionInfo, verificationCode: otp };
  }
  /**
   * Returns a QR code URL as described in
   * https://github.com/google/google-authenticator/wiki/Key-Uri-Format
   * This can be displayed to the user as a QR code to be scanned into a TOTP app like Google Authenticator.
   * If the optional parameters are unspecified, an accountName of <userEmail> and issuer of <firebaseAppName> are used.
   *
   * @param accountName the name of the account/app along with a user identifier.
   * @param issuer issuer of the TOTP (likely the app name).
   * @returns A QR code URL string.
   */
  generateQrCodeUrl(accountName, issuer) {
    let useDefaults = false;
    if (_isEmptyString(accountName) || _isEmptyString(issuer)) {
      useDefaults = true;
    }
    if (useDefaults) {
      if (_isEmptyString(accountName)) {
        accountName = this.auth.currentUser?.email || "unknownuser";
      }
      if (_isEmptyString(issuer)) {
        issuer = this.auth.name;
      }
    }
    return `otpauth://totp/${issuer}:${accountName}?secret=${this.secretKey}&issuer=${issuer}&algorithm=${this.hashingAlgorithm}&digits=${this.codeLength}`;
  }
};
function _isEmptyString(input) {
  return typeof input === "undefined" || input?.length === 0;
}
var name3 = "@firebase/auth";
var version3 = "1.11.0";
var AuthInterop = class {
  constructor(auth) {
    this.auth = auth;
    this.internalListeners = /* @__PURE__ */ new Map();
  }
  getUid() {
    this.assertAuthConfigured();
    return this.auth.currentUser?.uid || null;
  }
  async getToken(forceRefresh) {
    this.assertAuthConfigured();
    await this.auth._initializationPromise;
    if (!this.auth.currentUser) {
      return null;
    }
    const accessToken = await this.auth.currentUser.getIdToken(forceRefresh);
    return { accessToken };
  }
  addAuthTokenListener(listener) {
    this.assertAuthConfigured();
    if (this.internalListeners.has(listener)) {
      return;
    }
    const unsubscribe = this.auth.onIdTokenChanged((user) => {
      listener(user?.stsTokenManager.accessToken || null);
    });
    this.internalListeners.set(listener, unsubscribe);
    this.updateProactiveRefresh();
  }
  removeAuthTokenListener(listener) {
    this.assertAuthConfigured();
    const unsubscribe = this.internalListeners.get(listener);
    if (!unsubscribe) {
      return;
    }
    this.internalListeners.delete(listener);
    unsubscribe();
    this.updateProactiveRefresh();
  }
  assertAuthConfigured() {
    _assert(
      this.auth._initializationPromise,
      "dependent-sdk-initialized-before-auth"
      /* AuthErrorCode.DEPENDENT_SDK_INIT_BEFORE_AUTH */
    );
  }
  updateProactiveRefresh() {
    if (this.internalListeners.size > 0) {
      this.auth._startProactiveRefresh();
    } else {
      this.auth._stopProactiveRefresh();
    }
  }
};
function getVersionForPlatform(clientPlatform) {
  switch (clientPlatform) {
    case "Node":
      return "node";
    case "ReactNative":
      return "rn";
    case "Worker":
      return "webworker";
    case "Cordova":
      return "cordova";
    case "WebExtension":
      return "web-extension";
    default:
      return void 0;
  }
}
function registerAuth(clientPlatform) {
  _registerComponent(new Component(
    "auth",
    (container, { options: deps }) => {
      const app = container.getProvider("app").getImmediate();
      const heartbeatServiceProvider = container.getProvider("heartbeat");
      const appCheckServiceProvider = container.getProvider("app-check-internal");
      const { apiKey, authDomain } = app.options;
      _assert(apiKey && !apiKey.includes(":"), "invalid-api-key", { appName: app.name });
      const config = {
        apiKey,
        authDomain,
        clientPlatform,
        apiHost: "identitytoolkit.googleapis.com",
        tokenApiHost: "securetoken.googleapis.com",
        apiScheme: "https",
        sdkClientVersion: _getClientVersion(clientPlatform)
      };
      const authInstance = new AuthImpl(app, heartbeatServiceProvider, appCheckServiceProvider, config);
      _initializeAuthInstance(authInstance, deps);
      return authInstance;
    },
    "PUBLIC"
    /* ComponentType.PUBLIC */
  ).setInstantiationMode(
    "EXPLICIT"
    /* InstantiationMode.EXPLICIT */
  ).setInstanceCreatedCallback((container, _instanceIdentifier, _instance) => {
    const authInternalProvider = container.getProvider(
      "auth-internal"
      /* _ComponentName.AUTH_INTERNAL */
    );
    authInternalProvider.initialize();
  }));
  _registerComponent(new Component(
    "auth-internal",
    (container) => {
      const auth = _castAuth(container.getProvider(
        "auth"
        /* _ComponentName.AUTH */
      ).getImmediate());
      return ((auth2) => new AuthInterop(auth2))(auth);
    },
    "PRIVATE"
    /* ComponentType.PRIVATE */
  ).setInstantiationMode(
    "EXPLICIT"
    /* InstantiationMode.EXPLICIT */
  ));
  registerVersion(name3, version3, getVersionForPlatform(clientPlatform));
  registerVersion(name3, version3, "esm2020");
}
var DEFAULT_ID_TOKEN_MAX_AGE = 5 * 60;
var authIdTokenMaxAge = getExperimentalSetting("authIdTokenMaxAge") || DEFAULT_ID_TOKEN_MAX_AGE;
var lastPostedIdToken = null;
var mintCookieFactory = (url) => async (user) => {
  const idTokenResult = user && await user.getIdTokenResult();
  const idTokenAge = idTokenResult && ((/* @__PURE__ */ new Date()).getTime() - Date.parse(idTokenResult.issuedAtTime)) / 1e3;
  if (idTokenAge && idTokenAge > authIdTokenMaxAge) {
    return;
  }
  const idToken = idTokenResult?.token;
  if (lastPostedIdToken === idToken) {
    return;
  }
  lastPostedIdToken = idToken;
  await fetch(url, {
    method: idToken ? "POST" : "DELETE",
    headers: idToken ? {
      "Authorization": `Bearer ${idToken}`
    } : {}
  });
};
function getAuth(app = getApp()) {
  const provider = _getProvider(app, "auth");
  if (provider.isInitialized()) {
    return provider.getImmediate();
  }
  const auth = initializeAuth(app, {
    popupRedirectResolver: browserPopupRedirectResolver,
    persistence: [
      indexedDBLocalPersistence,
      browserLocalPersistence,
      browserSessionPersistence
    ]
  });
  const authTokenSyncPath = getExperimentalSetting("authTokenSyncURL");
  if (authTokenSyncPath && typeof isSecureContext === "boolean" && isSecureContext) {
    const authTokenSyncUrl = new URL(authTokenSyncPath, location.origin);
    if (location.origin === authTokenSyncUrl.origin) {
      const mintCookie = mintCookieFactory(authTokenSyncUrl.toString());
      beforeAuthStateChanged(auth, mintCookie, () => mintCookie(auth.currentUser));
      onIdTokenChanged(auth, (user) => mintCookie(user));
    }
  }
  const authEmulatorHost = getDefaultEmulatorHost("auth");
  if (authEmulatorHost) {
    connectAuthEmulator(auth, `http://${authEmulatorHost}`);
  }
  return auth;
}
function getScriptParentElement() {
  return document.getElementsByTagName("head")?.[0] ?? document;
}
_setExternalJSProvider({
  loadJS(url) {
    return new Promise((resolve, reject) => {
      const el = document.createElement("script");
      el.setAttribute("src", url);
      el.onload = resolve;
      el.onerror = (e) => {
        const error = _createError(
          "internal-error"
          /* AuthErrorCode.INTERNAL_ERROR */
        );
        error.customData = e;
        reject(error);
      };
      el.type = "text/javascript";
      el.charset = "UTF-8";
      getScriptParentElement().appendChild(el);
    });
  },
  gapiScript: "https://apis.google.com/js/api.js",
  recaptchaV2Script: "https://www.google.com/recaptcha/api.js",
  recaptchaEnterpriseScript: "https://www.google.com/recaptcha/enterprise.js?render="
});
registerAuth(
  "Browser"
  /* ClientPlatform.BROWSER */
);

// node_modules/@firebase/webchannel-wrapper/dist/bloom-blob/esm/bloom_blob_es2018.js
var commonjsGlobal = typeof globalThis !== "undefined" ? globalThis : typeof window !== "undefined" ? window : typeof global !== "undefined" ? global : typeof self !== "undefined" ? self : {};
var bloom_blob_es2018 = {};
var Integer;
var Md5;
(function() {
  var h;
  function k2(f, a) {
    function c() {
    }
    c.prototype = a.prototype;
    f.D = a.prototype;
    f.prototype = new c();
    f.prototype.constructor = f;
    f.C = function(d, e, g2) {
      for (var b2 = Array(arguments.length - 2), r = 2; r < arguments.length; r++) b2[r - 2] = arguments[r];
      return a.prototype[e].apply(d, b2);
    };
  }
  function l() {
    this.blockSize = -1;
  }
  function m() {
    this.blockSize = -1;
    this.blockSize = 64;
    this.g = Array(4);
    this.B = Array(this.blockSize);
    this.o = this.h = 0;
    this.s();
  }
  k2(m, l);
  m.prototype.s = function() {
    this.g[0] = 1732584193;
    this.g[1] = 4023233417;
    this.g[2] = 2562383102;
    this.g[3] = 271733878;
    this.o = this.h = 0;
  };
  function n(f, a, c) {
    c || (c = 0);
    var d = Array(16);
    if ("string" === typeof a) for (var e = 0; 16 > e; ++e) d[e] = a.charCodeAt(c++) | a.charCodeAt(c++) << 8 | a.charCodeAt(c++) << 16 | a.charCodeAt(c++) << 24;
    else for (e = 0; 16 > e; ++e) d[e] = a[c++] | a[c++] << 8 | a[c++] << 16 | a[c++] << 24;
    a = f.g[0];
    c = f.g[1];
    e = f.g[2];
    var g2 = f.g[3];
    var b2 = a + (g2 ^ c & (e ^ g2)) + d[0] + 3614090360 & 4294967295;
    a = c + (b2 << 7 & 4294967295 | b2 >>> 25);
    b2 = g2 + (e ^ a & (c ^ e)) + d[1] + 3905402710 & 4294967295;
    g2 = a + (b2 << 12 & 4294967295 | b2 >>> 20);
    b2 = e + (c ^ g2 & (a ^ c)) + d[2] + 606105819 & 4294967295;
    e = g2 + (b2 << 17 & 4294967295 | b2 >>> 15);
    b2 = c + (a ^ e & (g2 ^ a)) + d[3] + 3250441966 & 4294967295;
    c = e + (b2 << 22 & 4294967295 | b2 >>> 10);
    b2 = a + (g2 ^ c & (e ^ g2)) + d[4] + 4118548399 & 4294967295;
    a = c + (b2 << 7 & 4294967295 | b2 >>> 25);
    b2 = g2 + (e ^ a & (c ^ e)) + d[5] + 1200080426 & 4294967295;
    g2 = a + (b2 << 12 & 4294967295 | b2 >>> 20);
    b2 = e + (c ^ g2 & (a ^ c)) + d[6] + 2821735955 & 4294967295;
    e = g2 + (b2 << 17 & 4294967295 | b2 >>> 15);
    b2 = c + (a ^ e & (g2 ^ a)) + d[7] + 4249261313 & 4294967295;
    c = e + (b2 << 22 & 4294967295 | b2 >>> 10);
    b2 = a + (g2 ^ c & (e ^ g2)) + d[8] + 1770035416 & 4294967295;
    a = c + (b2 << 7 & 4294967295 | b2 >>> 25);
    b2 = g2 + (e ^ a & (c ^ e)) + d[9] + 2336552879 & 4294967295;
    g2 = a + (b2 << 12 & 4294967295 | b2 >>> 20);
    b2 = e + (c ^ g2 & (a ^ c)) + d[10] + 4294925233 & 4294967295;
    e = g2 + (b2 << 17 & 4294967295 | b2 >>> 15);
    b2 = c + (a ^ e & (g2 ^ a)) + d[11] + 2304563134 & 4294967295;
    c = e + (b2 << 22 & 4294967295 | b2 >>> 10);
    b2 = a + (g2 ^ c & (e ^ g2)) + d[12] + 1804603682 & 4294967295;
    a = c + (b2 << 7 & 4294967295 | b2 >>> 25);
    b2 = g2 + (e ^ a & (c ^ e)) + d[13] + 4254626195 & 4294967295;
    g2 = a + (b2 << 12 & 4294967295 | b2 >>> 20);
    b2 = e + (c ^ g2 & (a ^ c)) + d[14] + 2792965006 & 4294967295;
    e = g2 + (b2 << 17 & 4294967295 | b2 >>> 15);
    b2 = c + (a ^ e & (g2 ^ a)) + d[15] + 1236535329 & 4294967295;
    c = e + (b2 << 22 & 4294967295 | b2 >>> 10);
    b2 = a + (e ^ g2 & (c ^ e)) + d[1] + 4129170786 & 4294967295;
    a = c + (b2 << 5 & 4294967295 | b2 >>> 27);
    b2 = g2 + (c ^ e & (a ^ c)) + d[6] + 3225465664 & 4294967295;
    g2 = a + (b2 << 9 & 4294967295 | b2 >>> 23);
    b2 = e + (a ^ c & (g2 ^ a)) + d[11] + 643717713 & 4294967295;
    e = g2 + (b2 << 14 & 4294967295 | b2 >>> 18);
    b2 = c + (g2 ^ a & (e ^ g2)) + d[0] + 3921069994 & 4294967295;
    c = e + (b2 << 20 & 4294967295 | b2 >>> 12);
    b2 = a + (e ^ g2 & (c ^ e)) + d[5] + 3593408605 & 4294967295;
    a = c + (b2 << 5 & 4294967295 | b2 >>> 27);
    b2 = g2 + (c ^ e & (a ^ c)) + d[10] + 38016083 & 4294967295;
    g2 = a + (b2 << 9 & 4294967295 | b2 >>> 23);
    b2 = e + (a ^ c & (g2 ^ a)) + d[15] + 3634488961 & 4294967295;
    e = g2 + (b2 << 14 & 4294967295 | b2 >>> 18);
    b2 = c + (g2 ^ a & (e ^ g2)) + d[4] + 3889429448 & 4294967295;
    c = e + (b2 << 20 & 4294967295 | b2 >>> 12);
    b2 = a + (e ^ g2 & (c ^ e)) + d[9] + 568446438 & 4294967295;
    a = c + (b2 << 5 & 4294967295 | b2 >>> 27);
    b2 = g2 + (c ^ e & (a ^ c)) + d[14] + 3275163606 & 4294967295;
    g2 = a + (b2 << 9 & 4294967295 | b2 >>> 23);
    b2 = e + (a ^ c & (g2 ^ a)) + d[3] + 4107603335 & 4294967295;
    e = g2 + (b2 << 14 & 4294967295 | b2 >>> 18);
    b2 = c + (g2 ^ a & (e ^ g2)) + d[8] + 1163531501 & 4294967295;
    c = e + (b2 << 20 & 4294967295 | b2 >>> 12);
    b2 = a + (e ^ g2 & (c ^ e)) + d[13] + 2850285829 & 4294967295;
    a = c + (b2 << 5 & 4294967295 | b2 >>> 27);
    b2 = g2 + (c ^ e & (a ^ c)) + d[2] + 4243563512 & 4294967295;
    g2 = a + (b2 << 9 & 4294967295 | b2 >>> 23);
    b2 = e + (a ^ c & (g2 ^ a)) + d[7] + 1735328473 & 4294967295;
    e = g2 + (b2 << 14 & 4294967295 | b2 >>> 18);
    b2 = c + (g2 ^ a & (e ^ g2)) + d[12] + 2368359562 & 4294967295;
    c = e + (b2 << 20 & 4294967295 | b2 >>> 12);
    b2 = a + (c ^ e ^ g2) + d[5] + 4294588738 & 4294967295;
    a = c + (b2 << 4 & 4294967295 | b2 >>> 28);
    b2 = g2 + (a ^ c ^ e) + d[8] + 2272392833 & 4294967295;
    g2 = a + (b2 << 11 & 4294967295 | b2 >>> 21);
    b2 = e + (g2 ^ a ^ c) + d[11] + 1839030562 & 4294967295;
    e = g2 + (b2 << 16 & 4294967295 | b2 >>> 16);
    b2 = c + (e ^ g2 ^ a) + d[14] + 4259657740 & 4294967295;
    c = e + (b2 << 23 & 4294967295 | b2 >>> 9);
    b2 = a + (c ^ e ^ g2) + d[1] + 2763975236 & 4294967295;
    a = c + (b2 << 4 & 4294967295 | b2 >>> 28);
    b2 = g2 + (a ^ c ^ e) + d[4] + 1272893353 & 4294967295;
    g2 = a + (b2 << 11 & 4294967295 | b2 >>> 21);
    b2 = e + (g2 ^ a ^ c) + d[7] + 4139469664 & 4294967295;
    e = g2 + (b2 << 16 & 4294967295 | b2 >>> 16);
    b2 = c + (e ^ g2 ^ a) + d[10] + 3200236656 & 4294967295;
    c = e + (b2 << 23 & 4294967295 | b2 >>> 9);
    b2 = a + (c ^ e ^ g2) + d[13] + 681279174 & 4294967295;
    a = c + (b2 << 4 & 4294967295 | b2 >>> 28);
    b2 = g2 + (a ^ c ^ e) + d[0] + 3936430074 & 4294967295;
    g2 = a + (b2 << 11 & 4294967295 | b2 >>> 21);
    b2 = e + (g2 ^ a ^ c) + d[3] + 3572445317 & 4294967295;
    e = g2 + (b2 << 16 & 4294967295 | b2 >>> 16);
    b2 = c + (e ^ g2 ^ a) + d[6] + 76029189 & 4294967295;
    c = e + (b2 << 23 & 4294967295 | b2 >>> 9);
    b2 = a + (c ^ e ^ g2) + d[9] + 3654602809 & 4294967295;
    a = c + (b2 << 4 & 4294967295 | b2 >>> 28);
    b2 = g2 + (a ^ c ^ e) + d[12] + 3873151461 & 4294967295;
    g2 = a + (b2 << 11 & 4294967295 | b2 >>> 21);
    b2 = e + (g2 ^ a ^ c) + d[15] + 530742520 & 4294967295;
    e = g2 + (b2 << 16 & 4294967295 | b2 >>> 16);
    b2 = c + (e ^ g2 ^ a) + d[2] + 3299628645 & 4294967295;
    c = e + (b2 << 23 & 4294967295 | b2 >>> 9);
    b2 = a + (e ^ (c | ~g2)) + d[0] + 4096336452 & 4294967295;
    a = c + (b2 << 6 & 4294967295 | b2 >>> 26);
    b2 = g2 + (c ^ (a | ~e)) + d[7] + 1126891415 & 4294967295;
    g2 = a + (b2 << 10 & 4294967295 | b2 >>> 22);
    b2 = e + (a ^ (g2 | ~c)) + d[14] + 2878612391 & 4294967295;
    e = g2 + (b2 << 15 & 4294967295 | b2 >>> 17);
    b2 = c + (g2 ^ (e | ~a)) + d[5] + 4237533241 & 4294967295;
    c = e + (b2 << 21 & 4294967295 | b2 >>> 11);
    b2 = a + (e ^ (c | ~g2)) + d[12] + 1700485571 & 4294967295;
    a = c + (b2 << 6 & 4294967295 | b2 >>> 26);
    b2 = g2 + (c ^ (a | ~e)) + d[3] + 2399980690 & 4294967295;
    g2 = a + (b2 << 10 & 4294967295 | b2 >>> 22);
    b2 = e + (a ^ (g2 | ~c)) + d[10] + 4293915773 & 4294967295;
    e = g2 + (b2 << 15 & 4294967295 | b2 >>> 17);
    b2 = c + (g2 ^ (e | ~a)) + d[1] + 2240044497 & 4294967295;
    c = e + (b2 << 21 & 4294967295 | b2 >>> 11);
    b2 = a + (e ^ (c | ~g2)) + d[8] + 1873313359 & 4294967295;
    a = c + (b2 << 6 & 4294967295 | b2 >>> 26);
    b2 = g2 + (c ^ (a | ~e)) + d[15] + 4264355552 & 4294967295;
    g2 = a + (b2 << 10 & 4294967295 | b2 >>> 22);
    b2 = e + (a ^ (g2 | ~c)) + d[6] + 2734768916 & 4294967295;
    e = g2 + (b2 << 15 & 4294967295 | b2 >>> 17);
    b2 = c + (g2 ^ (e | ~a)) + d[13] + 1309151649 & 4294967295;
    c = e + (b2 << 21 & 4294967295 | b2 >>> 11);
    b2 = a + (e ^ (c | ~g2)) + d[4] + 4149444226 & 4294967295;
    a = c + (b2 << 6 & 4294967295 | b2 >>> 26);
    b2 = g2 + (c ^ (a | ~e)) + d[11] + 3174756917 & 4294967295;
    g2 = a + (b2 << 10 & 4294967295 | b2 >>> 22);
    b2 = e + (a ^ (g2 | ~c)) + d[2] + 718787259 & 4294967295;
    e = g2 + (b2 << 15 & 4294967295 | b2 >>> 17);
    b2 = c + (g2 ^ (e | ~a)) + d[9] + 3951481745 & 4294967295;
    f.g[0] = f.g[0] + a & 4294967295;
    f.g[1] = f.g[1] + (e + (b2 << 21 & 4294967295 | b2 >>> 11)) & 4294967295;
    f.g[2] = f.g[2] + e & 4294967295;
    f.g[3] = f.g[3] + g2 & 4294967295;
  }
  m.prototype.u = function(f, a) {
    void 0 === a && (a = f.length);
    for (var c = a - this.blockSize, d = this.B, e = this.h, g2 = 0; g2 < a; ) {
      if (0 == e) for (; g2 <= c; ) n(this, f, g2), g2 += this.blockSize;
      if ("string" === typeof f) for (; g2 < a; ) {
        if (d[e++] = f.charCodeAt(g2++), e == this.blockSize) {
          n(this, d);
          e = 0;
          break;
        }
      }
      else for (; g2 < a; ) if (d[e++] = f[g2++], e == this.blockSize) {
        n(this, d);
        e = 0;
        break;
      }
    }
    this.h = e;
    this.o += a;
  };
  m.prototype.v = function() {
    var f = Array((56 > this.h ? this.blockSize : 2 * this.blockSize) - this.h);
    f[0] = 128;
    for (var a = 1; a < f.length - 8; ++a) f[a] = 0;
    var c = 8 * this.o;
    for (a = f.length - 8; a < f.length; ++a) f[a] = c & 255, c /= 256;
    this.u(f);
    f = Array(16);
    for (a = c = 0; 4 > a; ++a) for (var d = 0; 32 > d; d += 8) f[c++] = this.g[a] >>> d & 255;
    return f;
  };
  function p2(f, a) {
    var c = q3;
    return Object.prototype.hasOwnProperty.call(c, f) ? c[f] : c[f] = a(f);
  }
  function t(f, a) {
    this.h = a;
    for (var c = [], d = true, e = f.length - 1; 0 <= e; e--) {
      var g2 = f[e] | 0;
      d && g2 == a || (c[e] = g2, d = false);
    }
    this.g = c;
  }
  var q3 = {};
  function u(f) {
    return -128 <= f && 128 > f ? p2(f, function(a) {
      return new t([a | 0], 0 > a ? -1 : 0);
    }) : new t([f | 0], 0 > f ? -1 : 0);
  }
  function v2(f) {
    if (isNaN(f) || !isFinite(f)) return w2;
    if (0 > f) return x2(v2(-f));
    for (var a = [], c = 1, d = 0; f >= c; d++) a[d] = f / c | 0, c *= 4294967296;
    return new t(a, 0);
  }
  function y2(f, a) {
    if (0 == f.length) throw Error("number format error: empty string");
    a = a || 10;
    if (2 > a || 36 < a) throw Error("radix out of range: " + a);
    if ("-" == f.charAt(0)) return x2(y2(f.substring(1), a));
    if (0 <= f.indexOf("-")) throw Error('number format error: interior "-" character');
    for (var c = v2(Math.pow(a, 8)), d = w2, e = 0; e < f.length; e += 8) {
      var g2 = Math.min(8, f.length - e), b2 = parseInt(f.substring(e, e + g2), a);
      8 > g2 ? (g2 = v2(Math.pow(a, g2)), d = d.j(g2).add(v2(b2))) : (d = d.j(c), d = d.add(v2(b2)));
    }
    return d;
  }
  var w2 = u(0), z2 = u(1), A2 = u(16777216);
  h = t.prototype;
  h.m = function() {
    if (B2(this)) return -x2(this).m();
    for (var f = 0, a = 1, c = 0; c < this.g.length; c++) {
      var d = this.i(c);
      f += (0 <= d ? d : 4294967296 + d) * a;
      a *= 4294967296;
    }
    return f;
  };
  h.toString = function(f) {
    f = f || 10;
    if (2 > f || 36 < f) throw Error("radix out of range: " + f);
    if (C2(this)) return "0";
    if (B2(this)) return "-" + x2(this).toString(f);
    for (var a = v2(Math.pow(f, 6)), c = this, d = ""; ; ) {
      var e = D2(c, a).g;
      c = F(c, e.j(a));
      var g2 = ((0 < c.g.length ? c.g[0] : c.h) >>> 0).toString(f);
      c = e;
      if (C2(c)) return g2 + d;
      for (; 6 > g2.length; ) g2 = "0" + g2;
      d = g2 + d;
    }
  };
  h.i = function(f) {
    return 0 > f ? 0 : f < this.g.length ? this.g[f] : this.h;
  };
  function C2(f) {
    if (0 != f.h) return false;
    for (var a = 0; a < f.g.length; a++) if (0 != f.g[a]) return false;
    return true;
  }
  function B2(f) {
    return -1 == f.h;
  }
  h.l = function(f) {
    f = F(this, f);
    return B2(f) ? -1 : C2(f) ? 0 : 1;
  };
  function x2(f) {
    for (var a = f.g.length, c = [], d = 0; d < a; d++) c[d] = ~f.g[d];
    return new t(c, ~f.h).add(z2);
  }
  h.abs = function() {
    return B2(this) ? x2(this) : this;
  };
  h.add = function(f) {
    for (var a = Math.max(this.g.length, f.g.length), c = [], d = 0, e = 0; e <= a; e++) {
      var g2 = d + (this.i(e) & 65535) + (f.i(e) & 65535), b2 = (g2 >>> 16) + (this.i(e) >>> 16) + (f.i(e) >>> 16);
      d = b2 >>> 16;
      g2 &= 65535;
      b2 &= 65535;
      c[e] = b2 << 16 | g2;
    }
    return new t(c, c[c.length - 1] & -2147483648 ? -1 : 0);
  };
  function F(f, a) {
    return f.add(x2(a));
  }
  h.j = function(f) {
    if (C2(this) || C2(f)) return w2;
    if (B2(this)) return B2(f) ? x2(this).j(x2(f)) : x2(x2(this).j(f));
    if (B2(f)) return x2(this.j(x2(f)));
    if (0 > this.l(A2) && 0 > f.l(A2)) return v2(this.m() * f.m());
    for (var a = this.g.length + f.g.length, c = [], d = 0; d < 2 * a; d++) c[d] = 0;
    for (d = 0; d < this.g.length; d++) for (var e = 0; e < f.g.length; e++) {
      var g2 = this.i(d) >>> 16, b2 = this.i(d) & 65535, r = f.i(e) >>> 16, E = f.i(e) & 65535;
      c[2 * d + 2 * e] += b2 * E;
      G2(c, 2 * d + 2 * e);
      c[2 * d + 2 * e + 1] += g2 * E;
      G2(c, 2 * d + 2 * e + 1);
      c[2 * d + 2 * e + 1] += b2 * r;
      G2(c, 2 * d + 2 * e + 1);
      c[2 * d + 2 * e + 2] += g2 * r;
      G2(c, 2 * d + 2 * e + 2);
    }
    for (d = 0; d < a; d++) c[d] = c[2 * d + 1] << 16 | c[2 * d];
    for (d = a; d < 2 * a; d++) c[d] = 0;
    return new t(c, 0);
  };
  function G2(f, a) {
    for (; (f[a] & 65535) != f[a]; ) f[a + 1] += f[a] >>> 16, f[a] &= 65535, a++;
  }
  function H2(f, a) {
    this.g = f;
    this.h = a;
  }
  function D2(f, a) {
    if (C2(a)) throw Error("division by zero");
    if (C2(f)) return new H2(w2, w2);
    if (B2(f)) return a = D2(x2(f), a), new H2(x2(a.g), x2(a.h));
    if (B2(a)) return a = D2(f, x2(a)), new H2(x2(a.g), a.h);
    if (30 < f.g.length) {
      if (B2(f) || B2(a)) throw Error("slowDivide_ only works with positive integers.");
      for (var c = z2, d = a; 0 >= d.l(f); ) c = I2(c), d = I2(d);
      var e = J2(c, 1), g2 = J2(d, 1);
      d = J2(d, 2);
      for (c = J2(c, 2); !C2(d); ) {
        var b2 = g2.add(d);
        0 >= b2.l(f) && (e = e.add(c), g2 = b2);
        d = J2(d, 1);
        c = J2(c, 1);
      }
      a = F(f, e.j(a));
      return new H2(e, a);
    }
    for (e = w2; 0 <= f.l(a); ) {
      c = Math.max(1, Math.floor(f.m() / a.m()));
      d = Math.ceil(Math.log(c) / Math.LN2);
      d = 48 >= d ? 1 : Math.pow(2, d - 48);
      g2 = v2(c);
      for (b2 = g2.j(a); B2(b2) || 0 < b2.l(f); ) c -= d, g2 = v2(c), b2 = g2.j(a);
      C2(g2) && (g2 = z2);
      e = e.add(g2);
      f = F(f, b2);
    }
    return new H2(e, f);
  }
  h.A = function(f) {
    return D2(this, f).h;
  };
  h.and = function(f) {
    for (var a = Math.max(this.g.length, f.g.length), c = [], d = 0; d < a; d++) c[d] = this.i(d) & f.i(d);
    return new t(c, this.h & f.h);
  };
  h.or = function(f) {
    for (var a = Math.max(this.g.length, f.g.length), c = [], d = 0; d < a; d++) c[d] = this.i(d) | f.i(d);
    return new t(c, this.h | f.h);
  };
  h.xor = function(f) {
    for (var a = Math.max(this.g.length, f.g.length), c = [], d = 0; d < a; d++) c[d] = this.i(d) ^ f.i(d);
    return new t(c, this.h ^ f.h);
  };
  function I2(f) {
    for (var a = f.g.length + 1, c = [], d = 0; d < a; d++) c[d] = f.i(d) << 1 | f.i(d - 1) >>> 31;
    return new t(c, f.h);
  }
  function J2(f, a) {
    var c = a >> 5;
    a %= 32;
    for (var d = f.g.length - c, e = [], g2 = 0; g2 < d; g2++) e[g2] = 0 < a ? f.i(g2 + c) >>> a | f.i(g2 + c + 1) << 32 - a : f.i(g2 + c);
    return new t(e, f.h);
  }
  m.prototype.digest = m.prototype.v;
  m.prototype.reset = m.prototype.s;
  m.prototype.update = m.prototype.u;
  Md5 = bloom_blob_es2018.Md5 = m;
  t.prototype.add = t.prototype.add;
  t.prototype.multiply = t.prototype.j;
  t.prototype.modulo = t.prototype.A;
  t.prototype.compare = t.prototype.l;
  t.prototype.toNumber = t.prototype.m;
  t.prototype.toString = t.prototype.toString;
  t.prototype.getBits = t.prototype.i;
  t.fromNumber = v2;
  t.fromString = y2;
  Integer = bloom_blob_es2018.Integer = t;
}).apply(typeof commonjsGlobal !== "undefined" ? commonjsGlobal : typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : {});

// node_modules/@firebase/firestore/dist/lite/index.browser.esm.js
var P = "4.9.0";
var User = class {
  constructor(t) {
    this.uid = t;
  }
  isAuthenticated() {
    return null != this.uid;
  }
  /**
   * Returns a key representing this user, suitable for inclusion in a
   * dictionary.
   */
  toKey() {
    return this.isAuthenticated() ? "uid:" + this.uid : "anonymous-user";
  }
  isEqual(t) {
    return t.uid === this.uid;
  }
};
User.UNAUTHENTICATED = new User(null), // TODO(mikelehen): Look into getting a proper uid-equivalent for
// non-FirebaseAuth providers.
User.GOOGLE_CREDENTIALS = new User("google-credentials-uid"), User.FIRST_PARTY = new User("first-party-uid"), User.MOCK_USER = new User("mock-user");
var A = "12.0.0";
var R = new Logger("@firebase/firestore");
function __PRIVATE_logDebug(t, ...e) {
  if (R.logLevel <= LogLevel.DEBUG) {
    const r = e.map(__PRIVATE_argToString);
    R.debug(`Firestore (${A}): ${t}`, ...r);
  }
}
function __PRIVATE_logError(t, ...e) {
  if (R.logLevel <= LogLevel.ERROR) {
    const r = e.map(__PRIVATE_argToString);
    R.error(`Firestore (${A}): ${t}`, ...r);
  }
}
function __PRIVATE_logWarn(t, ...e) {
  if (R.logLevel <= LogLevel.WARN) {
    const r = e.map(__PRIVATE_argToString);
    R.warn(`Firestore (${A}): ${t}`, ...r);
  }
}
function __PRIVATE_argToString(t) {
  if ("string" == typeof t) return t;
  try {
    return (function __PRIVATE_formatJSON(t2) {
      return JSON.stringify(t2);
    })(t);
  } catch (e) {
    return t;
  }
}
function fail(t, e, r) {
  let n = "Unexpected state";
  "string" == typeof e ? n = e : r = e, __PRIVATE__fail(t, n, r);
}
function __PRIVATE__fail(t, e, r) {
  let n = `FIRESTORE (${A}) INTERNAL ASSERTION FAILED: ${e} (ID: ${t.toString(16)})`;
  if (void 0 !== r) try {
    n += " CONTEXT: " + JSON.stringify(r);
  } catch (t2) {
    n += " CONTEXT: " + r;
  }
  throw __PRIVATE_logError(n), new Error(n);
}
function __PRIVATE_hardAssert(t, e, r, n) {
  let i = "Unexpected state";
  "string" == typeof r ? i = r : n = r, t || __PRIVATE__fail(e, i, n);
}
function __PRIVATE_debugCast(t, e) {
  return t;
}
var V = "ok";
var I = "cancelled";
var p = "unknown";
var y = "invalid-argument";
var g = "deadline-exceeded";
var w = "not-found";
var v = "permission-denied";
var D = "unauthenticated";
var b = "resource-exhausted";
var S = "failed-precondition";
var C = "aborted";
var N = "out-of-range";
var O = "unimplemented";
var q = "internal";
var B = "unavailable";
var FirestoreError = class extends FirebaseError {
  /** @hideconstructor */
  constructor(t, e) {
    super(t, e), this.code = t, this.message = e, // HACK: We write a toString property directly because Error is not a real
    // class and so inheritance does not work correctly. We could alternatively
    // do the same "back-door inheritance" trick that FirebaseError does.
    this.toString = () => `${this.name}: [code=${this.code}]: ${this.message}`;
  }
};
var __PRIVATE_OAuthToken = class {
  constructor(t, e) {
    this.user = e, this.type = "OAuth", this.headers = /* @__PURE__ */ new Map(), this.headers.set("Authorization", `Bearer ${t}`);
  }
};
var __PRIVATE_EmptyAuthCredentialsProvider = class {
  getToken() {
    return Promise.resolve(null);
  }
  invalidateToken() {
  }
  start(t, e) {
    t.enqueueRetryable((() => e(User.UNAUTHENTICATED)));
  }
  shutdown() {
  }
};
var __PRIVATE_EmulatorAuthCredentialsProvider = class {
  constructor(t) {
    this.token = t, /**
     * Stores the listener registered with setChangeListener()
     * This isn't actually necessary since the UID never changes, but we use this
     * to verify the listen contract is adhered to in tests.
     */
    this.changeListener = null;
  }
  getToken() {
    return Promise.resolve(this.token);
  }
  invalidateToken() {
  }
  start(t, e) {
    this.changeListener = e, // Fire with initial user.
    t.enqueueRetryable((() => e(this.token.user)));
  }
  shutdown() {
    this.changeListener = null;
  }
};
var __PRIVATE_LiteAuthCredentialsProvider = class {
  constructor(t) {
    this.auth = null, t.onInit(((t2) => {
      this.auth = t2;
    }));
  }
  getToken() {
    return this.auth ? this.auth.getToken().then(((t) => t ? (__PRIVATE_hardAssert("string" == typeof t.accessToken, 42297, {
      t
    }), new __PRIVATE_OAuthToken(t.accessToken, new User(this.auth.getUid()))) : null)) : Promise.resolve(null);
  }
  invalidateToken() {
  }
  start(t, e) {
  }
  shutdown() {
  }
};
var __PRIVATE_FirstPartyToken = class {
  constructor(t, e, r) {
    this.i = t, this.o = e, this.u = r, this.type = "FirstParty", this.user = User.FIRST_PARTY, this.l = /* @__PURE__ */ new Map();
  }
  /**
   * Gets an authorization token, using a provided factory function, or return
   * null.
   */
  h() {
    return this.u ? this.u() : null;
  }
  get headers() {
    this.l.set("X-Goog-AuthUser", this.i);
    const t = this.h();
    return t && this.l.set("Authorization", t), this.o && this.l.set("X-Goog-Iam-Authorization-Token", this.o), this.l;
  }
};
var __PRIVATE_FirstPartyAuthCredentialsProvider = class {
  constructor(t, e, r) {
    this.i = t, this.o = e, this.u = r;
  }
  getToken() {
    return Promise.resolve(new __PRIVATE_FirstPartyToken(this.i, this.o, this.u));
  }
  start(t, e) {
    t.enqueueRetryable((() => e(User.FIRST_PARTY)));
  }
  shutdown() {
  }
  invalidateToken() {
  }
};
var AppCheckToken = class {
  constructor(t) {
    this.value = t, this.type = "AppCheck", this.headers = /* @__PURE__ */ new Map(), t && t.length > 0 && this.headers.set("x-firebase-appcheck", this.value);
  }
};
var __PRIVATE_LiteAppCheckTokenProvider = class {
  constructor(e, r) {
    this.m = r, this.appCheck = null, this.T = null, _isFirebaseServerApp(e) && e.settings.appCheckToken && (this.T = e.settings.appCheckToken), r.onInit(((t) => {
      this.appCheck = t;
    }));
  }
  getToken() {
    return this.T ? Promise.resolve(new AppCheckToken(this.T)) : this.appCheck ? this.appCheck.getToken().then(((t) => t ? (__PRIVATE_hardAssert("string" == typeof t.token, 3470, {
      tokenResult: t
    }), new AppCheckToken(t.token)) : null)) : Promise.resolve(null);
  }
  invalidateToken() {
  }
  start(t, e) {
  }
  shutdown() {
  }
};
var DatabaseInfo = class {
  /**
   * Constructs a DatabaseInfo using the provided host, databaseId and
   * persistenceKey.
   *
   * @param databaseId - The database to use.
   * @param appId - The Firebase App Id.
   * @param persistenceKey - A unique identifier for this Firestore's local
   * storage (used in conjunction with the databaseId).
   * @param host - The Firestore backend host to connect to.
   * @param ssl - Whether to use SSL when connecting.
   * @param forceLongPolling - Whether to use the forceLongPolling option
   * when using WebChannel as the network transport.
   * @param autoDetectLongPolling - Whether to use the detectBufferingProxy
   * option when using WebChannel as the network transport.
   * @param longPollingOptions Options that configure long-polling.
   * @param useFetchStreams Whether to use the Fetch API instead of
   * XMLHTTPRequest
   */
  constructor(t, e, r, n, i, s, o, a, u, _) {
    this.databaseId = t, this.appId = e, this.persistenceKey = r, this.host = n, this.ssl = i, this.forceLongPolling = s, this.autoDetectLongPolling = o, this.longPollingOptions = a, this.useFetchStreams = u, this.isUsingEmulator = _;
  }
};
var Q = "(default)";
var DatabaseId = class _DatabaseId {
  constructor(t, e) {
    this.projectId = t, this.database = e || Q;
  }
  static empty() {
    return new _DatabaseId("", "");
  }
  get isDefaultDatabase() {
    return this.database === Q;
  }
  isEqual(t) {
    return t instanceof _DatabaseId && t.projectId === this.projectId && t.database === this.database;
  }
};
function __PRIVATE_randomBytes(t) {
  const e = (
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    "undefined" != typeof self && (self.crypto || self.msCrypto)
  ), r = new Uint8Array(t);
  if (e && "function" == typeof e.getRandomValues) e.getRandomValues(r);
  else
    for (let e2 = 0; e2 < t; e2++) r[e2] = Math.floor(256 * Math.random());
  return r;
}
var __PRIVATE_AutoId = class {
  static newId() {
    const t = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", e = 62 * Math.floor(256 / 62);
    let r = "";
    for (; r.length < 20; ) {
      const n = __PRIVATE_randomBytes(40);
      for (let i = 0; i < n.length; ++i)
        r.length < 20 && n[i] < e && (r += t.charAt(n[i] % 62));
    }
    return r;
  }
};
function __PRIVATE_primitiveComparator(t, e) {
  return t < e ? -1 : t > e ? 1 : 0;
}
function __PRIVATE_compareUtf8Strings(t, e) {
  const r = Math.min(t.length, e.length);
  for (let n = 0; n < r; n++) {
    const r2 = t.charAt(n), i = e.charAt(n);
    if (r2 !== i) return __PRIVATE_isSurrogate(r2) === __PRIVATE_isSurrogate(i) ? __PRIVATE_primitiveComparator(r2, i) : __PRIVATE_isSurrogate(r2) ? 1 : -1;
  }
  return __PRIVATE_primitiveComparator(t.length, e.length);
}
var k = 55296;
var L = 57343;
function __PRIVATE_isSurrogate(t) {
  const e = t.charCodeAt(0);
  return e >= k && e <= L;
}
function __PRIVATE_arrayEquals(t, e, r) {
  return t.length === e.length && t.every(((t2, n) => r(t2, e[n])));
}
var M = "__name__";
var BasePath = class _BasePath {
  constructor(t, e, r) {
    void 0 === e ? e = 0 : e > t.length && fail(637, {
      offset: e,
      range: t.length
    }), void 0 === r ? r = t.length - e : r > t.length - e && fail(1746, {
      length: r,
      range: t.length - e
    }), this.segments = t, this.offset = e, this.len = r;
  }
  get length() {
    return this.len;
  }
  isEqual(t) {
    return 0 === _BasePath.comparator(this, t);
  }
  child(t) {
    const e = this.segments.slice(this.offset, this.limit());
    return t instanceof _BasePath ? t.forEach(((t2) => {
      e.push(t2);
    })) : e.push(t), this.construct(e);
  }
  /** The index of one past the last segment of the path. */
  limit() {
    return this.offset + this.length;
  }
  popFirst(t) {
    return t = void 0 === t ? 1 : t, this.construct(this.segments, this.offset + t, this.length - t);
  }
  popLast() {
    return this.construct(this.segments, this.offset, this.length - 1);
  }
  firstSegment() {
    return this.segments[this.offset];
  }
  lastSegment() {
    return this.get(this.length - 1);
  }
  get(t) {
    return this.segments[this.offset + t];
  }
  isEmpty() {
    return 0 === this.length;
  }
  isPrefixOf(t) {
    if (t.length < this.length) return false;
    for (let e = 0; e < this.length; e++) if (this.get(e) !== t.get(e)) return false;
    return true;
  }
  isImmediateParentOf(t) {
    if (this.length + 1 !== t.length) return false;
    for (let e = 0; e < this.length; e++) if (this.get(e) !== t.get(e)) return false;
    return true;
  }
  forEach(t) {
    for (let e = this.offset, r = this.limit(); e < r; e++) t(this.segments[e]);
  }
  toArray() {
    return this.segments.slice(this.offset, this.limit());
  }
  /**
   * Compare 2 paths segment by segment, prioritizing numeric IDs
   * (e.g., "__id123__") in numeric ascending order, followed by string
   * segments in lexicographical order.
   */
  static comparator(t, e) {
    const r = Math.min(t.length, e.length);
    for (let n = 0; n < r; n++) {
      const r2 = _BasePath.compareSegments(t.get(n), e.get(n));
      if (0 !== r2) return r2;
    }
    return __PRIVATE_primitiveComparator(t.length, e.length);
  }
  static compareSegments(t, e) {
    const r = _BasePath.isNumericId(t), n = _BasePath.isNumericId(e);
    return r && !n ? -1 : !r && n ? 1 : r && n ? _BasePath.extractNumericId(t).compare(_BasePath.extractNumericId(e)) : __PRIVATE_compareUtf8Strings(t, e);
  }
  // Checks if a segment is a numeric ID (starts with "__id" and ends with "__").
  static isNumericId(t) {
    return t.startsWith("__id") && t.endsWith("__");
  }
  static extractNumericId(t) {
    return Integer.fromString(t.substring(4, t.length - 2));
  }
};
var ResourcePath = class _ResourcePath extends BasePath {
  construct(t, e, r) {
    return new _ResourcePath(t, e, r);
  }
  canonicalString() {
    return this.toArray().join("/");
  }
  toString() {
    return this.canonicalString();
  }
  /**
   * Returns a string representation of this path
   * where each path segment has been encoded with
   * `encodeURIComponent`.
   */
  toUriEncodedString() {
    return this.toArray().map(encodeURIComponent).join("/");
  }
  /**
   * Creates a resource path from the given slash-delimited string. If multiple
   * arguments are provided, all components are combined. Leading and trailing
   * slashes from all components are ignored.
   */
  static fromString(...t) {
    const e = [];
    for (const r of t) {
      if (r.indexOf("//") >= 0) throw new FirestoreError(y, `Invalid segment (${r}). Paths must not contain // in them.`);
      e.push(...r.split("/").filter(((t2) => t2.length > 0)));
    }
    return new _ResourcePath(e);
  }
  static emptyPath() {
    return new _ResourcePath([]);
  }
};
var x = /^[_a-zA-Z][_a-zA-Z0-9]*$/;
var FieldPath$1 = class _FieldPath$1 extends BasePath {
  construct(t, e, r) {
    return new _FieldPath$1(t, e, r);
  }
  /**
   * Returns true if the string could be used as a segment in a field path
   * without escaping.
   */
  static isValidIdentifier(t) {
    return x.test(t);
  }
  canonicalString() {
    return this.toArray().map(((t) => (t = t.replace(/\\/g, "\\\\").replace(/`/g, "\\`"), _FieldPath$1.isValidIdentifier(t) || (t = "`" + t + "`"), t))).join(".");
  }
  toString() {
    return this.canonicalString();
  }
  /**
   * Returns true if this field references the key of a document.
   */
  isKeyField() {
    return 1 === this.length && this.get(0) === M;
  }
  /**
   * The field designating the key of a document.
   */
  static keyField() {
    return new _FieldPath$1([M]);
  }
  /**
   * Parses a field string from the given server-formatted string.
   *
   * - Splitting the empty string is not allowed (for now at least).
   * - Empty segments within the string (e.g. if there are two consecutive
   *   separators) are not allowed.
   *
   * TODO(b/37244157): we should make this more strict. Right now, it allows
   * non-identifier path components, even if they aren't escaped.
   */
  static fromServerFormat(t) {
    const e = [];
    let r = "", n = 0;
    const __PRIVATE_addCurrentSegment = () => {
      if (0 === r.length) throw new FirestoreError(y, `Invalid field path (${t}). Paths must not be empty, begin with '.', end with '.', or contain '..'`);
      e.push(r), r = "";
    };
    let i = false;
    for (; n < t.length; ) {
      const e2 = t[n];
      if ("\\" === e2) {
        if (n + 1 === t.length) throw new FirestoreError(y, "Path has trailing escape character: " + t);
        const e3 = t[n + 1];
        if ("\\" !== e3 && "." !== e3 && "`" !== e3) throw new FirestoreError(y, "Path has invalid escape sequence: " + t);
        r += e3, n += 2;
      } else "`" === e2 ? (i = !i, n++) : "." !== e2 || i ? (r += e2, n++) : (__PRIVATE_addCurrentSegment(), n++);
    }
    if (__PRIVATE_addCurrentSegment(), i) throw new FirestoreError(y, "Unterminated ` in path: " + t);
    return new _FieldPath$1(e);
  }
  static emptyPath() {
    return new _FieldPath$1([]);
  }
};
var DocumentKey = class _DocumentKey {
  constructor(t) {
    this.path = t;
  }
  static fromPath(t) {
    return new _DocumentKey(ResourcePath.fromString(t));
  }
  static fromName(t) {
    return new _DocumentKey(ResourcePath.fromString(t).popFirst(5));
  }
  static empty() {
    return new _DocumentKey(ResourcePath.emptyPath());
  }
  get collectionGroup() {
    return this.path.popLast().lastSegment();
  }
  /** Returns true if the document is in the specified collectionId. */
  hasCollectionId(t) {
    return this.path.length >= 2 && this.path.get(this.path.length - 2) === t;
  }
  /** Returns the collection group (i.e. the name of the parent collection) for this key. */
  getCollectionGroup() {
    return this.path.get(this.path.length - 2);
  }
  /** Returns the fully qualified path to the parent collection. */
  getCollectionPath() {
    return this.path.popLast();
  }
  isEqual(t) {
    return null !== t && 0 === ResourcePath.comparator(this.path, t.path);
  }
  toString() {
    return this.path.toString();
  }
  static comparator(t, e) {
    return ResourcePath.comparator(t.path, e.path);
  }
  static isDocumentKey(t) {
    return t.length % 2 == 0;
  }
  /**
   * Creates and returns a new document key with the given segments.
   *
   * @param segments - The segments of the path to the document
   * @returns A new instance of DocumentKey
   */
  static fromSegments(t) {
    return new _DocumentKey(new ResourcePath(t.slice()));
  }
};
function __PRIVATE_validateNonEmptyArgument(t, e, r) {
  if (!r) throw new FirestoreError(y, `Function ${t}() cannot be called with an empty ${e}.`);
}
function __PRIVATE_validateDocumentPath(t) {
  if (!DocumentKey.isDocumentKey(t)) throw new FirestoreError(y, `Invalid document reference. Document references must have an even number of segments, but ${t} has ${t.length}.`);
}
function __PRIVATE_isPlainObject(t) {
  return "object" == typeof t && null !== t && (Object.getPrototypeOf(t) === Object.prototype || null === Object.getPrototypeOf(t));
}
function __PRIVATE_valueDescription(t) {
  if (void 0 === t) return "undefined";
  if (null === t) return "null";
  if ("string" == typeof t) return t.length > 20 && (t = `${t.substring(0, 20)}...`), JSON.stringify(t);
  if ("number" == typeof t || "boolean" == typeof t) return "" + t;
  if ("object" == typeof t) {
    if (t instanceof Array) return "an array";
    {
      const e = (
        /** try to get the constructor name for an object. */
        (function __PRIVATE_tryGetCustomObjectType(t2) {
          if (t2.constructor) return t2.constructor.name;
          return null;
        })(t)
      );
      return e ? `a custom ${e} object` : "an object";
    }
  }
  return "function" == typeof t ? "a function" : fail(12329, {
    type: typeof t
  });
}
function __PRIVATE_cast(t, e) {
  if ("_delegate" in t && // Unwrap Compat types
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (t = t._delegate), !(t instanceof e)) {
    if (e.name === t.constructor.name) throw new FirestoreError(y, "Type does not match the expected instance. Did you pass a reference from a different Firestore SDK?");
    {
      const r = __PRIVATE_valueDescription(t);
      throw new FirestoreError(y, `Expected type '${e.name}', but it was: ${r}`);
    }
  }
  return t;
}
function __PRIVATE_cloneLongPollingOptions(t) {
  const e = {};
  return void 0 !== t.timeoutSeconds && (e.timeoutSeconds = t.timeoutSeconds), e;
}
var U = null;
function __PRIVATE_generateUniqueDebugId() {
  return null === U ? U = (function __PRIVATE_generateInitialUniqueDebugId() {
    return 268435456 + Math.round(2147483648 * Math.random());
  })() : U++, "0x" + U.toString(16);
}
function __PRIVATE_isNegativeZero(t) {
  return 0 === t && 1 / t == -1 / 0;
}
var j = "RestConnection";
var z = {
  BatchGetDocuments: "batchGet",
  Commit: "commit",
  RunQuery: "runQuery",
  RunAggregationQuery: "runAggregationQuery"
};
var __PRIVATE_RestConnection = class {
  get P() {
    return false;
  }
  constructor(t) {
    this.databaseInfo = t, this.databaseId = t.databaseId;
    const e = t.ssl ? "https" : "http", r = encodeURIComponent(this.databaseId.projectId), n = encodeURIComponent(this.databaseId.database);
    this.A = e + "://" + t.host, this.R = `projects/${r}/databases/${n}`, this.V = this.databaseId.database === Q ? `project_id=${r}` : `project_id=${r}&database_id=${n}`;
  }
  I(t, e, r, n, i) {
    const s = __PRIVATE_generateUniqueDebugId(), o = this.p(t, e.toUriEncodedString());
    __PRIVATE_logDebug(j, `Sending RPC '${t}' ${s}:`, o, r);
    const a = {
      "google-cloud-resource-prefix": this.R,
      "x-goog-request-params": this.V
    };
    this.F(a, n, i);
    const { host: u } = new URL(o), _ = isCloudWorkstation(u);
    return this.v(t, o, a, r, _).then(((e2) => (__PRIVATE_logDebug(j, `Received RPC '${t}' ${s}: `, e2), e2)), ((e2) => {
      throw __PRIVATE_logWarn(j, `RPC '${t}' ${s} failed with error: `, e2, "url: ", o, "request:", r), e2;
    }));
  }
  D(t, e, r, n, i, s) {
    return this.I(t, e, r, n, i);
  }
  /**
   * Modifies the headers for a request, adding any authorization token if
   * present and any additional headers for the request.
   */
  F(t, e, r) {
    t["X-Goog-Api-Client"] = // SDK_VERSION is updated to different value at runtime depending on the entry point,
    // so we need to get its value when we need it in a function.
    (function __PRIVATE_getGoogApiClientValue() {
      return "gl-js/ fire/" + A;
    })(), // Content-Type: text/plain will avoid preflight requests which might
    // mess with CORS and redirects by proxies. If we add custom headers
    // we will need to change this code to potentially use the $httpOverwrite
    // parameter supported by ESF to avoid triggering preflight requests.
    t["Content-Type"] = "text/plain", this.databaseInfo.appId && (t["X-Firebase-GMPID"] = this.databaseInfo.appId), e && e.headers.forEach(((e2, r2) => t[r2] = e2)), r && r.headers.forEach(((e2, r2) => t[r2] = e2));
  }
  p(t, e) {
    const r = z[t];
    return `${this.A}/v1/${e}:${r}`;
  }
  /**
   * Closes and cleans up any resources associated with the connection. This
   * implementation is a no-op because there are no resources associated
   * with the RestConnection that need to be cleaned up.
   */
  terminate() {
  }
};
var W;
var K;
function __PRIVATE_mapCodeFromHttpStatus(t) {
  if (void 0 === t) return __PRIVATE_logError("RPC_ERROR", "HTTP error has no status"), p;
  switch (t) {
    case 200:
      return V;
    case 400:
      return S;
    // Other possibilities based on the forward mapping
    // return Code.INVALID_ARGUMENT;
    // return Code.OUT_OF_RANGE;
    case 401:
      return D;
    case 403:
      return v;
    case 404:
      return w;
    case 409:
      return C;
    // Other possibilities:
    // return Code.ALREADY_EXISTS;
    case 416:
      return N;
    case 429:
      return b;
    case 499:
      return I;
    case 500:
      return p;
    // Other possibilities:
    // return Code.INTERNAL;
    // return Code.DATA_LOSS;
    case 501:
      return O;
    case 503:
      return B;
    case 504:
      return g;
    default:
      return t >= 200 && t < 300 ? V : t >= 400 && t < 500 ? S : t >= 500 && t < 600 ? q : p;
  }
}
(K = W || (W = {}))[K.OK = 0] = "OK", K[K.CANCELLED = 1] = "CANCELLED", K[K.UNKNOWN = 2] = "UNKNOWN", K[K.INVALID_ARGUMENT = 3] = "INVALID_ARGUMENT", K[K.DEADLINE_EXCEEDED = 4] = "DEADLINE_EXCEEDED", K[K.NOT_FOUND = 5] = "NOT_FOUND", K[K.ALREADY_EXISTS = 6] = "ALREADY_EXISTS", K[K.PERMISSION_DENIED = 7] = "PERMISSION_DENIED", K[K.UNAUTHENTICATED = 16] = "UNAUTHENTICATED", K[K.RESOURCE_EXHAUSTED = 8] = "RESOURCE_EXHAUSTED", K[K.FAILED_PRECONDITION = 9] = "FAILED_PRECONDITION", K[K.ABORTED = 10] = "ABORTED", K[K.OUT_OF_RANGE = 11] = "OUT_OF_RANGE", K[K.UNIMPLEMENTED = 12] = "UNIMPLEMENTED", K[K.INTERNAL = 13] = "INTERNAL", K[K.UNAVAILABLE = 14] = "UNAVAILABLE", K[K.DATA_LOSS = 15] = "DATA_LOSS";
var __PRIVATE_FetchConnection = class extends __PRIVATE_RestConnection {
  S(t, e) {
    throw new Error("Not supported by FetchConnection");
  }
  async v(t, e, r, n, i) {
    const s = JSON.stringify(n);
    let o;
    try {
      const t2 = {
        method: "POST",
        headers: r,
        body: s
      };
      i && (t2.credentials = "include"), o = await fetch(e, t2);
    } catch (t2) {
      const e2 = t2;
      throw new FirestoreError(__PRIVATE_mapCodeFromHttpStatus(e2.status), "Request failed with error: " + e2.statusText);
    }
    if (!o.ok) {
      let t2 = await o.json();
      Array.isArray(t2) && (t2 = t2[0]);
      const e2 = t2?.error?.message;
      throw new FirestoreError(__PRIVATE_mapCodeFromHttpStatus(o.status), `Request failed with error: ${e2 ?? o.statusText}`);
    }
    return o.json();
  }
};
function __PRIVATE_objectSize(t) {
  let e = 0;
  for (const r in t) Object.prototype.hasOwnProperty.call(t, r) && e++;
  return e;
}
function forEach(t, e) {
  for (const r in t) Object.prototype.hasOwnProperty.call(t, r) && e(r, t[r]);
}
var __PRIVATE_Base64DecodeError = class extends Error {
  constructor() {
    super(...arguments), this.name = "Base64DecodeError";
  }
};
var ByteString = class _ByteString {
  constructor(t) {
    this.binaryString = t;
  }
  static fromBase64String(t) {
    const e = (function __PRIVATE_decodeBase64(t2) {
      try {
        return atob(t2);
      } catch (t3) {
        throw "undefined" != typeof DOMException && t3 instanceof DOMException ? new __PRIVATE_Base64DecodeError("Invalid base64 string: " + t3) : t3;
      }
    })(t);
    return new _ByteString(e);
  }
  static fromUint8Array(t) {
    const e = (
      /**
      * Helper function to convert an Uint8array to a binary string.
      */
      (function __PRIVATE_binaryStringFromUint8Array(t2) {
        let e2 = "";
        for (let r = 0; r < t2.length; ++r) e2 += String.fromCharCode(t2[r]);
        return e2;
      })(t)
    );
    return new _ByteString(e);
  }
  [Symbol.iterator]() {
    let t = 0;
    return {
      next: () => t < this.binaryString.length ? {
        value: this.binaryString.charCodeAt(t++),
        done: false
      } : {
        value: void 0,
        done: true
      }
    };
  }
  toBase64() {
    return (function __PRIVATE_encodeBase64(t) {
      return btoa(t);
    })(this.binaryString);
  }
  toUint8Array() {
    return (function __PRIVATE_uint8ArrayFromBinaryString(t) {
      const e = new Uint8Array(t.length);
      for (let r = 0; r < t.length; r++) e[r] = t.charCodeAt(r);
      return e;
    })(this.binaryString);
  }
  approximateByteSize() {
    return 2 * this.binaryString.length;
  }
  compareTo(t) {
    return __PRIVATE_primitiveComparator(this.binaryString, t.binaryString);
  }
  isEqual(t) {
    return this.binaryString === t.binaryString;
  }
};
ByteString.EMPTY_BYTE_STRING = new ByteString("");
var G = new RegExp(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.(\d+))?Z$/);
function __PRIVATE_normalizeTimestamp(t) {
  if (__PRIVATE_hardAssert(!!t, 39018), "string" == typeof t) {
    let e = 0;
    const r = G.exec(t);
    if (__PRIVATE_hardAssert(!!r, 46558, {
      timestamp: t
    }), r[1]) {
      let t2 = r[1];
      t2 = (t2 + "000000000").substr(0, 9), e = Number(t2);
    }
    const n = new Date(t);
    return {
      seconds: Math.floor(n.getTime() / 1e3),
      nanos: e
    };
  }
  return {
    seconds: __PRIVATE_normalizeNumber(t.seconds),
    nanos: __PRIVATE_normalizeNumber(t.nanos)
  };
}
function __PRIVATE_normalizeNumber(t) {
  return "number" == typeof t ? t : "string" == typeof t ? Number(t) : 0;
}
function __PRIVATE_normalizeByteString(t) {
  return "string" == typeof t ? ByteString.fromBase64String(t) : ByteString.fromUint8Array(t);
}
function property(t, e) {
  const r = {
    typeString: t
  };
  return e && (r.value = e), r;
}
function __PRIVATE_validateJSON(t, e) {
  if (!__PRIVATE_isPlainObject(t)) throw new FirestoreError(y, "JSON must be an object");
  let r;
  for (const n in e) if (e[n]) {
    const i = e[n].typeString, s = "value" in e[n] ? {
      value: e[n].value
    } : void 0;
    if (!(n in t)) {
      r = `JSON missing required field: '${n}'`;
      break;
    }
    const o = t[n];
    if (i && typeof o !== i) {
      r = `JSON field '${n}' must be a ${i}.`;
      break;
    }
    if (void 0 !== s && o !== s.value) {
      r = `Expected '${n}' field to equal '${s.value}'`;
      break;
    }
  }
  if (r) throw new FirestoreError(y, r);
  return true;
}
var J = -62135596800;
var H = 1e6;
var Timestamp = class _Timestamp {
  /**
   * Creates a new timestamp with the current date, with millisecond precision.
   *
   * @returns a new timestamp representing the current date.
   */
  static now() {
    return _Timestamp.fromMillis(Date.now());
  }
  /**
   * Creates a new timestamp from the given date.
   *
   * @param date - The date to initialize the `Timestamp` from.
   * @returns A new `Timestamp` representing the same point in time as the given
   *     date.
   */
  static fromDate(t) {
    return _Timestamp.fromMillis(t.getTime());
  }
  /**
   * Creates a new timestamp from the given number of milliseconds.
   *
   * @param milliseconds - Number of milliseconds since Unix epoch
   *     1970-01-01T00:00:00Z.
   * @returns A new `Timestamp` representing the same point in time as the given
   *     number of milliseconds.
   */
  static fromMillis(t) {
    const e = Math.floor(t / 1e3), r = Math.floor((t - 1e3 * e) * H);
    return new _Timestamp(e, r);
  }
  /**
   * Creates a new timestamp.
   *
   * @param seconds - The number of seconds of UTC time since Unix epoch
   *     1970-01-01T00:00:00Z. Must be from 0001-01-01T00:00:00Z to
   *     9999-12-31T23:59:59Z inclusive.
   * @param nanoseconds - The non-negative fractions of a second at nanosecond
   *     resolution. Negative second values with fractions must still have
   *     non-negative nanoseconds values that count forward in time. Must be
   *     from 0 to 999,999,999 inclusive.
   */
  constructor(t, e) {
    if (this.seconds = t, this.nanoseconds = e, e < 0) throw new FirestoreError(y, "Timestamp nanoseconds out of range: " + e);
    if (e >= 1e9) throw new FirestoreError(y, "Timestamp nanoseconds out of range: " + e);
    if (t < J) throw new FirestoreError(y, "Timestamp seconds out of range: " + t);
    if (t >= 253402300800) throw new FirestoreError(y, "Timestamp seconds out of range: " + t);
  }
  /**
   * Converts a `Timestamp` to a JavaScript `Date` object. This conversion
   * causes a loss of precision since `Date` objects only support millisecond
   * precision.
   *
   * @returns JavaScript `Date` object representing the same point in time as
   *     this `Timestamp`, with millisecond precision.
   */
  toDate() {
    return new Date(this.toMillis());
  }
  /**
   * Converts a `Timestamp` to a numeric timestamp (in milliseconds since
   * epoch). This operation causes a loss of precision.
   *
   * @returns The point in time corresponding to this timestamp, represented as
   *     the number of milliseconds since Unix epoch 1970-01-01T00:00:00Z.
   */
  toMillis() {
    return 1e3 * this.seconds + this.nanoseconds / H;
  }
  _compareTo(t) {
    return this.seconds === t.seconds ? __PRIVATE_primitiveComparator(this.nanoseconds, t.nanoseconds) : __PRIVATE_primitiveComparator(this.seconds, t.seconds);
  }
  /**
   * Returns true if this `Timestamp` is equal to the provided one.
   *
   * @param other - The `Timestamp` to compare against.
   * @returns true if this `Timestamp` is equal to the provided one.
   */
  isEqual(t) {
    return t.seconds === this.seconds && t.nanoseconds === this.nanoseconds;
  }
  /** Returns a textual representation of this `Timestamp`. */
  toString() {
    return "Timestamp(seconds=" + this.seconds + ", nanoseconds=" + this.nanoseconds + ")";
  }
  /**
   * Returns a JSON-serializable representation of this `Timestamp`.
   */
  toJSON() {
    return {
      type: _Timestamp._jsonSchemaVersion,
      seconds: this.seconds,
      nanoseconds: this.nanoseconds
    };
  }
  /**
   * Builds a `Timestamp` instance from a JSON object created by {@link Timestamp.toJSON}.
   */
  static fromJSON(t) {
    if (__PRIVATE_validateJSON(t, _Timestamp._jsonSchema)) return new _Timestamp(t.seconds, t.nanoseconds);
  }
  /**
   * Converts this object to a primitive string, which allows `Timestamp` objects
   * to be compared using the `>`, `<=`, `>=` and `>` operators.
   */
  valueOf() {
    const t = this.seconds - J;
    return String(t).padStart(12, "0") + "." + String(this.nanoseconds).padStart(9, "0");
  }
};
Timestamp._jsonSchemaVersion = "firestore/timestamp/1.0", Timestamp._jsonSchema = {
  type: property("string", Timestamp._jsonSchemaVersion),
  seconds: property("number"),
  nanoseconds: property("number")
};
function __PRIVATE_isServerTimestamp(t) {
  const e = (t?.mapValue?.fields || {}).__type__?.stringValue;
  return "server_timestamp" === e;
}
function __PRIVATE_getPreviousValue(t) {
  const e = t.mapValue.fields.__previous_value__;
  return __PRIVATE_isServerTimestamp(e) ? __PRIVATE_getPreviousValue(e) : e;
}
function __PRIVATE_getLocalWriteTime(t) {
  const e = __PRIVATE_normalizeTimestamp(t.mapValue.fields.__local_write_time__.timestampValue);
  return new Timestamp(e.seconds, e.nanos);
}
var Y = "__type__";
var Z = "__max__";
var tt = "__vector__";
var et = "value";
function __PRIVATE_typeOrder(t) {
  return "nullValue" in t ? 0 : "booleanValue" in t ? 1 : "integerValue" in t || "doubleValue" in t ? 2 : "timestampValue" in t ? 3 : "stringValue" in t ? 5 : "bytesValue" in t ? 6 : "referenceValue" in t ? 7 : "geoPointValue" in t ? 8 : "arrayValue" in t ? 9 : "mapValue" in t ? __PRIVATE_isServerTimestamp(t) ? 4 : (
    /** Returns true if the Value represents the canonical {@link #MAX_VALUE} . */
    (function __PRIVATE_isMaxValue(t2) {
      return (((t2.mapValue || {}).fields || {}).__type__ || {}).stringValue === Z;
    })(t) ? 9007199254740991 : (
      /** Returns true if `value` is a VetorValue. */
      (function __PRIVATE_isVectorValue(t2) {
        const e = (t2?.mapValue?.fields || {})[Y]?.stringValue;
        return e === tt;
      })(t) ? 10 : 11
    )
  ) : fail(28295, {
    value: t
  });
}
function __PRIVATE_valueEquals(t, e) {
  if (t === e) return true;
  const r = __PRIVATE_typeOrder(t);
  if (r !== __PRIVATE_typeOrder(e)) return false;
  switch (r) {
    case 0:
    case 9007199254740991:
      return true;
    case 1:
      return t.booleanValue === e.booleanValue;
    case 4:
      return __PRIVATE_getLocalWriteTime(t).isEqual(__PRIVATE_getLocalWriteTime(e));
    case 3:
      return (function __PRIVATE_timestampEquals(t2, e2) {
        if ("string" == typeof t2.timestampValue && "string" == typeof e2.timestampValue && t2.timestampValue.length === e2.timestampValue.length)
          return t2.timestampValue === e2.timestampValue;
        const r2 = __PRIVATE_normalizeTimestamp(t2.timestampValue), n = __PRIVATE_normalizeTimestamp(e2.timestampValue);
        return r2.seconds === n.seconds && r2.nanos === n.nanos;
      })(t, e);
    case 5:
      return t.stringValue === e.stringValue;
    case 6:
      return (function __PRIVATE_blobEquals(t2, e2) {
        return __PRIVATE_normalizeByteString(t2.bytesValue).isEqual(__PRIVATE_normalizeByteString(e2.bytesValue));
      })(t, e);
    case 7:
      return t.referenceValue === e.referenceValue;
    case 8:
      return (function __PRIVATE_geoPointEquals(t2, e2) {
        return __PRIVATE_normalizeNumber(t2.geoPointValue.latitude) === __PRIVATE_normalizeNumber(e2.geoPointValue.latitude) && __PRIVATE_normalizeNumber(t2.geoPointValue.longitude) === __PRIVATE_normalizeNumber(e2.geoPointValue.longitude);
      })(t, e);
    case 2:
      return (function __PRIVATE_numberEquals(t2, e2) {
        if ("integerValue" in t2 && "integerValue" in e2) return __PRIVATE_normalizeNumber(t2.integerValue) === __PRIVATE_normalizeNumber(e2.integerValue);
        if ("doubleValue" in t2 && "doubleValue" in e2) {
          const r2 = __PRIVATE_normalizeNumber(t2.doubleValue), n = __PRIVATE_normalizeNumber(e2.doubleValue);
          return r2 === n ? __PRIVATE_isNegativeZero(r2) === __PRIVATE_isNegativeZero(n) : isNaN(r2) && isNaN(n);
        }
        return false;
      })(t, e);
    case 9:
      return __PRIVATE_arrayEquals(t.arrayValue.values || [], e.arrayValue.values || [], __PRIVATE_valueEquals);
    case 10:
    case 11:
      return (function __PRIVATE_objectEquals(t2, e2) {
        const r2 = t2.mapValue.fields || {}, n = e2.mapValue.fields || {};
        if (__PRIVATE_objectSize(r2) !== __PRIVATE_objectSize(n)) return false;
        for (const t3 in r2) if (r2.hasOwnProperty(t3) && (void 0 === n[t3] || !__PRIVATE_valueEquals(r2[t3], n[t3]))) return false;
        return true;
      })(t, e);
    default:
      return fail(52216, {
        left: t
      });
  }
}
function __PRIVATE_isMapValue(t) {
  return !!t && "mapValue" in t;
}
function __PRIVATE_deepClone(t) {
  if (t.geoPointValue) return {
    geoPointValue: {
      ...t.geoPointValue
    }
  };
  if (t.timestampValue && "object" == typeof t.timestampValue) return {
    timestampValue: {
      ...t.timestampValue
    }
  };
  if (t.mapValue) {
    const e = {
      mapValue: {
        fields: {}
      }
    };
    return forEach(t.mapValue.fields, ((t2, r) => e.mapValue.fields[t2] = __PRIVATE_deepClone(r))), e;
  }
  if (t.arrayValue) {
    const e = {
      arrayValue: {
        values: []
      }
    };
    for (let r = 0; r < (t.arrayValue.values || []).length; ++r) e.arrayValue.values[r] = __PRIVATE_deepClone(t.arrayValue.values[r]);
    return e;
  }
  return {
    ...t
  };
}
var SnapshotVersion = class _SnapshotVersion {
  static fromTimestamp(t) {
    return new _SnapshotVersion(t);
  }
  static min() {
    return new _SnapshotVersion(new Timestamp(0, 0));
  }
  static max() {
    return new _SnapshotVersion(new Timestamp(253402300799, 999999999));
  }
  constructor(t) {
    this.timestamp = t;
  }
  compareTo(t) {
    return this.timestamp._compareTo(t.timestamp);
  }
  isEqual(t) {
    return this.timestamp.isEqual(t.timestamp);
  }
  /** Returns a number representation of the version for use in spec tests. */
  toMicroseconds() {
    return 1e6 * this.timestamp.seconds + this.timestamp.nanoseconds / 1e3;
  }
  toString() {
    return "SnapshotVersion(" + this.timestamp.toString() + ")";
  }
  toTimestamp() {
    return this.timestamp;
  }
};
var SortedMap = class _SortedMap {
  constructor(t, e) {
    this.comparator = t, this.root = e || LLRBNode.EMPTY;
  }
  // Returns a copy of the map, with the specified key/value added or replaced.
  insert(t, e) {
    return new _SortedMap(this.comparator, this.root.insert(t, e, this.comparator).copy(null, null, LLRBNode.BLACK, null, null));
  }
  // Returns a copy of the map, with the specified key removed.
  remove(t) {
    return new _SortedMap(this.comparator, this.root.remove(t, this.comparator).copy(null, null, LLRBNode.BLACK, null, null));
  }
  // Returns the value of the node with the given key, or null.
  get(t) {
    let e = this.root;
    for (; !e.isEmpty(); ) {
      const r = this.comparator(t, e.key);
      if (0 === r) return e.value;
      r < 0 ? e = e.left : r > 0 && (e = e.right);
    }
    return null;
  }
  // Returns the index of the element in this sorted map, or -1 if it doesn't
  // exist.
  indexOf(t) {
    let e = 0, r = this.root;
    for (; !r.isEmpty(); ) {
      const n = this.comparator(t, r.key);
      if (0 === n) return e + r.left.size;
      n < 0 ? r = r.left : (
        // Count all nodes left of the node plus the node itself
        (e += r.left.size + 1, r = r.right)
      );
    }
    return -1;
  }
  isEmpty() {
    return this.root.isEmpty();
  }
  // Returns the total number of nodes in the map.
  get size() {
    return this.root.size;
  }
  // Returns the minimum key in the map.
  minKey() {
    return this.root.minKey();
  }
  // Returns the maximum key in the map.
  maxKey() {
    return this.root.maxKey();
  }
  // Traverses the map in key order and calls the specified action function
  // for each key/value pair. If action returns true, traversal is aborted.
  // Returns the first truthy value returned by action, or the last falsey
  // value returned by action.
  inorderTraversal(t) {
    return this.root.inorderTraversal(t);
  }
  forEach(t) {
    this.inorderTraversal(((e, r) => (t(e, r), false)));
  }
  toString() {
    const t = [];
    return this.inorderTraversal(((e, r) => (t.push(`${e}:${r}`), false))), `{${t.join(", ")}}`;
  }
  // Traverses the map in reverse key order and calls the specified action
  // function for each key/value pair. If action returns true, traversal is
  // aborted.
  // Returns the first truthy value returned by action, or the last falsey
  // value returned by action.
  reverseTraversal(t) {
    return this.root.reverseTraversal(t);
  }
  // Returns an iterator over the SortedMap.
  getIterator() {
    return new SortedMapIterator(this.root, null, this.comparator, false);
  }
  getIteratorFrom(t) {
    return new SortedMapIterator(this.root, t, this.comparator, false);
  }
  getReverseIterator() {
    return new SortedMapIterator(this.root, null, this.comparator, true);
  }
  getReverseIteratorFrom(t) {
    return new SortedMapIterator(this.root, t, this.comparator, true);
  }
};
var SortedMapIterator = class {
  constructor(t, e, r, n) {
    this.isReverse = n, this.nodeStack = [];
    let i = 1;
    for (; !t.isEmpty(); ) if (i = e ? r(t.key, e) : 1, // flip the comparison if we're going in reverse
    e && n && (i *= -1), i < 0)
      t = this.isReverse ? t.left : t.right;
    else {
      if (0 === i) {
        this.nodeStack.push(t);
        break;
      }
      this.nodeStack.push(t), t = this.isReverse ? t.right : t.left;
    }
  }
  getNext() {
    let t = this.nodeStack.pop();
    const e = {
      key: t.key,
      value: t.value
    };
    if (this.isReverse) for (t = t.left; !t.isEmpty(); ) this.nodeStack.push(t), t = t.right;
    else for (t = t.right; !t.isEmpty(); ) this.nodeStack.push(t), t = t.left;
    return e;
  }
  hasNext() {
    return this.nodeStack.length > 0;
  }
  peek() {
    if (0 === this.nodeStack.length) return null;
    const t = this.nodeStack[this.nodeStack.length - 1];
    return {
      key: t.key,
      value: t.value
    };
  }
};
var LLRBNode = class _LLRBNode {
  constructor(t, e, r, n, i) {
    this.key = t, this.value = e, this.color = null != r ? r : _LLRBNode.RED, this.left = null != n ? n : _LLRBNode.EMPTY, this.right = null != i ? i : _LLRBNode.EMPTY, this.size = this.left.size + 1 + this.right.size;
  }
  // Returns a copy of the current node, optionally replacing pieces of it.
  copy(t, e, r, n, i) {
    return new _LLRBNode(null != t ? t : this.key, null != e ? e : this.value, null != r ? r : this.color, null != n ? n : this.left, null != i ? i : this.right);
  }
  isEmpty() {
    return false;
  }
  // Traverses the tree in key order and calls the specified action function
  // for each node. If action returns true, traversal is aborted.
  // Returns the first truthy value returned by action, or the last falsey
  // value returned by action.
  inorderTraversal(t) {
    return this.left.inorderTraversal(t) || t(this.key, this.value) || this.right.inorderTraversal(t);
  }
  // Traverses the tree in reverse key order and calls the specified action
  // function for each node. If action returns true, traversal is aborted.
  // Returns the first truthy value returned by action, or the last falsey
  // value returned by action.
  reverseTraversal(t) {
    return this.right.reverseTraversal(t) || t(this.key, this.value) || this.left.reverseTraversal(t);
  }
  // Returns the minimum node in the tree.
  min() {
    return this.left.isEmpty() ? this : this.left.min();
  }
  // Returns the maximum key in the tree.
  minKey() {
    return this.min().key;
  }
  // Returns the maximum key in the tree.
  maxKey() {
    return this.right.isEmpty() ? this.key : this.right.maxKey();
  }
  // Returns new tree, with the key/value added.
  insert(t, e, r) {
    let n = this;
    const i = r(t, n.key);
    return n = i < 0 ? n.copy(null, null, null, n.left.insert(t, e, r), null) : 0 === i ? n.copy(null, e, null, null, null) : n.copy(null, null, null, null, n.right.insert(t, e, r)), n.fixUp();
  }
  removeMin() {
    if (this.left.isEmpty()) return _LLRBNode.EMPTY;
    let t = this;
    return t.left.isRed() || t.left.left.isRed() || (t = t.moveRedLeft()), t = t.copy(null, null, null, t.left.removeMin(), null), t.fixUp();
  }
  // Returns new tree, with the specified item removed.
  remove(t, e) {
    let r, n = this;
    if (e(t, n.key) < 0) n.left.isEmpty() || n.left.isRed() || n.left.left.isRed() || (n = n.moveRedLeft()), n = n.copy(null, null, null, n.left.remove(t, e), null);
    else {
      if (n.left.isRed() && (n = n.rotateRight()), n.right.isEmpty() || n.right.isRed() || n.right.left.isRed() || (n = n.moveRedRight()), 0 === e(t, n.key)) {
        if (n.right.isEmpty()) return _LLRBNode.EMPTY;
        r = n.right.min(), n = n.copy(r.key, r.value, null, null, n.right.removeMin());
      }
      n = n.copy(null, null, null, null, n.right.remove(t, e));
    }
    return n.fixUp();
  }
  isRed() {
    return this.color;
  }
  // Returns new tree after performing any needed rotations.
  fixUp() {
    let t = this;
    return t.right.isRed() && !t.left.isRed() && (t = t.rotateLeft()), t.left.isRed() && t.left.left.isRed() && (t = t.rotateRight()), t.left.isRed() && t.right.isRed() && (t = t.colorFlip()), t;
  }
  moveRedLeft() {
    let t = this.colorFlip();
    return t.right.left.isRed() && (t = t.copy(null, null, null, null, t.right.rotateRight()), t = t.rotateLeft(), t = t.colorFlip()), t;
  }
  moveRedRight() {
    let t = this.colorFlip();
    return t.left.left.isRed() && (t = t.rotateRight(), t = t.colorFlip()), t;
  }
  rotateLeft() {
    const t = this.copy(null, null, _LLRBNode.RED, null, this.right.left);
    return this.right.copy(null, null, this.color, t, null);
  }
  rotateRight() {
    const t = this.copy(null, null, _LLRBNode.RED, this.left.right, null);
    return this.left.copy(null, null, this.color, null, t);
  }
  colorFlip() {
    const t = this.left.copy(null, null, !this.left.color, null, null), e = this.right.copy(null, null, !this.right.color, null, null);
    return this.copy(null, null, !this.color, t, e);
  }
  // For testing.
  checkMaxDepth() {
    const t = this.check();
    return Math.pow(2, t) <= this.size + 1;
  }
  // In a balanced RB tree, the black-depth (number of black nodes) from root to
  // leaves is equal on both sides.  This function verifies that or asserts.
  check() {
    if (this.isRed() && this.left.isRed()) throw fail(43730, {
      key: this.key,
      value: this.value
    });
    if (this.right.isRed()) throw fail(14113, {
      key: this.key,
      value: this.value
    });
    const t = this.left.check();
    if (t !== this.right.check()) throw fail(27949);
    return t + (this.isRed() ? 0 : 1);
  }
};
LLRBNode.EMPTY = null, LLRBNode.RED = true, LLRBNode.BLACK = false;
LLRBNode.EMPTY = new // Represents an empty node (a leaf node in the Red-Black Tree).
class LLRBEmptyNode {
  constructor() {
    this.size = 0;
  }
  get key() {
    throw fail(57766);
  }
  get value() {
    throw fail(16141);
  }
  get color() {
    throw fail(16727);
  }
  get left() {
    throw fail(29726);
  }
  get right() {
    throw fail(36894);
  }
  // Returns a copy of the current node.
  copy(t, e, r, n, i) {
    return this;
  }
  // Returns a copy of the tree, with the specified key/value added.
  insert(t, e, r) {
    return new LLRBNode(t, e);
  }
  // Returns a copy of the tree, with the specified key removed.
  remove(t, e) {
    return this;
  }
  isEmpty() {
    return true;
  }
  inorderTraversal(t) {
    return false;
  }
  reverseTraversal(t) {
    return false;
  }
  minKey() {
    return null;
  }
  maxKey() {
    return null;
  }
  isRed() {
    return false;
  }
  // For testing.
  checkMaxDepth() {
    return true;
  }
  check() {
    return 0;
  }
}();
var SortedSet = class _SortedSet {
  constructor(t) {
    this.comparator = t, this.data = new SortedMap(this.comparator);
  }
  has(t) {
    return null !== this.data.get(t);
  }
  first() {
    return this.data.minKey();
  }
  last() {
    return this.data.maxKey();
  }
  get size() {
    return this.data.size;
  }
  indexOf(t) {
    return this.data.indexOf(t);
  }
  /** Iterates elements in order defined by "comparator" */
  forEach(t) {
    this.data.inorderTraversal(((e, r) => (t(e), false)));
  }
  /** Iterates over `elem`s such that: range[0] &lt;= elem &lt; range[1]. */
  forEachInRange(t, e) {
    const r = this.data.getIteratorFrom(t[0]);
    for (; r.hasNext(); ) {
      const n = r.getNext();
      if (this.comparator(n.key, t[1]) >= 0) return;
      e(n.key);
    }
  }
  /**
   * Iterates over `elem`s such that: start &lt;= elem until false is returned.
   */
  forEachWhile(t, e) {
    let r;
    for (r = void 0 !== e ? this.data.getIteratorFrom(e) : this.data.getIterator(); r.hasNext(); ) {
      if (!t(r.getNext().key)) return;
    }
  }
  /** Finds the least element greater than or equal to `elem`. */
  firstAfterOrEqual(t) {
    const e = this.data.getIteratorFrom(t);
    return e.hasNext() ? e.getNext().key : null;
  }
  getIterator() {
    return new SortedSetIterator(this.data.getIterator());
  }
  getIteratorFrom(t) {
    return new SortedSetIterator(this.data.getIteratorFrom(t));
  }
  /** Inserts or updates an element */
  add(t) {
    return this.copy(this.data.remove(t).insert(t, true));
  }
  /** Deletes an element */
  delete(t) {
    return this.has(t) ? this.copy(this.data.remove(t)) : this;
  }
  isEmpty() {
    return this.data.isEmpty();
  }
  unionWith(t) {
    let e = this;
    return e.size < t.size && (e = t, t = this), t.forEach(((t2) => {
      e = e.add(t2);
    })), e;
  }
  isEqual(t) {
    if (!(t instanceof _SortedSet)) return false;
    if (this.size !== t.size) return false;
    const e = this.data.getIterator(), r = t.data.getIterator();
    for (; e.hasNext(); ) {
      const t2 = e.getNext().key, n = r.getNext().key;
      if (0 !== this.comparator(t2, n)) return false;
    }
    return true;
  }
  toArray() {
    const t = [];
    return this.forEach(((e) => {
      t.push(e);
    })), t;
  }
  toString() {
    const t = [];
    return this.forEach(((e) => t.push(e))), "SortedSet(" + t.toString() + ")";
  }
  copy(t) {
    const e = new _SortedSet(this.comparator);
    return e.data = t, e;
  }
};
var SortedSetIterator = class {
  constructor(t) {
    this.iter = t;
  }
  getNext() {
    return this.iter.getNext().key;
  }
  hasNext() {
    return this.iter.hasNext();
  }
};
var FieldMask = class _FieldMask {
  constructor(t) {
    this.fields = t, // TODO(dimond): validation of FieldMask
    // Sort the field mask to support `FieldMask.isEqual()` and assert below.
    t.sort(FieldPath$1.comparator);
  }
  static empty() {
    return new _FieldMask([]);
  }
  /**
   * Returns a new FieldMask object that is the result of adding all the given
   * fields paths to this field mask.
   */
  unionWith(t) {
    let e = new SortedSet(FieldPath$1.comparator);
    for (const t2 of this.fields) e = e.add(t2);
    for (const r of t) e = e.add(r);
    return new _FieldMask(e.toArray());
  }
  /**
   * Verifies that `fieldPath` is included by at least one field in this field
   * mask.
   *
   * This is an O(n) operation, where `n` is the size of the field mask.
   */
  covers(t) {
    for (const e of this.fields) if (e.isPrefixOf(t)) return true;
    return false;
  }
  isEqual(t) {
    return __PRIVATE_arrayEquals(this.fields, t.fields, ((t2, e) => t2.isEqual(e)));
  }
};
var ObjectValue = class _ObjectValue {
  constructor(t) {
    this.value = t;
  }
  static empty() {
    return new _ObjectValue({
      mapValue: {}
    });
  }
  /**
   * Returns the value at the given path or null.
   *
   * @param path - the path to search
   * @returns The value at the path or null if the path is not set.
   */
  field(t) {
    if (t.isEmpty()) return this.value;
    {
      let e = this.value;
      for (let r = 0; r < t.length - 1; ++r) if (e = (e.mapValue.fields || {})[t.get(r)], !__PRIVATE_isMapValue(e)) return null;
      return e = (e.mapValue.fields || {})[t.lastSegment()], e || null;
    }
  }
  /**
   * Sets the field to the provided value.
   *
   * @param path - The field path to set.
   * @param value - The value to set.
   */
  set(t, e) {
    this.getFieldsMap(t.popLast())[t.lastSegment()] = __PRIVATE_deepClone(e);
  }
  /**
   * Sets the provided fields to the provided values.
   *
   * @param data - A map of fields to values (or null for deletes).
   */
  setAll(t) {
    let e = FieldPath$1.emptyPath(), r = {}, n = [];
    t.forEach(((t2, i2) => {
      if (!e.isImmediateParentOf(i2)) {
        const t3 = this.getFieldsMap(e);
        this.applyChanges(t3, r, n), r = {}, n = [], e = i2.popLast();
      }
      t2 ? r[i2.lastSegment()] = __PRIVATE_deepClone(t2) : n.push(i2.lastSegment());
    }));
    const i = this.getFieldsMap(e);
    this.applyChanges(i, r, n);
  }
  /**
   * Removes the field at the specified path. If there is no field at the
   * specified path, nothing is changed.
   *
   * @param path - The field path to remove.
   */
  delete(t) {
    const e = this.field(t.popLast());
    __PRIVATE_isMapValue(e) && e.mapValue.fields && delete e.mapValue.fields[t.lastSegment()];
  }
  isEqual(t) {
    return __PRIVATE_valueEquals(this.value, t.value);
  }
  /**
   * Returns the map that contains the leaf element of `path`. If the parent
   * entry does not yet exist, or if it is not a map, a new map will be created.
   */
  getFieldsMap(t) {
    let e = this.value;
    e.mapValue.fields || (e.mapValue = {
      fields: {}
    });
    for (let r = 0; r < t.length; ++r) {
      let n = e.mapValue.fields[t.get(r)];
      __PRIVATE_isMapValue(n) && n.mapValue.fields || (n = {
        mapValue: {
          fields: {}
        }
      }, e.mapValue.fields[t.get(r)] = n), e = n;
    }
    return e.mapValue.fields;
  }
  /**
   * Modifies `fieldsMap` by adding, replacing or deleting the specified
   * entries.
   */
  applyChanges(t, e, r) {
    forEach(e, ((e2, r2) => t[e2] = r2));
    for (const e2 of r) delete t[e2];
  }
  clone() {
    return new _ObjectValue(__PRIVATE_deepClone(this.value));
  }
};
var MutableDocument = class _MutableDocument {
  constructor(t, e, r, n, i, s, o) {
    this.key = t, this.documentType = e, this.version = r, this.readTime = n, this.createTime = i, this.data = s, this.documentState = o;
  }
  /**
   * Creates a document with no known version or data, but which can serve as
   * base document for mutations.
   */
  static newInvalidDocument(t) {
    return new _MutableDocument(
      t,
      0,
      /* version */
      SnapshotVersion.min(),
      /* readTime */
      SnapshotVersion.min(),
      /* createTime */
      SnapshotVersion.min(),
      ObjectValue.empty(),
      0
      /* DocumentState.SYNCED */
    );
  }
  /**
   * Creates a new document that is known to exist with the given data at the
   * given version.
   */
  static newFoundDocument(t, e, r, n) {
    return new _MutableDocument(
      t,
      1,
      /* version */
      e,
      /* readTime */
      SnapshotVersion.min(),
      /* createTime */
      r,
      n,
      0
      /* DocumentState.SYNCED */
    );
  }
  /** Creates a new document that is known to not exist at the given version. */
  static newNoDocument(t, e) {
    return new _MutableDocument(
      t,
      2,
      /* version */
      e,
      /* readTime */
      SnapshotVersion.min(),
      /* createTime */
      SnapshotVersion.min(),
      ObjectValue.empty(),
      0
      /* DocumentState.SYNCED */
    );
  }
  /**
   * Creates a new document that is known to exist at the given version but
   * whose data is not known (e.g. a document that was updated without a known
   * base document).
   */
  static newUnknownDocument(t, e) {
    return new _MutableDocument(
      t,
      3,
      /* version */
      e,
      /* readTime */
      SnapshotVersion.min(),
      /* createTime */
      SnapshotVersion.min(),
      ObjectValue.empty(),
      2
      /* DocumentState.HAS_COMMITTED_MUTATIONS */
    );
  }
  /**
   * Changes the document type to indicate that it exists and that its version
   * and data are known.
   */
  convertToFoundDocument(t, e) {
    return !this.createTime.isEqual(SnapshotVersion.min()) || 2 !== this.documentType && 0 !== this.documentType || (this.createTime = t), this.version = t, this.documentType = 1, this.data = e, this.documentState = 0, this;
  }
  /**
   * Changes the document type to indicate that it doesn't exist at the given
   * version.
   */
  convertToNoDocument(t) {
    return this.version = t, this.documentType = 2, this.data = ObjectValue.empty(), this.documentState = 0, this;
  }
  /**
   * Changes the document type to indicate that it exists at a given version but
   * that its data is not known (e.g. a document that was updated without a known
   * base document).
   */
  convertToUnknownDocument(t) {
    return this.version = t, this.documentType = 3, this.data = ObjectValue.empty(), this.documentState = 2, this;
  }
  setHasCommittedMutations() {
    return this.documentState = 2, this;
  }
  setHasLocalMutations() {
    return this.documentState = 1, this.version = SnapshotVersion.min(), this;
  }
  setReadTime(t) {
    return this.readTime = t, this;
  }
  get hasLocalMutations() {
    return 1 === this.documentState;
  }
  get hasCommittedMutations() {
    return 2 === this.documentState;
  }
  get hasPendingWrites() {
    return this.hasLocalMutations || this.hasCommittedMutations;
  }
  isValidDocument() {
    return 0 !== this.documentType;
  }
  isFoundDocument() {
    return 1 === this.documentType;
  }
  isNoDocument() {
    return 2 === this.documentType;
  }
  isUnknownDocument() {
    return 3 === this.documentType;
  }
  isEqual(t) {
    return t instanceof _MutableDocument && this.key.isEqual(t.key) && this.version.isEqual(t.version) && this.documentType === t.documentType && this.documentState === t.documentState && this.data.isEqual(t.data);
  }
  mutableCopy() {
    return new _MutableDocument(this.key, this.documentType, this.version, this.readTime, this.createTime, this.data.clone(), this.documentState);
  }
  toString() {
    return `Document(${this.key}, ${this.version}, ${JSON.stringify(this.data.value)}, {createTime: ${this.createTime}}), {documentType: ${this.documentType}}), {documentState: ${this.documentState}})`;
  }
};
var __PRIVATE_QueryImpl = class {
  /**
   * Initializes a Query with a path and optional additional query constraints.
   * Path must currently be empty if this is a collection group query.
   */
  constructor(t, e = null, r = [], n = [], i = null, s = "F", o = null, a = null) {
    this.path = t, this.collectionGroup = e, this.explicitOrderBy = r, this.filters = n, this.limit = i, this.limitType = s, this.startAt = o, this.endAt = a, this.q = null, // The corresponding `Target` of this `Query` instance, for use with
    // non-aggregate queries.
    this.B = null, // The corresponding `Target` of this `Query` instance, for use with
    // aggregate queries. Unlike targets for non-aggregate queries,
    // aggregate query targets do not contain normalized order-bys, they only
    // contain explicit order-bys.
    this.$ = null, this.startAt, this.endAt;
  }
};
function __PRIVATE_toDouble(t, e) {
  if (t.useProto3Json) {
    if (isNaN(e)) return {
      doubleValue: "NaN"
    };
    if (e === 1 / 0) return {
      doubleValue: "Infinity"
    };
    if (e === -1 / 0) return {
      doubleValue: "-Infinity"
    };
  }
  return {
    doubleValue: __PRIVATE_isNegativeZero(e) ? "-0" : e
  };
}
function toNumber(t, e) {
  return (function isSafeInteger(t2) {
    return "number" == typeof t2 && Number.isInteger(t2) && !__PRIVATE_isNegativeZero(t2) && t2 <= Number.MAX_SAFE_INTEGER && t2 >= Number.MIN_SAFE_INTEGER;
  })(e) ? (function __PRIVATE_toInteger(t2) {
    return {
      integerValue: "" + t2
    };
  })(e) : __PRIVATE_toDouble(t, e);
}
var TransformOperation = class {
  constructor() {
    this._ = void 0;
  }
};
var __PRIVATE_ServerTimestampTransform = class extends TransformOperation {
};
var __PRIVATE_ArrayUnionTransformOperation = class extends TransformOperation {
  constructor(t) {
    super(), this.elements = t;
  }
};
var __PRIVATE_ArrayRemoveTransformOperation = class extends TransformOperation {
  constructor(t) {
    super(), this.elements = t;
  }
};
var __PRIVATE_NumericIncrementTransformOperation = class extends TransformOperation {
  constructor(t, e) {
    super(), this.serializer = t, this.k = e;
  }
};
var Precondition = class _Precondition {
  constructor(t, e) {
    this.updateTime = t, this.exists = e;
  }
  /** Creates a new empty Precondition. */
  static none() {
    return new _Precondition();
  }
  /** Creates a new Precondition with an exists flag. */
  static exists(t) {
    return new _Precondition(void 0, t);
  }
  /** Creates a new Precondition based on a version a document exists at. */
  static updateTime(t) {
    return new _Precondition(t);
  }
  /** Returns whether this Precondition is empty. */
  get isNone() {
    return void 0 === this.updateTime && void 0 === this.exists;
  }
  isEqual(t) {
    return this.exists === t.exists && (this.updateTime ? !!t.updateTime && this.updateTime.isEqual(t.updateTime) : !t.updateTime);
  }
};
var Mutation = class {
};
var __PRIVATE_SetMutation = class extends Mutation {
  constructor(t, e, r, n = []) {
    super(), this.key = t, this.value = e, this.precondition = r, this.fieldTransforms = n, this.type = 0;
  }
  getFieldMask() {
    return null;
  }
};
var __PRIVATE_PatchMutation = class extends Mutation {
  constructor(t, e, r, n, i = []) {
    super(), this.key = t, this.data = e, this.fieldMask = r, this.precondition = n, this.fieldTransforms = i, this.type = 1;
  }
  getFieldMask() {
    return this.fieldMask;
  }
};
var __PRIVATE_DeleteMutation = class extends Mutation {
  constructor(t, e) {
    super(), this.key = t, this.precondition = e, this.type = 2, this.fieldTransforms = [];
  }
  getFieldMask() {
    return null;
  }
};
var __PRIVATE_VerifyMutation = class extends Mutation {
  constructor(t, e) {
    super(), this.key = t, this.precondition = e, this.type = 3, this.fieldTransforms = [];
  }
  getFieldMask() {
    return null;
  }
};
var JsonProtoSerializer = class {
  constructor(t, e) {
    this.databaseId = t, this.useProto3Json = e;
  }
};
function toTimestamp(t, e) {
  if (t.useProto3Json) {
    return `${new Date(1e3 * e.seconds).toISOString().replace(/\.\d*/, "").replace("Z", "")}.${("000000000" + e.nanoseconds).slice(-9)}Z`;
  }
  return {
    seconds: "" + e.seconds,
    nanos: e.nanoseconds
  };
}
function __PRIVATE_toBytes(t, e) {
  return t.useProto3Json ? e.toBase64() : e.toUint8Array();
}
function __PRIVATE_toVersion(t, e) {
  return toTimestamp(t, e.toTimestamp());
}
function __PRIVATE_fromVersion(t) {
  return __PRIVATE_hardAssert(!!t, 49232), SnapshotVersion.fromTimestamp((function fromTimestamp(t2) {
    const e = __PRIVATE_normalizeTimestamp(t2);
    return new Timestamp(e.seconds, e.nanos);
  })(t));
}
function __PRIVATE_toResourceName(t, e) {
  return __PRIVATE_toResourcePath(t, e).canonicalString();
}
function __PRIVATE_toResourcePath(t, e) {
  const r = (function __PRIVATE_fullyQualifiedPrefixPath(t2) {
    return new ResourcePath(["projects", t2.projectId, "databases", t2.database]);
  })(t).child("documents");
  return void 0 === e ? r : r.child(e);
}
function __PRIVATE_toName(t, e) {
  return __PRIVATE_toResourceName(t.databaseId, e.path);
}
function fromName(t, e) {
  const r = (function __PRIVATE_fromResourceName(t2) {
    const e2 = ResourcePath.fromString(t2);
    return __PRIVATE_hardAssert(__PRIVATE_isValidResourceName(e2), 10190, {
      key: e2.toString()
    }), e2;
  })(e);
  if (r.get(1) !== t.databaseId.projectId) throw new FirestoreError(y, "Tried to deserialize key from different project: " + r.get(1) + " vs " + t.databaseId.projectId);
  if (r.get(3) !== t.databaseId.database) throw new FirestoreError(y, "Tried to deserialize key from different database: " + r.get(3) + " vs " + t.databaseId.database);
  return new DocumentKey((function __PRIVATE_extractLocalPathFromResourceName(t2) {
    return __PRIVATE_hardAssert(t2.length > 4 && "documents" === t2.get(4), 29091, {
      key: t2.toString()
    }), t2.popFirst(5);
  })(r));
}
function __PRIVATE_toMutationDocument(t, e, r) {
  return {
    name: __PRIVATE_toName(t, e),
    fields: r.value.mapValue.fields
  };
}
function __PRIVATE_fromBatchGetDocumentsResponse(t, e) {
  return "found" in e ? (function __PRIVATE_fromFound(t2, e2) {
    __PRIVATE_hardAssert(!!e2.found, 43571), e2.found.name, e2.found.updateTime;
    const r = fromName(t2, e2.found.name), n = __PRIVATE_fromVersion(e2.found.updateTime), i = e2.found.createTime ? __PRIVATE_fromVersion(e2.found.createTime) : SnapshotVersion.min(), s = new ObjectValue({
      mapValue: {
        fields: e2.found.fields
      }
    });
    return MutableDocument.newFoundDocument(r, n, i, s);
  })(t, e) : "missing" in e ? (function __PRIVATE_fromMissing(t2, e2) {
    __PRIVATE_hardAssert(!!e2.missing, 3894), __PRIVATE_hardAssert(!!e2.readTime, 22933);
    const r = fromName(t2, e2.missing), n = __PRIVATE_fromVersion(e2.readTime);
    return MutableDocument.newNoDocument(r, n);
  })(t, e) : fail(7234, {
    result: e
  });
}
function toMutation(t, e) {
  let r;
  if (e instanceof __PRIVATE_SetMutation) r = {
    update: __PRIVATE_toMutationDocument(t, e.key, e.value)
  };
  else if (e instanceof __PRIVATE_DeleteMutation) r = {
    delete: __PRIVATE_toName(t, e.key)
  };
  else if (e instanceof __PRIVATE_PatchMutation) r = {
    update: __PRIVATE_toMutationDocument(t, e.key, e.data),
    updateMask: __PRIVATE_toDocumentMask(e.fieldMask)
  };
  else {
    if (!(e instanceof __PRIVATE_VerifyMutation)) return fail(16599, {
      L: e.type
    });
    r = {
      verify: __PRIVATE_toName(t, e.key)
    };
  }
  return e.fieldTransforms.length > 0 && (r.updateTransforms = e.fieldTransforms.map(((t2) => (function __PRIVATE_toFieldTransform(t3, e2) {
    const r2 = e2.transform;
    if (r2 instanceof __PRIVATE_ServerTimestampTransform) return {
      fieldPath: e2.field.canonicalString(),
      setToServerValue: "REQUEST_TIME"
    };
    if (r2 instanceof __PRIVATE_ArrayUnionTransformOperation) return {
      fieldPath: e2.field.canonicalString(),
      appendMissingElements: {
        values: r2.elements
      }
    };
    if (r2 instanceof __PRIVATE_ArrayRemoveTransformOperation) return {
      fieldPath: e2.field.canonicalString(),
      removeAllFromArray: {
        values: r2.elements
      }
    };
    if (r2 instanceof __PRIVATE_NumericIncrementTransformOperation) return {
      fieldPath: e2.field.canonicalString(),
      increment: r2.k
    };
    throw fail(20930, {
      transform: e2.transform
    });
  })(0, t2)))), e.precondition.isNone || (r.currentDocument = (function __PRIVATE_toPrecondition(t2, e2) {
    return void 0 !== e2.updateTime ? {
      updateTime: __PRIVATE_toVersion(t2, e2.updateTime)
    } : void 0 !== e2.exists ? {
      exists: e2.exists
    } : fail(27497);
  })(t, e.precondition)), r;
}
function __PRIVATE_toDocumentMask(t) {
  const e = [];
  return t.fields.forEach(((t2) => e.push(t2.canonicalString()))), {
    fieldPaths: e
  };
}
function __PRIVATE_isValidResourceName(t) {
  return t.length >= 4 && "projects" === t.get(0) && "databases" === t.get(2);
}
function __PRIVATE_newSerializer(t) {
  return new JsonProtoSerializer(
    t,
    /* useProto3Json= */
    true
  );
}
var Datastore = class {
};
var __PRIVATE_DatastoreImpl = class extends Datastore {
  constructor(t, e, r, n) {
    super(), this.authCredentials = t, this.appCheckCredentials = e, this.connection = r, this.serializer = n, this.et = false;
  }
  rt() {
    if (this.et) throw new FirestoreError(S, "The client has already been terminated.");
  }
  /** Invokes the provided RPC with auth and AppCheck tokens. */
  I(t, e, r, n) {
    return this.rt(), Promise.all([this.authCredentials.getToken(), this.appCheckCredentials.getToken()]).then((([i, s]) => this.connection.I(t, __PRIVATE_toResourcePath(e, r), n, i, s))).catch(((t2) => {
      throw "FirebaseError" === t2.name ? (t2.code === D && (this.authCredentials.invalidateToken(), this.appCheckCredentials.invalidateToken()), t2) : new FirestoreError(p, t2.toString());
    }));
  }
  /** Invokes the provided RPC with streamed results with auth and AppCheck tokens. */
  D(t, e, r, n, i) {
    return this.rt(), Promise.all([this.authCredentials.getToken(), this.appCheckCredentials.getToken()]).then((([s, o]) => this.connection.D(t, __PRIVATE_toResourcePath(e, r), n, s, o, i))).catch(((t2) => {
      throw "FirebaseError" === t2.name ? (t2.code === D && (this.authCredentials.invalidateToken(), this.appCheckCredentials.invalidateToken()), t2) : new FirestoreError(p, t2.toString());
    }));
  }
  terminate() {
    this.et = true, this.connection.terminate();
  }
};
async function __PRIVATE_invokeCommitRpc(t, e) {
  const r = __PRIVATE_debugCast(t), n = {
    writes: e.map(((t2) => toMutation(r.serializer, t2)))
  };
  await r.I("Commit", r.serializer.databaseId, ResourcePath.emptyPath(), n);
}
async function __PRIVATE_invokeBatchGetDocumentsRpc(t, e) {
  const r = __PRIVATE_debugCast(t), n = {
    documents: e.map(((t2) => __PRIVATE_toName(r.serializer, t2)))
  }, i = await r.D("BatchGetDocuments", r.serializer.databaseId, ResourcePath.emptyPath(), n, e.length), s = /* @__PURE__ */ new Map();
  i.forEach(((t2) => {
    const e2 = __PRIVATE_fromBatchGetDocumentsResponse(r.serializer, t2);
    s.set(e2.key.toString(), e2);
  }));
  const o = [];
  return e.forEach(((t2) => {
    const e2 = s.get(t2.toString());
    __PRIVATE_hardAssert(!!e2, 55234, {
      key: t2
    }), o.push(e2);
  })), o;
}
var st = "ComponentProvider";
var ot = /* @__PURE__ */ new Map();
function __PRIVATE_getDatastore(t) {
  if (t._terminated) throw new FirestoreError(S, "The client has already been terminated.");
  if (!ot.has(t)) {
    __PRIVATE_logDebug(st, "Initializing Datastore");
    const e = (function __PRIVATE_newConnection(t2) {
      return new __PRIVATE_FetchConnection(t2);
    })((function __PRIVATE_makeDatabaseInfo(t2, e2, r2, n2) {
      return new DatabaseInfo(t2, e2, r2, n2.host, n2.ssl, n2.experimentalForceLongPolling, n2.experimentalAutoDetectLongPolling, __PRIVATE_cloneLongPollingOptions(n2.experimentalLongPollingOptions), n2.useFetchStreams, n2.isUsingEmulator);
    })(t._databaseId, t.app.options.appId || "", t._persistenceKey, t._freezeSettings())), r = __PRIVATE_newSerializer(t._databaseId), n = (function __PRIVATE_newDatastore(t2, e2, r2, n2) {
      return new __PRIVATE_DatastoreImpl(t2, e2, r2, n2);
    })(t._authCredentials, t._appCheckCredentials, e, r);
    ot.set(t, n);
  }
  return ot.get(t);
}
var at = 1048576;
var ut = "firestore.googleapis.com";
var _t = true;
var FirestoreSettingsImpl = class {
  constructor(t) {
    if (void 0 === t.host) {
      if (void 0 !== t.ssl) throw new FirestoreError(y, "Can't provide ssl option if host option is not set");
      this.host = ut, this.ssl = _t;
    } else this.host = t.host, this.ssl = t.ssl ?? _t;
    if (this.isUsingEmulator = void 0 !== t.emulatorOptions, this.credentials = t.credentials, this.ignoreUndefinedProperties = !!t.ignoreUndefinedProperties, this.localCache = t.localCache, void 0 === t.cacheSizeBytes) this.cacheSizeBytes = 41943040;
    else {
      if (-1 !== t.cacheSizeBytes && t.cacheSizeBytes < at) throw new FirestoreError(y, "cacheSizeBytes must be at least 1048576");
      this.cacheSizeBytes = t.cacheSizeBytes;
    }
    !(function __PRIVATE_validateIsNotUsedTogether(t2, e, r, n) {
      if (true === e && true === n) throw new FirestoreError(y, `${t2} and ${r} cannot be used together.`);
    })("experimentalForceLongPolling", t.experimentalForceLongPolling, "experimentalAutoDetectLongPolling", t.experimentalAutoDetectLongPolling), this.experimentalForceLongPolling = !!t.experimentalForceLongPolling, this.experimentalForceLongPolling ? this.experimentalAutoDetectLongPolling = false : void 0 === t.experimentalAutoDetectLongPolling ? this.experimentalAutoDetectLongPolling = true : (
      // For backwards compatibility, coerce the value to boolean even though
      // the TypeScript compiler has narrowed the type to boolean already.
      // noinspection PointlessBooleanExpressionJS
      this.experimentalAutoDetectLongPolling = !!t.experimentalAutoDetectLongPolling
    ), this.experimentalLongPollingOptions = __PRIVATE_cloneLongPollingOptions(t.experimentalLongPollingOptions ?? {}), (function __PRIVATE_validateLongPollingOptions(t2) {
      if (void 0 !== t2.timeoutSeconds) {
        if (isNaN(t2.timeoutSeconds)) throw new FirestoreError(y, `invalid long polling timeout: ${t2.timeoutSeconds} (must not be NaN)`);
        if (t2.timeoutSeconds < 5) throw new FirestoreError(y, `invalid long polling timeout: ${t2.timeoutSeconds} (minimum allowed value is 5)`);
        if (t2.timeoutSeconds > 30) throw new FirestoreError(y, `invalid long polling timeout: ${t2.timeoutSeconds} (maximum allowed value is 30)`);
      }
    })(this.experimentalLongPollingOptions), this.useFetchStreams = !!t.useFetchStreams;
  }
  isEqual(t) {
    return this.host === t.host && this.ssl === t.ssl && this.credentials === t.credentials && this.cacheSizeBytes === t.cacheSizeBytes && this.experimentalForceLongPolling === t.experimentalForceLongPolling && this.experimentalAutoDetectLongPolling === t.experimentalAutoDetectLongPolling && (function __PRIVATE_longPollingOptionsEqual(t2, e) {
      return t2.timeoutSeconds === e.timeoutSeconds;
    })(this.experimentalLongPollingOptions, t.experimentalLongPollingOptions) && this.ignoreUndefinedProperties === t.ignoreUndefinedProperties && this.useFetchStreams === t.useFetchStreams;
  }
};
var Firestore = class {
  /** @hideconstructor */
  constructor(t, e, r, n) {
    this._authCredentials = t, this._appCheckCredentials = e, this._databaseId = r, this._app = n, /**
     * Whether it's a Firestore or Firestore Lite instance.
     */
    this.type = "firestore-lite", this._persistenceKey = "(lite)", this._settings = new FirestoreSettingsImpl({}), this._settingsFrozen = false, this._emulatorOptions = {}, // A task that is assigned when the terminate() is invoked and resolved when
    // all components have shut down. Otherwise, Firestore is not terminated,
    // which can mean either the FirestoreClient is in the process of starting,
    // or restarting.
    this._terminateTask = "notTerminated";
  }
  /**
   * The {@link @firebase/app#FirebaseApp} associated with this `Firestore` service
   * instance.
   */
  get app() {
    if (!this._app) throw new FirestoreError(S, "Firestore was not initialized using the Firebase SDK. 'app' is not available");
    return this._app;
  }
  get _initialized() {
    return this._settingsFrozen;
  }
  get _terminated() {
    return "notTerminated" !== this._terminateTask;
  }
  _setSettings(t) {
    if (this._settingsFrozen) throw new FirestoreError(S, "Firestore has already been started and its settings can no longer be changed. You can only modify settings before calling any other methods on a Firestore object.");
    this._settings = new FirestoreSettingsImpl(t), this._emulatorOptions = t.emulatorOptions || {}, void 0 !== t.credentials && (this._authCredentials = (function __PRIVATE_makeAuthCredentialsProvider(t2) {
      if (!t2) return new __PRIVATE_EmptyAuthCredentialsProvider();
      switch (t2.type) {
        case "firstParty":
          return new __PRIVATE_FirstPartyAuthCredentialsProvider(t2.sessionIndex || "0", t2.iamToken || null, t2.authTokenFactory || null);
        case "provider":
          return t2.client;
        default:
          throw new FirestoreError(y, "makeAuthCredentialsProvider failed due to invalid credential type");
      }
    })(t.credentials));
  }
  _getSettings() {
    return this._settings;
  }
  _getEmulatorOptions() {
    return this._emulatorOptions;
  }
  _freezeSettings() {
    return this._settingsFrozen = true, this._settings;
  }
  _delete() {
    return "notTerminated" === this._terminateTask && (this._terminateTask = this._terminate()), this._terminateTask;
  }
  async _restart() {
    "notTerminated" === this._terminateTask ? await this._terminate() : this._terminateTask = "notTerminated";
  }
  /** Returns a JSON-serializable representation of this `Firestore` instance. */
  toJSON() {
    return {
      app: this._app,
      databaseId: this._databaseId,
      settings: this._settings
    };
  }
  /**
   * Terminates all components used by this client. Subclasses can override
   * this method to clean up their own dependencies, but must also call this
   * method.
   *
   * Only ever called once.
   */
  _terminate() {
    return (function __PRIVATE_removeComponents(t) {
      const e = ot.get(t);
      e && (__PRIVATE_logDebug(st, "Removing Datastore"), ot.delete(t), e.terminate());
    })(this), Promise.resolve();
  }
};
function getFirestore(t, r) {
  const n = "object" == typeof t ? t : getApp(), i = "string" == typeof t ? t : r || "(default)", s = _getProvider(n, "firestore/lite").getImmediate({
    identifier: i
  });
  if (!s._initialized) {
    const t2 = getDefaultEmulatorHostnameAndPort("firestore");
    t2 && connectFirestoreEmulator(s, ...t2);
  }
  return s;
}
function connectFirestoreEmulator(t, e, r, n = {}) {
  t = __PRIVATE_cast(t, Firestore);
  const i = isCloudWorkstation(e), s = t._getSettings(), o = {
    ...s,
    emulatorOptions: t._getEmulatorOptions()
  }, a = `${e}:${r}`;
  i && (pingServer(`https://${a}`), updateEmulatorBanner("Firestore", true)), s.host !== ut && s.host !== a && __PRIVATE_logWarn("Host has been set in both settings() and connectFirestoreEmulator(), emulator host will be used.");
  const u = {
    ...s,
    host: a,
    ssl: i,
    emulatorOptions: n
  };
  if (!deepEqual(u, o) && (t._setSettings(u), n.mockUserToken)) {
    let e2, r2;
    if ("string" == typeof n.mockUserToken) e2 = n.mockUserToken, r2 = User.MOCK_USER;
    else {
      e2 = createMockUserToken(n.mockUserToken, t._app?.options.projectId);
      const i2 = n.mockUserToken.sub || n.mockUserToken.user_id;
      if (!i2) throw new FirestoreError(y, "mockUserToken must contain 'sub' or 'user_id' field!");
      r2 = new User(i2);
    }
    t._authCredentials = new __PRIVATE_EmulatorAuthCredentialsProvider(new __PRIVATE_OAuthToken(e2, r2));
  }
}
var Query = class _Query {
  // This is the lite version of the Query class in the main SDK.
  /** @hideconstructor protected */
  constructor(t, e, r) {
    this.converter = e, this._query = r, /** The type of this Firestore reference. */
    this.type = "query", this.firestore = t;
  }
  withConverter(t) {
    return new _Query(this.firestore, t, this._query);
  }
};
var DocumentReference = class _DocumentReference {
  /** @hideconstructor */
  constructor(t, e, r) {
    this.converter = e, this._key = r, /** The type of this Firestore reference. */
    this.type = "document", this.firestore = t;
  }
  get _path() {
    return this._key.path;
  }
  /**
   * The document's identifier within its collection.
   */
  get id() {
    return this._key.path.lastSegment();
  }
  /**
   * A string representing the path of the referenced document (relative
   * to the root of the database).
   */
  get path() {
    return this._key.path.canonicalString();
  }
  /**
   * The collection this `DocumentReference` belongs to.
   */
  get parent() {
    return new CollectionReference(this.firestore, this.converter, this._key.path.popLast());
  }
  withConverter(t) {
    return new _DocumentReference(this.firestore, t, this._key);
  }
  /**
   * Returns a JSON-serializable representation of this `DocumentReference` instance.
   *
   * @returns a JSON representation of this object.
   */
  toJSON() {
    return {
      type: _DocumentReference._jsonSchemaVersion,
      referencePath: this._key.toString()
    };
  }
  static fromJSON(t, e, r) {
    if (__PRIVATE_validateJSON(e, _DocumentReference._jsonSchema)) return new _DocumentReference(t, r || null, new DocumentKey(ResourcePath.fromString(e.referencePath)));
  }
};
DocumentReference._jsonSchemaVersion = "firestore/documentReference/1.0", DocumentReference._jsonSchema = {
  type: property("string", DocumentReference._jsonSchemaVersion),
  referencePath: property("string")
};
var CollectionReference = class _CollectionReference extends Query {
  /** @hideconstructor */
  constructor(t, e, r) {
    super(t, e, (function __PRIVATE_newQueryForPath(t2) {
      return new __PRIVATE_QueryImpl(t2);
    })(r)), this._path = r, /** The type of this Firestore reference. */
    this.type = "collection";
  }
  /** The collection's identifier. */
  get id() {
    return this._query.path.lastSegment();
  }
  /**
   * A string representing the path of the referenced collection (relative
   * to the root of the database).
   */
  get path() {
    return this._query.path.canonicalString();
  }
  /**
   * A reference to the containing `DocumentReference` if this is a
   * subcollection. If this isn't a subcollection, the reference is null.
   */
  get parent() {
    const t = this._path.popLast();
    return t.isEmpty() ? null : new DocumentReference(
      this.firestore,
      /* converter= */
      null,
      new DocumentKey(t)
    );
  }
  withConverter(t) {
    return new _CollectionReference(this.firestore, t, this._path);
  }
};
function doc(t, e, ...r) {
  if (t = getModularInstance(t), // We allow omission of 'pathString' but explicitly prohibit passing in both
  // 'undefined' and 'null'.
  1 === arguments.length && (e = __PRIVATE_AutoId.newId()), __PRIVATE_validateNonEmptyArgument("doc", "path", e), t instanceof Firestore) {
    const n = ResourcePath.fromString(e, ...r);
    return __PRIVATE_validateDocumentPath(n), new DocumentReference(
      t,
      /* converter= */
      null,
      new DocumentKey(n)
    );
  }
  {
    if (!(t instanceof DocumentReference || t instanceof CollectionReference)) throw new FirestoreError(y, "Expected first argument to collection() to be a CollectionReference, a DocumentReference or FirebaseFirestore");
    const n = t._path.child(ResourcePath.fromString(e, ...r));
    return __PRIVATE_validateDocumentPath(n), new DocumentReference(t.firestore, t instanceof CollectionReference ? t.converter : null, new DocumentKey(n));
  }
}
var Bytes = class _Bytes {
  /** @hideconstructor */
  constructor(t) {
    this._byteString = t;
  }
  /**
   * Creates a new `Bytes` object from the given Base64 string, converting it to
   * bytes.
   *
   * @param base64 - The Base64 string used to create the `Bytes` object.
   */
  static fromBase64String(t) {
    try {
      return new _Bytes(ByteString.fromBase64String(t));
    } catch (t2) {
      throw new FirestoreError(y, "Failed to construct data from Base64 string: " + t2);
    }
  }
  /**
   * Creates a new `Bytes` object from the given Uint8Array.
   *
   * @param array - The Uint8Array used to create the `Bytes` object.
   */
  static fromUint8Array(t) {
    return new _Bytes(ByteString.fromUint8Array(t));
  }
  /**
   * Returns the underlying bytes as a Base64-encoded string.
   *
   * @returns The Base64-encoded string created from the `Bytes` object.
   */
  toBase64() {
    return this._byteString.toBase64();
  }
  /**
   * Returns the underlying bytes in a new `Uint8Array`.
   *
   * @returns The Uint8Array created from the `Bytes` object.
   */
  toUint8Array() {
    return this._byteString.toUint8Array();
  }
  /**
   * Returns a string representation of the `Bytes` object.
   *
   * @returns A string representation of the `Bytes` object.
   */
  toString() {
    return "Bytes(base64: " + this.toBase64() + ")";
  }
  /**
   * Returns true if this `Bytes` object is equal to the provided one.
   *
   * @param other - The `Bytes` object to compare against.
   * @returns true if this `Bytes` object is equal to the provided one.
   */
  isEqual(t) {
    return this._byteString.isEqual(t._byteString);
  }
  /**
   * Returns a JSON-serializable representation of this `Bytes` instance.
   *
   * @returns a JSON representation of this object.
   */
  toJSON() {
    return {
      type: _Bytes._jsonSchemaVersion,
      bytes: this.toBase64()
    };
  }
  /**
   * Builds a `Bytes` instance from a JSON object created by {@link Bytes.toJSON}.
   *
   * @param json a JSON object represention of a `Bytes` instance
   * @returns an instance of {@link Bytes} if the JSON object could be parsed. Throws a
   * {@link FirestoreError} if an error occurs.
   */
  static fromJSON(t) {
    if (__PRIVATE_validateJSON(t, _Bytes._jsonSchema)) return _Bytes.fromBase64String(t.bytes);
  }
};
Bytes._jsonSchemaVersion = "firestore/bytes/1.0", Bytes._jsonSchema = {
  type: property("string", Bytes._jsonSchemaVersion),
  bytes: property("string")
};
var FieldPath = class {
  /**
   * Creates a `FieldPath` from the provided field names. If more than one field
   * name is provided, the path will point to a nested field in a document.
   *
   * @param fieldNames - A list of field names.
   */
  constructor(...t) {
    for (let e = 0; e < t.length; ++e) if (0 === t[e].length) throw new FirestoreError(y, "Invalid field name at argument $(i + 1). Field names must not be empty.");
    this._internalPath = new FieldPath$1(t);
  }
  /**
   * Returns true if this `FieldPath` is equal to the provided one.
   *
   * @param other - The `FieldPath` to compare against.
   * @returns true if this `FieldPath` is equal to the provided one.
   */
  isEqual(t) {
    return this._internalPath.isEqual(t._internalPath);
  }
};
var FieldValue = class {
  /**
   * @param _methodName - The public API endpoint that returns this class.
   * @hideconstructor
   */
  constructor(t) {
    this._methodName = t;
  }
};
var GeoPoint = class _GeoPoint {
  /**
   * Creates a new immutable `GeoPoint` object with the provided latitude and
   * longitude values.
   * @param latitude - The latitude as number between -90 and 90.
   * @param longitude - The longitude as number between -180 and 180.
   */
  constructor(t, e) {
    if (!isFinite(t) || t < -90 || t > 90) throw new FirestoreError(y, "Latitude must be a number between -90 and 90, but was: " + t);
    if (!isFinite(e) || e < -180 || e > 180) throw new FirestoreError(y, "Longitude must be a number between -180 and 180, but was: " + e);
    this._lat = t, this._long = e;
  }
  /**
   * The latitude of this `GeoPoint` instance.
   */
  get latitude() {
    return this._lat;
  }
  /**
   * The longitude of this `GeoPoint` instance.
   */
  get longitude() {
    return this._long;
  }
  /**
   * Returns true if this `GeoPoint` is equal to the provided one.
   *
   * @param other - The `GeoPoint` to compare against.
   * @returns true if this `GeoPoint` is equal to the provided one.
   */
  isEqual(t) {
    return this._lat === t._lat && this._long === t._long;
  }
  /**
   * Actually private to JS consumers of our API, so this function is prefixed
   * with an underscore.
   */
  _compareTo(t) {
    return __PRIVATE_primitiveComparator(this._lat, t._lat) || __PRIVATE_primitiveComparator(this._long, t._long);
  }
  /**
   * Returns a JSON-serializable representation of this `GeoPoint` instance.
   *
   * @returns a JSON representation of this object.
   */
  toJSON() {
    return {
      latitude: this._lat,
      longitude: this._long,
      type: _GeoPoint._jsonSchemaVersion
    };
  }
  /**
   * Builds a `GeoPoint` instance from a JSON object created by {@link GeoPoint.toJSON}.
   *
   * @param json a JSON object represention of a `GeoPoint` instance
   * @returns an instance of {@link GeoPoint} if the JSON object could be parsed. Throws a
   * {@link FirestoreError} if an error occurs.
   */
  static fromJSON(t) {
    if (__PRIVATE_validateJSON(t, _GeoPoint._jsonSchema)) return new _GeoPoint(t.latitude, t.longitude);
  }
};
GeoPoint._jsonSchemaVersion = "firestore/geoPoint/1.0", GeoPoint._jsonSchema = {
  type: property("string", GeoPoint._jsonSchemaVersion),
  latitude: property("number"),
  longitude: property("number")
};
var VectorValue = class _VectorValue {
  /**
   * @private
   * @internal
   */
  constructor(t) {
    this._values = (t || []).map(((t2) => t2));
  }
  /**
   * Returns a copy of the raw number array form of the vector.
   */
  toArray() {
    return this._values.map(((t) => t));
  }
  /**
   * Returns `true` if the two `VectorValue` values have the same raw number arrays, returns `false` otherwise.
   */
  isEqual(t) {
    return (function __PRIVATE_isPrimitiveArrayEqual(t2, e) {
      if (t2.length !== e.length) return false;
      for (let r = 0; r < t2.length; ++r) if (t2[r] !== e[r]) return false;
      return true;
    })(this._values, t._values);
  }
  /**
   * Returns a JSON-serializable representation of this `VectorValue` instance.
   *
   * @returns a JSON representation of this object.
   */
  toJSON() {
    return {
      type: _VectorValue._jsonSchemaVersion,
      vectorValues: this._values
    };
  }
  /**
   * Builds a `VectorValue` instance from a JSON object created by {@link VectorValue.toJSON}.
   *
   * @param json a JSON object represention of a `VectorValue` instance.
   * @returns an instance of {@link VectorValue} if the JSON object could be parsed. Throws a
   * {@link FirestoreError} if an error occurs.
   */
  static fromJSON(t) {
    if (__PRIVATE_validateJSON(t, _VectorValue._jsonSchema)) {
      if (Array.isArray(t.vectorValues) && t.vectorValues.every(((t2) => "number" == typeof t2))) return new _VectorValue(t.vectorValues);
      throw new FirestoreError(y, "Expected 'vectorValues' field to be a number array");
    }
  }
};
VectorValue._jsonSchemaVersion = "firestore/vectorValue/1.0", VectorValue._jsonSchema = {
  type: property("string", VectorValue._jsonSchemaVersion),
  vectorValues: property("object")
};
var ct = /^__.*__$/;
var ParsedSetData = class {
  constructor(t, e, r) {
    this.data = t, this.fieldMask = e, this.fieldTransforms = r;
  }
  toMutation(t, e) {
    return null !== this.fieldMask ? new __PRIVATE_PatchMutation(t, this.data, this.fieldMask, e, this.fieldTransforms) : new __PRIVATE_SetMutation(t, this.data, e, this.fieldTransforms);
  }
};
var ParsedUpdateData = class {
  constructor(t, e, r) {
    this.data = t, this.fieldMask = e, this.fieldTransforms = r;
  }
  toMutation(t, e) {
    return new __PRIVATE_PatchMutation(t, this.data, this.fieldMask, e, this.fieldTransforms);
  }
};
function __PRIVATE_isWrite(t) {
  switch (t) {
    case 0:
    // fall through
    case 2:
    // fall through
    case 1:
      return true;
    case 3:
    case 4:
      return false;
    default:
      throw fail(40011, {
        it: t
      });
  }
}
var __PRIVATE_ParseContextImpl = class ___PRIVATE_ParseContextImpl {
  /**
   * Initializes a ParseContext with the given source and path.
   *
   * @param settings - The settings for the parser.
   * @param databaseId - The database ID of the Firestore instance.
   * @param serializer - The serializer to use to generate the Value proto.
   * @param ignoreUndefinedProperties - Whether to ignore undefined properties
   * rather than throw.
   * @param fieldTransforms - A mutable list of field transforms encountered
   * while parsing the data.
   * @param fieldMask - A mutable list of field paths encountered while parsing
   * the data.
   *
   * TODO(b/34871131): We don't support array paths right now, so path can be
   * null to indicate the context represents any location within an array (in
   * which case certain features will not work and errors will be somewhat
   * compromised).
   */
  constructor(t, e, r, n, i, s) {
    this.settings = t, this.databaseId = e, this.serializer = r, this.ignoreUndefinedProperties = n, // Minor hack: If fieldTransforms is undefined, we assume this is an
    // external call and we need to validate the entire path.
    void 0 === i && this.st(), this.fieldTransforms = i || [], this.fieldMask = s || [];
  }
  get path() {
    return this.settings.path;
  }
  get it() {
    return this.settings.it;
  }
  /** Returns a new context with the specified settings overwritten. */
  ot(t) {
    return new ___PRIVATE_ParseContextImpl({
      ...this.settings,
      ...t
    }, this.databaseId, this.serializer, this.ignoreUndefinedProperties, this.fieldTransforms, this.fieldMask);
  }
  ut(t) {
    const e = this.path?.child(t), r = this.ot({
      path: e,
      _t: false
    });
    return r.ct(t), r;
  }
  lt(t) {
    const e = this.path?.child(t), r = this.ot({
      path: e,
      _t: false
    });
    return r.st(), r;
  }
  ht(t) {
    return this.ot({
      path: void 0,
      _t: true
    });
  }
  ft(t) {
    return __PRIVATE_createError(t, this.settings.methodName, this.settings.dt || false, this.path, this.settings.Et);
  }
  /** Returns 'true' if 'fieldPath' was traversed when creating this context. */
  contains(t) {
    return void 0 !== this.fieldMask.find(((e) => t.isPrefixOf(e))) || void 0 !== this.fieldTransforms.find(((e) => t.isPrefixOf(e.field)));
  }
  st() {
    if (this.path) for (let t = 0; t < this.path.length; t++) this.ct(this.path.get(t));
  }
  ct(t) {
    if (0 === t.length) throw this.ft("Document fields must not be empty");
    if (__PRIVATE_isWrite(this.it) && ct.test(t)) throw this.ft('Document fields cannot begin and end with "__"');
  }
};
var __PRIVATE_UserDataReader = class {
  constructor(t, e, r) {
    this.databaseId = t, this.ignoreUndefinedProperties = e, this.serializer = r || __PRIVATE_newSerializer(t);
  }
  /** Creates a new top-level parse context. */
  Tt(t, e, r, n = false) {
    return new __PRIVATE_ParseContextImpl({
      it: t,
      methodName: e,
      Et: r,
      path: FieldPath$1.emptyPath(),
      _t: false,
      dt: n
    }, this.databaseId, this.serializer, this.ignoreUndefinedProperties);
  }
};
function __PRIVATE_newUserDataReader(t) {
  const e = t._freezeSettings(), r = __PRIVATE_newSerializer(t._databaseId);
  return new __PRIVATE_UserDataReader(t._databaseId, !!e.ignoreUndefinedProperties, r);
}
function __PRIVATE_parseSetData(t, e, r, n, i, s = {}) {
  const o = t.Tt(s.merge || s.mergeFields ? 2 : 0, e, r, i);
  __PRIVATE_validatePlainObject("Data must be an object, but it was:", o, n);
  const a = __PRIVATE_parseObject(n, o);
  let u, _;
  if (s.merge) u = new FieldMask(o.fieldMask), _ = o.fieldTransforms;
  else if (s.mergeFields) {
    const t2 = [];
    for (const n2 of s.mergeFields) {
      const i2 = __PRIVATE_fieldPathFromArgument$1(e, n2, r);
      if (!o.contains(i2)) throw new FirestoreError(y, `Field '${i2}' is specified in your field mask but missing from your input data.`);
      __PRIVATE_fieldMaskContains(t2, i2) || t2.push(i2);
    }
    u = new FieldMask(t2), _ = o.fieldTransforms.filter(((t3) => u.covers(t3.field)));
  } else u = null, _ = o.fieldTransforms;
  return new ParsedSetData(new ObjectValue(a), u, _);
}
var __PRIVATE_DeleteFieldValueImpl = class ___PRIVATE_DeleteFieldValueImpl extends FieldValue {
  _toFieldTransform(t) {
    if (2 !== t.it) throw 1 === t.it ? t.ft(`${this._methodName}() can only appear at the top level of your update data`) : t.ft(`${this._methodName}() cannot be used with set() unless you pass {merge:true}`);
    return t.fieldMask.push(t.path), null;
  }
  isEqual(t) {
    return t instanceof ___PRIVATE_DeleteFieldValueImpl;
  }
};
function __PRIVATE_parseUpdateData(t, e, r, n) {
  const i = t.Tt(1, e, r);
  __PRIVATE_validatePlainObject("Data must be an object, but it was:", i, n);
  const s = [], o = ObjectValue.empty();
  forEach(n, ((t2, n2) => {
    const a2 = __PRIVATE_fieldPathFromDotSeparatedString(e, t2, r);
    n2 = getModularInstance(n2);
    const u = i.lt(a2);
    if (n2 instanceof __PRIVATE_DeleteFieldValueImpl)
      s.push(a2);
    else {
      const t3 = __PRIVATE_parseData(n2, u);
      null != t3 && (s.push(a2), o.set(a2, t3));
    }
  }));
  const a = new FieldMask(s);
  return new ParsedUpdateData(o, a, i.fieldTransforms);
}
function __PRIVATE_parseUpdateVarargs(t, e, r, n, i, s) {
  const o = t.Tt(1, e, r), a = [__PRIVATE_fieldPathFromArgument$1(e, n, r)], u = [i];
  if (s.length % 2 != 0) throw new FirestoreError(y, `Function ${e}() needs to be called with an even number of arguments that alternate between field names and values.`);
  for (let t2 = 0; t2 < s.length; t2 += 2) a.push(__PRIVATE_fieldPathFromArgument$1(e, s[t2])), u.push(s[t2 + 1]);
  const _ = [], c = ObjectValue.empty();
  for (let t2 = a.length - 1; t2 >= 0; --t2) if (!__PRIVATE_fieldMaskContains(_, a[t2])) {
    const e2 = a[t2];
    let r2 = u[t2];
    r2 = getModularInstance(r2);
    const n2 = o.lt(e2);
    if (r2 instanceof __PRIVATE_DeleteFieldValueImpl)
      _.push(e2);
    else {
      const t3 = __PRIVATE_parseData(r2, n2);
      null != t3 && (_.push(e2), c.set(e2, t3));
    }
  }
  const l = new FieldMask(_);
  return new ParsedUpdateData(c, l, o.fieldTransforms);
}
function __PRIVATE_parseData(t, e) {
  if (__PRIVATE_looksLikeJsonObject(
    // Unwrap the API type from the Compat SDK. This will return the API type
    // from firestore-exp.
    t = getModularInstance(t)
  )) return __PRIVATE_validatePlainObject("Unsupported field value:", e, t), __PRIVATE_parseObject(t, e);
  if (t instanceof FieldValue)
    return (function __PRIVATE_parseSentinelFieldValue(t2, e2) {
      if (!__PRIVATE_isWrite(e2.it)) throw e2.ft(`${t2._methodName}() can only be used with update() and set()`);
      if (!e2.path) throw e2.ft(`${t2._methodName}() is not currently supported inside arrays`);
      const r = t2._toFieldTransform(e2);
      r && e2.fieldTransforms.push(r);
    })(t, e), null;
  if (void 0 === t && e.ignoreUndefinedProperties)
    return null;
  if (
    // If context.path is null we are inside an array and we don't support
    // field mask paths more granular than the top-level array.
    e.path && e.fieldMask.push(e.path), t instanceof Array
  ) {
    if (e.settings._t && 4 !== e.it) throw e.ft("Nested arrays are not supported");
    return (function __PRIVATE_parseArray(t2, e2) {
      const r = [];
      let n = 0;
      for (const i of t2) {
        let t3 = __PRIVATE_parseData(i, e2.ht(n));
        null == t3 && // Just include nulls in the array for fields being replaced with a
        // sentinel.
        (t3 = {
          nullValue: "NULL_VALUE"
        }), r.push(t3), n++;
      }
      return {
        arrayValue: {
          values: r
        }
      };
    })(t, e);
  }
  return (function __PRIVATE_parseScalarValue(t2, e2) {
    if (null === (t2 = getModularInstance(t2))) return {
      nullValue: "NULL_VALUE"
    };
    if ("number" == typeof t2) return toNumber(e2.serializer, t2);
    if ("boolean" == typeof t2) return {
      booleanValue: t2
    };
    if ("string" == typeof t2) return {
      stringValue: t2
    };
    if (t2 instanceof Date) {
      const r = Timestamp.fromDate(t2);
      return {
        timestampValue: toTimestamp(e2.serializer, r)
      };
    }
    if (t2 instanceof Timestamp) {
      const r = new Timestamp(t2.seconds, 1e3 * Math.floor(t2.nanoseconds / 1e3));
      return {
        timestampValue: toTimestamp(e2.serializer, r)
      };
    }
    if (t2 instanceof GeoPoint) return {
      geoPointValue: {
        latitude: t2.latitude,
        longitude: t2.longitude
      }
    };
    if (t2 instanceof Bytes) return {
      bytesValue: __PRIVATE_toBytes(e2.serializer, t2._byteString)
    };
    if (t2 instanceof DocumentReference) {
      const r = e2.databaseId, n = t2.firestore._databaseId;
      if (!n.isEqual(r)) throw e2.ft(`Document reference is for database ${n.projectId}/${n.database} but should be for database ${r.projectId}/${r.database}`);
      return {
        referenceValue: __PRIVATE_toResourceName(t2.firestore._databaseId || e2.databaseId, t2._key.path)
      };
    }
    if (t2 instanceof VectorValue)
      return (function __PRIVATE_parseVectorValue(t3, e3) {
        const r = {
          fields: {
            [Y]: {
              stringValue: tt
            },
            [et]: {
              arrayValue: {
                values: t3.toArray().map(((t4) => {
                  if ("number" != typeof t4) throw e3.ft("VectorValues must only contain numeric values.");
                  return __PRIVATE_toDouble(e3.serializer, t4);
                }))
              }
            }
          }
        };
        return {
          mapValue: r
        };
      })(t2, e2);
    throw e2.ft(`Unsupported field value: ${__PRIVATE_valueDescription(t2)}`);
  })(t, e);
}
function __PRIVATE_parseObject(t, e) {
  const r = {};
  return !(function isEmpty2(t2) {
    for (const e2 in t2) if (Object.prototype.hasOwnProperty.call(t2, e2)) return false;
    return true;
  })(t) ? forEach(t, ((t2, n) => {
    const i = __PRIVATE_parseData(n, e.ut(t2));
    null != i && (r[t2] = i);
  })) : (
    // If we encounter an empty object, we explicitly add it to the update
    // mask to ensure that the server creates a map entry.
    e.path && e.path.length > 0 && e.fieldMask.push(e.path)
  ), {
    mapValue: {
      fields: r
    }
  };
}
function __PRIVATE_looksLikeJsonObject(t) {
  return !("object" != typeof t || null === t || t instanceof Array || t instanceof Date || t instanceof Timestamp || t instanceof GeoPoint || t instanceof Bytes || t instanceof DocumentReference || t instanceof FieldValue || t instanceof VectorValue);
}
function __PRIVATE_validatePlainObject(t, e, r) {
  if (!__PRIVATE_looksLikeJsonObject(r) || !__PRIVATE_isPlainObject(r)) {
    const n = __PRIVATE_valueDescription(r);
    throw "an object" === n ? e.ft(t + " a custom object") : e.ft(t + " " + n);
  }
}
function __PRIVATE_fieldPathFromArgument$1(t, e, r) {
  if (
    // If required, replace the FieldPath Compat class with the firestore-exp
    // FieldPath.
    (e = getModularInstance(e)) instanceof FieldPath
  ) return e._internalPath;
  if ("string" == typeof e) return __PRIVATE_fieldPathFromDotSeparatedString(t, e);
  throw __PRIVATE_createError(
    "Field path arguments must be of type string or ",
    t,
    /* hasConverter= */
    false,
    /* path= */
    void 0,
    r
  );
}
var lt = new RegExp("[~\\*/\\[\\]]");
function __PRIVATE_fieldPathFromDotSeparatedString(t, e, r) {
  if (e.search(lt) >= 0) throw __PRIVATE_createError(
    `Invalid field path (${e}). Paths must not contain '~', '*', '/', '[', or ']'`,
    t,
    /* hasConverter= */
    false,
    /* path= */
    void 0,
    r
  );
  try {
    return new FieldPath(...e.split("."))._internalPath;
  } catch (n) {
    throw __PRIVATE_createError(
      `Invalid field path (${e}). Paths must not be empty, begin with '.', end with '.', or contain '..'`,
      t,
      /* hasConverter= */
      false,
      /* path= */
      void 0,
      r
    );
  }
}
function __PRIVATE_createError(t, e, r, n, i) {
  const s = n && !n.isEmpty(), o = void 0 !== i;
  let a = `Function ${e}() called with invalid data`;
  r && (a += " (via `toFirestore()`)"), a += ". ";
  let u = "";
  return (s || o) && (u += " (found", s && (u += ` in field ${n}`), o && (u += ` in document ${i}`), u += ")"), new FirestoreError(y, a + t + u);
}
function __PRIVATE_fieldMaskContains(t, e) {
  return t.some(((t2) => t2.isEqual(e)));
}
var DocumentSnapshot = class {
  // Note: This class is stripped down version of the DocumentSnapshot in
  // the legacy SDK. The changes are:
  // - No support for SnapshotMetadata.
  // - No support for SnapshotOptions.
  /** @hideconstructor protected */
  constructor(t, e, r, n, i) {
    this._firestore = t, this._userDataWriter = e, this._key = r, this._document = n, this._converter = i;
  }
  /** Property of the `DocumentSnapshot` that provides the document's ID. */
  get id() {
    return this._key.path.lastSegment();
  }
  /**
   * The `DocumentReference` for the document included in the `DocumentSnapshot`.
   */
  get ref() {
    return new DocumentReference(this._firestore, this._converter, this._key);
  }
  /**
   * Signals whether or not the document at the snapshot's location exists.
   *
   * @returns true if the document exists.
   */
  exists() {
    return null !== this._document;
  }
  /**
   * Retrieves all fields in the document as an `Object`. Returns `undefined` if
   * the document doesn't exist.
   *
   * @returns An `Object` containing all fields in the document or `undefined`
   * if the document doesn't exist.
   */
  data() {
    if (this._document) {
      if (this._converter) {
        const t = new QueryDocumentSnapshot(
          this._firestore,
          this._userDataWriter,
          this._key,
          this._document,
          /* converter= */
          null
        );
        return this._converter.fromFirestore(t);
      }
      return this._userDataWriter.convertValue(this._document.data.value);
    }
  }
  /**
   * Retrieves the field specified by `fieldPath`. Returns `undefined` if the
   * document or field doesn't exist.
   *
   * @param fieldPath - The path (for example 'foo' or 'foo.bar') to a specific
   * field.
   * @returns The data at the specified field location or undefined if no such
   * field exists in the document.
   */
  // We are using `any` here to avoid an explicit cast by our users.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  get(t) {
    if (this._document) {
      const e = this._document.data.field(__PRIVATE_fieldPathFromArgument("DocumentSnapshot.get", t));
      if (null !== e) return this._userDataWriter.convertValue(e);
    }
  }
};
var QueryDocumentSnapshot = class extends DocumentSnapshot {
  /**
   * Retrieves all fields in the document as an `Object`.
   *
   * @override
   * @returns An `Object` containing all fields in the document.
   */
  data() {
    return super.data();
  }
};
function __PRIVATE_fieldPathFromArgument(t, e) {
  return "string" == typeof e ? __PRIVATE_fieldPathFromDotSeparatedString(t, e) : e instanceof FieldPath ? e._internalPath : e._delegate._internalPath;
}
var AbstractUserDataWriter = class {
  convertValue(t, e = "none") {
    switch (__PRIVATE_typeOrder(t)) {
      case 0:
        return null;
      case 1:
        return t.booleanValue;
      case 2:
        return __PRIVATE_normalizeNumber(t.integerValue || t.doubleValue);
      case 3:
        return this.convertTimestamp(t.timestampValue);
      case 4:
        return this.convertServerTimestamp(t, e);
      case 5:
        return t.stringValue;
      case 6:
        return this.convertBytes(__PRIVATE_normalizeByteString(t.bytesValue));
      case 7:
        return this.convertReference(t.referenceValue);
      case 8:
        return this.convertGeoPoint(t.geoPointValue);
      case 9:
        return this.convertArray(t.arrayValue, e);
      case 11:
        return this.convertObject(t.mapValue, e);
      case 10:
        return this.convertVectorValue(t.mapValue);
      default:
        throw fail(62114, {
          value: t
        });
    }
  }
  convertObject(t, e) {
    return this.convertObjectMap(t.fields, e);
  }
  /**
   * @internal
   */
  convertObjectMap(t, e = "none") {
    const r = {};
    return forEach(t, ((t2, n) => {
      r[t2] = this.convertValue(n, e);
    })), r;
  }
  /**
   * @internal
   */
  convertVectorValue(t) {
    const e = t.fields?.[et].arrayValue?.values?.map(((t2) => __PRIVATE_normalizeNumber(t2.doubleValue)));
    return new VectorValue(e);
  }
  convertGeoPoint(t) {
    return new GeoPoint(__PRIVATE_normalizeNumber(t.latitude), __PRIVATE_normalizeNumber(t.longitude));
  }
  convertArray(t, e) {
    return (t.values || []).map(((t2) => this.convertValue(t2, e)));
  }
  convertServerTimestamp(t, e) {
    switch (e) {
      case "previous":
        const r = __PRIVATE_getPreviousValue(t);
        return null == r ? null : this.convertValue(r, e);
      case "estimate":
        return this.convertTimestamp(__PRIVATE_getLocalWriteTime(t));
      default:
        return null;
    }
  }
  convertTimestamp(t) {
    const e = __PRIVATE_normalizeTimestamp(t);
    return new Timestamp(e.seconds, e.nanos);
  }
  convertDocumentKey(t, e) {
    const r = ResourcePath.fromString(t);
    __PRIVATE_hardAssert(__PRIVATE_isValidResourceName(r), 9688, {
      name: t
    });
    const n = new DatabaseId(r.get(1), r.get(3)), i = new DocumentKey(r.popFirst(5));
    return n.isEqual(e) || // TODO(b/64130202): Somehow support foreign references.
    __PRIVATE_logError(`Document ${i} contains a document reference within a different database (${n.projectId}/${n.database}) which is not supported. It will be treated as a reference in the current database (${e.projectId}/${e.database}) instead.`), i;
  }
};
function __PRIVATE_applyFirestoreDataConverter(t, e, r) {
  let n;
  return n = t ? r && (r.merge || r.mergeFields) ? t.toFirestore(e, r) : t.toFirestore(e) : e, n;
}
var __PRIVATE_LiteUserDataWriter = class extends AbstractUserDataWriter {
  constructor(t) {
    super(), this.firestore = t;
  }
  convertBytes(t) {
    return new Bytes(t);
  }
  convertReference(t) {
    const e = this.convertDocumentKey(t, this.firestore._databaseId);
    return new DocumentReference(
      this.firestore,
      /* converter= */
      null,
      e
    );
  }
};
function getDoc(t) {
  const e = __PRIVATE_getDatastore((t = __PRIVATE_cast(t, DocumentReference)).firestore), r = new __PRIVATE_LiteUserDataWriter(t.firestore);
  return __PRIVATE_invokeBatchGetDocumentsRpc(e, [t._key]).then(((e2) => {
    __PRIVATE_hardAssert(1 === e2.length, 15618);
    const n = e2[0];
    return new DocumentSnapshot(t.firestore, r, t._key, n.isFoundDocument() ? n : null, t.converter);
  }));
}
var WriteBatch = class {
  /** @hideconstructor */
  constructor(t, e) {
    this._firestore = t, this._commitHandler = e, this._mutations = [], this._committed = false, this._dataReader = __PRIVATE_newUserDataReader(t);
  }
  set(t, e, r) {
    this._verifyNotCommitted();
    const n = __PRIVATE_validateReference(t, this._firestore), i = __PRIVATE_applyFirestoreDataConverter(n.converter, e, r), s = __PRIVATE_parseSetData(this._dataReader, "WriteBatch.set", n._key, i, null !== n.converter, r);
    return this._mutations.push(s.toMutation(n._key, Precondition.none())), this;
  }
  update(t, e, r, ...n) {
    this._verifyNotCommitted();
    const i = __PRIVATE_validateReference(t, this._firestore);
    let s;
    return s = "string" == typeof (e = getModularInstance(e)) || e instanceof FieldPath ? __PRIVATE_parseUpdateVarargs(this._dataReader, "WriteBatch.update", i._key, e, r, n) : __PRIVATE_parseUpdateData(this._dataReader, "WriteBatch.update", i._key, e), this._mutations.push(s.toMutation(i._key, Precondition.exists(true))), this;
  }
  /**
   * Deletes the document referred to by the provided {@link DocumentReference}.
   *
   * @param documentRef - A reference to the document to be deleted.
   * @returns This `WriteBatch` instance. Used for chaining method calls.
   */
  delete(t) {
    this._verifyNotCommitted();
    const e = __PRIVATE_validateReference(t, this._firestore);
    return this._mutations = this._mutations.concat(new __PRIVATE_DeleteMutation(e._key, Precondition.none())), this;
  }
  /**
   * Commits all of the writes in this write batch as a single atomic unit.
   *
   * The result of these writes will only be reflected in document reads that
   * occur after the returned promise resolves. If the client is offline, the
   * write fails. If you would like to see local modifications or buffer writes
   * until the client is online, use the full Firestore SDK.
   *
   * @returns A `Promise` resolved once all of the writes in the batch have been
   * successfully written to the backend as an atomic unit (note that it won't
   * resolve while you're offline).
   */
  commit() {
    return this._verifyNotCommitted(), this._committed = true, this._mutations.length > 0 ? this._commitHandler(this._mutations) : Promise.resolve();
  }
  _verifyNotCommitted() {
    if (this._committed) throw new FirestoreError(S, "A write batch can no longer be used after commit() has been called.");
  }
};
function __PRIVATE_validateReference(t, e) {
  if ((t = getModularInstance(t)).firestore !== e) throw new FirestoreError(y, "Provided document reference is from a different Firestore instance.");
  return t;
}
function writeBatch(t) {
  const e = __PRIVATE_getDatastore(t = __PRIVATE_cast(t, Firestore));
  return new WriteBatch(t, ((t2) => __PRIVATE_invokeCommitRpc(e, t2)));
}
!(function __PRIVATE_registerFirestore() {
  !(function __PRIVATE_setSDKVersion(t) {
    A = t;
  })(`${SDK_VERSION}_lite`), _registerComponent(new Component("firestore/lite", ((t, { instanceIdentifier: e, options: r }) => {
    const n = t.getProvider("app").getImmediate(), i = new Firestore(new __PRIVATE_LiteAuthCredentialsProvider(t.getProvider("auth-internal")), new __PRIVATE_LiteAppCheckTokenProvider(n, t.getProvider("app-check-internal")), (function __PRIVATE_databaseIdFromApp(t2, e2) {
      if (!Object.prototype.hasOwnProperty.apply(t2.options, ["projectId"])) throw new FirestoreError(y, '"projectId" not provided in firebase.initializeApp.');
      return new DatabaseId(t2.options.projectId, e2);
    })(n, e), n);
    return r && i._setSettings(r), i;
  }), "PUBLIC").setMultipleInstances(true)), // RUNTIME_ENV and BUILD_TARGET are replaced by real values during the compilation
  registerVersion("firestore-lite", P, ""), registerVersion("firestore-lite", P, "esm2020");
})();

// src/main.ts
var import_canonicalize2 = __toESM(require_canonicalize(), 1);

// src/sync.ts
var import_canonicalize = __toESM(require_canonicalize(), 1);
function sha256Bytes(value) {
  return crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)).then((bytes) => Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join(""));
}
async function digest(value) {
  const text = (0, import_canonicalize.default)(value);
  if (!text)
    throw new Error("record is not canonicalizable");
  return sha256Bytes(text);
}
function safeId(value, name4) {
  if (!value || value === "." || value === ".." || value.includes("/"))
    throw new Error(`${name4} is invalid`);
  return value;
}
function splitPath(path) {
  if (!path || path.startsWith("/") || path.endsWith("/") || path.split("/").some((part) => !part))
    throw new Error("instruction path is invalid");
  return path.split("/").map((part) => safeId(part, "path component"));
}
function validateBoundPath(parts, expected, mode, namespace) {
  if (parts.length % 2 !== 0 || parts[0] !== "projects" || parts[1] !== expected.projectId || parts[2] !== "workspaces" || parts[3] !== expected.workspaceId)
    throw new Error("instruction path binding is invalid");
  if (namespace === "runtime") {
    if (parts.length !== 10 || parts[4] !== "users" || parts[5] !== expected.firebaseUid || parts[6] !== "tasks" || parts[7] !== expected.taskId || parts[8] !== "manifests" && parts[8] !== "results" && parts[8] !== "events")
      throw new Error("instruction path binding is invalid");
    if (mode !== "read" || parts[8] === "manifests" && parts[9] !== "latest" || parts[8] !== "manifests" && !/^[a-f0-9]{64}$/.test(parts[9]))
      throw new Error("instruction path binding is invalid");
    return;
  }
  if (parts[4] !== "members" || parts[5] !== expected.firebaseUid || parts[6] !== "requests" && parts[6] !== "exports")
    throw new Error("instruction path binding is invalid");
  if (parts[6] === "exports" && parts.length !== 8)
    throw new Error("instruction path binding is invalid");
  if (parts[6] === "requests" && (parts.length !== 8 && parts.length !== 10 || parts.length === 10 && (parts[8] !== "approvals" || !parts[9])))
    throw new Error("instruction path binding is invalid");
}
var MIRROR_KEYS = /* @__PURE__ */ new Set(["expires_at_ts", "approved_at_ts", "created_at_ts", "committed_at_ts"]);
function cloneModel(value) {
  if (Array.isArray(value))
    return value.map(cloneModel);
  if (!value || typeof value !== "object")
    return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cloneModel(item)]));
}
function nativeEnvelope(value) {
  if (Array.isArray(value))
    return value.map(nativeEnvelope);
  if (!value || typeof value !== "object")
    return value;
  const result = {};
  for (const [key, item] of Object.entries(value)) {
    if (MIRROR_KEYS.has(key) && item && typeof item === "object") {
      const mirror = item;
      if (mirror.type === "firestore/timestamp/1.0" && Number.isInteger(mirror.seconds) && Number.isInteger(mirror.nanoseconds)) {
        result[key] = new Timestamp(mirror.seconds, mirror.nanoseconds);
        continue;
      }
    }
    result[key] = key === "approval" ? nativeEnvelope(item) : cloneModel(item);
  }
  return result;
}
function portableEnvelope(value) {
  if (Array.isArray(value))
    return value.map(portableEnvelope);
  if (!value || typeof value !== "object")
    return value;
  if (value instanceof Timestamp) {
    const mirror = value;
    return { type: "firestore/timestamp/1.0", seconds: mirror.seconds, nanoseconds: mirror.nanoseconds };
  }
  const result = {};
  for (const [key, item] of Object.entries(value))
    result[key] = portableEnvelope(item);
  return result;
}
function timestampMirror(value, iso, label) {
  if (typeof iso !== "string")
    throw new Error(`${label} timestamp is missing`);
  let expected;
  try {
    expected = timestampFromIso(iso);
  } catch {
    throw new Error(`${label} timestamp is malformed`);
  }
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error(`${label} timestamp mirror is malformed`);
  const mirror = value;
  if (mirror.type !== "firestore/timestamp/1.0" || !Number.isInteger(mirror.seconds) || !Number.isInteger(mirror.nanoseconds) || Object.keys(mirror).length !== 3 || mirror.seconds !== expected.seconds || mirror.nanoseconds !== expected.nanoseconds)
    throw new Error(`${label} timestamp mirror mismatch`);
}
function fixedTimestampMirrors(value, expectedExpiry, label = "instruction") {
  if (expectedExpiry !== void 0 && value.expires_at !== void 0 && value.expires_at !== expectedExpiry)
    throw new Error(`${label} expiry is not approved`);
  const expiry = expectedExpiry ?? (typeof value.expires_at === "string" ? value.expires_at : void 0);
  if (value.expires_at_ts !== void 0 || expectedExpiry !== void 0)
    timestampMirror(value.expires_at_ts, expiry, `${label} expiry`);
  if (value.approved_at !== void 0 || value.approved_at_ts !== void 0)
    timestampMirror(value.approved_at_ts, value.approved_at, `${label} approval`);
}
function instructionContextValue(instruction, key) {
  const directKey = { projectId: "project_id", workspaceId: "workspace_id", firebaseUid: "firebase_uid", googleSubject: "owner_google_subject", sessionId: "session_id", taskId: "task_id" }[key];
  if (!directKey)
    return void 0;
  const direct = instruction[directKey];
  if (typeof direct === "string")
    return direct;
  const descriptor = instruction.descriptor;
  const descriptorKey = { projectId: "project_id", workspaceId: "workspace_id", firebaseUid: "firebase_uid", googleSubject: "google_subject", sessionId: "session_id", taskId: "task_id" }[key];
  if (!descriptorKey)
    return void 0;
  const value = descriptor?.[descriptorKey] ?? (key === "googleSubject" ? descriptor?.google_sub : void 0);
  return typeof value === "string" ? value : void 0;
}
async function validateInstruction(instruction, expected) {
  if (instruction.version !== 1 || instruction.sdk !== "firebase/firestore/lite" || !instruction.bounds || instruction.bounds.max_documents !== 500 || instruction.bounds.max_bytes !== 1e6)
    throw new Error("instruction contract is invalid");
  if (!/^[a-f0-9]{64}$/.test(instruction.descriptor_hash))
    throw new Error("instruction descriptor hash is invalid");
  if (instruction.namespace !== "control" && instruction.namespace !== "runtime")
    throw new Error("instruction namespace is invalid");
  if (typeof instruction.database !== "string" || !instruction.database)
    throw new Error("instruction database is invalid");
  const expectedDatabaseId = instruction.namespace === "control" ? expected.controlDatabaseId : expected.runtimeDatabaseId;
  if (!expectedDatabaseId || instruction.database !== expectedDatabaseId)
    throw new Error("instruction database is invalid");
  if (instruction.descriptor) {
    const descriptorHash = await digest(instruction.descriptor);
    if (descriptorHash !== instruction.descriptor_hash)
      throw new Error("instruction descriptor hash is invalid");
    for (const key of ["project_id", "workspace_id", "firebase_uid", "session_id"]) {
      const descriptorValue = instruction.descriptor[key];
      const instructionValue = instruction[key];
      if (descriptorValue !== void 0 && instructionValue !== void 0 && descriptorValue !== instructionValue)
        throw new Error("instruction semantic binding is invalid");
    }
    const expiresAt = instruction.descriptor.expires_at;
    if (typeof expiresAt === "string") {
      const expiry = Date.parse(expiresAt);
      const sessionExpiry = expected.sessionExpiresAt ? Date.parse(expected.sessionExpiresAt) : Number.POSITIVE_INFINITY;
      if (!Number.isFinite(expiry) || expiry <= Date.now() || expiry > sessionExpiry)
        throw new Error("instruction grant has expired");
    } else {
      throw new Error("instruction grant expiry is missing");
    }
    if (typeof instruction.descriptor.kind !== "string" || !instruction.descriptor.kind)
      throw new Error("instruction kind is missing");
    const allowed = instruction.method === "writeBatch" && instruction.namespace === "control" ? /* @__PURE__ */ new Set(["task_request", "history_upload"]) : instruction.method === "getDoc" && instruction.namespace === "runtime" ? /* @__PURE__ */ new Set(["bounded_manifest_read", "exact_result_download", "reconciliation_read"]) : instruction.method === "getDoc" && (instruction.namespace === "control" || instruction.namespace === "runtime") ? /* @__PURE__ */ new Set(["reconciliation_read"]) : /* @__PURE__ */ new Set();
    if (!allowed.has(instruction.descriptor.kind))
      throw new Error("instruction kind and method are invalid");
  } else {
    throw new Error("instruction descriptor is missing");
  }
  if (!instruction.payload || typeof instruction.payload !== "object" || Array.isArray(instruction.payload))
    throw new Error("instruction executable payload is invalid");
  {
    const payload = instruction.payload;
    if (payload.method !== instruction.method || payload.database !== instruction.database)
      throw new Error("instruction executable payload is invalid");
    if (instruction.method === "writeBatch" && (!Array.isArray(payload.writes) || !Array.isArray(instruction.writes) || (0, import_canonicalize.default)(payload.writes) !== (0, import_canonicalize.default)(instruction.writes)))
      throw new Error("instruction executable payload is invalid");
    if (instruction.method === "getDoc" && (typeof payload.path !== "string" || payload.path !== instruction.path || (0, import_canonicalize.default)(payload.reads ?? null) !== (0, import_canonicalize.default)(instruction.reads ?? null) || payload.read_scope !== instruction.read_scope))
      throw new Error("instruction executable payload is invalid");
  }
  if (typeof instruction.payload_hash !== "string" || !instruction.payload_hash || await digest(instruction.payload) !== instruction.payload_hash)
    throw new Error("instruction payload hash is invalid");
  const descriptor = instruction.descriptor;
  const validateApprovalModel = async (data, requiredType, expectedChangeHash, requireSession = false) => {
    if (requiredType !== void 0 && data.approval_type !== requiredType)
      throw new Error("instruction approval type is invalid");
    const canonicalPayload = data.canonical_payload;
    if (typeof canonicalPayload !== "string" || typeof data.approval_hash !== "string")
      throw new Error("instruction approval model is invalid");
    let approval;
    try {
      approval = JSON.parse(canonicalPayload);
    } catch {
      throw new Error("instruction approval model is invalid");
    }
    if (!approval || typeof approval !== "object" || Array.isArray(approval) || (0, import_canonicalize.default)(approval) !== canonicalPayload || await sha256Bytes(canonicalPayload) !== data.approval_hash)
      throw new Error("instruction approval hash is invalid");
    const model = approval;
    const requiredKeys = ["schema_version", "approval_id", "task_id", "project_id", "workspace_id", "change_hash", "approver_id", "action_scope", "resource_versions", "policy_version", "trace_id", "approved_at", "expires_at"];
    const reconstructed = Object.fromEntries(requiredKeys.map((key) => [key, data[key]]));
    if (requiredKeys.some((key) => data[key] === void 0) || (0, import_canonicalize.default)(reconstructed) !== canonicalPayload)
      throw new Error("instruction approval model does not match executable data");
    if (expectedChangeHash !== void 0 && model.change_hash !== expectedChangeHash)
      throw new Error("instruction approval digest is invalid");
    const descriptorTaskId = typeof instruction.descriptor.task_id === "string" ? instruction.descriptor.task_id : typeof data.task_id === "string" ? data.task_id : expected.taskId;
    if (model.project_id !== expected.projectId || model.workspace_id !== expected.workspaceId || model.task_id !== descriptorTaskId || model.approver_id !== expected.googleSubject || model.expires_at !== instruction.descriptor.expires_at)
      throw new Error("instruction approval binding is invalid");
    for (const key of ["action_scope", "resource_versions", "policy_version"])
      if (instruction.descriptor[key] !== void 0 && (0, import_canonicalize.default)(model[key]) !== (0, import_canonicalize.default)(instruction.descriptor[key]))
        throw new Error("instruction approval binding is invalid");
    if (data.project_id !== expected.projectId || data.workspace_id !== expected.workspaceId || data.task_id !== descriptorTaskId || requireSession && data.session_id !== expected.sessionId || !requireSession && data.session_id !== void 0 && data.session_id !== expected.sessionId || data.approver_google_sub !== void 0 && data.approver_google_sub !== expected.googleSubject || data.approver_firebase_uid !== void 0 && data.approver_firebase_uid !== expected.firebaseUid)
      throw new Error("instruction approval binding is invalid");
  };
  for (const write of instruction.writes ?? []) {
    const data = write.data;
    fixedTimestampMirrors(data, descriptor.expires_at, "instruction write");
    if (data.approval && typeof data.approval === "object" && !Array.isArray(data.approval))
      fixedTimestampMirrors(data.approval, void 0, "instruction nested approval");
    const canonicalPayload = data.canonical_payload;
    if (typeof canonicalPayload === "string" && typeof data.request_hash === "string") {
      let parsed;
      try {
        parsed = JSON.parse(canonicalPayload);
      } catch {
        throw new Error("instruction canonical model is invalid");
      }
      if ((0, import_canonicalize.default)(parsed) !== canonicalPayload || await sha256Bytes(canonicalPayload) !== data.request_hash)
        throw new Error("instruction canonical model hash is invalid");
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        const requestKeys = ["schema_version", "task_id", "project_id", "workspace_id", "user_id", "content", "intent", "plan", "download_scopes", "apply_scopes", "scope", "resource_versions", "policy_version", "trace_id", "created_at"];
        const reconstructed = Object.fromEntries(requestKeys.filter((key) => data[key] !== void 0).map((key) => [key, data[key]]));
        if ((0, import_canonicalize.default)(reconstructed) !== canonicalPayload)
          throw new Error("instruction canonical model does not match executable data");
      }
    }
    if (typeof data.changeset_canonical === "string" && typeof data.changeset_hash === "string") {
      let changeset;
      try {
        changeset = JSON.parse(data.changeset_canonical);
      } catch {
        throw new Error("instruction canonical model is invalid");
      }
      if ((0, import_canonicalize.default)(changeset) !== data.changeset_canonical || await sha256Bytes(data.changeset_canonical) !== data.changeset_hash)
        throw new Error("instruction canonical model hash is invalid");
      if (data.changeset !== void 0 && (0, import_canonicalize.default)(data.changeset) !== data.changeset_canonical)
        throw new Error("instruction changeset mirror is invalid");
    }
    if (typeof canonicalPayload === "string" && typeof data.payload_hash === "string") {
      let payload;
      try {
        payload = JSON.parse(canonicalPayload);
      } catch {
        throw new Error("instruction canonical model is invalid");
      }
      if ((0, import_canonicalize.default)(payload) !== canonicalPayload || await sha256Bytes(canonicalPayload) !== data.payload_hash)
        throw new Error("instruction canonical model hash is invalid");
    }
    if (typeof data.approval_type === "string")
      await validateApprovalModel(data, data.approval_type, data.approval_type === "exact_apply" ? descriptor?.bound_digest : descriptor?.request_hash, true);
  }
  {
    const fields = [["projectId", "project"], ["workspaceId", "workspace"], ["firebaseUid", "firebase UID"], ["googleSubject", "owner"], ["sessionId", "session"]];
    for (const [key, label] of fields) {
      if (instructionContextValue(instruction, key) !== expected[key])
        throw new Error(`instruction ${label} binding is invalid`);
    }
  }
  if (instruction.method === "writeBatch") {
    const writes = instruction.writes ?? [];
    const paths = writes.map((write) => write.path);
    if (new Set(paths).size !== paths.length)
      throw new Error("instruction writes are not unique");
    const requests = writes.filter((write) => typeof write.data.request_hash === "string");
    const approvals = writes.filter((write) => typeof write.data.approval_type === "string");
    if (descriptor.kind === "task_request") {
      const required = descriptor.approval_type === "exact_apply" ? ["upload_run", "exact_apply"] : ["upload_run"];
      const request = requests[0];
      const requestParts = request ? splitPath(request.path) : [];
      const requestId = typeof descriptor.request_id === "string" ? descriptor.request_id : void 0;
      const requiredIds = request?.data.required_approvals;
      const approvalIds = approvals.map((write) => write.data.approval_id);
      const expectedRequestPath = requestId ? ["projects", expected.projectId, "workspaces", expected.workspaceId, "members", expected.firebaseUid, "requests", requestId].join("/") : "";
      if (writes.length !== 1 + required.length || requests.length !== 1 || !request || request.path !== expectedRequestPath || requestParts.length !== 8 || request.data.request_hash !== descriptor.request_hash || approvals.length !== required.length || !Array.isArray(requiredIds) || requiredIds.length !== required.length || new Set(approvalIds).size !== approvalIds.length || (0, import_canonicalize.default)([...requiredIds].sort()) !== (0, import_canonicalize.default)([...approvalIds].sort()) || required.some((type) => approvals.filter((write) => write.data.approval_type === type).length !== 1))
        throw new Error("instruction approvals are incomplete");
      for (const approvalWrite of approvals) {
        const approvalId = approvalWrite.data.approval_id;
        if (typeof approvalId !== "string" || approvalWrite.path !== `${expectedRequestPath}/approvals/${approvalId}`)
          throw new Error("instruction approval path is invalid");
        const expectedDigestKind = approvalWrite.data.approval_type === "exact_apply" ? descriptor.bound_digest_kind : "task_request";
        if (approvalWrite.data.request_id !== request.data.request_id || approvalWrite.data.firebase_uid !== expected.firebaseUid || approvalWrite.data.google_sub !== expected.googleSubject || approvalWrite.data.destination !== descriptor.destination || approvalWrite.data.bound_digest_kind !== expectedDigestKind)
          throw new Error("instruction approval binding is invalid");
      }
    }
    if (descriptor.kind === "history_upload") {
      const exportWrite = writes[0];
      const exportParts = exportWrite ? splitPath(exportWrite.path) : [];
      const approval = exportWrite?.data.approval;
      if (writes.length !== 1 || exportParts.length !== 8 || exportParts[6] !== "exports" || !approval || typeof approval !== "object")
        throw new Error("instruction history export is incomplete");
      const approvalModel = approval;
      if (approvalModel.approval_id !== descriptor.approval_id || approvalModel.change_hash !== descriptor.payload_hash || approvalModel.project_id !== expected.projectId || approvalModel.workspace_id !== expected.workspaceId || approvalModel.task_id !== expected.taskId || approvalModel.expires_at !== descriptor.expires_at || exportWrite.data.firebase_uid !== expected.firebaseUid || exportWrite.data.session_id !== expected.sessionId || exportWrite.data.owner_google_subject !== expected.googleSubject)
        throw new Error("instruction history approval binding is invalid");
      if (!(0, import_canonicalize.default)(approvalModel.action_scope) || !(0, import_canonicalize.default)(approvalModel.action_scope)?.includes("event_ids") || (0, import_canonicalize.default)(approvalModel.action_scope.event_ids) !== (0, import_canonicalize.default)(descriptor.event_ids))
        throw new Error("instruction history approval scope is invalid");
      await validateApprovalModel({ ...approvalModel, approval_hash: exportWrite.data.approval_hash });
    }
  }
  if (instruction.method === "getDoc" && instruction.path) {
    const expectedScope = { bounded_manifest_read: "manifest", exact_result_download: "exact_result", reconciliation_read: "reconciliation" };
    if (instruction.read_scope !== expectedScope[typeof descriptor.kind === "string" ? descriptor.kind : ""])
      throw new Error("instruction read scope is invalid");
    const readParts = splitPath(instruction.path);
    if (typeof descriptor.path === "string" && descriptor.path !== instruction.path)
      throw new Error("instruction read path is not approved");
    const resultId = typeof descriptor.result_id === "string" ? descriptor.result_id : typeof descriptor.result_hash === "string" ? descriptor.result_hash : void 0;
    if (resultId && readParts.includes("results") && readParts[readParts.length - 1] !== resultId)
      throw new Error("instruction result path is not approved");
    if (descriptor.kind === "reconciliation_read") {
      const approvedPaths = descriptor.paths;
      if (!Array.isArray(approvedPaths) || approvedPaths.length === 0 || typeof descriptor.target_operation_id !== "string" || typeof descriptor.target_descriptor_hash !== "string" || descriptor.database !== instruction.database || (0, import_canonicalize.default)(approvedPaths) !== (0, import_canonicalize.default)(instruction.reads?.map((read) => read.path) ?? [instruction.path]))
        throw new Error("instruction reconciliation paths are not approved");
    }
  }
}
async function executeLiteInstruction(databases, instruction, expected, isCurrent = () => true) {
  await validateInstruction(instruction, expected);
  if (!isCurrent())
    throw new Error("Firebase account changed during workflow operation");
  const db = databases[instruction.namespace];
  if (!db)
    throw new Error("instruction namespace is invalid");
  const expectedDatabaseId = instruction.namespace === "control" ? expected.controlDatabaseId : expected.runtimeDatabaseId;
  if (!expectedDatabaseId || db.databaseId !== expectedDatabaseId || instruction.database !== expectedDatabaseId)
    throw new Error("instruction database is invalid");
  if (instruction.method === "writeBatch") {
    if (!instruction.writes || instruction.writes.length === 0 || instruction.writes.length > instruction.bounds.max_documents)
      throw new Error("instruction batch is outside its bound");
    for (const write of instruction.writes) {
      if (write.mode !== "create")
        throw new Error("only create writes are allowed");
      const parts2 = splitPath(write.path);
      validateBoundPath(parts2, expected, "write", instruction.namespace);
    }
    const bytes = new TextEncoder().encode(JSON.stringify(instruction.writes.map((write) => ({ ...write, data: nativeEnvelope(write.data) })))).byteLength;
    if (bytes > instruction.bounds.max_bytes)
      throw new Error("instruction batch is outside its byte bound");
    if (!isCurrent())
      throw new Error("Firebase account changed during workflow operation");
    const batch = db.writeBatch();
    for (const write of instruction.writes) {
      batch.set(db.doc(...splitPath(write.path)), nativeEnvelope(write.data));
    }
    await batch.commit();
    return void 0;
  }
  if (instruction.method !== "getDoc" || !instruction.path)
    throw new Error("instruction read is invalid");
  const parts = splitPath(instruction.path);
  validateBoundPath(parts, expected, "read", instruction.namespace);
  const reads = instruction.reads ?? [{ method: "getDoc", path: instruction.path, whole_document: true }];
  if (reads.length === 0 || reads.length > instruction.bounds.max_documents || reads[0].path !== instruction.path || reads.some((read) => read.method !== "getDoc" || read.whole_document !== true))
    throw new Error("instruction reads are invalid");
  if (instruction.read_scope !== "reconciliation" && reads.length !== 1)
    throw new Error("instruction reads are invalid");
  const documents = [];
  for (const read of reads) {
    const readParts = splitPath(read.path);
    validateBoundPath(readParts, expected, "read", instruction.namespace);
    if (!isCurrent())
      throw new Error("Firebase account changed during workflow operation");
    const snapshot = await db.getDoc(db.doc(...readParts));
    if (!isCurrent())
      throw new Error("Firebase account changed during workflow operation");
    if (!snapshot.exists())
      throw new Error("remote document is unavailable");
    documents.push({ path: read.path, data: portableEnvelope(snapshot.data()) });
  }
  if (instruction.read_scope === "reconciliation") {
    const exactResult = expected.reconciliationTargetKind === "exact_result_download" || reads.some((read) => read.path.split("/").includes("results"));
    return exactResult ? documents[0].data : { documents };
  }
  return documents[0].data;
}
function timestampFromIso(iso) {
  const match = /^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)$/.exec(iso);
  if (!match)
    throw new Error("timestamp must be an ISO-8601 instant");
  const milliseconds = Date.parse(`${match[1]}${match[3]}`);
  const seconds = Math.floor(milliseconds / 1e3);
  const nanos = Number((match[2] ?? "").padEnd(9, "0"));
  return new Timestamp(seconds, nanos);
}

// src/main.ts
var q2 = (selector) => document.querySelector(selector);
var appElement = q2("#app");
var stateElement = q2("#state");
var loginButton = q2("#login");
var logoutButton = q2("#logout");
var setupOnly = q2("#setup-only");
var setupSubject = q2("#setup-subject");
var setupConfirm = q2("#setup-confirm");
var cloudGrant = q2("#cloud-grant");
var cloudGrantDetails = q2("#cloud-grant-details");
var consentLabel = q2("#cloud-consent-label");
var consentCheckbox = q2("#cloud-consent");
var consentButton = q2("#cloud-consent-submit");
var syncSection = q2("#manual-sync");
var syncPreview = q2("#sync-preview");
var syncUpload = q2("#sync-upload");
var syncConsent = q2("#sync-consent");
var syncDetails = q2("#sync-details");
var taskPreview = q2("#task-preview");
var taskRecord = q2("#task-record");
var taskConsent = q2("#task-consent");
var applyConsent = q2("#apply-consent");
var manifestPreview = q2("#manifest-preview");
var manifestRead = q2("#manifest-read");
var manifestConsent = q2("#manifest-consent");
var resultRead = q2("#result-read");
var resultDownload = q2("#result-download");
var resultConsent = q2("#result-consent");
var downloadDetails = q2("#download-details");
var reconcilePreviewButton = q2("#sync-reconcile");
var reconcileConsent = q2("#reconcile-consent");
var reconcileRead = q2("#reconcile-read");
function capability() {
  const value = new URLSearchParams(window.location.hash.slice(1)).get("capability");
  if (!value)
    throw new Error("trusted browser capability is missing");
  return value;
}
function localSubject() {
  const value = appElement?.dataset.localGoogleSub?.trim();
  if (!value)
    throw new Error("verified local Google subject is missing");
  return value;
}
async function sessionBootstrap() {
  const response = await fetch("/api/session", { headers: { "X-Session-Capability": capability() } });
  if (!response.ok)
    throw new Error("Trusted local approval session is unavailable");
  const value = await response.json();
  if (!value.googleSubject)
    throw new Error("verified local Google subject is missing");
  if (value.firebaseConfig && (!value.firebaseConfig.apiKey || !value.firebaseConfig.authDomain || !value.firebaseConfig.projectId))
    throw new Error("Firebase setup configuration is invalid");
  return value;
}
async function bindFirebaseIdentity(user, isCurrent = () => true) {
  const token = await user.getIdToken();
  if (!isCurrent())
    throw new Error("Firebase account changed during sign-in");
  const response = await fetch("/api/firebase-binding", { method: "POST", headers: { "Content-Type": "application/json", "X-Session-Capability": capability() }, body: JSON.stringify({ firebaseIdToken: token }) });
  if (!response.ok)
    throw new Error("Firebase identity binding was rejected");
  const binding = await response.json();
  if (!isCurrent())
    throw new Error("Firebase account changed during sign-in");
  if (binding.firebaseUid !== user.uid || binding.googleSubject !== localSubject())
    throw new Error("Firebase identity does not match the verified local Google account");
  return binding;
}
function validWorkflowConfig(value) {
  if (!value || typeof value !== "object")
    return false;
  return ["project_id", "workspace_id", "control_database_id", "runtime_database_id", "session_id", "session_expires_at"].every((key) => typeof value[key] === "string" && Boolean(value[key]));
}
function detailsText(value) {
  return JSON.stringify(value, null, 2);
}
async function bindInstructionToPreview(instruction, preview) {
  const descriptor = instruction.descriptor;
  if (!descriptor)
    throw new Error("workflow instruction descriptor is missing");
  const canonicalSame = (left, right) => (0, import_canonicalize2.default)(left) === (0, import_canonicalize2.default)(right);
  const descriptorKind = descriptor.kind;
  const kindsMatch = preview.kind === "reconciliation" ? descriptorKind === "reconciliation_read" : descriptorKind === preview.kind;
  if (typeof descriptorKind !== "string" || typeof preview.kind === "string" && !kindsMatch)
    throw new Error("workflow instruction kind is not the approved preview");
  for (const key of ["project_id", "workspace_id", "firebase_uid", "session_id", "task_id", "owner_google_subject", "google_subject", "approval_type", "bound_digest_kind", "database", "destination", "policy_version", "resource_versions", "scope", "apply_scopes", "download_scopes", "fields", "result_id", "result_hash"])
    if (preview[key] !== void 0 && descriptor[key] !== void 0 && !canonicalSame(preview[key], descriptor[key]))
      throw new Error("workflow instruction does not match its preview");
  if (preview.payload_hash !== void 0 && descriptor.payload_hash !== preview.payload_hash)
    throw new Error("history payload is not the approved preview");
  if (preview.request_hash !== void 0 && descriptor.request_hash !== preview.request_hash)
    throw new Error("task request is not the approved preview");
  if (preview.bound_digest !== void 0 && descriptor.bound_digest !== preview.bound_digest)
    throw new Error("task change set is not the approved preview");
  if (preview.result_id !== void 0 && descriptor.result_id !== preview.result_id)
    throw new Error("result ID is not the approved preview");
  if (preview.result_hash !== void 0 && descriptor.result_hash !== preview.result_hash)
    throw new Error("result hash is not the approved preview");
  if (preview.scope !== void 0 && descriptor.scope !== void 0 && !canonicalSame(preview.scope, descriptor.scope))
    throw new Error("result scope is not the approved preview");
  if (preview.fields !== void 0 && descriptor.fields !== void 0 && !canonicalSame(preview.fields, descriptor.fields))
    throw new Error("manifest fields are not the approved preview");
  for (const key of ["target_operation_id", "target_descriptor_hash", "database"])
    if (preview[key] !== void 0 && descriptor[key] !== void 0 && preview[key] !== descriptor[key])
      throw new Error("reconciliation target is not the approved preview");
  if (preview.paths !== void 0 && (!Array.isArray(descriptor.paths) || !canonicalSame(preview.paths, descriptor.paths)))
    throw new Error("reconciliation paths are not the approved preview");
  if (descriptor.kind === "reconciliation_read" && (!Array.isArray(descriptor.paths) || !canonicalSame(descriptor.paths, instruction.reads?.map((read) => read.path) ?? [instruction.path])))
    throw new Error("reconciliation reads are not the approved preview");
  if (preview.expires_at !== void 0 && descriptor.expires_at !== void 0 && preview.expires_at !== descriptor.expires_at)
    throw new Error("workflow expiry is not the approved preview");
  const writes = instruction.writes ?? [];
  if (Array.isArray(preview.records)) {
    const exportData = writes.map((write) => write.data).find((data) => data.kind === "history_upload");
    if (!exportData || !canonicalSame(preview.records, exportData.events) || typeof preview.payload_hash === "string" && exportData.payload_hash !== preview.payload_hash)
      throw new Error("history records are not the approved preview");
  }
  if (preview.request && typeof preview.request === "object") {
    const requestData = writes.map((write) => write.data).find((data) => data.request_hash !== void 0);
    if (!requestData)
      throw new Error("task request is missing from the instruction");
    const approved = { ...preview.request };
    delete approved.state;
    if (typeof requestData.canonical_payload !== "string" || !canonicalSame(approved, JSON.parse(requestData.canonical_payload)))
      throw new Error("task request is not the approved preview");
    if (typeof preview.request_hash === "string" && requestData.request_hash !== preview.request_hash)
      throw new Error("task request hash is not the approved preview");
  }
  if (preview.changeset && typeof preview.changeset === "object") {
    const changesetData = writes.map((write) => write.data).find((data) => typeof data.changeset_canonical === "string");
    if (!changesetData || !canonicalSame(preview.changeset, JSON.parse(changesetData.changeset_canonical)) || typeof preview.bound_digest === "string" && changesetData.changeset_hash !== preview.bound_digest)
      throw new Error("task changeset is not the approved preview");
  }
}
async function start() {
  if (!loginButton || !logoutButton || !stateElement || !setupOnly || !setupSubject || !setupConfirm || !cloudGrant || !cloudGrantDetails || !consentLabel || !consentCheckbox || !consentButton)
    return;
  const bootstrap = await sessionBootstrap();
  if (appElement)
    appElement.dataset.localGoogleSub = bootstrap.googleSubject;
  if (bootstrap.setupOnly || !bootstrap.firebaseConfig) {
    loginButton.hidden = true;
    setupOnly.hidden = false;
    setupSubject.textContent = `Verified Google subject: ${bootstrap.googleSubject}`;
    setupConfirm.addEventListener("click", async () => {
      setupConfirm.disabled = true;
      try {
        const response = await fetch("/api/setup-confirmation", { method: "POST", headers: { "Content-Type": "application/json", Origin: window.location.origin, "X-Session-Capability": capability() }, body: JSON.stringify({ googleSubject: bootstrap.googleSubject }) });
        if (!response.ok)
          throw new Error("Local setup confirmation was rejected");
        stateElement.textContent = "Local setup confirmation recorded; Firebase and task actions remain disabled.";
      } catch (error) {
        stateElement.textContent = error instanceof Error ? error.message : "Setup confirmation failed";
      } finally {
        setupConfirm.disabled = false;
      }
    });
    return;
  }
  const firebaseConfig = bootstrap.firebaseConfig;
  if (!firebaseConfig)
    return;
  const app = initializeApp(firebaseConfig);
  const auth = getAuth(app);
  await setPersistence(auth, inMemoryPersistence);
  const provider = new GoogleAuthProvider();
  let generation = 0;
  let activeUser;
  let identity;
  let controlDb;
  let runtimeDb;
  let uploadPreview;
  let taskPreviewResponse;
  let manifestPreviewResponse;
  let stagedManifest;
  let resultPreviewResponse;
  let previewRevision = 0;
  let workflowBusy = false;
  let reconciliationPreviewResponse;
  const unresolvedOperations = /* @__PURE__ */ new Map();
  const consumedPreviews = /* @__PURE__ */ new Map();
  const MAX_UNRESOLVED_OPERATIONS = 8;
  let unknownOperation;
  const workflow = validWorkflowConfig(bootstrap.workflowConfig) ? bootstrap.workflowConfig : void 0;
  const clearWorkflow = () => {
    workflowBusy = false;
    previewRevision += 1;
    uploadPreview = void 0;
    taskPreviewResponse = void 0;
    manifestPreviewResponse = void 0;
    stagedManifest = void 0;
    resultPreviewResponse = void 0;
    reconciliationPreviewResponse = void 0;
    unknownOperation = void 0;
    for (const box of [syncConsent, taskConsent, applyConsent, manifestConsent, resultConsent, reconcileConsent])
      if (box)
        box.checked = false;
    for (const button of [syncUpload, taskRecord, manifestRead, resultRead, resultDownload, reconcileRead])
      if (button)
        button.disabled = true;
    for (const button of [syncPreview, taskPreview, manifestPreview])
      if (button)
        button.disabled = false;
    if (reconcilePreviewButton)
      reconcilePreviewButton.hidden = true;
    if (syncSection)
      syncSection.hidden = true;
    if (syncDetails)
      syncDetails.textContent = "";
    if (downloadDetails)
      downloadDetails.textContent = "A bounded metadata read is required before any result is displayed.";
  };
  const invalidate = (message) => {
    generation += 1;
    activeUser = void 0;
    identity = void 0;
    controlDb = void 0;
    runtimeDb = void 0;
    clearWorkflow();
    cloudGrant.hidden = true;
    cloudGrantDetails.textContent = "";
    consentCheckbox.checked = false;
    consentLabel.hidden = true;
    consentButton.hidden = true;
    consentButton.disabled = false;
    logoutButton.hidden = true;
    loginButton.hidden = false;
    loginButton.disabled = false;
    if (message)
      stateElement.textContent = message;
  };
  const current = (g2, owner) => g2 === generation && activeUser === owner && auth.currentUser === owner;
  const currentAttempt = (g2, owner, revision) => current(g2, owner) && revision === previewRevision;
  const beginWorkflow = (button) => {
    if (workflowBusy) {
      stateElement.textContent = "Another workflow operation is in progress; wait for it to finish.";
      return false;
    }
    workflowBusy = true;
    button.disabled = true;
    return true;
  };
  const endWorkflow = (g2, owner, button) => {
    if (current(g2, owner)) {
      workflowBusy = false;
      button.disabled = false;
    }
  };
  const fenceConsent = (box, button) => {
    box?.addEventListener("change", () => {
      if (!box.checked) {
        previewRevision += 1;
        if (button)
          button.disabled = true;
      }
    });
  };
  fenceConsent(syncConsent, syncUpload);
  fenceConsent(taskConsent, taskRecord);
  fenceConsent(applyConsent, taskRecord);
  fenceConsent(manifestConsent, manifestRead);
  fenceConsent(resultConsent, resultDownload);
  fenceConsent(reconcileConsent, reconcileRead);
  const expected = () => {
    if (!identity)
      throw new Error("Firebase identity is not bound");
    return identity;
  };
  const bridgePost = async (path, body, owner, g2, isValid = () => current(g2, owner), hooks = {}) => {
    const token = await owner.getIdToken();
    if (!isValid())
      throw new Error("Firebase account changed during workflow operation");
    hooks.onDispatch?.();
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", Origin: window.location.origin, "X-Session-Capability": capability() }, body: JSON.stringify({ ...body, firebaseIdToken: token }) });
    if (!response.ok)
      throw new Error(`Workflow bridge rejected ${path}`);
    const value = await response.json();
    await hooks.onResponse?.(value);
    if (!isValid())
      throw new Error("Firebase account changed during workflow operation");
    return value;
  };
  const sdkClient = (database, databaseId) => ({ databaseId, writeBatch: () => {
    const batch = writeBatch(database);
    return { set: (ref, value) => batch.set(ref, value), commit: () => batch.commit() };
  }, doc: (...parts) => doc(database, parts[0] || "invalid", ...parts.slice(1)), getDoc: async (ref) => {
    const snapshot = await getDoc(ref);
    return { exists: () => snapshot.exists(), data: () => snapshot.data() ?? {} };
  } });
  const renderSync = (title, value) => {
    if (syncDetails)
      syncDetails.textContent = `${title}
${detailsText(value)}`;
  };
  const renderDownload = (title, value) => {
    if (downloadDetails)
      downloadDetails.textContent = `${title}
${detailsText(value)}`;
  };
  const forgetOperation = (operationId) => {
    unresolvedOperations.delete(operationId);
    for (const [previewId, challenge] of consumedPreviews)
      if (challenge.operationId === operationId)
        consumedPreviews.delete(previewId);
  };
  const captureReleased = (response, ownerContext, kind) => {
    if (!ownerContext || typeof response.operation_id !== "string" || typeof response.descriptor_hash !== "string")
      return false;
    if (!unresolvedOperations.has(response.operation_id) && unresolvedOperations.size >= MAX_UNRESOLVED_OPERATIONS)
      return false;
    unresolvedOperations.set(response.operation_id, { ownerGoogleSubject: ownerContext.googleSubject, firebaseUid: ownerContext.firebaseUid, sessionId: ownerContext.sessionId, operationId: response.operation_id, descriptorHash: response.descriptor_hash, kind, state: "released" });
    return true;
  };
  const consentHooks = (preview, ownerContext, kind, owner, g2, isValid) => ({
    onDispatch: () => {
      if (!ownerContext || typeof preview.operation_id !== "string" || typeof preview.descriptor_hash !== "string")
        throw new Error("Approved consent identity is unavailable.");
      if (consumedPreviews.has(preview.operation_id))
        throw new Error("This approved consent has already been issued; wait for its outcome or trusted recovery.");
      const retained = kind !== "reconciliation_read";
      if (retained && (unresolvedOperations.size >= MAX_UNRESOLVED_OPERATIONS || consumedPreviews.size >= MAX_UNRESOLVED_OPERATIONS))
        throw new Error("Unresolved operation capacity is full; no new consent was issued.");
      if (retained) {
        consumedPreviews.set(preview.operation_id, { ownerGoogleSubject: ownerContext.googleSubject, firebaseUid: ownerContext.firebaseUid, projectId: ownerContext.projectId, workspaceId: ownerContext.workspaceId, sessionId: ownerContext.sessionId, previewId: preview.operation_id, operationId: preview.operation_id, kind, state: "issued" });
        unresolvedOperations.set(preview.operation_id, { ownerGoogleSubject: ownerContext.googleSubject, firebaseUid: ownerContext.firebaseUid, sessionId: ownerContext.sessionId, operationId: preview.operation_id, descriptorHash: preview.descriptor_hash, kind, state: "issued" });
      }
    },
    onResponse: async (response) => {
      if (kind !== "reconciliation_read" && typeof preview.operation_id === "string" && typeof response.operation_id === "string" && typeof response.descriptor_hash === "string") {
        unresolvedOperations.delete(preview.operation_id);
        const challenge = consumedPreviews.get(preview.operation_id);
        if (challenge)
          Object.assign(challenge, { operationId: response.operation_id, state: "released" });
        if (!captureReleased(response, ownerContext, kind) && ownerContext)
          unresolvedOperations.set(preview.operation_id, { ownerGoogleSubject: ownerContext.googleSubject, firebaseUid: ownerContext.firebaseUid, sessionId: ownerContext.sessionId, operationId: preview.operation_id, descriptorHash: String(preview.descriptor_hash), kind, state: "issued" });
        if (ownerContext && !isValid() && current(g2, owner))
          await markUnknown(response, owner, g2, kind, true, ownerContext);
      }
    }
  });
  const eligibleUnknown = (ownerContext = identity) => ownerContext && [...unresolvedOperations.values()].find((operation) => operation.state === "confirmed" && operation.ownerGoogleSubject === ownerContext.googleSubject && operation.firebaseUid === ownerContext.firebaseUid && operation.sessionId === ownerContext.sessionId && operation.kind !== "bounded_manifest_read" && operation.kind !== "reconciliation_read");
  const showNextUnknown = (ownerContext = identity) => {
    const next = eligibleUnknown(ownerContext);
    unknownOperation = next ? { operationId: next.operationId, descriptorHash: next.descriptorHash, kind: next.kind } : void 0;
    if (reconcilePreviewButton)
      reconcilePreviewButton.hidden = !next;
  };
  const issuanceNotice = (ownerContext = identity) => ownerContext && [...consumedPreviews.values()].find((challenge) => challenge.state === "issued" && challenge.ownerGoogleSubject === ownerContext.googleSubject && challenge.firebaseUid === ownerContext.firebaseUid && challenge.projectId === ownerContext.projectId && challenge.workspaceId === ownerContext.workspaceId && challenge.sessionId === ownerContext.sessionId);
  const refuseConsumedPreview = (preview, details) => {
    if (preview && typeof preview.operation_id === "string" && consumedPreviews.has(preview.operation_id)) {
      if (details)
        details.textContent = "This approved consent has already been issued; wait for its outcome or trusted recovery.";
      return true;
    }
    return false;
  };
  const showLostConsent = (preview, ownerContext, details) => {
    if (!preview || !ownerContext || typeof preview.operation_id !== "string")
      return;
    const challenge = consumedPreviews.get(preview.operation_id);
    if (challenge?.state === "issued" && challenge.ownerGoogleSubject === ownerContext.googleSubject && challenge.firebaseUid === ownerContext.firebaseUid && challenge.projectId === ownerContext.projectId && challenge.workspaceId === ownerContext.workspaceId && challenge.sessionId === ownerContext.sessionId && details)
      details.textContent = "Consent response unavailable; this approved operation is retained as pending and cannot be reissued until trusted recovery.";
  };
  const recoveryDetails = (kind) => kind === "exact_result_download" || kind === "bounded_manifest_read" ? downloadDetails : syncDetails;
  const markUnknown = async (response, owner, g2, kind = "writeBatch", notify = true, ownerContext = identity) => {
    if (typeof response.operation_id !== "string" || typeof response.descriptor_hash !== "string" || !ownerContext)
      return;
    const handle = { ownerGoogleSubject: ownerContext.googleSubject, firebaseUid: ownerContext.firebaseUid, sessionId: ownerContext.sessionId, operationId: response.operation_id, descriptorHash: response.descriptor_hash, kind, state: "released" };
    unresolvedOperations.set(handle.operationId, handle);
    if (current(g2, owner)) {
      let callbackConfirmed = !notify;
      if (notify) {
        try {
          const acknowledgement = await bridgePost("/api/workflow/ack", { operationId: handle.operationId, descriptorHash: handle.descriptorHash, status: "unknown", sessionId: handle.sessionId }, owner, g2);
          if (acknowledgement.status === "acknowledged")
            forgetOperation(handle.operationId);
          else if (acknowledgement.status === "unknown") {
            const confirmed = unresolvedOperations.get(handle.operationId);
            if (confirmed)
              confirmed.state = "confirmed";
            for (const challenge of consumedPreviews.values())
              if (challenge.operationId === handle.operationId)
                challenge.state = "confirmed";
          }
          callbackConfirmed = acknowledgement.status === "acknowledged" || acknowledgement.status === "unknown";
        } catch {
        }
      }
      if (callbackConfirmed && unresolvedOperations.has(handle.operationId))
        showNextUnknown(ownerContext);
      else if (!callbackConfirmed && current(g2, owner)) {
        const details = recoveryDetails(kind);
        if (details)
          details.textContent = "Recovery remains pending because the host confirmation was unavailable; return to this account to retry the original recovery.";
      }
    }
  };
  loginButton.addEventListener("click", async () => {
    loginButton.disabled = true;
    const loginGeneration = generation;
    let loginOwner;
    try {
      const result = await signInWithPopup(auth, provider);
      if (generation !== loginGeneration)
        throw new Error("Firebase account changed during sign-in");
      const owner = result.user;
      loginOwner = owner;
      generation += 1;
      activeUser = owner;
      const boundGeneration = generation;
      clearWorkflow();
      const binding = await bindFirebaseIdentity(owner, () => generation === boundGeneration && activeUser === owner && auth.currentUser === owner);
      if (!current(boundGeneration, owner))
        throw new Error("Firebase account changed during sign-in");
      stateElement.textContent = `Signed in as ${binding.googleSubject};
Firebase UID is bound for this session.`;
      loginButton.hidden = true;
      logoutButton.hidden = false;
      consentLabel.hidden = false;
      consentButton.disabled = false;
      if (workflow) {
        const selectedTaskId = typeof bootstrap.pendingTask?.payload.task_id === "string" ? bootstrap.pendingTask.payload.task_id : typeof bootstrap.pendingHistory?.[0]?.task_id === "string" ? bootstrap.pendingHistory[0].task_id : "";
        identity = { googleSubject: binding.googleSubject, firebaseUid: binding.firebaseUid, projectId: workflow.project_id, workspaceId: workflow.workspace_id, taskId: selectedTaskId, sessionId: workflow.session_id, controlDatabaseId: workflow.control_database_id, runtimeDatabaseId: workflow.runtime_database_id, sessionExpiresAt: workflow.session_expires_at };
        if (bootstrap.workflowRecovery === true) {
          try {
            const recovery = await bridgePost("/api/workflow/recovery", { sessionId: workflow.session_id }, owner, boundGeneration);
            const operations = Array.isArray(recovery.operations) ? recovery.operations : [];
            for (const value of operations) {
              if (!value || typeof value !== "object")
                continue;
              const operation = value;
              if (operation.state !== "unknown" || typeof operation.operation_id !== "string" || typeof operation.descriptor_hash !== "string" || typeof operation.kind !== "string")
                continue;
              unresolvedOperations.set(operation.operation_id, { ownerGoogleSubject: binding.googleSubject, firebaseUid: binding.firebaseUid, sessionId: workflow.session_id, operationId: operation.operation_id, descriptorHash: operation.descriptor_hash, kind: operation.kind, state: "confirmed" });
            }
          } catch {
          }
        }
        const returnedUnknown = [...unresolvedOperations.values()].find((operation) => operation.state === "released" && operation.ownerGoogleSubject === binding.googleSubject && operation.firebaseUid === binding.firebaseUid && operation.sessionId === workflow.session_id && operation.kind !== "bounded_manifest_read" && operation.kind !== "reconciliation_read");
        if (returnedUnknown) {
          await markUnknown({ operation_id: returnedUnknown.operationId, descriptor_hash: returnedUnknown.descriptorHash }, owner, boundGeneration, returnedUnknown.kind, true, identity);
          if (!current(boundGeneration, owner))
            throw new Error("Firebase account changed during sign-in");
        } else {
          showNextUnknown(identity);
        }
        const pendingIssuance = issuanceNotice(identity);
        if (pendingIssuance && syncDetails)
          syncDetails.textContent = "A consent response is unavailable; this approved operation remains pending and cannot be reissued until trusted recovery.";
        controlDb = sdkClient(getFirestore(app, workflow.control_database_id), workflow.control_database_id);
        runtimeDb = sdkClient(getFirestore(app, workflow.runtime_database_id), workflow.runtime_database_id);
        if (syncSection)
          syncSection.hidden = false;
        if (!selectedTaskId) {
          if (taskPreview)
            taskPreview.disabled = true;
          if (manifestPreview)
            manifestPreview.disabled = true;
          if (downloadDetails)
            downloadDetails.textContent = "No trusted task is selected; task and result controls remain disabled.";
        }
        if (syncPreview && syncUpload && syncConsent)
          syncPreview.onclick = async () => {
            if (syncPreview.disabled)
              return;
            if (!beginWorkflow(syncPreview))
              return;
            uploadPreview = void 0;
            syncConsent.checked = false;
            syncUpload.disabled = true;
            const g2 = generation;
            const revision = ++previewRevision;
            try {
              const records = bootstrap.pendingHistory ?? [];
              const preview = await bridgePost("/api/workflow/preview", { kind: "history_upload", projectId: workflow.project_id, workspaceId: workflow.workspace_id, records, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              uploadPreview = preview;
              syncConsent.checked = false;
              syncUpload.disabled = records.length === 0;
              renderSync("History preview (no SDK calls):", preview);
            } catch (error) {
              if (current(g2, owner) && syncDetails)
                syncDetails.textContent = error instanceof Error ? error.message : "History preview failed";
            } finally {
              endWorkflow(g2, owner, syncPreview);
            }
          };
        if (syncUpload && syncConsent)
          syncUpload.onclick = async () => {
            const g2 = generation;
            const revision = previewRevision;
            const preview = uploadPreview;
            const ownerContext = identity && { ...identity };
            if (!preview || !syncConsent.checked) {
              if (syncDetails)
                syncDetails.textContent = "Explicit history upload consent is required.";
              return;
            }
            if (refuseConsumedPreview(preview, syncDetails))
              return;
            if (!beginWorkflow(syncUpload))
              return;
            let consent;
            try {
              consent = await bridgePost("/api/workflow/consent", { operationId: preview.operation_id, descriptorHash: preview.descriptor_hash, consent: true, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision), consentHooks(preview, ownerContext, "writeBatch", owner, g2, () => currentAttempt(g2, owner, revision)));
              if (!currentAttempt(g2, owner, revision))
                return;
              const instruction = consent.instruction;
              if (!instruction)
                throw new Error(`History upload status: ${String(consent.status || "unknown")}`);
              await bindInstructionToPreview(instruction, preview);
              await executeLiteInstruction({ control: controlDb, runtime: runtimeDb }, instruction, expected(), () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              const ack = await bridgePost("/api/workflow/ack", { operationId: consent.operation_id, descriptorHash: consent.descriptor_hash, ackId: String(preview.operation_id), sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision));
              if (currentAttempt(g2, owner, revision) && syncDetails) {
                if (ack.status === "acknowledged") {
                  forgetOperation(String(consent.operation_id));
                  syncDetails.textContent = "History upload recorded.";
                } else {
                  syncDetails.textContent = "History upload outcome is unknown; reconcile explicitly before retrying.";
                  await markUnknown(consent, owner, g2, "writeBatch", true, ownerContext);
                }
              }
            } catch (error) {
              if (consent)
                await markUnknown(consent, owner, g2, "writeBatch", true, ownerContext);
              if (current(g2, owner)) {
                showLostConsent(preview, ownerContext, syncDetails);
                if (syncDetails && !syncDetails.textContent.includes("retained as pending"))
                  syncDetails.textContent = error instanceof Error ? error.message : "History upload was refused";
              }
            } finally {
              endWorkflow(g2, owner, syncUpload);
            }
          };
        if (taskPreview && taskRecord && taskConsent && bootstrap.pendingTask)
          taskPreview.onclick = async () => {
            if (taskPreview.disabled)
              return;
            if (!beginWorkflow(taskPreview))
              return;
            taskPreviewResponse = void 0;
            taskConsent.checked = false;
            applyConsent && (applyConsent.checked = false);
            taskRecord.disabled = true;
            const g2 = generation;
            const revision = ++previewRevision;
            try {
              const preview = await bridgePost("/api/workflow/preview", { kind: "task_request", projectId: workflow.project_id, workspaceId: workflow.workspace_id, request: bootstrap.pendingTask.payload, changeset: bootstrap.pendingTask.changeset, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              taskPreviewResponse = preview;
              taskConsent.checked = false;
              if (applyConsent)
                applyConsent.checked = false;
              taskRecord.disabled = false;
              renderSync("Task/change preview (no SDK calls):", preview);
            } catch (error) {
              if (current(g2, owner) && syncDetails)
                syncDetails.textContent = error instanceof Error ? error.message : "Task preview failed";
            } finally {
              endWorkflow(g2, owner, taskPreview);
            }
          };
        if (taskRecord && taskConsent)
          taskRecord.onclick = async () => {
            const g2 = generation;
            const revision = previewRevision;
            const preview = taskPreviewResponse;
            const ownerContext = identity && { ...identity };
            const needsApply = Boolean(bootstrap.pendingTask?.changeset);
            if (!preview || !taskConsent.checked || needsApply && !applyConsent?.checked) {
              if (syncDetails)
                syncDetails.textContent = needsApply ? "Both upload/run and exact apply approvals are required." : "Exact task approval is required.";
              return;
            }
            if (refuseConsumedPreview(preview, syncDetails))
              return;
            if (!beginWorkflow(taskRecord))
              return;
            let consent;
            try {
              consent = await bridgePost("/api/workflow/consent", { operationId: preview.operation_id, descriptorHash: preview.descriptor_hash, consent: true, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision), consentHooks(preview, ownerContext, "writeBatch", owner, g2, () => currentAttempt(g2, owner, revision)));
              if (!currentAttempt(g2, owner, revision))
                return;
              const instruction = consent.instruction;
              if (!instruction)
                throw new Error(`Task status: ${String(consent.status || "unknown")}`);
              await bindInstructionToPreview(instruction, preview);
              await executeLiteInstruction({ control: controlDb, runtime: runtimeDb }, instruction, expected(), () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              const ack = await bridgePost("/api/workflow/ack", { operationId: consent.operation_id, descriptorHash: consent.descriptor_hash, ackId: String(preview.operation_id), sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision));
              if (currentAttempt(g2, owner, revision) && syncDetails) {
                if (ack.status === "acknowledged") {
                  forgetOperation(String(consent.operation_id));
                  syncDetails.textContent = "Task request and approvals recorded atomically.";
                } else {
                  syncDetails.textContent = "Task outcome is unknown; reconcile explicitly.";
                  await markUnknown(consent, owner, g2, "writeBatch", true, ownerContext);
                }
              }
            } catch (error) {
              if (consent)
                await markUnknown(consent, owner, g2, "writeBatch", true, ownerContext);
              if (current(g2, owner)) {
                showLostConsent(preview, ownerContext, syncDetails);
                if (syncDetails && !syncDetails.textContent.includes("retained as pending"))
                  syncDetails.textContent = error instanceof Error ? error.message : "Task record was refused";
              }
            } finally {
              endWorkflow(g2, owner, taskRecord);
            }
          };
        if (manifestPreview && manifestRead && manifestConsent)
          manifestPreview.onclick = async () => {
            if (manifestPreview.disabled)
              return;
            if (!beginWorkflow(manifestPreview))
              return;
            manifestPreviewResponse = void 0;
            manifestConsent.checked = false;
            manifestRead.disabled = true;
            stagedManifest = void 0;
            resultPreviewResponse = void 0;
            if (resultConsent)
              resultConsent.checked = false;
            resultRead.disabled = true;
            resultDownload.disabled = true;
            const g2 = generation;
            const revision = ++previewRevision;
            try {
              const preview = await bridgePost("/api/workflow/preview", { kind: "bounded_manifest_read", projectId: workflow.project_id, workspaceId: workflow.workspace_id, taskId: identity.taskId, fields: ["schema_version", "kind", "result_id", "result_hash", "scope", "project_id", "workspace_id", "firebase_uid", "google_subject", "task_id", "available", "expires_at", "expires_at_ts"], sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              manifestPreviewResponse = preview;
              stagedManifest = void 0;
              resultPreviewResponse = void 0;
              manifestConsent.checked = false;
              if (resultConsent)
                resultConsent.checked = false;
              if (resultRead)
                resultRead.disabled = true;
              if (resultDownload)
                resultDownload.disabled = true;
              manifestRead.disabled = false;
              renderDownload("Manifest preview (no read):", preview);
            } catch (error) {
              if (current(g2, owner) && downloadDetails)
                downloadDetails.textContent = error instanceof Error ? error.message : "Manifest preview failed";
            } finally {
              endWorkflow(g2, owner, manifestPreview);
            }
          };
        if (manifestRead && manifestConsent)
          manifestRead.onclick = async () => {
            const g2 = generation;
            const revision = previewRevision;
            const ownerContext = identity && { ...identity };
            if (!manifestPreviewResponse || !manifestConsent.checked) {
              if (downloadDetails)
                downloadDetails.textContent = "Explicit manifest consent is required.";
              return;
            }
            if (refuseConsumedPreview(manifestPreviewResponse, downloadDetails))
              return;
            if (!beginWorkflow(manifestRead))
              return;
            try {
              const consent = await bridgePost("/api/workflow/consent", { operationId: manifestPreviewResponse.operation_id, descriptorHash: manifestPreviewResponse.descriptor_hash, consent: true, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision), consentHooks(manifestPreviewResponse, ownerContext, "bounded_manifest_read", owner, g2, () => currentAttempt(g2, owner, revision)));
              if (!currentAttempt(g2, owner, revision))
                return;
              const instruction = consent.instruction;
              if (!instruction)
                throw new Error("Manifest instruction is unavailable");
              await bindInstructionToPreview(instruction, manifestPreviewResponse);
              const manifest = await executeLiteInstruction({ control: controlDb, runtime: runtimeDb }, instruction, expected(), () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              const manifestAck = await bridgePost("/api/workflow/ack", { operationId: consent.operation_id, descriptorHash: consent.descriptor_hash, manifest, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              if (manifestAck.status !== "acknowledged")
                throw new Error("Manifest acknowledgement was not accepted");
              forgetOperation(String(consent.operation_id));
              stagedManifest = manifest;
              resultRead.disabled = false;
              renderDownload("Staged manifest (exact result requires a separate preview and consent):", manifest);
            } catch (error) {
              if (current(g2, owner)) {
                showLostConsent(manifestPreviewResponse, ownerContext, downloadDetails);
                manifestPreviewResponse = void 0;
                manifestConsent.checked = false;
                manifestRead.disabled = true;
                if (manifestPreview)
                  manifestPreview.disabled = false;
                if (downloadDetails && !downloadDetails.textContent.includes("retained as pending"))
                  downloadDetails.textContent = error instanceof Error ? error.message : "Manifest read failed";
              }
            } finally {
              endWorkflow(g2, owner, manifestRead);
            }
          };
        if (resultRead && resultConsent)
          resultRead.onclick = async () => {
            if (resultRead.disabled)
              return;
            if (!beginWorkflow(resultRead))
              return;
            resultPreviewResponse = void 0;
            resultConsent.checked = false;
            resultDownload.disabled = true;
            const g2 = generation;
            const revision = ++previewRevision;
            if (!stagedManifest || !manifestPreviewResponse) {
              if (downloadDetails)
                downloadDetails.textContent = "A staged manifest is required.";
              resultRead.disabled = false;
              return;
            }
            try {
              const preview = await bridgePost("/api/workflow/preview", { kind: "exact_result_download", projectId: workflow.project_id, workspaceId: workflow.workspace_id, taskId: identity.taskId, scope: stagedManifest.scope, metadataDescriptorHash: manifestPreviewResponse.descriptor_hash, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              resultPreviewResponse = preview;
              resultConsent.checked = false;
              resultDownload.disabled = false;
              renderDownload("Exact result preview (no read):", preview);
            } catch (error) {
              if (current(g2, owner) && downloadDetails)
                downloadDetails.textContent = error instanceof Error ? error.message : "Result preview failed";
            } finally {
              endWorkflow(g2, owner, resultRead);
            }
          };
        if (resultDownload && resultConsent)
          resultDownload.onclick = async () => {
            const g2 = generation;
            const revision = previewRevision;
            const ownerContext = identity && { ...identity };
            if (!resultPreviewResponse || !resultConsent.checked) {
              if (downloadDetails)
                downloadDetails.textContent = "Separate exact result consent is required.";
              return;
            }
            if (refuseConsumedPreview(resultPreviewResponse, downloadDetails))
              return;
            if (!beginWorkflow(resultDownload))
              return;
            let consent;
            try {
              consent = await bridgePost("/api/workflow/consent", { operationId: resultPreviewResponse.operation_id, descriptorHash: resultPreviewResponse.descriptor_hash, consent: true, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision), consentHooks(resultPreviewResponse, ownerContext, "exact_result_download", owner, g2, () => currentAttempt(g2, owner, revision)));
              if (!currentAttempt(g2, owner, revision))
                return;
              const instruction = consent.instruction;
              if (!instruction)
                throw new Error("Result instruction is unavailable");
              await bindInstructionToPreview(instruction, resultPreviewResponse);
              const result2 = await executeLiteInstruction({ control: controlDb, runtime: runtimeDb }, instruction, expected(), () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              const ack = await bridgePost("/api/workflow/ack", { operationId: consent.operation_id, descriptorHash: consent.descriptor_hash, result: result2, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              if (ack.status === "acknowledged") {
                forgetOperation(String(consent.operation_id));
                renderDownload("Exact result downloaded and imported:", result2);
              } else {
                if (downloadDetails)
                  downloadDetails.textContent = "Result outcome is unknown; reconcile explicitly.";
                await markUnknown(consent, owner, g2, "exact_result_download", true, ownerContext);
              }
            } catch (error) {
              if (consent && !(error instanceof Error && error.message.includes("account changed")))
                await markUnknown(consent, owner, g2, "exact_result_download", true, ownerContext);
              if (current(g2, owner)) {
                showLostConsent(resultPreviewResponse, ownerContext, downloadDetails);
                if (downloadDetails && !downloadDetails.textContent.includes("retained as pending"))
                  downloadDetails.textContent = error instanceof Error ? error.message : "Result download failed";
              }
            } finally {
              endWorkflow(g2, owner, resultDownload);
            }
          };
        if (reconcilePreviewButton && reconcileRead && reconcileConsent)
          reconcilePreviewButton.onclick = async () => {
            if (reconcilePreviewButton.disabled)
              return;
            if (!beginWorkflow(reconcilePreviewButton))
              return;
            reconciliationPreviewResponse = void 0;
            reconcileConsent.checked = false;
            reconcileRead.disabled = true;
            const g2 = generation;
            const revision = ++previewRevision;
            if (!unknownOperation) {
              if (syncDetails)
                syncDetails.textContent = "No unresolved operation is available for reconciliation.";
              reconcilePreviewButton.disabled = false;
              return;
            }
            try {
              const preview = await bridgePost("/api/workflow/preview", { kind: "reconciliation", projectId: workflow.project_id, workspaceId: workflow.workspace_id, operationId: unknownOperation.operationId, descriptorHash: unknownOperation.descriptorHash, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              reconcilePreviewButton.dataset.previewId = String(preview.operation_id);
              reconcilePreviewButton.dataset.descriptorHash = String(preview.descriptor_hash);
              reconciliationPreviewResponse = structuredClone(preview);
              reconcileConsent.checked = false;
              reconcileRead.disabled = false;
              renderSync("Reconciliation preview (exact paths):", preview);
            } catch (error) {
              if (current(g2, owner) && syncDetails)
                syncDetails.textContent = error instanceof Error ? error.message : "Reconciliation preview failed";
            } finally {
              endWorkflow(g2, owner, reconcilePreviewButton);
            }
          };
        if (reconcileRead && reconcileConsent && reconcilePreviewButton)
          reconcileRead.onclick = async () => {
            const g2 = generation;
            const revision = previewRevision;
            const ownerContext = identity && { ...identity };
            const preview = reconciliationPreviewResponse;
            const operationId = reconcilePreviewButton.dataset.previewId;
            const descriptorHash = reconcilePreviewButton.dataset.descriptorHash;
            if (!operationId || !descriptorHash || !preview || !reconcileConsent.checked) {
              if (syncDetails)
                syncDetails.textContent = "Explicit reconciliation read consent is required.";
              return;
            }
            if (refuseConsumedPreview({ operation_id: operationId }, syncDetails))
              return;
            if (!beginWorkflow(reconcileRead))
              return;
            try {
              const consent = await bridgePost("/api/workflow/consent", { operationId, descriptorHash, consent: true, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision), consentHooks({ operation_id: operationId, descriptor_hash: descriptorHash }, ownerContext, "reconciliation_read", owner, g2, () => currentAttempt(g2, owner, revision)));
              if (!currentAttempt(g2, owner, revision))
                return;
              const instruction = consent.instruction;
              if (!instruction)
                throw new Error("Reconciliation instruction is unavailable");
              await bindInstructionToPreview(instruction, reconciliationPreviewResponse);
              const observed = await executeLiteInstruction({ control: controlDb, runtime: runtimeDb }, instruction, { ...expected(), reconciliationTargetKind: unknownOperation?.kind }, () => currentAttempt(g2, owner, revision));
              if (!currentAttempt(g2, owner, revision))
                return;
              const result2 = await bridgePost("/api/workflow/reconcile", { operationId: consent.operation_id, descriptorHash: consent.descriptor_hash, observed, sessionId: workflow.session_id }, owner, g2, () => currentAttempt(g2, owner, revision));
              if (result2.status === "reconciled" || result2.status === "acknowledged") {
                forgetOperation(unknownOperation?.operationId ?? "");
                forgetOperation(String(consent.operation_id));
                reconciliationPreviewResponse = void 0;
                showNextUnknown(ownerContext);
              }
              if (currentAttempt(g2, owner, revision) && syncDetails)
                syncDetails.textContent = `Reconciliation status: ${String(result2.status || "unknown")}.`;
            } catch (error) {
              if (current(g2, owner)) {
                reconciliationPreviewResponse = void 0;
                reconcileConsent.checked = false;
                reconcileRead.disabled = true;
                if (syncDetails)
                  syncDetails.textContent = error instanceof Error ? error.message : "Reconciliation failed";
                showNextUnknown(ownerContext);
              }
            } finally {
              endWorkflow(g2, owner, reconcileRead);
              if (current(g2, owner) && !reconciliationPreviewResponse)
                reconcileRead.disabled = true;
            }
          };
      }
      if (bootstrap.cloudGrant) {
        cloudGrant.hidden = false;
        consentButton.hidden = false;
        cloudGrantDetails.textContent = `Purpose: ${bootstrap.cloudGrant.purpose};
destination: ${bootstrap.cloudGrant.destination};
full verified scopes: ${bootstrap.cloudGrant.scopes.join(", ")};
expires: ${bootstrap.cloudGrant.expiresAt}`;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Sign-in failed";
      if (loginOwner && activeUser === loginOwner && current(generation, loginOwner)) {
        stateElement.textContent = message;
        await signOut(auth).catch(() => void 0);
      } else if (generation === loginGeneration || !activeUser)
        stateElement.textContent = message;
    } finally {
      if (generation === loginGeneration || !activeUser)
        loginButton.disabled = false;
    }
  });
  logoutButton.addEventListener("click", async () => {
    invalidate("Signed out; no Firebase identity remains in this session.");
    await signOut(auth).catch(() => void 0);
  });
  onAuthStateChanged(auth, (user) => {
    if (activeUser && user !== activeUser)
      invalidate(user ? "Firebase account changed; workflow state was cleared." : "Signed out; workflow state was cleared.");
  });
  consentButton.addEventListener("click", async () => {
    const owner = activeUser;
    const g2 = generation;
    if (!consentCheckbox.checked || !owner || !bootstrap.cloudGrant) {
      stateElement.textContent = "Explicit human consent is required.";
      return;
    }
    consentButton.disabled = true;
    try {
      const token = await owner.getIdToken();
      if (!current(g2, owner))
        return;
      const response = await fetch("/api/cloud-grant-consent", { method: "POST", headers: { "Content-Type": "application/json", Origin: window.location.origin, "X-Session-Capability": capability() }, body: JSON.stringify({ firebaseIdToken: token, googleSubject: localSubject(), ...bootstrap.cloudGrant, consent: true }) });
      if (!response.ok)
        throw new Error("Cloud grant consent was rejected");
      if (current(g2, owner))
        stateElement.textContent = "Cloud grant consent recorded for this account and purpose.";
    } catch (error) {
      if (current(g2, owner))
        stateElement.textContent = error instanceof Error ? error.message : "Consent failed";
    } finally {
      if (current(g2, owner))
        consentButton.disabled = false;
    }
  });
}
start().catch((error) => {
  if (stateElement)
    stateElement.textContent = error instanceof Error ? error.message : "Setup is unavailable";
});
/*! Bundled license information:

@firebase/util/dist/index.esm.js:
@firebase/util/dist/index.esm.js:
@firebase/util/dist/index.esm.js:
@firebase/util/dist/index.esm.js:
@firebase/util/dist/index.esm.js:
@firebase/util/dist/index.esm.js:
@firebase/util/dist/index.esm.js:
@firebase/util/dist/index.esm.js:
@firebase/util/dist/index.esm.js:
@firebase/logger/dist/esm/index.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2017 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/util/dist/index.esm.js:
  (**
   * @license
   * Copyright 2022 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2017 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2025 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2021 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/util/dist/index.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2022 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/util/dist/index.esm.js:
@firebase/component/dist/esm/index.esm.js:
@firebase/app/dist/esm/index.esm.js:
@firebase/app/dist/esm/index.esm.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2019 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/util/dist/index.esm.js:
firebase/app/dist/esm/index.esm.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/util/dist/index.esm.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
  (**
   * @license
   * Copyright 2021 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/app/dist/esm/index.esm.js:
  (**
   * @license
   * Copyright 2019 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2023 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/app/dist/esm/index.esm.js:
  (**
   * @license
   * Copyright 2021 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2019 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/auth/dist/esm/index-9ccb475d.js:
@firebase/auth/dist/esm/index-9ccb475d.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2019 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/auth/dist/esm/index-9ccb475d.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2022 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2023 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/auth/dist/esm/index-9ccb475d.js:
  (**
   * @license
   * Copyright 2019 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/auth/dist/esm/index-9ccb475d.js:
  (**
   * @license
   * Copyright 2019 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2025 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/auth/dist/esm/index-9ccb475d.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2019 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2020 Google LLC.
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/auth/dist/esm/index-9ccb475d.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2021 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2019 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/auth/dist/esm/index-9ccb475d.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2020 Google LLC.
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2021 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/webchannel-wrapper/dist/bloom-blob/esm/bloom_blob_es2018.js:
  (** @license
  Copyright The Closure Library Authors.
  SPDX-License-Identifier: Apache-2.0
  *)
  (** @license
  
   Copyright The Closure Library Authors.
   SPDX-License-Identifier: Apache-2.0
  *)

@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
  * @license
  * Copyright 2020 Google LLC
  *
  * Licensed under the Apache License, Version 2.0 (the "License");
  * you may not use this file except in compliance with the License.
  * You may obtain a copy of the License at
  *
  *   http://www.apache.org/licenses/LICENSE-2.0
  *
  * Unless required by applicable law or agreed to in writing, software
  * distributed under the License is distributed on an "AS IS" BASIS,
  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  * See the License for the specific language governing permissions and
  * limitations under the License.
  *)
  (**
   * @license
   * Copyright 2017 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2017 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2023 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2017 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2017 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2023 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2017 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2023 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2025 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2017 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2019 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2018 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2017 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/firestore/dist/lite/index.browser.esm.js:
@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2017 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2022 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@firebase/firestore/dist/lite/index.browser.esm.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2017 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
   * @license
   * Copyright 2024 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
  (**
  * @license
  * Copyright 2017 Google LLC
  *
  * Licensed under the Apache License, Version 2.0 (the "License");
  * you may not use this file except in compliance with the License.
  * You may obtain a copy of the License at
  *
  *   http://www.apache.org/licenses/LICENSE-2.0
  *
  * Unless required by applicable law or agreed to in writing, software
  * distributed under the License is distributed on an "AS IS" BASIS,
  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  * See the License for the specific language governing permissions and
  * limitations under the License.
  *)
*/
