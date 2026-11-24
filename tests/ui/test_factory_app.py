"""HTTP and JS runtime dashboard contracts; no Playwright dependency in lockfile."""
import json
import re
import shutil
import subprocess
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

from healthvideo.approver_pin import set_pin
from healthvideo.workflows import dashboard, factory
from tests.helpers import create_v2_project_fixture

DASHBOARD_HTML = Path(__file__).resolve().parents[2] / 'src/healthvideo/workflows/dashboard.html'


def _extract_dashboard_scripts() -> list[str]:
    html = DASHBOARD_HTML.read_text(encoding='utf-8')
    return re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.DOTALL)


def _run_workshop_js(test_body: str, *, pre_storage: dict[str, str] | None = None) -> None:
    node = shutil.which('node')
    assert node is not None, 'Node.js is required to run dashboard UI runtime tests'
    scripts = _extract_dashboard_scripts()
    assert len(scripts) >= 1
    instrumented_script = (
        scripts[0]
        + '\n;globalThis.__pyh = {'
        ' wsNormalizeWorkState, wsResolveRoleState, wsResolveMachineState,'
        ' wsSvgSig, renderWorkshop, refresh, openWorkshopPopover,'
        ' renderWorkshopPopoverContent,'
        ' getState: () => ({'
        '   wsOffline, wsPageHidden, wsInView, wsMotionEnabled,'
        '   wsHasActiveExecution, wsSelectedId, companyData, overviewData, state'
        ' }),'
        ' setState: (patch) => {'
        '   if ("companyData" in patch) companyData = patch.companyData;'
        '   if ("overviewData" in patch) overviewData = patch.overviewData;'
        '   if ("state" in patch) state = patch.state;'
        '   if ("wsOffline" in patch) wsOffline = patch.wsOffline;'
        ' },'
        ' tabVideo, renderPv, wireVideoNle, pvBuildTimelineModel,'
        ' WS_AVATARS, wsIsoSvg, wsPersonSvg, wsPropSvg, wsGateEmptySvg,'
        ' pvFormatTc, pvParseJumpInput, stopPvVideoRuntime,'
        ' updateChatContext, closeProduct, postJson,'
        ' getVideoState: () => ({ pv, pvTab, chatCtx, pvVideoState }),'
        ' setVideoState: (patch) => {'
        '   if ("pv" in patch) pv = patch.pv;'
        '   if ("pvTab" in patch) pvTab = patch.pvTab;'
        ' },'
        '};'
    )
    runner = r'''
const fs = require('fs');
const vm = require('vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));

const VOID_TAGS = new Set([
  'area','base','br','col','embed','hr','img','input','link','meta',
  'param','source','track','wbr','path','rect','circle','ellipse',
  'line','polygon','polyline','stop','animate','animatetransform',
]);

function kebab(s) {
  return s.replace(/[A-Z]/g, m => '-' + m.toLowerCase());
}
function camel(s) {
  return s.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
}

function parseAttrs(raw) {
  const attrs = {};
  const re = /([a-zA-Z0-9_:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>/]+)))?/g;
  let m;
  while ((m = re.exec(raw)) !== null) {
    const key = m[1];
    if (key === '/') continue;
    const val = m[2] ?? m[3] ?? m[4] ?? '';
    attrs[key] = val;
  }
  return attrs;
}

function parseHtml(html, doc) {
  const root = doc.createElement('fragment');
  const stack = [root];
  const tagRe = /<!--[\s\S]*?-->|<\/([a-zA-Z0-9_-]+)\s*>|<([a-zA-Z0-9_-]+)([^>]*)>|([^<]+)/g;
  let m;
  while ((m = tagRe.exec(String(html || ''))) !== null) {
    const top = stack[stack.length - 1];
    if (m[1]) {
      const closeName = m[1].toUpperCase();
      for (let i = stack.length - 1; i > 0; i--) {
        if (stack[i].tagName === closeName) {
          stack.length = i;
          break;
        }
      }
    } else if (m[2]) {
      const tag = m[2];
      const rawAttrs = m[3] || '';
      const selfClosing = rawAttrs.trimEnd().endsWith('/') || VOID_TAGS.has(tag.toLowerCase());
      const el = doc.createElement(tag);
      const attrs = parseAttrs(rawAttrs.replace(/\/\s*$/, ''));
      for (const [k, v] of Object.entries(attrs)) {
        el.attrs[k] = v;
      }
      top.appendChild(el);
      if (!selfClosing) stack.push(el);
    } else if (m[4]) {
      top._text += m[4];
    }
  }
  return [...root.children];
}

function matchSingleSelector(el, sel) {
  const s = sel.trim();
  if (!s) return false;
  let rem = s;
  const tagMatch = rem.match(/^([a-zA-Z0-9_-]+)/);
  if (tagMatch) {
    if (el.tagName !== tagMatch[1].toUpperCase()) return false;
    rem = rem.slice(tagMatch[1].length);
  }
  while (rem.length) {
    if (rem[0] === '#') {
      const m = rem.match(/^#([a-zA-Z0-9_-]+)/);
      if (!m || el.attrs.id !== m[1]) return false;
      rem = rem.slice(m[0].length);
    } else if (rem[0] === '.') {
      const m = rem.match(/^\.([a-zA-Z0-9_-]+)/);
      if (!m) return false;
      const cls = String(el.attrs['class'] || '').split(/\s+/).filter(Boolean);
      if (!cls.includes(m[1])) return false;
      rem = rem.slice(m[0].length);
    } else if (rem[0] === '[') {
      const m = rem.match(/^\[([a-zA-Z0-9_-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\]]*)))?\]/);
      if (!m) return false;
      const attrName = m[1];
      if (!(attrName in el.attrs)) return false;
      const expected = m[2] ?? m[3] ?? m[4];
      if (expected !== undefined && el.attrs[attrName] !== expected) return false;
      rem = rem.slice(m[0].length);
    } else {
      return false;
    }
  }
  return true;
}

function matchSelector(el, selector) {
  for (const branch of selector.split(',')) {
    const parts = branch.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) continue;
    if (!matchSingleSelector(el, parts[parts.length - 1])) continue;
    let cur = el.parentNode;
    let idx = parts.length - 2;
    while (idx >= 0 && cur) {
      if (matchSingleSelector(cur, parts[idx])) idx--;
      cur = cur.parentNode;
    }
    if (idx < 0) return true;
  }
  return false;
}

class FakeElement {
  constructor(tag, doc, id = '') {
    this.tagName = String(tag || 'div').toUpperCase();
    this._doc = doc;
    this.attrs = {};
    if (id) this.attrs.id = id;
    this.children = [];
    this.parentNode = null;
    this._text = '';
    this._innerHtml = '';
    this._innerHtmlWrites = 0;
    this.style = {};
    this.scrollTop = 0;
    this.scrollHeight = 120;
    this.clientHeight = 120;
    this.disabled = false;
    this.value = '';
    this.elements = new Proxy({}, { get: () => ({ value: '', focus() {} }) });
    const self = this;
    this.dataset = new Proxy({}, {
      get(_, prop) {
        return self.attrs['data-' + kebab(String(prop))];
      },
      set(_, prop, val) {
        self.attrs['data-' + kebab(String(prop))] = String(val);
        return true;
      },
    });
    this.classList = {
      add(...names) {
        const cur = new Set(String(self.attrs['class'] || '').split(/\s+/).filter(Boolean));
        names.forEach(n => cur.add(n));
        self.attrs['class'] = [...cur].join(' ');
      },
      remove(...names) {
        const cur = new Set(String(self.attrs['class'] || '').split(/\s+/).filter(Boolean));
        names.forEach(n => cur.delete(n));
        self.attrs['class'] = [...cur].join(' ');
      },
      toggle(name, force) {
        const has = this.contains(name);
        const next = force === undefined ? !has : Boolean(force);
        if (next) this.add(name);
        else this.remove(name);
        return next;
      },
      contains(name) {
        return String(self.attrs['class'] || '').split(/\s+/).filter(Boolean).includes(name);
      },
    };
  }
  get id() { return this.attrs.id || ''; }
  set id(v) { this.attrs.id = String(v); }
  get className() { return this.attrs['class'] || ''; }
  set className(v) { this.attrs['class'] = String(v); }
  get hidden() { return 'hidden' in this.attrs; }
  set hidden(v) {
    if (v) this.attrs.hidden = '';
    else delete this.attrs.hidden;
  }
  get firstChild() { return this.children[0] || null; }
  get textContent() {
    if (!this.children.length) return this._text;
    return this._text + this.children.map(c => c.textContent).join('');
  }
  set textContent(v) {
    this.children = [];
    this._text = String(v ?? '');
  }
  get innerHTML() {
    const ser = (n) => {
      const a = Object.entries(n.attrs).map(([k, v]) => (v === '' ? k : `${k}="${v}"`)).join(' ');
      const tag = n.tagName.toLowerCase();
      const open = a ? `<${tag} ${a}>` : `<${tag}>`;
      const body = n.children.length ? n.children.map(ser).join('') : (n._text || '');
      return `${open}${body}</${tag}>`;
    };
    if (this.children.length) return this.children.map(ser).join('');
    return this._innerHtml || this._text;
  }
  set innerHTML(html) {
    this._innerHtmlWrites++;
    this._innerHtml = String(html ?? '');
    this._text = '';
    this.children = [];
    for (const child of parseHtml(this._innerHtml, this._doc)) {
      this.appendChild(child);
    }
  }
  setAttribute(k, v) { this.attrs[String(k)] = String(v); }
  getAttribute(k) { return (String(k) in this.attrs) ? this.attrs[String(k)] : null; }
  hasAttribute(k) { return String(k) in this.attrs; }
  removeAttribute(k) { delete this.attrs[String(k)]; }
  appendChild(node) {
    if (node.parentNode) node.remove();
    node.parentNode = this;
    this.children.push(node);
    return node;
  }
  insertBefore(node, ref) {
    if (node.parentNode) node.remove();
    node.parentNode = this;
    if (!ref) {
      this.children.push(node);
      return node;
    }
    const idx = this.children.indexOf(ref);
    if (idx === -1) this.children.push(node);
    else this.children.splice(idx, 0, node);
    return node;
  }
  remove() {
    if (!this.parentNode) return;
    const idx = this.parentNode.children.indexOf(this);
    if (idx >= 0) this.parentNode.children.splice(idx, 1);
    this.parentNode = null;
  }
  contains(target) {
    let cur = target;
    while (cur) {
      if (cur === this) return true;
      cur = cur.parentNode;
    }
    return false;
  }
  closest(sel) {
    let cur = this;
    while (cur) {
      if (matchSelector(cur, sel)) return cur;
      cur = cur.parentNode;
    }
    return null;
  }
  querySelectorAll(sel) {
    const out = [];
    const walk = (node) => {
      for (const ch of node.children) {
        if (matchSelector(ch, sel)) out.push(ch);
        walk(ch);
      }
    };
    walk(this);
    return out;
  }
  querySelector(sel) {
    return this.querySelectorAll(sel)[0] || null;
  }
  focus() {}
  pause() {}
  scrollIntoView() {}
  addEventListener() {}
  getBoundingClientRect() {
    return { left: 20, top: 20, right: 200, bottom: 180, width: 180, height: 160 };
  }
}

const byId = new Map();
const listeners = {};
const doc = {
  hidden: false,
  title: '',
  createElement(tag) { return new FakeElement(tag, doc); },
  getElementById(id) {
    if (!byId.has(id)) {
      const el = new FakeElement('div', doc, id);
      byId.set(id, el);
    }
    return byId.get(id);
  },
  querySelectorAll(sel) {
    const out = [];
    for (const el of byId.values()) {
      if (matchSelector(el, sel)) out.push(el);
      out.push(...el.querySelectorAll(sel));
    }
    return [...new Set(out)];
  },
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
  addEventListener(ev, fn) {
    if (!listeners[ev]) listeners[ev] = [];
    listeners[ev].push(fn);
  },
  dispatch(ev) {
    for (const fn of (listeners[ev] || [])) fn({ type: ev });
  },
};
doc.documentElement = doc.getElementById('__html__');
doc.body = doc.getElementById('__body__');

// Build workshop DOM skeleton matching dashboard.html
const wsEl = doc.getElementById('workshop');
wsEl.dataset.motion = 'on';
wsEl.dataset.paused = 'false';
wsEl.dataset.liveFlow = 'false';
const btnMotion = doc.getElementById('btn-ws-motion');
btnMotion.innerHTML = '<span class="ws-motion-label">Hoạt cảnh: Bật</span>';
wsEl.appendChild(btnMotion);
wsEl.appendChild(doc.getElementById('ws-counters'));
wsEl.appendChild(doc.getElementById('ws-row-1'));
wsEl.appendChild(doc.getElementById('ws-row-2'));

const wsPop = doc.getElementById('ws-popover');
wsPop.hidden = true;
wsPop.appendChild(doc.getElementById('ws-pop-title'));
wsPop.appendChild(doc.getElementById('ws-pop-meta'));
wsPop.appendChild(doc.getElementById('ws-pop-close'));
wsPop.appendChild(doc.getElementById('ws-pop-body'));

const storageMap = new Map(Object.entries(payload.preStorage || {}));
const localStorage = {
  getItem(k) { return storageMap.has(String(k)) ? storageMap.get(String(k)) : null; },
  setItem(k, v) { storageMap.set(String(k), String(v)); },
  removeItem(k) { storageMap.delete(String(k)); },
};

const observers = [];
class FakeIntersectionObserver {
  constructor(cb) {
    this.cb = cb;
    this.observed = [];
    observers.push(this);
  }
  observe(el) { this.observed.push(el); }
  trigger(entries) { this.cb(entries, this); }
}

let fetchHandler = (url) => {
  if (url.startsWith('/api/status')) {
    return {
      ok: true, status: 200,
      async json() {
        return {
          factory: { running: false, pid: null },
          waiting: 0,
          projects: [],
          stages: ['1','2','3','4','5','6','7'],
          log: [],
          agents: [],
          now: '2026-11-14T10:00:00Z',
          standards: 0,
        };
      },
    };
  }
  if (url.startsWith('/api/company')) {
    return {
      ok: true, status: 200,
      async json() { return { roles: [], production_running: [], production: { work_state: 'idle' } }; },
    };
  }
  if (url.startsWith('/api/overview')) {
    return { ok: true, status: 200, async json() { return { tiles: {}, projects: [], decisions: [], resting: [] }; } };
  }
  if (url.startsWith('/api/activity')) {
    return { ok: true, status: 200, async json() { return { items: [] }; } };
  }
  if (url.startsWith('/api/progress')) {
    return { ok: true, status: 200, async json() { return { phases: [], doing: [], total: 0, done: 0 }; } };
  }
  if (url.startsWith('/api/chat')) {
    return { ok: true, status: 200, async json() { return { messages: [] }; } };
  }
  return { ok: true, status: 200, async json() { return {}; } };
};

let fetchCalls = 0;
const win = {
  innerWidth: 1280,
  innerHeight: 800,
  matchMedia: () => ({ matches: false }),
  addEventListener() {},
};

const sandbox = {
  window: win,
  document: doc,
  localStorage,
  IntersectionObserver: FakeIntersectionObserver,
  CSS: { escape: (s) => String(s) },
  fetch: async (url, opts) => {
    fetchCalls++;
    return fetchHandler(String(url), opts);
  },
  setInterval: () => 1,
  setTimeout: () => 1,
  clearTimeout: () => {},
  URL: require('node:url').URL,
  URLSearchParams,
  Date,
  Math,
  Map,
  Set,
  Array,
  Object,
  JSON,
  Promise,
  Error,
  Number,
  String,
  Boolean,
  encodeURIComponent,
  confirm: () => true,
  FormData: class { constructor() {} get() { return ''; } },
};
sandbox.globalThis = sandbox;

vm.runInNewContext(payload.script, sandbox);

const AsyncFn = Object.getPrototypeOf(async function(){}).constructor;
const fn = new AsyncFn(
  'ctx',
  payload.test
);
fn({
  pyh: sandbox.__pyh,
  doc,
  localStorage,
  observers,
  setFetchHandler(h) { fetchHandler = h; },
  getFetchCalls() { return fetchCalls; },
  resetFetchCalls() { fetchCalls = 0; },
}).then(
  () => process.exit(0),
  (err) => { console.error(err && err.stack ? err.stack : err); process.exit(1); }
);
'''
    payload = json.dumps({
        'script': instrumented_script,
        'test': test_body,
        'preStorage': pre_storage or {},
    })
    res = subprocess.run(
        [node, '-e', runner],
        input=payload,
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=20,
        check=False,
    )
    assert res.returncode == 0, f'Node harness failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}'


@pytest.fixture
def app(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Unexpected background factory start')

    monkeypatch.setattr(factory, 'start_background', forbidden)
    pin = tmp_path / 'config/approver-pin.json'
    set_pin('918273', path=pin)
    monkeypatch.setattr(dashboard, 'pin_path', lambda: pin)
    server = dashboard.DashboardServer(tmp_path, 0, token='fixture-token', agents=list)
    create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    queue = tmp_path / 'topics/queue.yaml'
    queue.parent.mkdir(parents=True)
    queue.write_text('version: 1\nentries: []\n', encoding='utf-8')
    # Codes are allocated once and persisted; allocate before the snapshot so reads stay write-free.
    from healthvideo.project_codes import project_codes
    project_codes(tmp_path)
    server.protected_bytes = {p: p.read_bytes() for folder in ('projects', 'topics')
                              for p in (tmp_path / folder).rglob('*') if p.is_file()}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    assert all(path.read_bytes() == before for path, before in server.protected_bytes.items())
    assert {p for folder in ('projects', 'topics') for p in (tmp_path / folder).rglob('*') if p.is_file()} == set(server.protected_bytes)


def request(app, path, body=None, *, token='fixture-token', host=None):
    conn = HTTPConnection('127.0.0.1', app.server_address[1], timeout=20)
    headers = {'X-Dashboard-Token': token, 'Content-Type': 'application/json'}
    if host:
        headers['Host'] = host
    conn.request('GET' if body is None else 'POST', path,
                 body=None if body is None else json.dumps(body), headers=headers)
    response = conn.getresponse()
    raw = response.read()
    conn.close()
    if response.getheader('Content-Type', '').startswith('application/json'):
        return response.status, json.loads(raw)
    return response.status, raw


def test_status_and_start_button_have_no_acceptance_gate(app):
    status, page = request(app, '/')
    assert status == 200
    assert b'id="factory-acceptance"' not in page
    status, data = request(app, '/api/status')
    assert status == 200, data
    assert 'can_start' not in data['factory']
    assert 'id="btn-start" type="button" title="Bật xưởng sản xuất"'.encode() in page


def test_gate_decide_five_attempt_lockout(app):
    path, project = next(iter(dashboard.factory.projects(app.root)))
    gate_url = f'/api/project/{path.name}/decide'
    gate = {'revision': project.active_revision, 'action': 'approve', 'reviewer': 'Fixture', 'pin': '000000'}
    for _ in range(5):
        assert request(app, gate_url, gate)[0] == 403
    assert app.limiter.locked_until > 0
    assert request(app, gate_url, {**gate, 'pin': '918273'})[0] == 403


def test_workshop_company_contract_and_motion_controls_are_read_only(app):
    status, raw_page = request(app, '/')
    assert status == 200
    page = raw_page.decode('utf-8')
    assert 'id="btn-ws-motion"' in page
    assert 'prefers-reduced-motion: reduce' in page
    assert 'Chưa xác minh' in page
    assert 'Đang nghỉ' in page

    status, company = request(app, '/api/company')
    assert status == 200, company
    assert company['production_running'] == []
    assert company['production']['work_state'] == 'idle'
    for role in company['roles']:
        assert role['work_state'] == 'idle'
        assert role['work_label']

    status, ov = request(app, '/api/overview')
    assert status == 200, ov
    assert ov['tiles']['running'] == 0
    assert ov['tiles']['waiting_doctor'] == 1


def test_workshop_html_contract_and_responsive_styles():
    html = DASHBOARD_HTML.read_text(encoding='utf-8')
    assert html.count('https://fonts.googleapis.com') <= 2
    assert 'cdn.' not in html and 'unpkg' not in html and 'jsdelivr' not in html
    assert 'id="btn-ws-motion"' in html
    assert "'pyh-ws-motion'" in html
    assert 'data-motion="on"' in html
    assert 'data-live-flow="false"' in html
    assert 'visibilitychange' in html
    assert 'IntersectionObserver' in html
    assert 'prefers-reduced-motion: reduce' in html

    # All 13 role action classes must exist in CSS and JS
    for cls in (
        'ws-act-researcher',
        'ws-act-scout',
        'ws-act-medical',
        'ws-act-writer',
        'ws-act-storyboard',
        'ws-act-voice',
        'ws-act-critic',
        'ws-act-art',
        'ws-act-editor',
        'ws-act-copywriter',
        'ws-act-shorts',
        'ws-act-coordinator',
        'ws-act-analyst',
    ):
        assert cls in html

    # All 7 distinct Vietnamese state labels
    for label in (
        'Đang làm',
        'Đang nghỉ',
        'Chờ duyệt',
        'Chờ model',
        'Chờ thử lại',
        'Dừng do lỗi',
        'Chưa xác minh',
    ):
        assert label in html

    # Live flow belt animation must be gated on data-live-flow="true"
    assert '.ws-turn-track::after{' in html
    assert 'animation:none' in html
    assert '#workshop[data-live-flow="true"] .ws-turn-track::after{' in html

    # Banned render_machine heuristic must be gone; doc copy retained
    assert (
        "p => (p.state === 'medically_approved' || p.state === 'production_in_progress') && !p.blocked"
        not in html
    )
    assert 'Máy dựng (xưởng tự chạy)' in html
    assert 'medically_approved' in html
    assert 'production_in_progress' in html

    # Responsive CSS guards for narrow viewports & mobile popover
    assert '@media (max-width: 680px)' in html or '@media (max-width:680px)' in html
    assert '@media (max-width:420px)' in html or '@media (max-width: 420px)' in html
    assert 'overflow-wrap:anywhere' in html or 'overflow-wrap: anywhere' in html
    assert 'max-width:calc(100vw - 24px)' in html or 'max-width: calc(100vw - 24px)' in html


def test_workshop_js_work_state_and_render_machine_contracts():
    _run_workshop_js(r'''
    const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
    const { pyh, doc } = ctx;

    // 1. State normalization & last_error isolation
    assert(pyh.wsNormalizeWorkState('waiting') === 'waiting_gate', 'waiting -> waiting_gate');
    assert(pyh.wsNormalizeWorkState('retrying') === 'waiting_retry', 'retrying -> waiting_retry');
    assert(pyh.wsNormalizeWorkState('waiting_model') === 'waiting_model', 'waiting_model');
    assert(pyh.wsNormalizeWorkState('unknown') === 'unknown', 'unknown');

    assert(
      pyh.wsResolveRoleState({ id: 'scout', work_state: 'idle', last_error: 'Old timeout', running: [] }, true, false) === 'idle',
      'last_error must NOT coerce idle role into error state'
    );
    assert(
      pyh.wsResolveRoleState({ id: 'scout', work_state: 'error', last_error: 'Crash' }, true, false) === 'error',
      'error work_state must resolve to error'
    );
    assert(
      pyh.wsResolveRoleState({ id: 'scout', work_state: 'working' }, true, true) === 'unknown',
      'offline mode must force unknown'
    );

    // 2. render_machine never infers working from project.state alone
    const machineBlocked = pyh.wsResolveMachineState({
      production: { work_state: 'idle', running: [] },
      production_running: [],
    }, false);
    assert(machineBlocked === 'idle', 'render_machine stays idle when no verified production PID');

    const machineWorking = pyh.wsResolveMachineState({
      production: { work_state: 'working', running: [] },
      production_running: [],
    }, false);
    assert(machineWorking === 'working', 'production.work_state === working activates machine');

    const machineWorkingPid = pyh.wsResolveMachineState({
      production: { work_state: 'idle', running: [] },
      production_running: [{ slug: 'hypertension', title: 'Hypertension', duration_s: 12 }],
    }, false);
    assert(machineWorkingPid === 'working', 'non-empty production_running activates machine');

    // 3. Full role rendering: all 13 ws-act-* classes when working; idle has coffee cup & no ws-act-*
    const allRoleIds = [
      'researcher', 'scout', 'medical_expert', 'writer', 'storyboard_director', 'voice_director',
      'script_critic', 'art_director', 'editor', 'product_critic', 'copywriter', 'shorts_producer',
      'coordinator', 'coordinator_senior', 'feedback_analyst',
    ];
    pyh.setState({
      wsOffline: false,
      overviewData: {
        projects: [
          { slug: 'p1', title: 'P1', state: 'medically_approved', blocked: '' },
          { slug: 'p2', title: 'P2', state: 'production_in_progress', blocked: '' },
        ],
      },
      companyData: {
        production: { work_state: 'idle', work_label: 'Đang nghỉ' },
        production_running: [],
        roles: allRoleIds.map((id) => ({
          id,
          short: id,
          name: id,
          work_state: 'working',
          work_label: 'Đang làm',
          running: [{ step: 'draft', step_label: 'Đang xử lý', slug: 'p1', duration_s: 8, cli: 'claude', model: 'm' }],
          recent: [],
          models_used: [],
          configured_models: [],
          steps: [],
          step_labels: ['Xử lý'],
          tier: 'main',
        })),
      },
    });
    pyh.renderWorkshop();

    const machineBtn = doc.querySelector('[data-station-id="render_machine"]');
    assert(machineBtn && machineBtn.classList.contains('is-idle'), 'render_machine must stay is-idle despite medically_approved/production_in_progress');
    assert(!machineBtn.classList.contains('is-working'), 'render_machine must NOT be is-working');

    pyh.openWorkshopPopover('render_machine', machineBtn);
    const popText = doc.getElementById('ws-pop-body').innerHTML;
    assert(popText.includes('medically_approved') && popText.includes('production_in_progress'), 'machine popover must retain pipeline copy');
    assert(doc.getElementById('ws-pop-title').textContent.includes('Máy dựng (xưởng tự chạy)'), 'machine popover title check');

    const expectedActs = [
      'ws-act-researcher', 'ws-act-scout', 'ws-act-medical', 'ws-act-writer',
      'ws-act-storyboard', 'ws-act-voice', 'ws-act-critic',
      'ws-act-art', 'ws-act-editor', 'ws-act-copywriter', 'ws-act-shorts',
      'ws-act-coordinator', 'ws-act-analyst',
    ];
    const stationBtns = doc.querySelectorAll('[data-station-id]');
    for (const act of expectedActs) {
      assert(stationBtns.some((b) => b.classList.contains(act)), 'Missing active role class: ' + act);
    }

    // 4. Verify non-working labels & distinct idle coffee cup vs working pose
    const curComp = pyh.getState().companyData;
    curComp.roles = [
      { id: 'scout', name: 'Scout', work_state: 'idle', work_label: 'Đang nghỉ', last_error: 'Stale error', running: [], recent: [], models_used: [], configured_models: [], steps: [], step_labels: [], tier: 'helper' },
      { id: 'medical_expert', name: 'Med', work_state: 'waiting_model', work_label: 'Chờ model', running: [], recent: [], models_used: [], configured_models: [], steps: [], step_labels: [], tier: 'main' },
      { id: 'writer', name: 'Writer', work_state: 'retrying', work_label: 'Chờ thử lại', running: [], recent: [], models_used: [], configured_models: [], steps: [], step_labels: [], tier: 'main' },
      { id: 'editor', name: 'Editor', work_state: 'error', work_label: 'Dừng do lỗi', running: [], recent: [], models_used: [], configured_models: [], steps: [], step_labels: [], tier: 'main' },
    ];
    pyh.renderWorkshop();

    const scoutBtn = doc.querySelector('[data-station-id="scout"]');
    assert(scoutBtn.classList.contains('is-idle') && !scoutBtn.classList.contains('has-error'), 'scout with last_error must remain is-idle');
    assert(!scoutBtn.classList.contains('ws-act-scout'), 'idle scout must not have ws-act-scout');
    assert(scoutBtn.querySelector('.ws-iso-stage').innerHTML.includes('translate(124,64)'), 'idle station must render coffee cup at (124,64)');
    assert(scoutBtn.textContent.includes('Đang nghỉ'), 'idle station label');

    const medBtn = doc.querySelector('[data-station-id="medical_expert"]');
    assert(medBtn.classList.contains('is-waiting-model') && medBtn.textContent.includes('Chờ model'), 'waiting_model label & class');

    const writerBtn = doc.querySelector('[data-station-id="writer"]');
    assert(writerBtn.classList.contains('is-waiting-retry') && writerBtn.textContent.includes('Chờ thử lại'), 'waiting_retry label & class');

    const editorBtn = doc.querySelector('[data-station-id="editor"]');
    assert(editorBtn.classList.contains('has-error') && editorBtn.textContent.includes('Dừng do lỗi'), 'error label & class');
    ''')


def test_workshop_js_keyed_reconciliation_and_duration_independence():
    _run_workshop_js(r'''
    const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
    const { pyh, doc } = ctx;

    const makeRole = (dur) => ({
      id: 'scout',
      name: 'Scout',
      work_state: 'working',
      work_label: 'Đang làm',
      running: [{ step: 'research', step_label: 'Quét chủ đề', slug: 'sleep-debt', duration_s: dur, cli: 'claude', model: 'm' }],
      recent: [],
      models_used: [],
      configured_models: [],
      steps: ['research'],
      step_labels: ['Quét chủ đề'],
      tier: 'helper',
    });

    const sig3 = pyh.wsSvgSig({ id: 'scout', workState: 'working', actClass: 'ws-act-scout', folders: [{ slug: 'a', tone: 'work' }], running: [{ duration_s: 3 }] });
    const sig15 = pyh.wsSvgSig({ id: 'scout', workState: 'working', actClass: 'ws-act-scout', folders: [{ slug: 'a', tone: 'work' }], running: [{ duration_s: 15 }] });
    assert(sig3 === sig15, 'wsSvgSig must ignore duration_s changes');

    pyh.setState({
      wsOffline: false,
      overviewData: { projects: [{ slug: 'sleep-debt', title: 'Sleep Debt', state: 'in_progress', blocked: '' }] },
      companyData: { production: { work_state: 'idle' }, production_running: [], roles: [makeRole(3)] },
    });
    pyh.renderWorkshop();

    const scoutBtn = doc.querySelector('[data-station-id="scout"]');
    const stageEl = scoutBtn.querySelector('.ws-iso-stage');
    const svgRef = stageEl.firstChild;
    const durEl = scoutBtn.querySelector('[data-ws-dur]');
    assert(durEl.textContent === '3s', 'initial duration badge should be 3s');

    // Open popover to also check popover duration updates without body wipe
    pyh.openWorkshopPopover('scout', scoutBtn);
    const popBody = doc.getElementById('ws-pop-body');
    const popBodyWritesBefore = popBody._innerHtmlWrites;
    const stageWritesBefore = stageEl._innerHtmlWrites;

    // Simulate 3s poll ticks updating duration_s 3 -> 9 -> 15
    for (const nextDur of [9, 15]) {
      pyh.getState().companyData.roles = [makeRole(nextDur)];
      pyh.renderWorkshop();
      assert(doc.querySelector('[data-station-id="scout"]') === scoutBtn, 'button node must be reconciled in-place');
      assert(stageEl.firstChild === svgRef, 'SVG node reference must not be recreated when duration_s changes');
      assert(stageEl._innerHtmlWrites === stageWritesBefore, 'stage innerHTML must not be rewritten on duration tick');
      assert(durEl.textContent === nextDur + 's', 'duration badge should update to ' + nextDur + 's');
    }
    assert(popBody._innerHtmlWrites === popBodyWritesBefore, 'open popover body must not wipe on duration tick');
    assert(popBody.querySelector('[data-ws-pop-dur]').textContent === '15 giây', 'open popover duration span should update in place');
    ''')


def test_workshop_js_offline_503_motion_toggle_visibility_and_observer():
    _run_workshop_js(r'''
    const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
    const { pyh, doc, localStorage, observers, setFetchHandler, getFetchCalls, resetFetchCalls } = ctx;

    let compStatus = 200;
    let throwFetch = false;
    let roleState = 'working';

    setFetchHandler((url) => {
      if (throwFetch) throw new Error('network error');
      if (url.startsWith('/api/company')) {
        if (compStatus !== 200) {
          return { ok: false, status: compStatus, async json() { return { error: 'unavailable' }; } };
        }
        return {
          ok: true, status: 200,
          async json() {
            return {
              production: { work_state: 'idle' },
              production_running: [],
              roles: [{
                id: 'scout',
                name: 'Scout',
                work_state: roleState,
                work_label: roleState === 'working' ? 'Đang làm' : 'Đang nghỉ',
                running: roleState === 'working'
                  ? [{ step: 'research', step_label: 'Quét', slug: 't1', duration_s: 5, cli: 'claude', model: 'm' }]
                  : [],
                recent: [], models_used: [], configured_models: [], steps: [], step_labels: [], tier: 'helper',
              }],
            };
          },
        };
      }
      if (url.startsWith('/api/status')) {
        return {
          ok: true, status: 200,
          async json() {
            return {
              factory: { running: true, pid: 101 },
              waiting: 0, projects: [], stages: ['1','2','3','4','5','6','7'],
              log: [], agents: [], now: '2026-11-14T10:00:00Z', standards: 0,
            };
          },
        };
      }
      if (url.startsWith('/api/overview')) return { ok: true, status: 200, async json() { return { tiles: {}, projects: [], decisions: [], resting: [] }; } };
      if (url.startsWith('/api/activity')) return { ok: true, status: 200, async json() { return { items: [] }; } };
      if (url.startsWith('/api/progress')) return { ok: true, status: 200, async json() { return { phases: [], doing: [], total: 0, done: 0 }; } };
      return { ok: true, status: 200, async json() { return { messages: [] }; } };
    });

    const ws = doc.getElementById('workshop');
    const offlineBanner = doc.getElementById('offline');
    const btnMotion = doc.getElementById('btn-ws-motion');

    // 1. Online + working -> liveFlow true
    await pyh.refresh();
    assert(pyh.getState().wsOffline === false, 'should be online');
    assert(ws.dataset.offline === 'false', 'dataset.offline false');
    assert(ws.dataset.paused === 'false', 'dataset.paused false');
    assert(ws.dataset.liveFlow === 'true', 'dataset.liveFlow true while role is working');

    // 2. HTTP 503 on /api/company -> offline mode, liveFlow false, stations Chưa xác minh
    compStatus = 503;
    await pyh.refresh();
    assert(pyh.getState().wsOffline === true, '503 sets wsOffline = true');
    assert(offlineBanner.classList.contains('show'), '503 shows offline banner');
    assert(ws.dataset.offline === 'true', '503 sets dataset.offline = true');
    assert(ws.dataset.paused === 'true', '503 pauses motion');
    assert(ws.dataset.liveFlow === 'false', '503 disables liveFlow');
    const scout503 = doc.querySelector('[data-station-id="scout"]');
    assert(scout503.classList.contains('is-unknown') && scout503.textContent.includes('Chưa xác minh'), '503 flips station to Chưa xác minh');

    // 3. Recovery then fetch exception -> offline again
    compStatus = 200;
    await pyh.refresh();
    assert(pyh.getState().wsOffline === false && ws.dataset.liveFlow === 'true', 'recovers after 200');

    throwFetch = true;
    await pyh.refresh();
    assert(pyh.getState().wsOffline === true && ws.dataset.liveFlow === 'false', 'fetch throw triggers offline & stops flow');

    // Restore online working for motion/visibility/observer tests
    throwFetch = false;
    await pyh.refresh();
    assert(ws.dataset.liveFlow === 'true', 'back online with liveFlow true');

    // 4. Motion toggle button is read-only & persists localStorage 'pyh-ws-motion'
    resetFetchCalls();
    btnMotion.onclick();
    assert(getFetchCalls() === 0, 'motion toggle must not make any network call');
    assert(localStorage.getItem('pyh-ws-motion') === 'off', 'persists off to localStorage');
    assert(ws.dataset.motion === 'off', 'dataset.motion = off');
    assert(ws.dataset.paused === 'true' && ws.dataset.liveFlow === 'false', 'motion off pauses animations and flow');
    assert(btnMotion.getAttribute('aria-pressed') === 'false', 'aria-pressed updates to false');
    assert(btnMotion.querySelector('.ws-motion-label').textContent === 'Hoạt cảnh: Tắt', 'button label updates');

    btnMotion.onclick();
    assert(localStorage.getItem('pyh-ws-motion') === 'on', 'persists on to localStorage');
    assert(ws.dataset.motion === 'on' && ws.dataset.paused === 'false' && ws.dataset.liveFlow === 'true', 'motion back on');
    assert(btnMotion.getAttribute('aria-pressed') === 'true', 'aria-pressed updates back to true');

    // 5. visibilitychange pauses and resumes
    doc.hidden = true;
    doc.dispatch('visibilitychange');
    assert(ws.dataset.paused === 'true' && ws.dataset.liveFlow === 'false', 'hidden tab pauses workshop');
    doc.hidden = false;
    doc.dispatch('visibilitychange');
    assert(ws.dataset.paused === 'false' && ws.dataset.liveFlow === 'true', 'visible tab resumes workshop');

    // 6. IntersectionObserver pauses offscreen and resumes onscreen
    assert(observers.length >= 1, 'IntersectionObserver must observe #workshop');
    observers[0].trigger([{ isIntersecting: false }]);
    assert(ws.dataset.paused === 'true' && ws.dataset.liveFlow === 'false', 'offscreen workshop pauses');
    observers[0].trigger([{ isIntersecting: true }]);
    assert(ws.dataset.paused === 'false' && ws.dataset.liveFlow === 'true', 'onscreen workshop resumes');
    ''')

    # Also verify persisted 'off' state in localStorage initializes button & dataset off on fresh load
    _run_workshop_js(
        r'''
        const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
        const ws = ctx.doc.getElementById('workshop');
        const btn = ctx.doc.getElementById('btn-ws-motion');
        assert(ws.dataset.motion === 'off', 'initializes off from localStorage');
        assert(ws.dataset.paused === 'true', 'starts paused when motion preference is off');
        assert(btn.getAttribute('aria-pressed') === 'false', 'aria-pressed starts false');
        ''',
        pre_storage={'pyh-ws-motion': 'off'},
    )


def test_progress_tasks_and_cards_wrap_long_notes_without_horizontal_overflow():
    html = DASHBOARD_HTML.read_text(encoding='utf-8')
    assert '.prog-task .meta{margin-left:auto;white-space:nowrap}' not in html
    assert '.prog-task{display:flex;gap:10px;align-items:baseline;padding:5px 0 5px 14px;font-size:14px;min-width:0}' in html
    assert '.prog-task > div,.prog-body{flex:1 1 auto;min-width:0;overflow-wrap:anywhere}' in html
    assert '.prog-task .prog-note,.prog-task > div .meta{white-space:normal;overflow-wrap:anywhere;line-height:1.45}' in html
    assert '.prog-task > .meta,.prog-task .prog-owner{margin-left:auto;white-space:nowrap;flex-shrink:0}' in html
    assert '.proj-layout{display:grid;grid-template-columns:148px minmax(0,1fr);gap:16px;align-items:start}' in html
    assert '.steps{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:5px;margin:12px 0 6px}' in html
    assert '.act-row{display:grid;grid-template-columns:auto minmax(0,1fr) auto;' in html
    assert '.row{display:grid;grid-template-columns:64px minmax(0,1fr) auto;' in html

    _run_workshop_js(
        r'''
        const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
        const longNote = 'Sol viết, Carbon high y khoa, Carbon medium kiểm duyệt/hình/dựng, '
          + 'Hydrogen việc nhẹ, Sonnet chấm sản phẩm; cache/pilot-archive/2026-11-14/long_unbroken_token_'
          + 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
        ctx.setFetchHandler(async (url) => {
          if (url.startsWith('/api/status')) {
            return {
              ok: true, status: 200,
              async json() {
                return {
                  factory: { running: false, pid: null },
                  waiting: 0, projects: [], stages: ['1','2','3','4','5','6','7'],
                  log: [], agents: [], now: '2026-11-14T10:00:00Z', standards: 0,
                };
              },
            };
          }
          if (url.startsWith('/api/company')) {
            return { ok: true, status: 200, async json() { return { roles: [], production_running: [], production: { work_state: 'idle' } }; } };
          }
          if (url.startsWith('/api/overview')) {
            return { ok: true, status: 200, async json() { return { tiles: {}, projects: [], decisions: [], resting: [] }; } };
          }
          if (url.startsWith('/api/activity')) {
            return { ok: true, status: 200, async json() { return { items: [] }; } };
          }
          if (url.startsWith('/api/progress')) {
            return {
              ok: true, status: 200,
              async json() {
                return {
                  total: 2, done: 1, updated: '2026-11-14',
                  doing: [{ id: 'R1.6', title: 'Hoạt cảnh nhân viên', status: 'doing', owner: 'agy', note: longNote }],
                  phases: [{
                    id: 'R1', title: 'Hoàn thiện xưởng trước khi làm video mới', total: 2, done: 1,
                    tasks: [
                      { id: 'R1.3', title: 'Phân model ban đầu', status: 'done', owner: 'codex', note: longNote },
                      { id: 'R1.6', title: 'Hoạt cảnh nhân viên', status: 'doing', owner: 'agy', note: longNote },
                    ],
                  }],
                };
              },
            };
          }
          return { ok: true, status: 200, async json() { return { messages: [] }; } };
        });

        await ctx.pyh.refresh();
        const doc = ctx.doc;
        assert(doc.getElementById('prog-total').textContent === '1/2 việc · cập nhật 2026-11-14', 'renders total header');
        const doingBody = doc.getElementById('prog-doing').querySelector('.prog-body');
        const doingNote = doc.getElementById('prog-doing').querySelector('.prog-note');
        const doingOwner = doc.getElementById('prog-doing').querySelector('.prog-owner');
        assert(doingBody && doingNote && doingOwner, 'doing progress task must separate prog-body, prog-note, prog-owner');
        assert(doingNote.textContent === longNote, 'doing note text preserved');
        assert(doingOwner.textContent === 'agy', 'doing owner separated into .prog-owner');
        assert(doc.getElementById('prog-phases').querySelectorAll('.prog-body').length === 2, 'phases render 2 .prog-body containers');
        assert(doc.getElementById('prog-phases').querySelectorAll('.prog-note').length === 2, 'phases render 2 .prog-note wrappers');
        assert(doc.getElementById('prog-phases').querySelectorAll('.prog-owner').length === 2, 'phases render 2 .prog-owner spans');
        '''
    )


def test_script_guidance_row_in_doctor_tasks():
    html = Path(dashboard.HTML_PATH).read_text(encoding='utf-8')
    assert "d.kind === 'script_guidance'" in html
    assert 'Gửi hướng dẫn' in html and 'Xem nhận xét' in html
    assert 'function startScriptGuidance' in html
    assert "b.dataset.guideProduct ? 'video' : 'script'" in html
    assert "product ? 'Thợ dựng' : 'Biên kịch'" in html
    assert 'aria-label="Gửi hướng dẫn:' in html
    assert '.todo-row.todo-guidance>.chip' in html


def test_workshop_avatars_cover_18_stations_with_distinct_personalities():
    _run_workshop_js(r'''
    const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
    const { pyh } = ctx;
    const ids = [
      'researcher', 'scout', 'medical_expert', 'writer', 'storyboard_director', 'voice_director',
      'script_critic', 'art_director', 'editor', 'product_critic', 'copywriter', 'shorts_producer',
      'coordinator', 'coordinator_senior', 'feedback_analyst', 'repair_engineer', 'gate_medical', 'gate_video',
    ];
    const avatars = pyh.WS_AVATARS;
    assert(ids.every((id) => avatars[id]), 'WS_AVATARS must define all 18 station identities');
    assert(Object.keys(avatars).length === 18, 'WS_AVATARS must contain exactly 18 identities');

    const styles = new Set(ids.map((id) => avatars[id].style));
    const outfits = new Set(ids.map((id) => avatars[id].outfit));
    const skins = new Set(ids.map((id) => avatars[id].skin));
    for (const s of ['side', 'bob', 'bun', 'ponytail', 'curly', 'undercut', 'crop', 'long']) {
      assert(styles.has(s), 'missing hair style ' + s);
    }
    assert(outfits.size >= 7, 'need at least 7 distinct outfits, got ' + outfits.size);
    assert(skins.size >= 6, 'need at least 6 distinct skin tones, got ' + skins.size);
    for (const id of ['medical_expert', 'gate_medical', 'gate_video']) {
      assert(avatars[id].outfit === 'blouse' && avatars[id].steth && avatars[id].glasses === 'thin', id + ' wears blouse + stethoscope + thin glasses');
    }
    for (const id of ['art_director', 'storyboard_director']) {
      assert(avatars[id].headwear === 'beret' || avatars[id].style === 'bun', id + ' has artistic beret or bun');
      assert(avatars[id].phones, id + ' wears studio headphones');
    }
    for (const id of ['voice_director', 'editor', 'shorts_producer', 'coordinator', 'coordinator_senior']) {
      assert(avatars[id].phones === 'on', id + ' wears headphones');
    }
    assert(avatars.coordinator.mic && avatars.coordinator_senior.mic, 'coordinators have mic boom');
    for (const id of ['script_critic', 'product_critic', 'feedback_analyst']) {
      assert(avatars[id].glasses === 'square' && avatars[id].outfit === 'vest' && avatars[id].pin, id + ' wears square glasses, vest and badge');
    }
    assert(avatars.repair_engineer.headwear === 'cap' && avatars.repair_engineer.outfit === 'tech', 'repair engineer: cap/goggles + orange harness');
    assert(avatars.scout.headwear === 'ranger' && avatars.scout.outfit === 'jacket', 'scout: ranger hat + jacket');

    const states = ['working', 'idle', 'error', 'waiting_model', 'waiting_retry', 'waiting_gate', 'unknown'];
    for (const id of ids) {
      for (const ws of states) {
        const st = { id, isGate: id.startsWith('gate_'), isMachine: false, workState: ws, folders: [], actClass: '', running: [] };
        const svg = pyh.wsIsoSvg(st);
        assert(svg.startsWith('<svg') && svg.endsWith('</svg>'), `${id}/${ws} renders a complete svg`);
        assert(!svg.includes('undefined') && !svg.includes('NaN'), `${id}/${ws} svg must not leak undefined/NaN`);
        assert(!svg.includes('stroke-dasharray="3 2.2"'), `${id}/${ws} must not draw the old dashed placeholder circle`);
        if (ws === 'working' && !st.isGate) {
          assert(svg.includes('ws-arm-l') && svg.includes('ws-arm-r'), id + ' working keeps ws-arm-l / ws-arm-r');
          assert((svg.match(/ws-person-bob/g) || []).length === 2, id + ' working animates body and arms together');
        }
        if (ws === 'idle' && !st.isGate) {
          assert(svg.includes('translate(124,64)'), id + ' idle keeps coffee cup at translate(124,64)');
          assert(!svg.includes('ws-person-bob'), id + ' idle must not bob');
        }
      }
    }

    // Gate sitting empty: leather armchair + gold nameplate instead of a dashed circle.
    const gateIdle = pyh.wsIsoSvg({ id: 'gate_medical', isGate: true, isMachine: false, workState: 'idle', folders: [], actClass: '' });
    assert(gateIdle.includes('ws-gate-armchair') && gateIdle.includes('#6b2d1d'), 'empty gate renders a leather armchair');
    assert(gateIdle.includes('#fbbf24') && gateIdle.includes('polygon points="76,82 90,75 100,80 86,87"'), 'empty gate shows gold nameplate on desk');
    const gateWait = pyh.wsIsoSvg({ id: 'gate_video', isGate: true, isMachine: false, workState: 'waiting_gate', folders: [{ slug: 'a', tone: 'gate' }], actClass: '' });
    assert(!gateWait.includes('ws-gate-armchair') && gateWait.includes('#f8fafc'), 'waiting gate shows the doctor in a white blouse');

    // Worn accessories moved onto the person: no floating headphone strokes left in wsPropSvg.
    for (const id of ['art_director', 'editor', 'coordinator']) {
      const prop = pyh.wsPropSvg(id, 'working');
      assert(!prop.includes('M90 25c0-6 20-6 20 0') && !prop.includes('M110 28l-5 5'), id + ' prop must not draw detached headphones');
    }
    const coord = pyh.wsIsoSvg({ id: 'coordinator', isGate: false, isMachine: false, workState: 'working', folders: [], actClass: '' });
    assert(coord.includes('M90.2 31.6C90.6 36 94.4 37.4 97.8 36.2'), 'coordinator headset has a mic boom on the head group');
    const med = pyh.wsIsoSvg({ id: 'medical_expert', isGate: false, isMachine: false, workState: 'idle', folders: [], actClass: '' });
    assert(med.includes('M95.4 42.4c-2.6 5.8'), 'medical expert wears a stethoscope');

    // Face expression follows workState.
    const working = pyh.wsIsoSvg({ id: 'writer', isGate: false, isMachine: false, workState: 'working', folders: [], actClass: '' });
    const errored = pyh.wsIsoSvg({ id: 'writer', isGate: false, isMachine: false, workState: 'error', folders: [], actClass: '' });
    assert(working.includes('M94.4 25.4l3.8.9') && errored.includes('M94.4 26.4l3.8-1.1'), 'brows: focused when working, worried on error');
    assert(errored.includes('#7dd3fc'), 'error face shows a sweat drop');

    // Rendering never depends on duration_s, so wsSvgSig stays stable.
    const a = pyh.wsSvgSig({ id: 'writer', workState: 'working', actClass: 'ws-act-writer', folders: [], running: [{ duration_s: 1 }] });
    const b = pyh.wsSvgSig({ id: 'writer', workState: 'working', actClass: 'ws-act-writer', folders: [], running: [{ duration_s: 99 }] });
    assert(a === b, 'wsSvgSig must ignore duration changes');
    ''')


def test_video_nle_timeline_runtime_transport_inspector_and_fallback(tmp_path):
    node = shutil.which('node')
    assert node is not None, 'Node.js is required to run dashboard UI runtime tests'
    scripts = _extract_dashboard_scripts()
    assert len(scripts) >= 1
    for idx, script in enumerate(scripts):
        js_file = tmp_path / f'dash_{idx}.js'
        js_file.write_text(script, encoding='utf-8')
        proc = subprocess.run([node, '--check', str(js_file)], capture_output=True, check=False)
        assert proc.returncode == 0, proc.stderr.decode('utf-8', 'replace')

    _run_workshop_js(r'''
    const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
    const { pyh, doc } = ctx;

    assert(pyh.pvFormatTc(0, 30) === '00:00:00', 'tc 0');
    assert(pyh.pvFormatTc(95, 30) === '00:03:05', 'tc 95');
    assert(pyh.pvParseJumpInput('8327', 30) === 8327, 'jump raw frame');
    assert(pyh.pvParseJumpInput('04:37', 30) === (4 * 60 + 37) * 30, 'jump MM:SS');
    assert(pyh.pvParseJumpInput('00:03:05', 30) === 95, 'jump MM:SS:FF');

    const bundle = {
      slug: 'nle-demo',
      title: 'Demo NLE',
      code: 'PYH-099',
      state: 'awaiting_video_review',
      state_label: 'Chờ duyệt video',
      gate: 'video',
      revision: '001',
      media: [
        { label: 'Video hoàn chỉnh', url: '/media/nle-demo/video.mp4', kind: 'mp4' },
        { label: 'Clip CL01', url: '/media/nle-demo/clips/CL01.mp4', kind: 'mp4' },
        { label: 'Giọng đọc', url: '/media/nle-demo/audio/narration-voice.wav', kind: 'wav' },
      ],
      timeline: [
        { scene: 'S01', start_s: 0.0, end_s: 3.0, open_change: true },
        { scene: 'S02', start_s: 3.0, end_s: 7.0, open_change: false },
      ],
      frame_inspector: {
        fps: 30,
        total_frames: 210,
        duration_s: 7.0,
        format_profile: 'youtube_long',
        scenes: [
          {
            id: 'S01', index: 0, start_frame: 0, end_frame: 90, duration_frames: 90,
            start_s: 0.0, end_s: 3.0, audio_ms: 2700, visual: 'anatomy_animation',
            script_line_id: 'N01', claim_id: 'C01', chapter_id: 'CH01', source_marker: '[1]',
            on_screen_text: 'Chữ cảnh S01', narration: 'Lời đọc cảnh một',
            mascot_pose: 'explain',
            anatomy: { subject: 'liver_organ', state: 'normal', severity: 0.0, motion: 'Xoay nhẹ' },
            beats: [{ at: 'cảnh một', start_frame: 30, abs_frame: 30, focus: 'overview', labels: [] }],
            entrances: [{ text: 'Chữ cảnh S01', start_frame: 5, abs_frame: 5 }],
            words: [{ text: 'Lời', start_frame: 0, end_frame: 15 }, { text: 'đọc', start_frame: 15, end_frame: 30 }],
            assets: [], open_change: true,
          },
          {
            id: 'S02', index: 1, start_frame: 90, end_frame: 210, duration_frames: 120,
            start_s: 3.0, end_s: 7.0, audio_ms: 3400, visual: 'source_card',
            script_line_id: 'N02', claim_id: 'C02', chapter_id: 'CH02', source_marker: '[2]',
            on_screen_text: 'Chữ cảnh S02', narration: 'Lời đọc cảnh hai',
            mascot_pose: null, anatomy: null,
            beats: [], entrances: [], words: [], assets: [], open_change: false,
          },
        ],
        sfx: [{ id: 'whoosh-soft', scene: 'S02', at: 0, time: 3.0, frame: 90 }],
        markers: [
          { kind: 'issue', source: 'product_review', frame: 95, scene: 'S02', label: 'S02@00:03 · hình rõ', detail: 'Chữ nhỏ', severity: 'warn' },
          { kind: 'open_change', source: 'change_request', frame: 0, scene: 'S01', label: 'S01 · Đang sửa', detail: 'Sửa màu', severity: 'info' },
        ],
        contact_sheets: {
          sheets: [{ name: 'final-contact-sheet-001.jpg', url: '/media/nle-demo/review-sheet/final-contact-sheet-001.jpg' }],
          sample_frames: [0, 45, 150],
        },
      },
      draft: [], claims: [], records: [], lines: [], activity: [], feedback: [],
    };

    doc.getElementById('pv').classList.add('show');
    pyh.setVideoState({ pv: bundle, pvTab: 'video' });
    pyh.updateChatContext({ slug: bundle.slug, revision: bundle.revision, view: 'video', scene: null, time_s: null });
    pyh.renderPv();

    const body = doc.getElementById('pv-body');
    const nle = body.querySelector('#pv-nle-timeline');
    const transport = body.querySelector('#pv-transport');
    const inspector = body.querySelector('#pv-frame-inspector');
    const playhead = body.querySelector('#pv-playhead');
    const vid = body.querySelector('#pv-video');
    assert(nle && transport && inspector && playhead && vid, 'all NLE panels and #pv-video must render');
    assert(vid.getAttribute('preload') === 'auto', '#pv-video must preload auto so first frame decodes');
    assert(body.querySelector('#pv-video[controls][playsinline]'), '#pv-video must expose native controls and playsinline');
    assert(body.innerHTML.indexOf('pv-nle-studio') < body.innerHTML.indexOf('Ng\\u01b0\\u1eddi duy\\u1ec7t s\\u1ea3n ph\\u1ea9m') || !body.innerHTML.includes('Ng\\u01b0\\u1eddi duy\\u1ec7t s\\u1ea3n ph\\u1ea9m'), '.pv-nle-studio comes before review/QA cards');
    assert(body.querySelector('#pv-scene-strip'), 'backward-compatible #pv-scene-strip must exist');
    assert(body.querySelectorAll('.nle-v1-block').length === 2, 'V1 track renders 2 scene blocks');
    assert(body.querySelector('#pv-tc-readout').textContent === '00:00:00', 'initial timecode 00:00:00');
    assert(body.querySelector('#pv-frame-readout').textContent === 'Frame 0 / 210 @ 30 fps', 'initial frame readout');

    // Simulating loadedmetadata at currentTime=0 primes frame 0 at 0.02s while keeping Frame 0 readout
    vid.currentTime = 0;
    vid.paused = true;
    vid.onloadedmetadata();
    assert(Math.abs(vid.currentTime - 0.02) < 1e-6, 'onloadedmetadata primes frame 0 to 0.02s');
    assert(body.querySelector('#pv-tc-readout').textContent === '00:00:00', 'primed timecode remains 00:00:00');

    // +1f step
    body.querySelector('#pv-btn-fwd-1').onclick();
    assert(Math.abs(vid.currentTime - (1 + 0.02) / 30) < 1e-6, '+1f sets currentTime to 1.02/30');
    assert(body.querySelector('#pv-tc-readout').textContent === '00:00:01', '+1f timecode 00:00:01');
    assert(inspector.textContent.includes('Cảnh S01') && inspector.textContent.includes('Frame nội cảnh: 1 / 90'), 'inspector tracks S01 frame 1');

    // +10f step
    body.querySelector('#pv-btn-fwd-10').onclick();
    assert(Math.abs(vid.currentTime - (11 + 0.02) / 30) < 1e-6, '+10f sets currentTime to 11.02/30');
    assert(body.querySelector('#pv-frame-readout').textContent === 'Frame 11 / 210 @ 30 fps', '+10f readout 11');

    // -1f step
    body.querySelector('#pv-btn-back-1').onclick();
    assert(Math.abs(vid.currentTime - (10 + 0.02) / 30) < 1e-6, '-1f sets currentTime to 10.02/30');

    // Jump via timecode input to S02 (frame 95 = 00:03:05)
    const jumpInp = body.querySelector('#pv-frame-jump');
    jumpInp.value = '00:03:05';
    body.querySelector('#pv-jump-form').onsubmit({ preventDefault() {} });
    assert(Math.abs(vid.currentTime - (95 + 0.02) / 30) < 1e-6, 'jump to 00:03:05 -> frame 95');
    assert(inspector.textContent.includes('Cảnh S02') && inspector.textContent.includes('Frame nội cảnh: 5 / 120'), 'inspector switches to S02');
    assert(pyh.getVideoState().chatCtx.scene === 'S02' && pyh.getVideoState().chatCtx.time_s === 3, 'chatCtx updates to S02 @ 3s');

    // Jump via scene chip [data-scene="S01"]
    body.querySelector('#pv-scene-strip [data-scene="S01"]').onclick();
    assert(Math.abs(vid.currentTime - (0 + 0.02) / 30) < 1e-6, 'scene chip S01 jumps to frame 0');
    assert(pyh.getVideoState().chatCtx.scene === 'S01', 'chatCtx updates to S01');

    // Safezone toggle & zoom & vertical clip source switch
    body.querySelector('#pv-safezone-toggle').onclick();
    assert(body.querySelector('#pv-stage-wrap').classList.contains('show-safezone'), 'safezone overlay toggles on');

    body.querySelector('[data-nle-zoom="4"]').onclick();
    assert(String(body.querySelector('#pv-nle-canvas').style.width || '').endsWith('px'), 'zoom 4x sets pixel width');

    const clipBtn = body.querySelectorAll('[data-pv-src]')[1];
    clipBtn.onclick();
    assert(body.querySelector('#pv-stage-frame').classList.contains('is-vertical'), 'Clip switches viewport to 9:16');
    assert(vid.src === '/media/nle-demo/clips/CL01.mp4', 'video src switches to Clip CL01');

    // Pin frame to chat
    body.querySelector('#pv-pin-frame-chat').onclick();
    assert(doc.getElementById('chat-panel').classList.contains('open'), 'pin button opens chat panel');
    assert(doc.getElementById('chat-input').value.startsWith('[Cảnh S01 · Frame '), 'pin button populates frame prefix');

    // Fallback when b.frame_inspector is absent
    const fallbackBundle = {
      slug: 'fb-demo', title: 'Fallback', code: 'PYH-100', state: 'awaiting_video_review',
      state_label: 'Chờ duyệt video', gate: 'video', revision: '001',
      media: [{ label: 'Video hoàn chỉnh', url: '/media/fb-demo/video.mp4', kind: 'mp4' }],
      timeline: [{ scene: 'S01', start_s: 0, end_s: 2.5, open_change: false }],
      storyboard: { scenes: [{ id: 'S01', visual: 'whiteboard', on_screen_text: 'Fallback text', narration: 'Fallback narration' }] },
      draft: [], claims: [], records: [], lines: [], activity: [], feedback: [],
    };
    pyh.setVideoState({ pv: fallbackBundle, pvTab: 'video' });
    pyh.renderPv();
    assert(body.querySelector('#pv-nle-timeline') && body.querySelectorAll('.nle-v1-block').length === 1, 'fallback without frame_inspector still renders NLE timeline');

    pyh.closeProduct();
    assert(pyh.getVideoState().pvVideoState.active === false, 'closeProduct cleans up video runtime');
    ''')


def test_stage12_guidance_blocked_card_and_preset_replies():
    _run_workshop_js(r'''
    const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
    const { pyh, doc, setFetchHandler } = ctx;

    const answerPosts = [];
    const longSummary = 'Hình minh họa tế bào gan ở cảnh này đang thiếu mũi tên chỉ đường đi của men gan và nhãn chữ hơi chồng lên vùng tối ở góc phải màn hình khi chuyển sang khung hình tiếp theo, cần chỉnh bố cục rõ ràng hơn.';
    const longLoc = 'S04@01:12-01:35 · anatomy-overlay-liver-enzymes-very-long-label';
    const openQuestion = {
      id: 'dq-abc123',
      station: '12',
      kind: 'stuck_issue',
      question: 'Trạm 12 kẹt cùng issue qua 2 vòng duyệt sản phẩm; bác sĩ chọn hướng xử lý tiếp theo.',
      context: [
        { code: 'PR-01', location: longLoc, summary: longSummary },
        { code: 'PR-03', location: 'S09@03:10', summary: 'Cảnh dài 28 giây chưa tách nhịp.' },
      ],
      options: [
        { id: 'fix_visuals', label: 'Sửa hình các cảnh bị nêu', detail: 'Giao Thợ dựng sửa lại hình ảnh các cảnh còn mở.' },
        { id: 'split_long_scenes', label: 'Tách cảnh dài', detail: 'Tách cảnh dài để cải thiện nhịp.' },
      ],
      allow_free_text: true,
      created_at: '2026-11-21T10:00:00+00:00',
      status: 'open',
      answer: null,
    };

    const baseBundle = {
      slug: 'demo-stage12-stuck',
      title: 'Demo Trạm 12 kẹt',
      code: 'PYH-112',
      state: 'production_in_progress',
      state_label: 'Chờ ý kiến bác sĩ',
      gate: null,
      revision: '002',
      blocked: '',
      doctor_question: openQuestion,
      media: [], timeline: [], draft: [], claims: [], records: [], lines: [], activity: [], feedback: [],
    };

    setFetchHandler((url, opts) => {
      if (url === '/api/project/demo-stage12-stuck/answer-question' && opts && opts.method === 'POST') {
        answerPosts.push(JSON.parse(opts.body));
        return { ok: true, status: 200, async json() { return { ok: true, summary: 'Đã ghi nhận' }; } };
      }
      if (url === '/api/project/demo-stage12-stuck/bundle') {
        return { ok: true, status: 200, async json() { return { ...baseBundle, doctor_question: null }; } };
      }
      if (url.startsWith('/api/status')) {
        return {
          ok: true, status: 200,
          async json() {
            return {
              factory: { running: false, pid: null }, waiting: 0,
              projects: [{
                slug: 'demo-stage12-stuck', code: 'PYH-112', title: 'Demo Trạm 12 kẹt',
                state: 'production_in_progress', state_label: 'Chờ ý kiến bác sĩ',
                stage: 4, gate: null, blocked: '', doctor_question: openQuestion,
                paused: false, revision: '002', comments: 0,
                handler: { label: 'Chờ ý kiến bác sĩ', kind: 'doctor', reason: openQuestion.question },
              }],
              stages: ['1','2','3','4','5','6','7'], log: [], agents: [], now: '2026-11-21T10:00:00Z', standards: 0,
            };
          },
        };
      }
      if (url.startsWith('/api/overview')) {
        return {
          ok: true, status: 200,
          async json() {
            return {
              tiles: { running: 0, waiting_doctor: 1, done_7d: 0, done_30d: 0, avg_days_topic_to_video: 0, models_resting: 0 },
              decisions: [{
                kind: 'doctor_question', slug: 'demo-stage12-stuck', code: 'PYH-112',
                title: 'Demo Trạm 12 kẹt', gate: null, count: 2, revision: '002',
                station: '12', question_id: 'dq-abc123', question: openQuestion.question,
              }],
              projects: [
                { slug: 'demo-stage12-stuck', gate: null, blocked: '', doctor_question: openQuestion },
                { slug: 'real-blocked', gate: null, blocked: 'TTS lỗi', doctor_question: null },
              ],
              resting: [],
            };
          },
        };
      }
      return { ok: true, status: 200, async json() { return {}; } };
    });

    // Refresh home view: verify neutral badge "Chờ ý kiến bác sĩ" and separate count in #tiles
    await pyh.refresh();
    const tilesText = doc.getElementById('tiles').textContent;
    assert(tilesText.includes('1 chờ ý kiến') && tilesText.includes('1 cần chú ý'), 'tiles shows separate chờ ý kiến count: ' + tilesText);
    const chip = doc.getElementById('projects').querySelector('.chip.question');
    assert(chip && chip.textContent === 'Chờ ý kiến bác sĩ', 'project row shows neutral Chờ ý kiến bác sĩ badge');
    assert(!doc.getElementById('projects').querySelector('.chip.bad'), 'question project must not use red Bị chặn badge');

    // Detail modal renders merged #pv-stage12-card from b.doctor_question
    doc.getElementById('pv').classList.add('show');
    pyh.setVideoState({ pv: baseBundle, pvTab: 'overview' });
    pyh.renderPv();

    const slot = doc.getElementById('pv-card-slot');
    const card = slot.querySelector('#pv-stage12-card');
    assert(card, 'doctor question card must render in #pv-card-slot');
    assert(card.textContent.includes('Chờ ý kiến bác sĩ'), 'card heading must be Chờ ý kiến bác sĩ');

    const items = card.querySelectorAll('.s12-issue');
    assert(items.length === 2, 'context items must render');
    assert(items[0].dataset.s12Issue === 'PR-01' && items[1].dataset.s12Issue === 'PR-03', 'context codes match');

    const at0 = items[0].querySelector('.s12-at');
    assert(at0 && at0.textContent.length <= 48 && at0.textContent.endsWith('…'), 'long location shortened');
    assert(at0.getAttribute('title') === longLoc, 'full location kept in title');

    const btns = card.querySelectorAll('[data-dq-option]');
    assert(btns.length === 2, 'must render two option buttons');
    assert(btns[0].dataset.dqOption === 'fix_visuals' && btns[0].classList.contains('primary'), 'recommended option first with primary style');
    assert(btns[1].dataset.dqOption === 'split_long_scenes', 'second option id matches');

    const freeInput = card.querySelector('#dq-free-text');
    assert(freeInput, 'free text input rendered when allow_free_text is true');
    freeInput.value = 'Chỉnh nhãn rõ hơn';

    // Clicking option posts exact payload to /api/project/<slug>/answer-question
    await btns[0].onclick();
    assert(answerPosts.length === 1, 'option click sends one POST');
    assert(answerPosts[0].question_id === 'dq-abc123', 'payload includes question_id');
    assert(answerPosts[0].option_id === 'fix_visuals', 'payload includes option_id');
    assert(answerPosts[0].text === 'Chỉnh nhãn rõ hơn', 'payload includes optional free text');
    assert(answerPosts[0].expected_revision === '002', 'payload includes expected_revision');

    // No open doctor_question -> card does NOT render even if blocked text exists
    const blockedOnly = { ...baseBundle, doctor_question: null, blocked: 'TTS lỗi: timeout kết nối' };
    pyh.setVideoState({ pv: blockedOnly, pvTab: 'overview' });
    pyh.renderPv();
    assert(!slot.querySelector('#pv-stage12-card'), 'no doctor_question must not render card');
    ''')


def test_overview_status_labels_friendly_errors_offline_and_mobile_chat():
    html = DASHBOARD_HTML.read_text(encoding='utf-8')
    assert '--brand-navy:#12304A' in html and '--brand-teal:#18A6A6' in html
    assert '--brand-yellow:#F4B942' in html and '--brand-offwhite:#F7F4EC' in html
    assert 'id="btn-chat-close"' in html

    _run_workshop_js(r'''
    const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
    const { pyh, doc, setFetchHandler } = ctx;

    // 1. Initial offline load shows Vietnamese recovery message + retry button
    setFetchHandler(async () => { throw new Error('network down'); });
    await pyh.refresh();
    assert(doc.getElementById('offline').classList.contains('show'), 'offline banner shown');
    assert(doc.getElementById('projects').textContent.includes('Không tải được danh sách dự án'), 'friendly offline projects card');
    assert(doc.getElementById('btn-retry-load'), 'retry button rendered on initial offline error');

    // 2. Online load renders uniform Vietnamese status labels, friendly errors, and todo badge
    setFetchHandler(async (url) => {
      if (url.startsWith('/api/status')) {
        return {
          ok: true, status: 200,
          async json() {
            return {
              factory: { running: true, pid: 123 }, waiting: 1,
              stages: ['Chủ đề', 'Nghiên cứu', 'Kịch bản', 'Duyệt y khoa', 'Sản xuất', 'Duyệt video', 'Đóng gói'],
              log: [], agents: [], now: '2026-11-22T18:00:00Z', standards: 0,
              projects: [
                {
                  slug: 'err-proj', code: 'PYH-003', title: 'Dự án lỗi hình',
                  state: 'medically_approved', state_label: 'Bị chặn · sản xuất',
                  stage: 4, gate: null, paused: false, revision: '001', comments: 0,
                  blocked: 'ValueError: Visual review requires current rendered contact sheet',
                  handler: { label: 'Kỹ sư sửa lỗi đang sửa lỗi', kind: 'repair', reason: 'Visual review requires current rendered contact sheet' },
                },
                {
                  slug: 'gate-proj', code: 'PYH-002', title: 'Dự án chờ duyệt',
                  state: 'draft_ready', state_label: 'Chờ duyệt y khoa',
                  stage: 3, gate: 'medical', paused: false, revision: '001', comments: 0,
                  blocked: '', handler: { label: 'Chờ bác sĩ', kind: 'doctor', reason: '' },
                },
                {
                  slug: 'run-proj', code: 'PYH-001', title: 'Dự án đang chạy',
                  state: 'researching', state_label: 'Đang nghiên cứu',
                  stage: 1, gate: null, paused: false, revision: '001', comments: 0,
                  blocked: '', handler: { label: 'Chuyên gia y học', kind: 'work', reason: '' },
                },
                {
                  slug: 'pause-proj', code: 'PYH-004', title: 'Dự án tạm dừng',
                  state: 'draft_ready', state_label: 'Tạm dừng · kịch bản',
                  stage: 2, gate: null, paused: true, revision: '001', comments: 0,
                  blocked: '', handler: { label: 'Tạm dừng', kind: 'paused', reason: '' },
                },
              ],
            };
          },
        };
      }
      if (url.startsWith('/api/overview')) {
        return {
          ok: true, status: 200,
          async json() {
            return {
              tiles: { running: 1, waiting_doctor: 1, done_7d: 0, done_30d: 0, avg_days_topic_to_video: 0, models_resting: 0 },
              decisions: [{ slug: 'gate-proj', code: 'PYH-002', title: 'Dự án chờ duyệt', gate: 'medical', count: 1 }],
              projects: [
                { slug: 'err-proj', blocked: 'Visual review requires current rendered contact sheet', gate: null, paused: false },
                { slug: 'gate-proj', blocked: '', gate: 'medical', paused: false },
                { slug: 'run-proj', blocked: '', gate: null, paused: false },
                { slug: 'pause-proj', blocked: '', gate: null, paused: true },
              ],
              resting: [],
            };
          },
        };
      }
      if (url.startsWith('/api/company')) return { ok: true, status: 200, async json() { return { roles: [], production_running: [], production: { work_state: 'idle' } }; } };
      if (url.startsWith('/api/activity')) return { ok: true, status: 200, async json() { return { items: [] }; } };
      if (url.startsWith('/api/progress')) return { ok: true, status: 200, async json() { return { phases: [], doing: [], total: 0, done: 0 }; } };
      return { ok: true, status: 200, async json() { return {}; } };
    });

    await pyh.refresh();
    const projectsEl = doc.getElementById('projects');
    const errRow = projectsEl.querySelector('[data-row-slug="err-proj"]');
    assert(errRow && errRow.querySelector('.chip.bad').textContent === 'Lỗi cần xử lý', 'error row shows Lỗi cần xử lý');
    assert(!errRow.textContent.includes('Visual review requires'), 'raw English error must be translated');
    assert(errRow.textContent.includes('Chưa có bảng ảnh liên hoàn mới nhất'), 'friendly Vietnamese error shown');
    const gateRow = projectsEl.querySelector('[data-row-slug="gate-proj"]');
    assert(gateRow && gateRow.querySelector('.chip.gate').textContent === 'Chờ bác sĩ · Duyệt y khoa', 'medical gate label');
    const runRow = projectsEl.querySelector('[data-row-slug="run-proj"]');
    assert(runRow && runRow.querySelector('.chip.work').textContent === 'Đang chạy', 'running label');
    const pauseRow = projectsEl.querySelector('[data-row-slug="pause-proj"]');
    assert(pauseRow && pauseRow.querySelector('.chip.paused').textContent === 'Tạm dừng', 'paused label');
    assert(doc.getElementById('todo-count').textContent === '1' && !doc.getElementById('todo-count').hidden, 'todo badge shows 1');
    assert(doc.getElementById('decisions').classList.contains('has-items'), 'decisions highlighted when active');

    // 3. Mobile chat drawer toggle and close
    const chatPanel = doc.getElementById('chat-panel');
    doc.getElementById('btn-chat-toggle').onclick();
    assert(chatPanel.classList.contains('open'), 'chat toggle opens chat drawer');
    doc.getElementById('btn-chat-close').onclick();
    assert(!chatPanel.classList.contains('open'), 'chat close closes chat drawer');
    ''')


def test_retry_force_auto_start_and_token_auto_refresh():
    _run_workshop_js(r'''
    const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
    const { pyh, doc, setFetchHandler } = ctx;

    let factoryRunning = false;
    let currentToken = 'fresh-server-token';
    let staleOnce = true;
    const calls = [];

    const makeBundle = (blocked = 'ValueError: Visual review requires current rendered contact sheet') => ({
      slug: 'pyh-003', code: 'PYH-003', title: 'Gan tổn thương',
      state: 'medically_approved', state_label: 'Bị chặn · sản xuất',
      gate: null, revision: '001', blocked, doctor_question: null,
      media: [], timeline: [], draft: [], claims: [], records: [], lines: [], activity: [], feedback: [],
    });

    setFetchHandler(async (url, opts = {}) => {
      const method = (opts && opts.method) || 'GET';
      const headers = (opts && opts.headers) || {};
      const body = opts && opts.body ? JSON.parse(opts.body) : null;
      calls.push({ url, method, token: headers['X-Dashboard-Token'], body });

      if (url === '/') {
        return {
          ok: true, status: 200,
          async text() { return `<script>let TOKEN = '${currentToken}';</script>`; },
        };
      }
      if (url === '/api/project/pyh-003/retry' && method === 'POST') {
        if (staleOnce && headers['X-Dashboard-Token'] !== currentToken) {
          staleOnce = false;
          return { ok: false, status: 403, async json() { return { error: 'forbidden' }; } };
        }
        if (headers['X-Dashboard-Token'] !== currentToken) {
          return { ok: false, status: 403, async json() { return { error: 'forbidden' }; } };
        }
        return { ok: true, status: 200, async json() { return { ok: true, message: 'OK' }; } };
      }
      if (url === '/api/factory/start' && method === 'POST') {
        factoryRunning = true;
        return { ok: true, status: 200, async json() { return { ok: true, message: 'Đã bật xưởng' }; } };
      }
      if (url.startsWith('/api/project/pyh-003/bundle')) {
        return { ok: true, status: 200, async json() { return makeBundle(); } };
      }
      if (url.startsWith('/api/status')) {
        return {
          ok: true, status: 200,
          async json() {
            return {
              factory: { running: factoryRunning, pid: factoryRunning ? 999 : null },
              waiting: 0,
              stages: ['1','2','3','4','5','6','7'],
              log: [], agents: [], now: '2026-11-23T09:00:00Z', standards: 0,
              projects: [{
                slug: 'pyh-003', code: 'PYH-003', title: 'Gan tổn thương',
                state: 'medically_approved', state_label: 'Bị chặn · sản xuất',
                stage: 4, gate: null, paused: false, revision: '001', comments: 0,
                blocked: 'ValueError: Visual review requires current rendered contact sheet',
                handler: { label: 'Kỹ sư sửa lỗi', kind: 'repair', reason: 'Visual review requires current rendered contact sheet' },
              }],
            };
          },
        };
      }
      if (url.startsWith('/api/overview')) {
        return {
          ok: true, status: 200,
          async json() {
            return {
              tiles: { running: 0, waiting_doctor: 0, done_7d: 0, done_30d: 0, avg_days_topic_to_video: 0, models_resting: 0 },
              decisions: [], projects: [{ slug: 'pyh-003', blocked: 'err', gate: null, paused: false }], resting: [],
            };
          },
        };
      }
      if (url.startsWith('/api/company')) return { ok: true, status: 200, async json() { return { roles: [], production_running: [], production: { work_state: 'idle' } }; } };
      if (url.startsWith('/api/activity')) return { ok: true, status: 200, async json() { return { items: [] }; } };
      if (url.startsWith('/api/progress')) return { ok: true, status: 200, async json() { return { phases: [], doing: [], total: 0, done: 0 }; } };
      return { ok: true, status: 200, async json() { return {}; } };
    });

    // 1. Overview "Làm lại" button: stale 403 triggers token refresh + transparent retry with force:true, then auto-starts stopped factory
    await pyh.refresh();
    const retryBtn = doc.getElementById('projects').querySelector('[data-retry-project="pyh-003"]');
    assert(retryBtn, 'overview retry button rendered');
    await retryBtn.onclick();

    const retryPosts = calls.filter(c => c.url === '/api/project/pyh-003/retry');
    assert(retryPosts.length === 2, '403 forbidden triggers exactly one transparent retry: ' + retryPosts.length);
    assert(retryPosts[1].token === 'fresh-server-token', 'second retry uses refreshed token');
    assert(retryPosts[1].body && retryPosts[1].body.force === true && retryPosts[1].body.expected_revision === '001', 'sends force:true and expected_revision');
    assert(calls.some(c => c.url === '/'), 'fetched / to refresh CSRF token');
    assert(calls.filter(c => c.url === '/api/factory/start').length === 1, 'auto-started stopped factory');
    assert(doc.getElementById('toast').textContent === 'Đã gỡ lỗi chặn và khởi chạy lại dự án!', 'shows combined success toast');

    // 2. #pv-retry & #pv-inline-retry when factory already running: sends force:true and does NOT call /api/factory/start again
    doc.getElementById('pv').classList.add('show');
    pyh.setVideoState({ pv: makeBundle(), pvTab: 'overview' });
    pyh.renderPv();
    await doc.getElementById('pv-retry').onclick();
    assert(calls.filter(c => c.url === '/api/project/pyh-003/retry').length === 3, '#pv-retry posts retry');
    assert(calls.filter(c => c.url === '/api/factory/start').length === 1, 'does not re-start already running factory');

    await doc.getElementById('pv-body').querySelector('#pv-inline-retry').onclick();
    assert(calls.filter(c => c.url === '/api/project/pyh-003/retry').length === 4, '#pv-inline-retry posts retry');
    assert(calls.filter(c => c.url === '/api/factory/start').length === 1, 'still does not re-start running factory');

    // 3. Real medical gate mismatch error surfaces cleanly via friendlyError without calling /api/factory/start
    setFetchHandler(async (url, opts = {}) => {
      if (url === '/api/project/pyh-003/retry') {
        return { ok: false, status: 400, async json() { return { error: 'Tệp đã duyệt y khoa đã đổi; bác sĩ phải mở lại cổng y khoa.' }; } };
      }
      if (url === '/api/project/pyh-003/gate/decide') {
        return { ok: false, status: 403, async json() { return { error: 'PIN sai.' }; } };
      }
      return { ok: true, status: 200, async json() { return {}; } };
    });
    await doc.getElementById('pv-retry').onclick();
    assert(doc.getElementById('toast').textContent.includes('mở lại cổng y khoa'), 'real gate error surfaced in toast');

    // 4. Non-forbidden 403 (e.g. wrong PIN) must NOT refresh token or retry
    let pinErr = '';
    try {
      await pyh.postJson('/api/project/pyh-003/gate/decide', { pin: '000000' });
    } catch (e) {
      pinErr = e.message;
    }
    assert(pinErr === 'PIN sai.', 'wrong PIN 403 throws exact error without token refresh: ' + pinErr);
    ''')


def test_zero_hang_error_ui_active_repair_escalation_and_stopped_reminder():
    _run_workshop_js(r'''
    const assert = (cond, msg) => { if (!cond) throw new Error(msg); };
    const { pyh, doc, setFetchHandler } = ctx;

    const futureIso = new Date(Date.now() + 15 * 60 * 1000).toISOString();
    const posts = [];

    // Part A: Running factory with is_running / diagnosing / repairing / future retry_after -> no dead red error
    setFetchHandler(async (url, opts = {}) => {
      if (url.startsWith('/api/status')) {
        return {
          ok: true, status: 200,
          async json() {
            return {
              factory: { running: true, pid: 101 }, waiting: 0,
              stages: ['Chủ đề', 'Nghiên cứu', 'Kịch bản', 'Duyệt y khoa', 'Sản xuất', 'Duyệt video', 'Đóng gói'],
              log: [], agents: [], now: '2026-11-23T10:00:00Z', standards: 0,
              projects: [
                { slug: 'p-run', code: 'PYH-001', title: 'Đang dựng dù có blocked cũ', state: 'medically_approved', state_label: 'Sản xuất', stage: 4, gate: null, paused: false, revision: '001', blocked: 'TimeoutExpired cũ' },
                { slug: 'p-diag', code: 'PYH-002', title: 'Đang chẩn đoán', state: 'medically_approved', state_label: 'Sản xuất', stage: 4, gate: null, paused: false, revision: '001', blocked: 'Lỗi A' },
                { slug: 'p-rep', code: 'PYH-003', title: 'Đang sửa mã', state: 'medically_approved', state_label: 'Sản xuất', stage: 4, gate: null, paused: false, revision: '001', blocked: 'Lỗi B' },
                { slug: 'p-cd', code: 'PYH-004', title: 'Hẹn thử lại', state: 'medically_approved', state_label: 'Sản xuất', stage: 4, gate: null, paused: false, revision: '001', blocked: 'Lỗi C' },
              ],
            };
          },
        };
      }
      if (url.startsWith('/api/overview')) {
        return {
          ok: true, status: 200,
          async json() {
            return {
              tiles: { running: 1, waiting_doctor: 0, done_7d: 0, done_30d: 0, avg_days_topic_to_video: 0, models_resting: 0 },
              decisions: [],
              projects: [
                { slug: 'p-run', blocked: 'TimeoutExpired cũ', gate: null, paused: false, is_running: true },
                { slug: 'p-diag', blocked: 'Lỗi A', gate: null, paused: false, is_running: false, repair: { phase: 'diagnosing', detail: 'Đọc log sản xuất' } },
                { slug: 'p-rep', blocked: 'Lỗi B', gate: null, paused: false, is_running: false, repair: { phase: 'repairing' } },
                { slug: 'p-cd', blocked: 'Lỗi C', gate: null, paused: false, is_running: false, repair: { phase: 'cooldown' }, retry_after: futureIso },
              ],
              resting: [],
            };
          },
        };
      }
      if (url.startsWith('/api/company')) return { ok: true, status: 200, async json() { return { roles: [], production_running: [], production: { work_state: 'idle' } }; } };
      if (url.startsWith('/api/activity')) return { ok: true, status: 200, async json() { return { items: [] }; } };
      if (url.startsWith('/api/progress')) return { ok: true, status: 200, async json() { return { phases: [], doing: [], total: 0, done: 0 }; } };
      return { ok: true, status: 200, async json() { return {}; } };
    });

    await pyh.refresh();
    const projBox = doc.getElementById('projects');
    assert(!projBox.querySelector('.chip.bad') && !projBox.querySelector('.prow.blocked'), 'active/auto-repairing projects must not show red error');
    const rRun = projBox.querySelector('[data-row-slug="p-run"]');
    assert(rRun.querySelector('.chip.work').textContent === 'Đang chạy' && rRun.textContent.includes('Máy dựng đang chạy'), 'is_running overrides stale blocked');
    const rDiag = projBox.querySelector('[data-row-slug="p-diag"]');
    assert(rDiag.querySelector('.chip.work').textContent === 'Đang tự khắc phục' && rDiag.textContent.includes('Trưởng nhóm đang chẩn đoán sự cố'), 'diagnosing text');
    const rRep = projBox.querySelector('[data-row-slug="p-rep"]');
    assert(rRep.querySelector('.chip.work').textContent === 'Đang tự khắc phục' && rRep.textContent.includes('Kỹ sư sửa lỗi đang vá mã') && rRep.textContent.includes('chạy test'), 'repairing text');
    const rCd = projBox.querySelector('[data-row-slug="p-cd"]');
    assert(rCd.querySelector('.chip.work').textContent === 'Đang tự khắc phục' && rCd.textContent.includes('Xưởng hẹn tự thử lại lúc '), 'future retry_after HH:MM');

    // Part B: Escalation card in "Việc của bác sĩ" + stopped factory reminder when blocked has no doctor_question
    const escQuestion = {
      id: 'esc-001',
      kind: 'escalation',
      station: 'repair',
      question: 'Hết 2 lượt tự sửa lỗi bundle Remotion.',
      context: [{ code: 'LOG', location: 'produce.py', summary: 'Đệ quy bundle quá thời gian' }],
      options: [
        { id: 'retry_repair_cycle', label: 'Cho phép xử lý / thử sửa thêm 1 chu kỳ' },
        { id: 'reopen_or_delegate', label: 'Giao làm lại theo chỉ đạo của tôi' },
        { id: 'pause_project', label: 'Tạm dừng dự án này' },
      ],
      allow_free_text: true,
      status: 'open',
    };
    setFetchHandler(async (url, opts = {}) => {
      if (opts && opts.method === 'POST') {
        posts.push({ url, body: opts.body ? JSON.parse(opts.body) : null });
        return { ok: true, status: 200, async json() { return { ok: true, summary: 'Đã ghi nhận chỉ đạo' }; } };
      }
      if (url.startsWith('/api/status')) {
        return {
          ok: true, status: 200,
          async json() {
            return {
              factory: { running: false, pid: null }, waiting: 0,
              stages: ['1','2','3','4','5','6','7'], log: [], agents: [], now: '2026-11-23T10:05:00Z', standards: 0,
              projects: [
                { slug: 'p-esc', code: 'PYH-003', title: 'Men gan', state: 'medically_approved', state_label: 'Chờ ý kiến bác sĩ', stage: 4, gate: null, paused: false, revision: '001', blocked: 'Hết lượt sửa', doctor_question: escQuestion },
                { slug: 'p-unhandled', code: 'PYH-004', title: 'Vitamin C', state: 'draft_ready', state_label: 'Bị chặn', stage: 2, gate: null, paused: false, revision: '001', blocked: 'Lỗi viết kịch bản', doctor_question: null },
              ],
            };
          },
        };
      }
      if (url.startsWith('/api/overview')) {
        return {
          ok: true, status: 200,
          async json() {
            return {
              tiles: { running: 0, waiting_doctor: 1, done_7d: 0, done_30d: 0, avg_days_topic_to_video: 0, models_resting: 0 },
              decisions: [{
                kind: 'doctor_question', question_kind: 'escalation', slug: 'p-esc', code: 'PYH-003',
                title: 'Men gan', revision: '001', question_id: 'esc-001', question: escQuestion.question, count: 3,
              }],
              projects: [
                { slug: 'p-esc', code: 'PYH-003', title: 'Men gan', state: 'medically_approved', revision: '001', blocked: 'Hết lượt sửa', gate: null, paused: false, doctor_question: escQuestion },
                { slug: 'p-unhandled', code: 'PYH-004', title: 'Vitamin C', state: 'draft_ready', revision: '001', blocked: 'Lỗi viết kịch bản', gate: null, paused: false, doctor_question: null },
              ],
              resting: [],
            };
          },
        };
      }
      if (url.startsWith('/api/company')) return { ok: true, status: 200, async json() { return { roles: [], production_running: [], production: { work_state: 'idle' } }; } };
      if (url.startsWith('/api/activity')) return { ok: true, status: 200, async json() { return { items: [] }; } };
      if (url.startsWith('/api/progress')) return { ok: true, status: 200, async json() { return { phases: [], doing: [], total: 0, done: 0 }; } };
      return { ok: true, status: 200, async json() { return {}; } };
    });

    await pyh.refresh();
    const decEl = doc.getElementById('decisions');
    const escCard = decEl.querySelector('[data-esc-card="p-esc"]');
    assert(escCard && escCard.textContent.includes('Trình cấp trên'), 'escalation card rendered in Việc của bác sĩ');
    assert(escCard.querySelectorAll('[data-esc-opt]').length === 3, 'escalation card renders 3 option buttons');
    const ta = escCard.querySelector('[data-esc-text="p-esc"]');
    assert(ta, 'escalation card renders free-text directive textarea');
    ta.value = 'Ưu tiên sửa xong sớm';
    await escCard.querySelector('[data-esc-opt="retry_repair_cycle"]').onclick();
    assert(posts.some(p => p.url === '/api/project/p-esc/answer-question' && p.body.option_id === 'retry_repair_cycle' && p.body.text === 'Ưu tiên sửa xong sớm'), 'escalation option posts answer-question');

    const startReminder = decEl.querySelector('#btn-todo-start-factory');
    assert(startReminder && startReminder.textContent.includes('Bật xưởng xử lý ngay'), 'stopped factory reminder button rendered when blocked unhandled');
    await startReminder.onclick();
    assert(posts.some(p => p.url === '/api/factory/start'), 'reminder button starts factory');
    ''')
