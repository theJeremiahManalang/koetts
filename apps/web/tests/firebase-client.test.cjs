const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");
const compiled = ts.transpileModule(fs.readFileSync(require.resolve("../features/identity/firebase-client.ts"), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;

function load(env = {}) {
  const api = {};
  const apps = [];
  const modules = {
    "firebase/app": {
      getApps: () => apps,
      getApp: () => apps[0],
      initializeApp: config => { const app = { config }; apps.push(app); return app; },
    },
    "firebase/auth": { getAuth: app => app },
  };
  new Function("exports", "require", "process", compiled)(api, name => modules[name], { env });
  return { ...api, apps };
}

test("missing Firebase config fails before initializing an app", () => {
  const api = load();
  assert.throws(() => api.getFirebaseAuth(), /not configured/);
  assert.equal(api.apps.length, 0);
});

test("configured Firebase app is reused across calls", () => {
  const api = load({ NEXT_PUBLIC_FIREBASE_API_KEY: "public-key", NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: "example.firebaseapp.com", NEXT_PUBLIC_FIREBASE_PROJECT_ID: "example", NEXT_PUBLIC_FIREBASE_APP_ID: "app-id", GEMINI_API_KEY: "private-server-key" });
  const first = api.getFirebaseAuth();
  assert.equal(api.getFirebaseAuth(), first);
  assert.equal(api.apps.length, 1);
  assert.equal(JSON.stringify(first).includes("private-server-key"), false);
});

test("Google errors provide recoverable instructions without exposing raw provider errors", () => {
  const api = load();
  assert.match(api.authErrorMessage({ code: "auth/popup-blocked" }), /Allow popups/);
  assert.match(api.authErrorMessage({ code: "auth/popup-closed-by-user" }), /cancelled/);
  assert.match(api.authErrorMessage({ code: "auth/network-request-failed" }), /internet connection/);
  assert.match(api.authErrorMessage({ code: "auth/unauthorized-domain" }), /not authorized/);
  assert.equal(api.authErrorMessage({ code: "auth/unknown", message: "sensitive-provider-details" }).includes("sensitive"), false);
});
