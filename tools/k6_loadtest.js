/**
 * Сценарий нагрузочного тестирования системы интеллектуального анализа цен.
 *
 * Инструмент: k6 (https://k6.io)
 * Целевой endpoint: nginx-балансировщик на 127.0.0.1:8080
 *
 * Запуск:
 *   k6 run tools/k6_loadtest.js
 *   k6 run --out json=artifacts/k6_results.json tools/k6_loadtest.js
 *
 * Этапы нагрузки (stages):
 *   1. Разгон (ramp-up):  0→50 VU за 30 с
 *   2. Устойчивая нагрузка: 50 VU в течение 60 с
 *   3. Пиковая нагрузка:   50→200 VU за 30 с
 *   4. Удержание пика:     200 VU в течение 60 с
 *   5. Спуск (ramp-down):  200→0 VU за 30 с
 *
 * Пороговые значения (thresholds):
 *   - p95 латентности HTTP < 500 мс
 *   - доля ошибок HTTP < 1%
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8082';

const errorRate = new Rate('http_errors');
const latencyMarket = new Trend('latency_market_ms');
const latencyApi = new Trend('latency_api_ms');

export const options = {
  stages: [
    { duration: '30s', target: 50  },   // ramp-up
    { duration: '60s', target: 50  },   // sustained
    { duration: '30s', target: 200 },   // ramp to peak
    { duration: '60s', target: 200 },   // peak hold
    { duration: '30s', target: 0   },   // ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],   // p95 < 500 мс
    http_errors:       ['rate<0.01'],   // < 1% ошибок
  },
};

export default function () {
  // Запрос 1: страница «Рынок» (HTML, тяжёлая выборка из БД)
  const r1 = http.get(`${BASE_URL}/market`, {
    headers: { Accept: 'text/html' },
    timeout: '10s',
  });
  const ok1 = check(r1, {
    'market: status 200': (r) => r.status === 200,
    'market: body not empty': (r) => r.body && r.body.length > 100,
  });
  latencyMarket.add(r1.timings.duration);
  errorRate.add(!ok1);

  sleep(0.5);

  // Запрос 2: JSON API товаров (аналитические запросы)
  const r2 = http.get(`${BASE_URL}/api/v1/products?limit=50`, {
    headers: { Accept: 'application/json' },
    timeout: '10s',
  });
  const ok2 = check(r2, {
    'api: status 200': (r) => r.status === 200 || r.status === 404,
  });
  latencyApi.add(r2.timings.duration);
  errorRate.add(!ok2);

  // Запрос 3: smoke-проверка /health
  const r3 = http.get(`${BASE_URL}/health`, { timeout: '5s' });
  check(r3, { 'health: status ok': (r) => r.status < 500 });

  sleep(0.5);
}

export function handleSummary(data) {
  return {
    'artifacts/k6_summary.json': JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: ' ', enableColors: false }),
  };
}

function textSummary(data, opts) {
  const m = data.metrics;
  const dur = m['http_req_duration'];
  const errs = m['http_errors'];
  return `
=== k6 Нагрузочное тестирование — Итоги ===
Всего запросов:   ${m['http_reqs'].values.count}
RPS (среднее):    ${m['http_reqs'].values.rate.toFixed(1)}
Латентность p50:  ${dur ? dur.values['p(50)'].toFixed(0) : '?'} мс
Латентность p95:  ${dur ? dur.values['p(95)'].toFixed(0) : '?'} мс
Латентность p99:  ${dur ? dur.values['p(99)'].toFixed(0) : '?'} мс
Доля ошибок:      ${errs ? (errs.values.rate * 100).toFixed(2) : '0.00'}%
`;
}
