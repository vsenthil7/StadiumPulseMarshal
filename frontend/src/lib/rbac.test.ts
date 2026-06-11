// Runnable unit test (node:test) for the frontend RBAC mirror. Proves the role
// ranking and the key permission separations match backend/app/rbac/policy.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ROLE_RANK, permissionsFor, roleHas, roleMeets } from './rbac.ts';

test('role ranking viewer<operator<responder<admin', () => {
  const order = ['viewer', 'operator', 'responder', 'admin'] as const;
  for (let i = 1; i < order.length; i++) {
    assert.ok(ROLE_RANK[order[i]] > ROLE_RANK[order[i - 1]]);
  }
});

test('viewer is read-only (no incident:write, no approve)', () => {
  assert.ok(roleHas('viewer', 'incident:read'));
  assert.ok(roleHas('viewer', 'slo:read'));
  assert.ok(!roleHas('viewer', 'incident:write'));
  assert.ok(!roleHas('viewer', 'remediation:approve'));
});

test('operator can write + scenario but cannot approve remediations', () => {
  assert.ok(roleHas('operator', 'incident:write'));
  assert.ok(roleHas('operator', 'scenario:write'));
  assert.ok(!roleHas('operator', 'remediation:approve'));
});

test('responder adds remediation:approve over operator', () => {
  assert.ok(roleHas('responder', 'remediation:approve'));
  assert.ok(roleHas('responder', 'incident:write'));
  assert.ok(!roleHas('responder', 'webhook:admin'));
  assert.ok(!roleHas('responder', 'settings:write'));
});

test('admin has everything incl. webhook:admin + settings:write', () => {
  assert.ok(roleHas('admin', 'webhook:admin'));
  assert.ok(roleHas('admin', 'settings:write'));
  assert.ok(roleHas('admin', 'remediation:approve'));
});

test('roleMeets gate matches ranking', () => {
  assert.ok(roleMeets('responder', 'operator'));
  assert.ok(!roleMeets('viewer', 'operator'));
  assert.ok(roleMeets('admin', 'admin'));
});

test('permissionsFor non-empty for every role', () => {
  for (const r of ['viewer', 'operator', 'responder', 'admin'] as const) {
    assert.ok(permissionsFor(r).size > 0);
  }
});
