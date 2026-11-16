const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const appSource = fs.readFileSync(
  path.join(__dirname, "../ui/web/static/app.js"),
  "utf8",
);

const appCss = fs.readFileSync(
  path.join(__dirname, "../ui/web/static/app.css"),
  "utf8",
);

const appHtml = fs.readFileSync(
  path.join(__dirname, "../ui/web/templates/index.html"),
  "utf8",
);

function createElement(id, attributes = {}) {
  const classes = new Set();
  const listeners = new Map();
  const queryResults = new Map();
  return {
    id,
    attributes,
    listeners,
    style: {},
    value: "",
    textContent: "",
    disabled: false,
    title: "",
    classList: {
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
      toggle(name, force) {
        const enabled = force === undefined ? !classes.has(name) : !!force;
        if (enabled) classes.add(name);
        else classes.delete(name);
        return enabled;
      },
    },
    addEventListener(name, handler) {
      if (!listeners.has(name)) listeners.set(name, []);
      listeners.get(name).push(handler);
    },
    dispatch(name, values = {}) {
      const event = {
        pointerId: 1,
        clientX: 100,
        clientY: 100,
        preventDefault() {},
        ...values,
      };
      if (name === "click" && this.disabled) return event;
      const propertyHandler = this[`on${name}`];
      if (typeof propertyHandler === "function") propertyHandler.call(this, event);
      for (const handler of listeners.get(name) || []) handler(event);
      return event;
    },
    getAttribute(name) { return attributes[name] ?? null; },
    setAttribute(name, value) { attributes[name] = String(value); },
    setPointerCapture() {},
    focus() { this.focused = true; },
    getBoundingClientRect() { return { left: 0, top: 0, width: 200, height: 200 }; },
    querySelector(selector) {
      if (selector === ".knob") return this.knob || createElement(`${id}-knob`);
      if (selector === "span") {
        if (!queryResults.has(selector)) queryResults.set(selector, createElement(`${id}-span`));
        return queryResults.get(selector);
      }
      return null;
    },
  };
}

function createHarness(settings = {}) {
  const calls = [];
  const elements = new Map();
  const deviceName = createElement("deviceName");
  deviceName.value = "Web Controller";
  elements.set("deviceName", deviceName);
  const mouseSensitivity = createElement("mouseSensitivity");
  mouseSensitivity.value = "17";
  elements.set("mouseSensitivity", mouseSensitivity);
  const steeringSensitivity = createElement("steeringSensitivity");
  steeringSensitivity.value = "10";
  elements.set("steeringSensitivity", steeringSensitivity);
  const tapToClick = createElement("tapToClick");
  tapToClick.checked = true;
  elements.set("tapToClick", tapToClick);
  const gamepadButton = createElement("button-A", { "data-button": "A" });
  const quickKeys = ["LEFT", "UP", "DOWN", "RIGHT"].map((key) =>
    createElement(`key-${key}`, { "data-key": key, "data-permission": "keyboard" }),
  );
  const leftStick = createElement("leftStick");
  const rightStick = createElement("rightStick");
  leftStick.knob = createElement("left-knob");
  rightStick.knob = createElement("right-knob");
  const touchpad = createElement("touchpad");
  elements.set("leftStick", leftStick);
  elements.set("rightStick", rightStick);
  elements.set("touchpad", touchpad);
  const mouseTab = createElement("mouse-tab", { "data-tab": "mouse" });
  const views = ["gamepad", "mouse", "remote", "session"].map((name) => {
    const view = createElement(`view-${name}`);
    elements.set(view.id, view);
    return view;
  });
  const documentListeners = new Map();
  const windowListeners = new Map();
  const body = createElement("body");
  const documentElement = createElement("documentElement");
  const sessionValues = new Map([
    ["ib.web.token", "test-session-token"],
    ["ib.web.name", "Test browser"],
  ]);
  const preferenceValues = new Map();
  if (settings.preferences) {
    preferenceValues.set("ib.web.preferences", JSON.stringify(settings.preferences));
  }
  let now = 1000;
  let failNextState = false;
  const heldStateResponses = [];
  const webSockets = [];
  const frames = [];
  const timers = new Map();
  let timerSequence = 0;
  function queueTimeout(callback, delay) {
    const id = ++timerSequence;
    timers.set(id, { callback, delay: Number(delay) || 0 });
    return id;
  }
  function clearQueuedTimeout(id) {
    timers.delete(id);
  }

  const document = {
    readyState: "complete",
    hidden: false,
    body,
    documentElement,
    fullscreenElement: null,
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, createElement(id));
      return elements.get(id);
    },
    querySelectorAll(selector) {
      if (selector === ".tab") return [mouseTab];
      if (selector === ".view") return views;
      if (selector === ".pad-key[data-button]") return [gamepadButton];
      if (selector === "[data-key]") return quickKeys;
      if (selector === "[data-permission]") return quickKeys;
      if (selector === ".knob") return [leftStick.knob, rightStick.knob];
      if (selector === ".pad-key.pressed,.btn.pressed") {
        return [gamepadButton].filter((element) => element.classList.contains("pressed"));
      }
      return [];
    },
    addEventListener(name, handler) {
      if (!documentListeners.has(name)) documentListeners.set(name, []);
      documentListeners.get(name).push(handler);
    },
    dispatch(name) {
      for (const handler of documentListeners.get(name) || []) handler({ type: name });
    },
  };
  const window = {
    location: { hash: settings.hash || "", pathname: "/", search: "", protocol: "https:", host: "vpadconnect.test" },
    confirmCalls: 0,
    DeviceOrientationEvent: function DeviceOrientationEvent() {},
    DeviceMotionEvent: function DeviceMotionEvent() {},
    addEventListener(name, handler) { windowListeners.set(name, handler); },
    removeEventListener(name, handler) {
      if (windowListeners.get(name) === handler) windowListeners.delete(name);
    },
    confirm() { this.confirmCalls += 1; return true; },
  };
  const fetch = (url, options = {}) => {
    calls.push({ url, options });
    if (url === "/api/state" && failNextState) {
      failNextState = false;
      return Promise.reject(new Error("connection lost"));
    }
    const requestBody = options.body ? JSON.parse(options.body) : {};
    const body = url === "/api/action"
      ? { ok: true, result: { capabilities: settings.capabilities || {
        pc_status: true, keyboard: true, media: true, clipboard: true,
        app_launch: true, presentation: true, power: true,
      } } }
      : url === "/api/info"
        ? { ok: true, fingerprint: settings.fingerprint || "ab".repeat(32) }
        : url === "/api/pair"
          ? { ok: true, token: "paired-session-token", name: requestBody.name }
          : { ok: true };
    if (url === "/api/state" && settings.holdStateResponses) {
      return new Promise((resolve) => {
        heldStateResponses.push(() => resolve({ ok: true, json: () => Promise.resolve(body) }));
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  };
  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      this.sent = [];
      this.readyState = 0;
      this.bufferedAmount = 0;
      webSockets.push(this);
    }
    send(raw) {
      this.sent.push(JSON.parse(raw));
    }
    close() {
      this.readyState = 3;
      if (this.onclose) this.onclose({});
    }
  }

  const sandbox = {
    document,
    window,
    fetch,
    sessionStorage: {
      getItem(key) { return sessionValues.get(key) || null; },
      setItem(key, value) { sessionValues.set(key, value); },
      removeItem(key) { sessionValues.delete(key); },
    },
    localStorage: {
      getItem(key) { return preferenceValues.get(key) || null; },
      setItem(key, value) { preferenceValues.set(key, value); },
      removeItem(key) { preferenceValues.delete(key); },
    },
    DeviceOrientationEvent: window.DeviceOrientationEvent,
    DeviceMotionEvent: window.DeviceMotionEvent,
    URLSearchParams,
    performance: { now() { now += 5; return now; } },
    requestAnimationFrame(callback) { frames.push(callback); },
    setTimeout: queueTimeout,
    clearTimeout: clearQueuedTimeout,
    history: { replaceState() {} },
  };
  sandbox.WebSocket = settings.websocket ? FakeWebSocket : undefined;

  vm.runInNewContext(appSource, sandbox, { filename: "ui/web/static/app.js" });
  return {
    calls,
    document,
    window,
    elements,
    gamepadButton,
    leftStick,
    mouseTab,
    quickKeys,
    sessionValues,
    preferenceValues,
    webSockets,
    runTimer(delay) {
      const entry = [...timers.entries()].find(([, timer]) => timer.delay === delay);
      if (!entry) return false;
      timers.delete(entry[0]);
      entry[1].callback();
      return true;
    },
    scheduledDelays() { return [...timers.values()].map((timer) => timer.delay); },
    dispatchWindow(name, event) {
      const handler = windowListeners.get(name);
      if (handler) handler(event);
    },
    touchpad,
    tickFrame() {
      const callback = frames.shift();
      if (callback) callback();
    },
    setFailNextState() { failNextState = true; },
    releaseNextState() { const release = heldStateResponses.shift(); if (release) release(); },
    pendingStateResponses() { return heldStateResponses.length; },
  };
}

async function settle() {
  for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setImmediate(resolve));
}

function stateRequests(harness) {
  return harness.calls
    .filter(({ url }) => url === "/api/state")
    .map(({ options }) => JSON.parse(options.body));
}

test("browser control preferences restore and persist without storing the session token", async () => {
  const harness = createHarness({
    preferences: {
      name: "Living room tablet",
      mouseSensitivity: 2.4,
      steeringSensitivity: 1.8,
      tapToClick: false,
      preset: "driving",
    },
  });
  await settle();

  assert.equal(harness.elements.get("deviceName").value, "Living room tablet");
  assert.equal(harness.elements.get("mouseSensitivity").value, "24");
  assert.equal(harness.elements.get("steeringSensitivity").value, "18");
  assert.equal(harness.elements.get("tapToClick").checked, false);
  assert.equal(harness.elements.get("driving").classList.contains("active"), true);

  harness.elements.get("deviceName").value = "Bedroom phone";
  harness.elements.get("deviceName").dispatch("input");
  harness.elements.get("mouseSensitivity").value = "25";
  harness.elements.get("mouseSensitivity").dispatch("input");
  harness.elements.get("steeringSensitivity").value = "20";
  harness.elements.get("steeringSensitivity").dispatch("input");
  harness.elements.get("tapToClick").checked = true;
  harness.elements.get("tapToClick").dispatch("change");
  harness.elements.get("reverseScroll").checked = true;
  harness.elements.get("reverseScroll").dispatch("change");
  harness.elements.get("scrollSensitivity").value = "1";
  harness.elements.get("scrollSensitivity").dispatch("input");
  assert.equal(JSON.parse(harness.preferenceValues.get("ib.web.preferences")).scrollSensitivity, 0.1);
  assert.equal(harness.elements.get("scrollSensitivityValue").textContent, "0.1×");

  harness.elements.get("scrollSensitivity").value = "200";
  harness.elements.get("scrollSensitivity").dispatch("input");
  harness.elements.get("hapticsEnabled").checked = true;
  harness.elements.get("hapticsEnabled").dispatch("change");
  harness.elements.get("standard").dispatch("click");

  assert.deepEqual(JSON.parse(harness.preferenceValues.get("ib.web.preferences")), {
    name: "Bedroom phone",
    mouseSensitivity: 2.5,
    steeringSensitivity: 2,
    airMouseSensitivity: 2,
    tapToClick: true,
    reverseScroll: true,
    scrollSensitivity: 20,
    hapticsEnabled: true,
    keepScreenAwake: false,
    preset: "standard",
    controllerStyle: "xbox",
  });
  assert.equal(harness.sessionValues.get("ib.web.token"), "test-session-token");
  assert.equal(harness.preferenceValues.has("ib.web.token"), false);
});

test("invalid saved browser preferences fall back to safe control defaults", async () => {
  const harness = createHarness({
    preferences: {
      name: "   ",
      mouseSensitivity: 99,
      steeringSensitivity: "2.0",
      tapToClick: "false",
      preset: "unknown",
    },
  });
  await settle();

  assert.equal(harness.elements.get("deviceName").value, "Web Controller");
  assert.equal(harness.elements.get("mouseSensitivity").value, "17");
  assert.equal(harness.elements.get("steeringSensitivity").value, "10");
  assert.equal(harness.elements.get("tapToClick").checked, true);
  assert.equal(harness.elements.get("standard").classList.contains("active"), true);
  assert.equal(harness.elements.get("driving").classList.contains("active"), false);
});

test("saved steering sensitivity changes tilt response in driving mode", async () => {
  async function maximumSteer(sensitivity) {
    const harness = createHarness({
      preferences: { steeringSensitivity: sensitivity, preset: "driving" },
    });
    await settle();
    harness.elements.get("tiltToggle").dispatch("click");
    harness.dispatchWindow("deviceorientation", { gamma: 0 });
    for (let i = 0; i < 15; i += 1) {
      harness.dispatchWindow("deviceorientation", { gamma: 5 });
    }
    await settle();
    return Math.max(...stateRequests(harness).map((request) => request.joystick.left_x));
  }

  assert.ok(await maximumSteer(2) > await maximumSteer(1));
});

test("desktop QR link pre-fills its pairing code and verifies its fingerprint", async () => {
  const fingerprint = "ab".repeat(32);
  const harness = createHarness({
    hash: `#pair=123456&fp=${fingerprint}`,
    fingerprint,
  });
  await settle();

  assert.equal(harness.elements.get("pairCode").value, "123456");
  harness.elements.get("pairButton").dispatch("click");
  await settle();

  const pairRequest = harness.calls.find(({ url }) => url === "/api/pair");
  assert.ok(pairRequest);
  const pairPayload = JSON.parse(pairRequest.options.body);
  assert.deepEqual(Object.keys(pairPayload).sort(), ["code", "device_id", "name"]);
  assert.equal(pairPayload.code, "123456");
  assert.equal(pairPayload.name, "Web Controller");
  assert.match(pairPayload.device_id, /^[a-f0-9]{32}$/);
  assert.equal(
    pairPayload.device_id,
    harness.preferenceValues.get("vpadconnect.companion.id"),
  );
  assert.equal(harness.window.confirmCalls, 0);
  assert.equal(harness.sessionValues.get("ib.web.token"), "paired-session-token");
});

test("QR fingerprint mismatch blocks pairing before a session is created", async () => {
  const harness = createHarness({
    hash: `#pair=123456&fp=${"ab".repeat(32)}`,
    fingerprint: "cd".repeat(32),
  });
  await settle();

  harness.elements.get("pairButton").dispatch("click");
  await settle();

  assert.equal(harness.calls.some(({ url }) => url === "/api/pair"), false);
  assert.match(harness.elements.get("pairMessage").textContent, /fingerprint mismatch/i);
  assert.equal(harness.window.confirmCalls, 0);
});

test("web keyboard navigation buttons send authenticated arrow-key actions", async () => {
  const harness = createHarness();
  await settle();

  for (const key of ["LEFT", "UP", "DOWN", "RIGHT"]) {
    const button = harness.quickKeys.find((item) => item.getAttribute("data-key") === key);
    button.dispatch("click", { detail: 1 });
    await settle();
  }

  const requests = harness.calls
    .filter(({ url }) => url === "/api/action")
    .map(({ options }) => ({ options, body: JSON.parse(options.body) }))
    .filter(({ body }) => body.action === "keyboard_key");
  assert.deepEqual(requests.map(({ body }) => body.payload.key), ["LEFT", "UP", "DOWN", "RIGHT"]);
  assert.ok(requests.every(({ options }) =>
    options.headers.Authorization === "Bearer test-session-token"));
});

test("web keyboard navigation buttons stay disabled without PC keyboard permission", async () => {
  const harness = createHarness({
    capabilities: {
      pc_status: true, keyboard: false, media: false, clipboard: false,
      app_launch: false, presentation: false, power: false,
    },
  });
  await settle();

  const leftArrow = harness.quickKeys.find((button) => button.getAttribute("data-key") === "LEFT");
  assert.equal(leftArrow.disabled, true);
  leftArrow.dispatch("click", { detail: 1 });
  await settle();
  assert.equal(harness.calls.some(({ url, options }) =>
    url === "/api/action" && JSON.parse(options.body).action === "keyboard_key"), false);
});

test("a gamepad button stays held until every touch pointer releases it", async () => {
  const harness = createHarness();
  await settle();
  harness.gamepadButton.dispatch("pointerdown", { pointerId: 10 });
  harness.gamepadButton.dispatch("pointerdown", { pointerId: 11 });
  harness.gamepadButton.dispatch("pointerup", { pointerId: 10 });
  await settle();
  assert.equal(stateRequests(harness).at(-1).buttons.A, 1);

  harness.gamepadButton.dispatch("pointerup", { pointerId: 11 });
  await settle();
  assert.equal(stateRequests(harness).at(-1).buttons.A, 0);
});

test("gamepad buttons respond to keyboard activation and release on keyup", async () => {
  const harness = createHarness();
  await settle();

  harness.gamepadButton.dispatch("keydown", { key: "Enter" });
  await settle();
  assert.equal(stateRequests(harness).at(-1).buttons.A, 1);

  harness.gamepadButton.dispatch("keyup", { key: "Enter" });
  await settle();
  assert.equal(stateRequests(harness).at(-1).buttons.A, 0);
});

test("cancelling a stick pointer returns that stick to neutral", async () => {
  const harness = createHarness();
  await settle();

  harness.leftStick.dispatch("pointerdown", { pointerId: 20, clientX: 168 });
  await settle();
  assert.equal(stateRequests(harness).at(-1).joystick.left_x, 255);

  harness.leftStick.dispatch("pointercancel", { pointerId: 20 });
  await settle();
  assert.equal(stateRequests(harness).at(-1).joystick.left_x, 128);
  assert.equal(stateRequests(harness).at(-1).joystick.left_y, 128);
});

test("a cancelled touchpad gesture does not become a tap-to-click", async () => {
  const harness = createHarness();
  await settle();
  harness.mouseTab.dispatch("click");
  await settle();

  harness.touchpad.dispatch("pointerdown", { pointerId: 30 });
  harness.touchpad.dispatch("pointercancel", { pointerId: 30 });
  await settle();

  assert.equal(stateRequests(harness).at(-1).mouse.left, 0);
});

test("a quick second tap held on the touchpad starts a left-button drag", async () => {
  const harness = createHarness();
  await settle();
  harness.mouseTab.dispatch("click");
  await settle();

  harness.touchpad.dispatch("pointerdown", { pointerId: 71, clientX: 100, clientY: 100 });
  harness.touchpad.dispatch("pointerup", { pointerId: 71, clientX: 100, clientY: 100 });
  await settle();
  assert.equal(stateRequests(harness).at(-1).mouse.left, 1);
  harness.runTimer(100);
  await settle();
  assert.equal(stateRequests(harness).at(-1).mouse.left, 0);

  harness.touchpad.dispatch("pointerdown", { pointerId: 72, clientX: 101, clientY: 100 });
  harness.runTimer(240);
  await settle();
  assert.equal(stateRequests(harness).at(-1).mouse.left, 1);

  harness.touchpad.dispatch("pointermove", { pointerId: 72, clientX: 130, clientY: 118 });
  await settle();
  assert.equal(stateRequests(harness).at(-1).mouse.left, 1);
  assert.ok(stateRequests(harness).at(-1).mouse.dx > 0);
  assert.ok(stateRequests(harness).at(-1).mouse.dy > 0);

  harness.touchpad.dispatch("pointerup", { pointerId: 72, clientX: 130, clientY: 118 });
  await settle();
  assert.equal(stateRequests(harness).at(-1).mouse.left, 0);
});

test("a simultaneous two-finger touchpad tap sends a right click, not a scroll", async () => {
  const harness = createHarness();
  await settle();
  harness.mouseTab.dispatch("click");
  await settle();

  harness.touchpad.dispatch("pointerdown", { pointerId: 81, clientX: 100, clientY: 100 });
  harness.touchpad.dispatch("pointerdown", { pointerId: 82, clientX: 112, clientY: 100 });
  harness.touchpad.dispatch("pointerup", { pointerId: 81, clientX: 100, clientY: 100 });
  harness.touchpad.dispatch("pointerup", { pointerId: 82, clientX: 112, clientY: 100 });
  await settle();

  assert.equal(stateRequests(harness).at(-1).mouse.right, 1);
  assert.equal(stateRequests(harness).at(-1).mouse.scroll, 0);
  harness.runTimer(100);
  await settle();
  assert.equal(stateRequests(harness).at(-1).mouse.right, 0);
});

test("two-finger touchpad movement sends mouse scroll input", async () => {
  const harness = createHarness();
  await settle();
  harness.mouseTab.dispatch("click");
  await settle();

  harness.touchpad.dispatch("pointerdown", { pointerId: 31, clientX: 100, clientY: 100 });
  harness.touchpad.dispatch("pointerdown", { pointerId: 32, clientX: 110, clientY: 100 });
  harness.touchpad.dispatch("pointermove", { pointerId: 32, clientX: 110, clientY: 128 });
  for (let i = 0; i < 10; i += 1) harness.tickFrame();
  await settle();

  assert.equal(stateRequests(harness).at(-1).mode, "mouse");
  assert.equal(stateRequests(harness).at(-1).mouse.scroll, -20);
});

test("reverse scrolling reverses two-finger touchpad direction", async () => {
  const harness = createHarness();
  await settle();
  harness.elements.get("reverseScroll").checked = true;
  harness.elements.get("reverseScroll").dispatch("change");
  harness.mouseTab.dispatch("click");
  await settle();

  harness.touchpad.dispatch("pointerdown", { pointerId: 41, clientX: 100, clientY: 100 });
  harness.touchpad.dispatch("pointerdown", { pointerId: 42, clientX: 110, clientY: 100 });
  harness.touchpad.dispatch("pointermove", { pointerId: 42, clientX: 110, clientY: 128 });
  for (let i = 0; i < 10; i += 1) harness.tickFrame();
  await settle();

  assert.equal(stateRequests(harness).at(-1).mouse.scroll, 20);
  assert.equal(JSON.parse(harness.preferenceValues.get("ib.web.preferences")).reverseScroll, true);
});

test("touchpad scroll slider exposes very low and very high sensitivities", () => {
  assert.match(appHtml, /id="scrollSensitivity" type="range" min="1" max="200" value="20"/);
});

test("scroll sensitivity scales the faster two-finger touchpad scroll amount", async () => {
  const harness = createHarness();
  await settle();
  harness.elements.get("scrollSensitivity").value = "200";
  harness.elements.get("scrollSensitivity").dispatch("input");
  harness.mouseTab.dispatch("click");
  await settle();

  harness.touchpad.dispatch("pointerdown", { pointerId: 51, clientX: 100, clientY: 100 });
  harness.touchpad.dispatch("pointerdown", { pointerId: 52, clientX: 110, clientY: 100 });
  harness.touchpad.dispatch("pointermove", { pointerId: 52, clientX: 110, clientY: 102 });
  for (let i = 0; i < 10; i += 1) harness.tickFrame();
  await settle();

  assert.equal(stateRequests(harness).at(-1).mouse.scroll, -20);
  assert.equal(JSON.parse(harness.preferenceValues.get("ib.web.preferences")).scrollSensitivity, 20);
  assert.equal(harness.elements.get("scrollSensitivityValue").textContent, "20.0×");
});

test("keyboard arrows operate and recenter a focused stick", async () => {
  const harness = createHarness();
  await settle();

  harness.leftStick.dispatch("keydown", { key: "ArrowRight" });
  await settle();
  assert.equal(stateRequests(harness).at(-1).joystick.left_x, 255);

  harness.leftStick.dispatch("keyup", { key: "ArrowRight" });
  await settle();
  assert.equal(stateRequests(harness).at(-1).joystick.left_x, 128);
});

test("visibility loss clears held input and a temporary network failure preserves the session", async () => {
  const harness = createHarness();
  await settle();
  harness.leftStick.dispatch("pointerdown", { pointerId: 40, clientX: 168 });
  await settle();

  harness.document.hidden = true;
  harness.document.dispatch("visibilitychange");
  await settle();
  assert.equal(stateRequests(harness).at(-1).joystick.left_x, 128);

  harness.document.hidden = false;
  harness.leftStick.dispatch("pointerdown", { pointerId: 42, clientX: 168 });
  await settle();
  assert.equal(stateRequests(harness).at(-1).joystick.left_x, 255);
  harness.leftStick.dispatch("pointercancel", { pointerId: 42 });
  await settle();

  harness.setFailNextState();
  harness.gamepadButton.dispatch("pointerdown", { pointerId: 41 });
  await settle();
  assert.equal(harness.calls.some(({ url }) => url === "/api/disconnect"), false);
  assert.equal(harness.sessionValues.get("ib.web.token"), "test-session-token");
  assert.equal(harness.elements.get("badge").querySelector("span").textContent, "Reconnecting…");
  assert.match(harness.elements.get("toast").textContent, /connection to your PC was lost/i);
  assert.equal(harness.gamepadButton.classList.contains("pressed"), false);
});


test("state updates are coalesced while a slow request is in flight, then the newest stick position is sent", async () => {
  const harness = createHarness({ holdStateResponses: true });
  await settle();

  harness.leftStick.dispatch("pointerdown", { pointerId: 61, clientX: 168, clientY: 100 });
  assert.equal(harness.pendingStateResponses(), 1);
  assert.equal(stateRequests(harness).at(-1).joystick.left_x, 255);

  harness.leftStick.dispatch("pointermove", { pointerId: 61, clientX: 130, clientY: 100 });
  assert.equal(harness.pendingStateResponses(), 1);
  harness.releaseNextState();
  await settle();

  assert.equal(harness.pendingStateResponses(), 1);
  assert.ok(stateRequests(harness).length >= 2);
  assert.equal(stateRequests(harness).at(-1).joystick.left_x, 184);
  harness.releaseNextState();
  await settle();
});

test("Driving mode enables motion steering and maps orientation changes to the left stick", async () => {
  const harness = createHarness();
  await settle();

  harness.elements.get("driving").dispatch("click");
  await settle();
  assert.equal(harness.elements.get("tiltToggle").textContent, "Disable tilt steering");

  harness.dispatchWindow("deviceorientation", { gamma: 0 });
  harness.dispatchWindow("deviceorientation", { gamma: 15 });
  await settle();

  assert.ok(stateRequests(harness).at(-1).joystick.left_x > 128);
});


test("landscape gyro steering uses the corrected left-right direction", async () => {
  const harness = createHarness();
  harness.window.screen = { orientation: { type: "landscape-primary", angle: 90 } };
  await settle();

  harness.elements.get("driving").dispatch("click");
  await settle();
  harness.dispatchWindow("deviceorientation", { beta: 0, gamma: 0 });
  harness.dispatchWindow("deviceorientation", { beta: 15, gamma: 0 });
  await settle();

  assert.ok(stateRequests(harness).at(-1).joystick.left_x > 128);
});

test("controller layout toggles between authentic Xbox and PlayStation labels and persists", async () => {
  const harness = createHarness();
  await settle();

  assert.equal(harness.elements.get("controllerStyle").textContent, "Xbox layout");
  assert.equal(harness.elements.get("faceY").textContent, "Y");
  harness.elements.get("focus").dispatch("click");
  harness.elements.get("controllerStyle").dispatch("click");

  assert.equal(harness.document.body.classList.contains("focus-mode"), true);
  assert.equal(harness.elements.get("controllerStyle").textContent, "PlayStation layout");
  assert.equal(harness.elements.get("controller").classList.contains("playstation-layout"), true);
  assert.equal(harness.elements.get("faceY").textContent, "△");
  assert.equal(harness.elements.get("faceX").textContent, "□");
  assert.equal(harness.elements.get("faceB").textContent, "○");
  assert.equal(harness.elements.get("faceA").textContent, "×");
  const saved = JSON.parse(harness.preferenceValues.get("ib.web.preferences"));
  assert.equal(saved.controllerStyle, "playstation");

  harness.elements.get("controllerStyle").dispatch("click");
  assert.equal(harness.elements.get("controllerStyle").textContent, "Xbox layout");
  assert.equal(harness.elements.get("faceY").textContent, "Y");
});


test("WebSocket backpressure drops stale mouse movement instead of replaying it with lag", async () => {
  const harness = createHarness({ websocket: true });
  await settle();

  const socket = harness.webSockets[0];
  socket.readyState = 1;
  socket.onopen({});
  socket.onmessage({ data: JSON.stringify({ type: "ready" }) });
  harness.tickFrame();

  harness.elements.get("airMouseToggle").dispatch("click");
  harness.tickFrame();

  socket.bufferedAmount = 8192;
  for (let i = 0; i < 30; i += 1) {
    harness.dispatchWindow("devicemotion", {
      interval: 16,
      rotationRate: { alpha: 0, beta: 0, gamma: 35 },
      acceleration: { x: 0, y: 0, z: 0 },
    });
    harness.tickFrame();
  }

  socket.bufferedAmount = 0;
  harness.tickFrame();
  const states = socket.sent.filter((packet) => packet.type === "state");
  assert.ok(states.length >= 2);
  assert.equal(states.at(-1).state.mouse.dx, 0, "stale movement must not burst out when the socket recovers");
  assert.equal(states.at(-1).state.mouse.dy, 0);
});

test("WebSocket backpressure drops stale mouse movement instead of replaying it with lag", async () => {
  const harness = createHarness({ websocket: true });
  await settle();

  const socket = harness.webSockets[0];
  socket.readyState = 1;
  socket.onopen({});
  socket.onmessage({ data: JSON.stringify({ type: "ready" }) });
  harness.tickFrame();

  harness.elements.get("airMouseToggle").dispatch("click");
  harness.tickFrame();

  socket.bufferedAmount = 8192;
  for (let i = 0; i < 30; i += 1) {
    harness.dispatchWindow("devicemotion", {
      interval: 16,
      rotationRate: { alpha: 0, beta: 0, gamma: 35 },
      acceleration: { x: 0, y: 0, z: 0 },
    });
    harness.tickFrame();
  }

  socket.bufferedAmount = 0;
  harness.tickFrame();
  const states = socket.sent.filter((packet) => packet.type === "state");
  assert.ok(states.length >= 2);
  assert.equal(states.at(-1).state.mouse.dx, 0, "stale movement must not burst out when the socket recovers");
  assert.equal(states.at(-1).state.mouse.dy, 0);
});

test("paired controller streams input over one persistent WebSocket without state POSTs", async () => {
  const harness = createHarness({ websocket: true });
  await settle();

  assert.equal(harness.webSockets.length, 1);
  const socket = harness.webSockets[0];
  assert.equal(socket.url, "wss://vpadconnect.test/api/stream");
  socket.readyState = 1;
  socket.onopen({});
  assert.deepEqual(socket.sent[0], { type: "auth", token: "test-session-token" });
  socket.onmessage({ data: JSON.stringify({ type: "ready" }) });

  harness.tickFrame();
  harness.leftStick.dispatch("pointerdown", { pointerId: 91, clientX: 168, clientY: 100 });
  harness.tickFrame();
  let snapshots = socket.sent.filter((packet) => packet.type === "state");
  assert.equal(snapshots.at(-1).state.joystick.left_x, 255);

  harness.leftStick.dispatch("pointermove", { pointerId: 91, clientX: 130, clientY: 100 });
  harness.tickFrame();
  snapshots = socket.sent.filter((packet) => packet.type === "state");
  assert.ok(snapshots.at(-1).state.joystick.left_x < 255);
  assert.equal(harness.calls.filter(({ url }) => url === "/api/state").length, 0);

  harness.leftStick.dispatch("pointercancel", { pointerId: 91 });
  harness.tickFrame();
  snapshots = socket.sent.filter((packet) => packet.type === "state");
  assert.equal(snapshots.at(-1).state.joystick.left_x, 128);
});




test("unexpected WebSocket loss retries after five seconds and reports recovery with toasts", async () => {
  const harness = createHarness({ websocket: true });
  await settle();

  const first = harness.webSockets[0];
  first.readyState = 1;
  first.onopen({});
  first.onmessage({ data: JSON.stringify({ type: "ready" }) });
  first.close();

  assert.equal(harness.sessionValues.get("ib.web.token"), "test-session-token");
  assert.equal(harness.elements.get("badge").querySelector("span").textContent, "Reconnecting…");
  assert.match(harness.elements.get("toast").textContent, /connection to your PC was lost/i);
  assert.ok(harness.scheduledDelays().includes(5000));

  assert.equal(harness.runTimer(5000), true);
  await settle();
  assert.equal(harness.webSockets.length, 2);
  assert.match(harness.elements.get("toast").textContent, /trying to reconnect to your PC/i);

  const second = harness.webSockets[1];
  second.readyState = 1;
  second.onopen({});
  second.onmessage({ data: JSON.stringify({ type: "ready" }) });
  assert.equal(harness.elements.get("badge").querySelector("span").textContent, "Connected");
  assert.match(harness.elements.get("toast").textContent, /connection to your PC was restored/i);
});


test("desktop shutdown invalidates the stored browser session and stops reconnect attempts", async () => {
  const harness = createHarness({ websocket: true });
  await settle();

  const socket = harness.webSockets[0];
  socket.readyState = 1;
  socket.onopen({});
  socket.onmessage({ data: JSON.stringify({ type: "ready" }) });
  socket.onmessage({ data: JSON.stringify({ type: "error", error: "server_shutdown" }) });

  assert.equal(harness.sessionValues.has("ib.web.token"), false);
  assert.equal(harness.elements.get("badge").querySelector("span").textContent, "Not paired");
  assert.equal(harness.elements.get("pairPanel").classList.contains("hidden"), false);
  assert.match(harness.elements.get("toast").textContent, /VPadConnect on the PC was stopped/i);
  assert.equal(harness.webSockets.length, 1);
  harness.runTimer(5000);
  await settle();
  assert.equal(harness.webSockets.length, 1);
});



test("Focus stays on the selected mouse tab and focuses the touch surface", async () => {
  const harness = createHarness();
  await settle();

  harness.mouseTab.dispatch("click");
  assert.equal(harness.elements.get("view-mouse").classList.contains("active"), true);
  harness.elements.get("focus").dispatch("click");

  assert.equal(harness.document.body.classList.contains("focus-mode"), true);
  assert.equal(harness.elements.get("view-mouse").classList.contains("active"), true);
  assert.equal(harness.elements.get("view-gamepad").classList.contains("active"), false);
  assert.equal(harness.touchpad.focused, true);
  assert.match(harness.elements.get("toast").textContent, /mouse focus enabled/i);
});


test("6-axis Air Mouse uses the correct horizontal gyro axis, preserves vertical pitch, and calibrates robustly", async () => {
  const harness = createHarness();
  await settle();

  harness.elements.get("airMouseToggle").dispatch("click");
  assert.equal(harness.elements.get("airMouseToggle").getAttribute("aria-pressed"), "true");
  assert.equal(harness.touchpad.classList.contains("air-mouse-active"), true);

  for (let i = 0; i < 12; i += 1) {
    harness.dispatchWindow("devicemotion", {
      interval: 16,
      rotationRate: { alpha: 0, beta: 0, gamma: 0 },
      acceleration: { x: 0, y: 0, z: 0 },
    });
  }
  // A one-frame gyro spike while the page is hidden must not poison neutral calibration.
  harness.document.hidden = true;
  harness.dispatchWindow("devicemotion", {
    interval: 16,
    rotationRate: { alpha: 0, beta: 0, gamma: 180 },
    acceleration: { x: 0, y: 0, z: 0 },
  });
  harness.document.hidden = false;
  harness.elements.get("airMouseCalibrate").dispatch("click");
  assert.match(harness.elements.get("airMouseStatus").textContent, /gyro.*calibrated/i);

  // beta is the screen-side axis, not the twist/yaw axis used for horizontal cursor movement.
  for (let i = 0; i < 40; i += 1) {
    harness.dispatchWindow("devicemotion", {
      interval: 16,
      rotationRate: { alpha: 0, beta: 28, gamma: 0 },
      acceleration: { x: 0, y: 0, z: 0 },
    });
  }
  await settle();
  assert.equal(stateRequests(harness).some((request) => request.mouse.dx !== 0), false, "beta-only rotation must not drive horizontal cursor movement");

  for (let i = 0; i < 40; i += 1) {
    harness.dispatchWindow("devicemotion", {
      interval: 16,
      rotationRate: { alpha: 0, beta: 0, gamma: 28 },
      acceleration: { x: 0, y: 0, z: 0 },
    });
  }
  await settle();
  assert.ok(stateRequests(harness).some((request) => request.mouse.dx < 0), "positive gamma rotation should move the cursor left after reversing horizontal direction");
  assert.ok(stateRequests(harness).some((request) => request.mouse.dx <= -10), "accelerated gyro movement should feel responsive at default sensitivity");

  for (let i = 0; i < 40; i += 1) {
    harness.dispatchWindow("devicemotion", {
      interval: 16,
      rotationRate: { alpha: 28, beta: 0, gamma: 0 },
      acceleration: { x: 0, y: 0, z: 0 },
    });
  }
  await settle();
  assert.ok(stateRequests(harness).some((request) => request.mouse.dy < 0), "vertical pitch must retain its existing alpha axis and move the cursor up");

  harness.elements.get("airMouseSensitivity").value = "50";
  harness.elements.get("airMouseSensitivity").dispatch("input");
  assert.equal(JSON.parse(harness.preferenceValues.get("ib.web.preferences")).airMouseSensitivity, 5);
  assert.equal(harness.elements.get("airMouseSensitivityValue").textContent, "5.0×");

  harness.elements.get("airMouseToggle").dispatch("click");
  assert.equal(harness.elements.get("airMouseToggle").getAttribute("aria-pressed"), "false");
  assert.equal(harness.touchpad.classList.contains("air-mouse-active"), false);
});


test("Air Mouse disables automatically when switching to gamepad output", async () => {
  const harness = createHarness();
  await settle();
  harness.mouseTab.dispatch("click");
  harness.elements.get("airMouseToggle").dispatch("click");
  assert.equal(harness.elements.get("airMouseToggle").getAttribute("aria-pressed"), "true");

  harness.elements.get("mouseMode").dispatch("click");
  assert.equal(harness.elements.get("airMouseToggle").getAttribute("aria-pressed"), "false");
});


test("web companion navigation and controls use reduced-motion-aware animations", () => {
  assert.match(appCss, /\.tab\.active\s*\{[^}]*animation:\s*vpad-tab-select/s);
  assert.match(appCss, /\.view\.active\s*\{[^}]*animation:\s*vpad-view-enter/s);
  assert.match(appCss, /vpad-card-enter/);
  assert.match(appCss, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  assert.match(appCss, /transition-duration:\s*\.01ms\s*!important/);
  assert.match(appCss, /animation-duration:\s*\.01ms\s*!important/);
});


test("Shooter preset turns L2/R2 into digital hold controls and persists", async () => {
  const harness = createHarness({ preferences: { preset: "shooter" } });
  await settle();

  assert.equal(harness.elements.get("shooter").classList.contains("active"), true);
  assert.equal(harness.elements.get("controller").classList.contains("preset-shooter"), true);
  assert.equal(harness.elements.get("leftTriggerHint").textContent, "AIM");
  assert.equal(harness.elements.get("rightTriggerHint").textContent, "FIRE");

  harness.elements.get("rightTriggerDigital").dispatch("pointerdown", { pointerId: 71 });
  await settle();
  assert.equal(stateRequests(harness).at(-1).analog.R2, 255);
  assert.equal(harness.elements.get("rightTriggerDigital").getAttribute("aria-pressed"), "true");

  harness.elements.get("rightTriggerDigital").dispatch("pointerup", { pointerId: 71 });
  await settle();
  assert.equal(stateRequests(harness).at(-1).analog.R2, 0);
  assert.equal(harness.elements.get("rightTriggerDigital").getAttribute("aria-pressed"), "false");
  assert.equal(JSON.parse(harness.preferenceValues.get("ib.web.preferences")).preset, "shooter");
});

test("web companion keeps ABXY positions stable and exposes the Reymit support link", () => {
  assert.match(appCss, /\.faces \.face|\.faces\s*\{[^}]*display:grid/s);
  assert.match(appCss, /\.faces \.face\.y\s*\{grid-column:2;grid-row:1\}/);
  assert.match(appCss, /\.faces \.face\.x\s*\{grid-column:1;grid-row:2\}/);
  assert.match(appCss, /\.faces \.face\.b\s*\{grid-column:3;grid-row:2\}/);
  assert.match(appCss, /\.faces \.face\.a\s*\{grid-column:2;grid-row:3\}/);
  assert.match(appHtml, /href="https:\/\/reymit\.ir\/arvinnotdev"/);
  assert.match(appHtml, /Buy me a coffee/);
});
