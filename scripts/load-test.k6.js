// k6 load test for Helm API.
//
// Run from a network-close VPS:
//
//   k6 run -e BASE_URL=https://api.helm.app -e JWT=<supabase access token> \
//          scripts/load-test.k6.js
//
// Defaults target a 5-minute ramp to 100 concurrent VUs, mostly hitting
// /health + /ready (cheap), with a 10% slice doing /users/me/today
// (DB-backed). /chat is intentionally excluded — it costs Anthropic tokens
// per request and would dominate the bill for a load test.
//
// SLO targets that should hold:
//   - /health p99 < 100ms
//   - /ready  p99 < 300ms (one DB roundtrip)
//   - /today  p99 < 800ms (a handful of DB queries)
//   - error_rate < 1%
//
// k6 install:
//   brew install k6        # macOS
//   apt-get install k6     # Debian/Ubuntu (after the k6 apt repo)

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const JWT = __ENV.JWT || "";
const AUTH_HEADERS = JWT ? { Authorization: `Bearer ${JWT}` } : {};

const errorRate = new Rate("errors");
const todayLatency = new Trend("today_latency_ms", true);

export const options = {
  stages: [
    { duration: "1m", target: 25 }, // ramp to 25 VUs
    { duration: "2m", target: 100 }, // ramp to 100 VUs
    { duration: "2m", target: 100 }, // hold at 100 VUs
    { duration: "30s", target: 0 }, // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(99)<800"],
    "http_req_duration{endpoint:health}": ["p(99)<100"],
    "http_req_duration{endpoint:ready}": ["p(99)<300"],
    "http_req_duration{endpoint:today}": ["p(99)<800"],
    errors: ["rate<0.01"],
  },
};

export default function () {
  // 80% — cheap liveness probes (matches load-balancer cadence + browser polls)
  const h = http.get(`${BASE_URL}/health`, { tags: { endpoint: "health" } });
  check(h, { "health 200": (r) => r.status === 200 }) || errorRate.add(1);

  // Deterministic 10/10/80 split via __ITER so p99 deltas across runs
  // reflect server changes, not RNG sampling variance.
  const slot = __ITER % 10;

  if (slot === 0) {
    const r = http.get(`${BASE_URL}/ready`, { tags: { endpoint: "ready" } });
    check(r, { "ready 200": (x) => x.status === 200 }) || errorRate.add(1);
  }

  if (slot === 1 && JWT) {
    const t = http.get(`${BASE_URL}/users/me/today`, {
      headers: AUTH_HEADERS,
      tags: { endpoint: "today" },
    });
    todayLatency.add(t.timings.duration);
    check(t, { "today 200": (x) => x.status === 200 }) || errorRate.add(1);
  }

  sleep(1);
}
