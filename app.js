/* 데일리 투두 — 개인용 달력 투두리스트
 * 데이터: localStorage 'daily-todo-v1' (기기 안에만 저장)
 *   { v, items:[{id,name}], days:{ 'YYYY-MM-DD': { done:{id:true}, extra:[{id,name}], memo:{id:'...'} } } }
 *   - items: 모든 날짜에 공통인 기본 항목(항목 편집에서 관리)
 *   - days[key].extra: 그날만의 '생각나는 일' 추가 목록
 *   - days[key].memo: 예전 버전의 항목별 메모(화면에는 쓰지 않고, 지우지 않고 그대로 보존)
 */
(() => {
  'use strict';

  const STORE_KEY = 'daily-todo-v1';
  const DEFAULT_NAMES = [
    '장신대 성경문제',
    '장신대 개론문제',
    '장신대 암송구절',
    '성경읽기',
    '중학 영어',
    '듀오링고 5',
    '전기가오리 독서',
    '시사인',
    '일반 서적',
    '기독교 서적',
    '계단운동',
    '걷기'
  ];
  const WEEK = ['일', '월', '화', '수', '목', '금', '토'];
  const CHECK_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5.5 12.6l4.2 4.2 8.8-9.4"/></svg>';
  const X_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>';
  const NAME_MAX = 40;

  const pad = (n) => String(n).padStart(2, '0');
  const keyOf = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const parseKey = (k) => {
    const [y, m, d] = k.split('-').map(Number);
    return new Date(y, m - 1, d);
  };
  const todayKey = () => keyOf(new Date());
  const rand = () => Math.random().toString(36).slice(2, 6);
  const uid = () => 'i' + Date.now().toString(36) + rand();
  const extraUid = () => 'e' + Date.now().toString(36) + rand();

  const $ = (sel) => document.querySelector(sel);

  /* ── 데이터 ───────────────────────────────────────── */
  function defaultState() {
    return {
      v: 2,
      items: DEFAULT_NAMES.map((name, i) => ({ id: 'd' + (i + 1), name })),
      days: {}
    };
  }

  function normalize(raw) {
    if (!raw || typeof raw !== 'object' || !Array.isArray(raw.items)) return null;
    const seen = new Set();
    const items = [];
    raw.items.forEach((it, idx) => {
      if (!it || typeof it.name !== 'string') return;
      const name = it.name.trim().slice(0, 30);
      if (!name) return;
      let id = typeof it.id === 'string' && it.id ? it.id : 'x' + idx + uid();
      while (seen.has(id)) id = id + '_' + idx;
      seen.add(id);
      items.push({ id, name });
    });
    const days = {};
    if (raw.days && typeof raw.days === 'object') {
      Object.keys(raw.days).forEach((k) => {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(k)) return;
        const src = raw.days[k];
        if (!src || typeof src !== 'object') return;

        // 그날만의 추가 항목
        const extra = [];
        const extraIds = new Set();
        if (Array.isArray(src.extra)) {
          src.extra.forEach((it, idx) => {
            if (!it || typeof it.name !== 'string') return;
            const name = it.name.trim().slice(0, NAME_MAX);
            if (!name) return;
            let id = typeof it.id === 'string' && it.id ? it.id : 'e' + idx + uid();
            while (extraIds.has(id) || seen.has(id)) id = id + '_' + idx;
            extraIds.add(id);
            extra.push({ id, name });
          });
        }

        // 예전 버전의 항목별 메모(화면에는 안 쓰지만 지우지 않고 보존)
        const memo = {};
        Object.keys(src.memo || {}).forEach((id) => {
          const v = src.memo[id];
          if (typeof v === 'string' && v.length && (seen.has(id) || extraIds.has(id))) {
            memo[id] = v.slice(0, 200);
          }
        });

        const done = {};
        Object.keys(src.done || {}).forEach((id) => {
          if (src.done[id] === true && (seen.has(id) || extraIds.has(id))) done[id] = true;
        });

        if (Object.keys(done).length || Object.keys(memo).length || extra.length) {
          days[k] = { done, extra, memo };
        }
      });
    }
    return { v: 2, items, days };
  }

  function loadState() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (!raw) return null;
      return normalize(JSON.parse(raw));
    } catch (e) {
      return null;
    }
  }

  let state = loadState() || defaultState();

  function save() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(state));
    } catch (e) {
      /* 저장 공간이 없는 경우는 조용히 넘어간다 */
    }
  }

  function dayOf(key, create) {
    let day = state.days[key];
    if (!day && create) {
      day = { done: {}, extra: [], memo: {} };
      state.days[key] = day;
    }
    if (day && !Array.isArray(day.extra)) day.extra = [];
    return day;
  }

  function pruneDay(key) {
    const day = state.days[key];
    if (!day) return;
    if (!Object.keys(day.done).length && !Object.keys(day.memo).length && !(day.extra || []).length) {
      delete state.days[key];
    }
  }

  function extrasOf(key) {
    const day = state.days[key];
    return day && Array.isArray(day.extra) ? day.extra : [];
  }

  /* ── 상태(화면) ────────────────────────────────────── */
  let selected = todayKey();
  const start = parseKey(selected);
  let view = { y: start.getFullYear(), m: start.getMonth() };
  let toastTimer = null;
  let undoAction = null;
  let highlightId = null;

  /* ── 계산 ─────────────────────────────────────────── */
  function idsFor(key) {
    const ids = state.items.map((it) => it.id);
    extrasOf(key).forEach((it) => ids.push(it.id));
    return ids;
  }

  function statsFor(key) {
    const day = state.days[key];
    const ids = idsFor(key);
    const total = ids.length;
    let count = 0;
    if (day) for (const id of ids) if (day.done[id]) count++;
    const ratio = total ? count / total : 0;
    let level = 0;
    if (total && ratio === 1) level = 3;
    else if (ratio >= 0.5) level = 2;
    else if (ratio > 0) level = 1;
    return { count, total, ratio, level };
  }

  function labelFor(key) {
    const t = todayKey();
    if (key === t) return '오늘';
    const d = parseKey(key);
    const t0 = parseKey(t);
    const diff = Math.round((d - t0) / 86400000);
    if (diff === -1) return '어제';
    if (diff === 1) return '내일';
    return `${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEK[d.getDay()]})`;
  }

  /* ── 달력 ─────────────────────────────────────────── */
  const dayGrid = $('#dayGrid');

  function renderCalendar() {
    const first = new Date(view.y, view.m, 1);
    const startPad = first.getDay();
    const daysInMonth = new Date(view.y, view.m + 1, 0).getDate();
    const cellCount = Math.ceil((startPad + daysInMonth) / 7) * 7;
    const tKey = todayKey();

    $('#calTitle').textContent = `${view.y}년 ${view.m + 1}월`;

    const frag = document.createDocumentFragment();
    for (let i = 0; i < cellCount; i++) {
      const num = i - startPad + 1;
      if (num < 1 || num > daysInMonth) {
        const blank = document.createElement('div');
        blank.className = 'day-blank';
        frag.appendChild(blank);
        continue;
      }
      const key = `${view.y}-${pad(view.m + 1)}-${pad(num)}`;
      const st = statsFor(key);
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'day lv' + st.level + (key === selected ? ' sel' : '') + (key === tKey ? ' today' : '');
      btn.dataset.date = key;
      btn.setAttribute('aria-pressed', key === selected ? 'true' : 'false');
      btn.setAttribute('aria-label', `${view.m + 1}월 ${num}일 ${WEEK[i % 7]}요일, ${st.total}개 중 ${st.count}개 완료`);

      const numEl = document.createElement('span');
      numEl.className = 'num';
      numEl.textContent = String(num);
      const markEl = document.createElement('span');
      markEl.className = 'mark';
      markEl.setAttribute('aria-hidden', 'true');
      if (st.level === 3) markEl.textContent = '✓';
      btn.append(numEl, markEl);
      frag.appendChild(btn);
    }
    dayGrid.innerHTML = '';
    dayGrid.appendChild(frag);
  }

  /* ── 요약 ─────────────────────────────────────────── */
  function renderSummary() {
    const st = statsFor(selected);
    $('#summaryDate').textContent = labelFor(selected);
    $('#doneCount').textContent = String(st.count);
    $('#totalCount').textContent = String(st.total);
    $('#summaryBar').setAttribute('aria-valuenow', String(Math.round(st.ratio * 100)));
    $('#barFill').style.width = (st.ratio * 100).toFixed(1) + '%';

    const countEl = document.querySelector('.summary-count');
    const msg = $('#summaryMsg');
    let text;
    if (!st.total) {
      countEl.classList.remove('done-all');
      text = '항목이 없어요. 아래 빈칸에 적거나 ‘항목 편집’에서 추가해 보세요.';
      msg.classList.remove('all');
    } else if (st.count === st.total) {
      countEl.classList.add('done-all');
      text = '오늘 할 일을 모두 끝냈어요! 🎉';
      msg.classList.add('all');
    } else {
      countEl.classList.remove('done-all');
      msg.classList.remove('all');
      if (st.count === 0) text = '오늘 할 일을 하나씩 시작해 볼까요?';
      else text = `${st.total - st.count}개 남았어요. 이대로만 가요!`;
    }
    msg.textContent = text;
  }

  /* ── 목록 ─────────────────────────────────────────── */
  const todoList = $('#todoList');

  function buildRow(item, day, isExtra) {
    const done = !!(day && day.done[item.id]);

    const li = document.createElement('li');
    li.className = 'todo' + (done ? ' done' : '') + (isExtra ? ' todo-extra' : '');
    if (item.id === highlightId) li.classList.add('is-new');
    li.dataset.id = item.id;

    const check = document.createElement('button');
    check.type = 'button';
    check.className = 'check';
    check.dataset.act = 'toggle';
    check.setAttribute('role', 'checkbox');
    check.setAttribute('aria-checked', done ? 'true' : 'false');
    check.setAttribute('aria-label', `${item.name} 완료`);
    check.innerHTML = CHECK_SVG;

    const main = document.createElement('div');
    main.className = 'todo-main';

    const name = document.createElement('span');
    name.className = 'todo-name';
    name.textContent = item.name;

    main.append(name);

    if (isExtra) {
      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'todo-del';
      del.dataset.act = 'del-extra';
      del.setAttribute('aria-label', `${item.name} 지우기`);
      del.title = '지우기';
      del.innerHTML = X_SVG;
      main.append(del);
    }

    li.append(check, main);
    return li;
  }

  function renderList() {
    const day = state.days[selected];
    const extras = extrasOf(selected);
    todoList.innerHTML = '';

    if (!state.items.length && !extras.length) {
      const empty = document.createElement('li');
      empty.className = 'empty';
      empty.innerHTML = '아직 항목이 없어요.<br>아래 빈칸에 적거나 <b>항목 편집</b>에서 추가해 보세요.';
      todoList.appendChild(empty);
      highlightId = null;
      return;
    }

    const frag = document.createDocumentFragment();
    for (const item of state.items) frag.appendChild(buildRow(item, day, false));
    for (const item of extras) frag.appendChild(buildRow(item, day, true));
    todoList.appendChild(frag);
    highlightId = null;
  }

  function setChecked(li, on, animate) {
    const item = state.items.find((it) => it.id === li.dataset.id);
    const extra = item ? null : extrasOf(selected).find((it) => it.id === li.dataset.id);
    const label = item ? item.name : (extra ? extra.name : '');
    const check = li.querySelector('.check');
    li.classList.toggle('done', on);
    if (check) {
      check.setAttribute('aria-checked', on ? 'true' : 'false');
      if (label) check.setAttribute('aria-label', `${label} 완료`);
      if (animate) {
        check.classList.remove('pop');
        void check.offsetWidth;
        check.classList.add('pop');
      }
    }
  }

  function toggleItem(id, animate) {
    const day = dayOf(selected, true);
    if (day.done[id]) delete day.done[id];
    else day.done[id] = true;
    const on = !!day.done[id];
    pruneDay(selected);
    save();

    const li = todoList.querySelector(`.todo[data-id="${CSS.escape(id)}"]`);
    if (li) setChecked(li, on, animate);
    renderSummary();
    renderCalendar();
  }

  /* ── 그날만의 추가 항목 ────────────────────────────── */
  function addExtra(name) {
    const v = name.trim().replace(/\s+/g, ' ').slice(0, NAME_MAX);
    if (!v) return;
    const day = dayOf(selected, true);
    const item = { id: extraUid(), name: v };
    day.extra.push(item);
    highlightId = item.id;
    save();
    renderList();
    renderSummary();
    renderCalendar();
    const row = todoList.querySelector(`.todo[data-id="${CSS.escape(item.id)}"]`);
    if (row && row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
  }

  function removeExtra(id) {
    const day = state.days[selected];
    if (!day || !Array.isArray(day.extra)) return;
    const idx = day.extra.findIndex((it) => it.id === id);
    if (idx < 0) return;
    const snapshot = JSON.parse(JSON.stringify(state));
    const removed = day.extra[idx];
    day.extra.splice(idx, 1);
    delete day.done[id];
    pruneDay(selected);
    save();
    renderAll();
    showToast(`‘${removed.name}’을 지웠어요`, '되돌리기', () => {
      state = snapshot;
      save();
      renderAll();
    });
  }

  /* ── 이벤트: 달력/목록 ─────────────────────────────── */
  dayGrid.addEventListener('click', (e) => {
    const btn = e.target.closest('.day');
    if (!btn || !btn.dataset.date) return;
    selectDate(btn.dataset.date);
  });

  function selectDate(key) {
    if (key === selected) return;
    selected = key;
    const d = parseKey(key);
    if (d.getMonth() !== view.m || d.getFullYear() !== view.y) view = { y: d.getFullYear(), m: d.getMonth() };
    renderCalendar();
    renderList();
    renderSummary();
  }

  $('#prevMonth').addEventListener('click', () => {
    view.m -= 1;
    if (view.m < 0) { view.m = 11; view.y -= 1; }
    renderCalendar();
  });

  $('#nextMonth').addEventListener('click', () => {
    view.m += 1;
    if (view.m > 11) { view.m = 0; view.y += 1; }
    renderCalendar();
  });

  $('#todayBtn').addEventListener('click', () => {
    const t = todayKey();
    const d = parseKey(t);
    view = { y: d.getFullYear(), m: d.getMonth() };
    selected = t;
    renderCalendar();
    renderList();
    renderSummary();
  });

  todoList.addEventListener('click', (e) => {
    const del = e.target.closest('[data-act="del-extra"]');
    if (del) {
      const li = del.closest('.todo');
      if (li) removeExtra(li.dataset.id);
      return;
    }
    const btn = e.target.closest('[data-act="toggle"]');
    if (!btn) return;
    const li = btn.closest('.todo');
    if (li) toggleItem(li.dataset.id, true);
  });

  /* ── 맨 아래 빈칸: 그날 생각나는 일 ─────────────────── */
  const quickForm = $('#quickAdd');
  const quickInput = $('#quickInput');

  quickForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const name = quickInput.value;
    if (!name.trim()) {
      quickInput.focus();
      return;
    }
    addExtra(name);
    quickInput.value = '';
    quickInput.focus({ preventScroll: true });
  });

  /* ── 편집 시트 ─────────────────────────────────────── */
  const backdrop = $('#sheetBackdrop');
  const editList = $('#editList');
  const addInput = $('#addInput');

  const UP_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 14.5l6-6 6 6"/></svg>';
  const DOWN_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9.5l6 6 6-6"/></svg>';
  const DEL_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';

  function iconButton(cls, svg, label, disabled) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'icon-btn ' + cls;
    b.innerHTML = svg;
    b.setAttribute('aria-label', label);
    b.title = label;
    b.disabled = !!disabled;
    return b;
  }

  function renderEditList() {
    editList.innerHTML = '';
    if (!state.items.length) {
      const li = document.createElement('li');
      li.className = 'sheet-note';
      li.textContent = '항목이 없어요. 아래에서 추가해 주세요.';
      editList.appendChild(li);
      return;
    }
    state.items.forEach((item, idx) => {
      const li = document.createElement('li');
      li.className = 'edit-row';
      li.dataset.id = item.id;

      const num = document.createElement('span');
      num.className = 'edit-idx';
      num.textContent = String(idx + 1);

      const input = document.createElement('input');
      input.type = 'text';
      input.className = 'edit-name';
      input.value = item.name;
      input.maxLength = 30;
      input.dataset.act = 'rename';
      input.setAttribute('aria-label', `${idx + 1}번 항목 이름`);

      const actions = document.createElement('div');
      actions.className = 'edit-actions';

      const up = iconButton('up', UP_SVG, '위로', idx === 0);
      up.dataset.act = 'up';
      const down = iconButton('down', DOWN_SVG, '아래로', idx === state.items.length - 1);
      down.dataset.act = 'down';
      const del = iconButton('del', DEL_SVG, `${item.name} 삭제`);
      del.dataset.act = 'del';

      actions.append(up, down, del);
      li.append(num, input, actions);
      editList.appendChild(li);
    });
  }

  function openSheet() {
    renderEditList();
    backdrop.hidden = false;
    document.body.classList.add('sheet-open');
  }

  function closeSheet() {
    backdrop.hidden = true;
    document.body.classList.remove('sheet-open');
    $('#editBtn').focus({ preventScroll: true });
  }

  $('#editBtn').addEventListener('click', openSheet);
  $('#sheetClose').addEventListener('click', closeSheet);
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) closeSheet();
  });

  editList.addEventListener('input', (e) => {
    const input = e.target.closest('.edit-name');
    if (!input) return;
    const li = input.closest('.edit-row');
    const item = state.items.find((it) => it.id === li.dataset.id);
    if (!item) return;
    const v = input.value.slice(0, 30);
    item.name = v || '이름 없음';
    save();
    syncNames();
  });

  editList.addEventListener('blur', (e) => {
    const input = e.target.closest('.edit-name');
    if (!input) return;
    const li = input.closest('.edit-row');
    const item = state.items.find((it) => it.id === li.dataset.id);
    if (!item) return;
    if (!input.value.trim()) {
      item.name = '이름 없음';
      input.value = item.name;
      save();
      syncNames();
    }
  }, true);

  function syncNames() {
    todoList.querySelectorAll('.todo').forEach((li) => {
      const item = state.items.find((it) => it.id === li.dataset.id);
      if (!item) return;
      const name = li.querySelector('.todo-name');
      if (name && name.textContent !== item.name) name.textContent = item.name;
      const check = li.querySelector('.check');
      if (check) check.setAttribute('aria-label', `${item.name} 완료`);
    });
  }

  editList.addEventListener('click', (e) => {
    const btn = e.target.closest('.icon-btn');
    if (!btn) return;
    const li = btn.closest('.edit-row');
    const idx = state.items.findIndex((it) => it.id === li.dataset.id);
    if (idx < 0) return;

    if (btn.dataset.act === 'up' && idx > 0) {
      [state.items[idx - 1], state.items[idx]] = [state.items[idx], state.items[idx - 1]];
      save();
      renderEditList();
      renderList();
    } else if (btn.dataset.act === 'down' && idx < state.items.length - 1) {
      [state.items[idx + 1], state.items[idx]] = [state.items[idx], state.items[idx + 1]];
      save();
      renderEditList();
      renderList();
    } else if (btn.dataset.act === 'del') {
      removeItem(idx);
    }
  });

  function removeItem(idx) {
    const item = state.items[idx];
    if (!item) return;
    const snapshot = JSON.parse(JSON.stringify(state));
    state.items.splice(idx, 1);
    Object.keys(state.days).forEach((k) => {
      const day = state.days[k];
      delete day.done[item.id];
      delete day.memo[item.id];
      pruneDay(k);
    });
    save();
    renderAll();
    renderEditList();
    showToast(`‘${item.name}’ 항목을 삭제했어요`, '되돌리기', () => {
      state = snapshot;
      save();
      renderAll();
      renderEditList();
    });
  }

  $('#addForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const name = addInput.value.trim();
    if (!name) {
      addInput.focus();
      return;
    }
    state.items.push({ id: uid(), name: name.slice(0, 30) });
    save();
    addInput.value = '';
    renderAll();
    renderEditList();
    addInput.focus();
    const body = document.querySelector('.sheet-body');
    if (body) body.scrollTop = body.scrollHeight;
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !backdrop.hidden) closeSheet();
  });

  /* ── 백업 ─────────────────────────────────────────── */
  $('#exportBtn').addEventListener('click', () => {
    const payload = {
      app: 'daily-todo',
      version: 2,
      exportedAt: new Date().toISOString(),
      items: state.items,
      days: state.days
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `daily-todo-backup-${todayKey()}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    showToast('JSON 파일로 내보냈어요');
  });

  $('#importBtn').addEventListener('click', () => $('#importFile').click());

  $('#importFile').addEventListener('change', (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      let data = null;
      try {
        data = normalize(JSON.parse(String(reader.result)));
      } catch (err) {
        data = null;
      }
      if (!data) {
        showToast('이 파일은 불러올 수 없어요');
        return;
      }
      if (!window.confirm('지금 기록을 이 파일의 내용으로 바꿀까요? 지금 기록은 사라져요.')) return;
      state = data;
      save();
      renderAll();
      renderEditList();
      showToast('기록을 불러왔어요');
    };
    reader.onerror = () => showToast('파일을 읽지 못했어요');
    reader.readAsText(file);
  });

  /* ── 토스트 ───────────────────────────────────────── */
  const toast = $('#toast');
  const toastText = $('#toastText');
  const toastBtn = $('#toastBtn');

  function showToast(text, actionLabel, action) {
    toastText.textContent = text;
    undoAction = typeof action === 'function' ? action : null;
    if (undoAction && actionLabel) {
      toastBtn.textContent = actionLabel;
      toastBtn.hidden = false;
    } else {
      toastBtn.hidden = true;
    }
    toast.hidden = false;
    toast.classList.remove('show');
    void toast.offsetWidth;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(hideToast, undoAction ? 6000 : 2600);
  }

  function hideToast() {
    toast.classList.remove('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.hidden = true;
      toastBtn.hidden = true;
      undoAction = null;
    }, 220);
  }

  toastBtn.addEventListener('click', () => {
    const fn = undoAction;
    undoAction = null;
    hideToast();
    if (fn) fn();
  });

  /* ── 전체 렌더 ─────────────────────────────────────── */
  function renderAll() {
    renderCalendar();
    renderList();
    renderSummary();
  }

  function renderHeaderDate() {
    const d = new Date();
    $('#todayLine').textContent = `${d.getMonth() + 1}월 ${d.getDate()}일 ${WEEK[d.getDay()]}요일 · 매일 조금씩`;
  }

  renderHeaderDate();
  renderAll();

  /* 자정을 넘기면 '오늘' 표시를 새로 잡는다 */
  let lastToday = todayKey();
  setInterval(() => {
    const t = todayKey();
    if (t === lastToday) return;
    lastToday = t;
    renderHeaderDate();
    renderCalendar();
    renderSummary();
  }, 60000);

  /* PWA 서비스워커 */
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('./sw.js').catch(() => {});
    });
  }
})();
