// k6 matchday load test — simulates a World Cup match traffic profile.
// Run: k6 run --vus 300 --duration 5m k6/matchday_load.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8088";

const errorRate = new Rate("errors");
const healthLatency = new Trend("health_latency", true);
const sloLatency = new Trend("slo_latency", true);
const incidentLatency = new Trend("incident_latency", true);

export const options = {
  scenarios: {
    matchday: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 100 }, // pre-match
        { duration: "5m", target: 300 }, // kickoff surge
        { duration: "10m", target: 300 }, // sustained
        { duration: "3m", target: 0 },   // cooldown
      ],
    },
  },
  thresholds: {
    health_latency: ["p(95)<50"],
    slo_latency: ["p(95)<200"],
    incident_latency: ["p(95)<200"],
    errors: ["rate<0.01"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  let r = http.get(`${BASE_URL}/api/v1/health`);
  healthLatency.add(r.timings.duration);
  errorRate.add(r.status !== 200);
  check(r, { "health 200": (r) => r.status === 200 });

  r = http.get(`${BASE_URL}/api/v1/slo`);
  sloLatency.add(r.timings.duration);
  errorRate.add(r.status !== 200 && r.status !== 401);
  check(r, { "slo ok": (r) => [200, 401].includes(r.status) });

  r = http.get(`${BASE_URL}/api/v1/incidents?limit=20`);
  incidentLatency.add(r.timings.duration);
  errorRate.add(r.status !== 200 && r.status !== 401);
  check(r, { "incident ok": (r) => [200, 401].includes(r.status) });

  r = http.get(`${BASE_URL}/api/v1/problems`);
  errorRate.add(r.status >= 500);

  sleep(0.1 + Math.random() * 0.2);
}

export function handleSummary(data) {
  return { "k6/results_summary.json": JSON.stringify(data, null, 2) };
}
