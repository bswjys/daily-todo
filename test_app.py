"""데일리 투두 — Playwright 검증 (390×844 모바일 / 1280×800 PC)

    LD_LIBRARY_PATH=/workspace/.browserlibs/lib python3 test_app.py

검증
- 기본 12개 항목에 메모 입력칸이 없고 '체크 동그라미 + 이름'만 있는지
- 맨 아래 자유 추가 빈칸: Enter·버튼 추가, 그날만 표시, 체크·지우기(되돌리기),
  새로고침 유지, 날짜별 독립
- 요약 카운트·달력 색상이 그날 추가 항목까지 포함하는지(1~49 / 50~99 / 100%)
- 루틴 카드 접기/펴기: 헤더 클릭·버튼, 접혀도 진행률/막대 표시, 새로고침 유지
- 예정사항 카드: 추가·체크·지우기·내일로 미루기(되돌리기)·접기/펴기, 배지
- 달력 예정 점 표시, 루틴 달성률·달력 색과 분리
- 예전 데이터(항목별 메모 포함) 호환, 새 plans 데이터 보존, 깨진 저장값 복구
- 항목 편집(추가·이름·순서·삭제), 백업, 월 이동
- 콘솔 오류 0, 가로 넘침 0 (390 / 1280)
- 대표 스크린샷 downloads/daily_todo/01_home_390.png, 02_checked_390.png
"""
import functools
import http.server
import json
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
SHOTS = '/workspace/downloads/daily_todo'
os.makedirs(SHOTS, exist_ok=True)
REPO_SHOTS = os.path.join(ROOT, 'shots')
os.makedirs(REPO_SHOTS, exist_ok=True)

PASSES, FAILS = [], []


def check(name, cond, extra=''):
    if cond:
        PASSES.append(name)
        print('PASS  ' + name)
    else:
        FAILS.append(name)
        print('FAIL  ' + name + (' — ' + str(extra) if extra else ''))


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Handler, directory=ROOT))
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d/' % PORT

DEFAULT_NAMES = [
    '장신대 성경문제', '장신대 개론문제', '장신대 암송구절', '성경읽기', '중학 영어',
    '듀오링고 5', '전기가오리 독서', '시사인', '일반 서적', '기독교 서적', '계단운동', '걷기'
]


def new_page(browser, w=390, h=844, mobile=True):
    ctx = browser.new_context(
        viewport={'width': w, 'height': h},
        timezone_id='Asia/Seoul',
        locale='ko-KR',
        device_scale_factor=2 if mobile else 1,
        has_touch=mobile,
        is_mobile=mobile,
    )
    pg = ctx.new_page()
    errors = []
    pg.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
    pg.errors = errors
    return ctx, pg


def fresh(pg):
    pg.goto(BASE + 'index.html', wait_until='domcontentloaded')
    pg.evaluate('localStorage.clear()')
    pg.reload(wait_until='networkidle')
    pg.wait_for_timeout(300)


def reload(pg):
    pg.reload(wait_until='networkidle')
    pg.wait_for_timeout(320)


def today_key(pg):
    return shift_key(pg, 0)


def shift_key(pg, n):
    return pg.evaluate("""(n) => {
      const d = new Date(); d.setDate(d.getDate() + n);
      const p = x => String(x).padStart(2,'0');
      return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`;
    }""", n)


def future_key(pg, n):
    """오늘+n일. 달력이 이번 달만 그리므로 월말이면 이번 달 마지막 날로 붙인다."""
    return pg.evaluate("""(n) => {
      const now = new Date();
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + n);
      const p = x => String(x).padStart(2,'0');
      if (d.getMonth() !== now.getMonth()) {
        const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        return `${last.getFullYear()}-${p(last.getMonth()+1)}-${p(last.getDate())}`;
      }
      return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`;
    }""", n)


def rows(pg):
    return pg.evaluate("""() => Array.from(document.querySelectorAll('#todoList .todo')).map(li => {
      const main = li.querySelector('.todo-main');
      return {
        id: li.dataset.id,
        name: li.querySelector('.todo-name').textContent,
        done: li.classList.contains('done'),
        aria: li.querySelector('.check').getAttribute('aria-checked'),
        extra: li.classList.contains('todo-extra'),
        inputs: main.querySelectorAll('input, textarea').length,
        children: main.children.length,
        hasDel: !!li.querySelector('.todo-del'),
        height: Math.round(li.getBoundingClientRect().height)
      };
    })""")


def plan_rows(pg):
    return pg.evaluate("""() => Array.from(document.querySelectorAll('#planList .todo')).map(li => {
      const later = li.querySelector('.plan-later');
      const del = li.querySelector('.todo-del');
      return {
        id: li.dataset.id,
        name: li.querySelector('.todo-name').textContent,
        done: li.classList.contains('done'),
        aria: li.querySelector('.check').getAttribute('aria-checked'),
        hasLater: !!later,
        laterVisible: !!(later && later.offsetParent !== null),
        laterText: later ? later.textContent : '',
        laterW: later ? Math.round(later.getBoundingClientRect().width) : 0,
        hasDel: !!del,
        height: Math.round(li.getBoundingClientRect().height)
      };
    })""")


def day_cell(pg, key):
    return pg.evaluate("""(k) => {
      const b = document.querySelector(`.day[data-date="${k}"]`);
      if (!b) return null;
      const cs = getComputedStyle(b);
      const d = b.querySelector('.dot');
      const dcs = d ? getComputedStyle(d) : null;
      const box = b.getBoundingClientRect();
      const dbox = d ? d.getBoundingClientRect() : null;
      return {
        cls: b.className, bg: cs.backgroundColor, color: cs.color,
        num: b.querySelector('.num').textContent,
        mark: b.querySelector('.mark').textContent,
        dot: d ? { cls: d.className, bg: dcs.backgroundColor, vis: dcs.visibility,
                   w: Math.round(dbox.width), inside: dbox.bottom <= box.bottom + 0.5 } : null,
        aria: b.getAttribute('aria-label')
      };
    }""", key)


def summary(pg):
    return pg.evaluate("""() => ({
      date: document.querySelector('#summaryDate').textContent,
      sub: document.querySelector('#summarySub').textContent,
      subHidden: document.querySelector('#summarySub').hidden,
      done: Number(document.querySelector('#doneCount').textContent),
      total: Number(document.querySelector('#totalCount').textContent),
      msg: document.querySelector('#summaryMsg').textContent,
      barW: document.querySelector('#barFill').style.width,
      barNow: document.querySelector('#summaryBar').getAttribute('aria-valuenow')
    })""")


def plan_badge(pg):
    return pg.evaluate("""() => {
      const b = document.querySelector('#planBadge');
      return { text: b.textContent, cls: b.className, visible: b.offsetParent !== null };
    }""")


def fold(pg, which):
    card = '#routineCard' if which == 'routine' else '#planCard'
    btn = '#routineFold' if which == 'routine' else '#planFold'
    body = '#routineBody' if which == 'routine' else '#planBody'
    return pg.evaluate("""([card, btn, body]) => ({
      collapsed: document.querySelector(card).classList.contains('collapsed'),
      expanded: document.querySelector(btn).getAttribute('aria-expanded'),
      label: document.querySelector(btn).getAttribute('aria-label'),
      bodyVisible: document.querySelector(body).offsetParent !== null,
      btnVisible: document.querySelector(btn).offsetParent !== null
    })""", [card, btn, body])


def overflow(pg):
    return pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")


def stored(pg):
    return json.loads(pg.evaluate("localStorage.getItem('daily-todo-v1')"))


def ui_store(pg):
    raw = pg.evaluate("localStorage.getItem('daily-todo-ui')")
    return json.loads(raw) if raw else None


def check_all(pg):
    n = len(rows(pg))
    for i in range(n):
        if not rows(pg)[i]['done']:
            pg.click(f'#todoList .todo:nth-child({i + 1}) .check')
            pg.wait_for_timeout(35)
    pg.wait_for_timeout(260)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ── 모바일 ──────────────────────────────────────────────
        ctx, pg = new_page(browser)
        fresh(pg)
        tk = today_key(pg)

        check('제목/헤더 표시', pg.inner_text('h1') == '데일리 투두', pg.inner_text('h1'))
        ncells = pg.eval_on_selector_all('#dayGrid > *', 'els => els.length')
        check('달력 7칸 단위로 렌더', ncells % 7 == 0 and 35 <= ncells <= 42, ncells)
        check('기본 선택 = 오늘', pg.get_attribute('.day.sel', 'data-date') == tk)
        check('오늘 표시', 'today' in (day_cell(pg, tk) or {}).get('cls', ''))
        check('index.html 마크업 v=5', pg.eval_on_selector('script[src]', 'e => e.getAttribute("src")').endswith('?v=5'))
        check('styles.css v=5', pg.eval_on_selector('link[rel=stylesheet]', 'e => e.getAttribute("href")').endswith('?v=5'))
        sw_txt = pg.evaluate("fetch('./sw.js').then(r => r.text())")
        check('캐시 버전 daily-todo-v5', "'daily-todo-v5'" in sw_txt and "VERSION = '5'" in sw_txt)

        r = rows(pg)
        check('기본 항목 12개', len(r) == 12, len(r))
        check('항목 순서 일치', [x['name'] for x in r] == DEFAULT_NAMES, [x['name'] for x in r])

        # ① 항목별 메모 제거
        memo_n = pg.eval_on_selector_all('#todoList .memo', 'e => e.length')
        input_n = pg.eval_on_selector_all('#todoList .todo-main input', 'e => e.length')
        check('항목별 메모 입력칸 0개', memo_n == 0 and input_n == 0, (memo_n, input_n))
        check('12개 행 모두 입력칸 없음', all(x['inputs'] == 0 for x in r), [x['inputs'] for x in r])
        check('12개 행 = 체크 + 이름만', all(x['children'] == 1 and not x['hasDel'] for x in r),
              [(x['children'], x['hasDel']) for x in r])
        check('행 높이 48px 이하로 납작', pg.eval_on_selector('#todoList .todo', 'e => e.getBoundingClientRect().height') <= 48,
              pg.eval_on_selector('#todoList .todo', 'e => e.getBoundingClientRect().height'))

        # ② 맨 아래 빈칸
        check('맨 아래 자유 추가 칸 보임', pg.is_visible('#quickInput') and pg.is_visible('#quickBtn'))
        ph = pg.get_attribute('#quickInput', 'placeholder')
        check('빈칸 안내 문구', '생각나는' in ph, ph)
        check('추가 칸이 목록 맨 아래', pg.evaluate("""() => {
          const f = document.querySelector('#quickAdd').getBoundingClientRect();
          const list = document.querySelector('#todoList').getBoundingClientRect();
          return f.top >= list.bottom - 1;
        }"""))

        s = summary(pg)
        check('요약 0 / 12 완료', s['done'] == 0 and s['total'] == 12, s)
        check('요약 라벨 오늘', s['date'] == '오늘', s['date'])
        check('헤더에 날짜 함께 표시', not s['subHidden'] and '월' in s['sub'] and '일' in s['sub'], s)
        check('달력 lv0 기본', 'lv0' in day_cell(pg, tk)['cls'], day_cell(pg, tk)['cls'])

        # ── 루틴 카드 접기/펴기 ─────────────────────────────
        f = fold(pg, 'routine')
        check('루틴 카드 기본 펼침', not f['collapsed'] and f['expanded'] == 'true' and f['bodyVisible'], f)
        check('접기 버튼 헤더에 보임', f['btnVisible'] and '접기' in f['label'], f)
        pg.click('#routineFold')
        pg.wait_for_timeout(220)
        f = fold(pg, 'routine')
        check('접기 버튼 → 접힘', f['collapsed'] and f['expanded'] == 'false' and not f['bodyVisible'], f)
        check('접혀도 진행률 숫자 보임', pg.is_visible('#doneCount') and pg.is_visible('#totalCount'))
        check('접혀도 진행 막대 보임', pg.is_visible('#summaryBar')
              and pg.eval_on_selector('#summaryBar', 'e => e.getBoundingClientRect().height') >= 4)
        check('접힌 상태 localStorage 저장', (ui_store(pg) or {}).get('routineCollapsed') is True, ui_store(pg))
        reload(pg)
        f = fold(pg, 'routine')
        check('새로고침 후 접힘 유지', f['collapsed'] and not f['bodyVisible'], f)
        check('접힌 채로 요약 숫자 유지', summary(pg)['total'] == 12, summary(pg))
        pg.click('#routineHead')
        pg.wait_for_timeout(220)
        f = fold(pg, 'routine')
        check('헤더 클릭 → 다시 펼침', not f['collapsed'] and f['expanded'] == 'true' and f['bodyVisible'], f)
        check('펼침 상태 저장', (ui_store(pg) or {}).get('routineCollapsed') is False, ui_store(pg))
        reload(pg)
        check('새로고침 후 펼침 유지', not fold(pg, 'routine')['collapsed'] and fold(pg, 'routine')['bodyVisible'])
        check('펼친 뒤 목록 12개', len(rows(pg)) == 12, len(rows(pg)))

        # 1개 체크
        pg.click('#todoList .todo:nth-child(1) .check')
        pg.wait_for_timeout(320)
        s = summary(pg)
        check('1개 체크 → 요약 1 / 12', s['done'] == 1, s)
        check('1개 체크 → 진행바 8.3%', s['barW'].startswith('8.3'), s['barW'])
        check('체크된 행 done', rows(pg)[0]['done'] is True)
        check('체크 aria-checked', rows(pg)[0]['aria'] == 'true')
        c = day_cell(pg, tk)
        check('오늘 칸 lv1(연파랑)', 'lv1' in c['cls'] and c['bg'] == 'rgb(233, 242, 254)', c)

        # Enter 로 추가
        pg.fill('#quickInput', '약국 들르기')
        pg.press('#quickInput', 'Enter')
        pg.wait_for_timeout(260)
        r2 = rows(pg)
        check('Enter 로 그날 항목 추가 (13개)', len(r2) == 13, len(r2))
        check('추가한 항목 이름·위치', r2[-1]['name'] == '약국 들르기' and r2[-1]['extra'] is True, r2[-1])
        check('추가 항목은 입력칸 없이 체크+이름+✕', r2[-1]['inputs'] == 0 and r2[-1]['children'] == 2 and r2[-1]['hasDel'], r2[-1])
        check('추가 후 입력칸 비움', pg.input_value('#quickInput') == '', pg.input_value('#quickInput'))
        check('추가 후 입력칸 포커스 유지', pg.evaluate("document.activeElement.id") == 'quickInput',
              pg.evaluate("document.activeElement.id"))
        s = summary(pg)
        check('요약 총 13개로 반영', s['total'] == 13 and s['done'] == 1, s)
        d = stored(pg)
        check('localStorage 날짜별 저장', d['days'][tk]['extra'][0]['name'] == '약국 들르기', d['days'][tk].get('extra'))
        check('추가 항목은 기본 items에 안 들어감', len(d['items']) == 12, len(d['items']))

        extra_id = r2[-1]['id']
        pg.click(f'#todoList .todo[data-id="{extra_id}"] .check')
        pg.wait_for_timeout(280)
        s = summary(pg)
        check('추가 항목 체크 → 2 / 13', s['done'] == 2 and s['total'] == 13, s)
        check('추가 항목 체크 저장', stored(pg)['days'][tk]['done'].get(extra_id) is True)
        check('달력 aria 13개 중 2개', '13개 중 2개 완료' in day_cell(pg, tk)['aria'], day_cell(pg, tk)['aria'])

        # + 추가 버튼으로 한 개 더
        pg.fill('#quickInput', '세탁소 맡기기')
        pg.click('#quickBtn')
        pg.wait_for_timeout(260)
        r3 = rows(pg)
        check('버튼으로 추가 (14개)', len(r3) == 14 and r3[-1]['name'] == '세탁소 맡기기', len(r3))
        check('두 번째 추가 항목 요약 14', summary(pg)['total'] == 14, summary(pg))

        # 새로고침 유지
        reload(pg)
        r4 = rows(pg)
        check('새로고침 후 14개 유지', len(r4) == 14 and r4[-1]['name'] == '세탁소 맡기기', len(r4))
        check('새로고침 후 체크 유지', r4[0]['done'] and [x for x in r4 if x['id'] == extra_id][0]['done'], r4[0])
        check('새로고침 후 요약 2 / 14', summary(pg)['done'] == 2 and summary(pg)['total'] == 14, summary(pg))

        # 날짜별 독립 (어제)
        yk = shift_key(pg, -1)
        pg.click(f'.day[data-date="{yk}"]')
        pg.wait_for_timeout(250)
        ry = rows(pg)
        check('어제는 기본 12개만', len(ry) == 12 and all(not x['extra'] for x in ry), len(ry))
        check('어제는 체크 비어 있음', all(not x['done'] for x in ry))
        check('어제 라벨', summary(pg)['date'] == '어제', summary(pg)['date'])
        check('어제에도 날짜 함께 표시', not summary(pg)['subHidden'], summary(pg))
        pg.fill('#quickInput', '어제만 할 일')
        pg.press('#quickInput', 'Enter')
        pg.wait_for_timeout(240)
        pg.click('#todoList .todo:nth-child(5) .check')
        pg.wait_for_timeout(220)
        check('어제 1 / 13 (그날 추가 포함)', summary(pg)['done'] == 1 and summary(pg)['total'] == 13, summary(pg))

        # 오늘 복귀
        pg.click(f'.day[data-date="{tk}"]')
        pg.wait_for_timeout(250)
        r5 = rows(pg)
        check('오늘 복귀 시 14개 유지', len(r5) == 14, len(r5))
        check('오늘 복귀 시 체크 유지', r5[0]['done'] and r5[4]['done'] is False, r5[0])
        check('날짜별 추가 항목 섞이지 않음', sorted(x['name'] for x in r5[12:]) == sorted(['약국 들르기', '세탁소 맡기기']),
              [x['name'] for x in r5[12:]])

        # ── 예정사항 카드 ───────────────────────────────────
        check('예정사항 카드 보임', pg.is_visible('#planCard') and pg.inner_text('.plan-title') == '예정사항')
        check('예정사항 카드가 루틴 카드 바로 아래', pg.evaluate("""() => {
          const a = document.querySelector('#routineCard').getBoundingClientRect();
          const b = document.querySelector('#planCard').getBoundingClientRect();
          return b.top >= a.bottom - 1 && b.top - a.bottom < 24;
        }"""))
        check('예정사항 카드 흰 배경', pg.eval_on_selector('#planCard', "e => getComputedStyle(e).backgroundColor") == 'rgb(255, 255, 255)')
        check('예정사항 빈 상태 안내', '아직 예정사항이 없어요' in pg.inner_text('#planList'))
        check('예정사항 빈칸 안내 문구', '예정사항을 적어보세요' == pg.get_attribute('#planInput', 'placeholder'),
              pg.get_attribute('#planInput', 'placeholder'))
        b = plan_badge(pg)
        check('예정사항 배지 0건', b['text'] == '0건' and b['visible'], b)
        check('예정사항 기본 펼침', not fold(pg, 'plan')['collapsed'] and fold(pg, 'plan')['bodyVisible'])

        # Enter 로 예정사항 추가
        pg.fill('#planInput', '병원 예약 10시')
        pg.press('#planInput', 'Enter')
        pg.wait_for_timeout(260)
        pr = plan_rows(pg)
        check('예정사항 Enter 추가', len(pr) == 1 and pr[0]['name'] == '병원 예약 10시', pr)
        check('예정사항 줄 = 동그라미 + 내용 + 내일 + ✕',
              pr[0]['hasLater'] and pr[0]['laterVisible'] and '내일' in pr[0]['laterText'] and pr[0]['hasDel']
              and pr[0]['height'] <= 52, pr[0])
        check('예정사항 내일 버튼 작고 깔끔', 30 <= pr[0]['laterW'] <= 60, pr[0]['laterW'])
        check('예정사항 추가 후 빈칸 비움', pg.input_value('#planInput') == '', pg.input_value('#planInput'))
        check('예정사항 저장(days.plans)', stored(pg)['days'][tk]['plans'][0]['name'] == '병원 예약 10시',
              stored(pg)['days'][tk].get('plans'))
        check('예정사항은 기본 items 에 안 들어감', len(stored(pg)['items']) == 12)
        check('예정사항 추가해도 루틴 총계 그대로 14', summary(pg)['total'] == 14 and summary(pg)['done'] == 2, summary(pg))
        check('예정사항 배지 남은 1건', plan_badge(pg)['text'] == '남은 1건', plan_badge(pg))
        check('예정사항 배지 주황', plan_badge(pg)['cls'].find('left') >= 0, plan_badge(pg))

        # 달력 예정 점
        c = day_cell(pg, tk)
        check('달력에 예정 점 표시', c['dot'] and c['dot']['vis'] == 'visible' and c['dot']['w'] >= 3, c['dot'])
        check('예정 점이 칸 안에 들어감', c['dot']['inside'], c['dot'])
        check('예정 점 주황', c['dot']['bg'] == 'rgb(245, 158, 11)', c['dot']['bg'])
        check('예정 점은 루틴 색(연파랑)과 별개', 'lv1' in c['cls'] and c['bg'] == 'rgb(233, 242, 254)', c)
        check('달력 aria 에 예정사항 안내', '예정사항 1건 중 0건 완료' in c['aria'], c['aria'])
        fc = day_cell(pg, shift_key(pg, 2))
        check('예정 없는 날은 점 숨김(자리 유지)', fc['dot'] and fc['dot']['vis'] == 'hidden', fc['dot'])

        # 버튼으로 두 번째 추가
        pg.fill('#planInput', '은행 들르기')
        pg.click('#planBtn')
        pg.wait_for_timeout(240)
        pr = plan_rows(pg)
        check('예정사항 버튼 추가 (2건)', len(pr) == 2 and pr[1]['name'] == '은행 들르기', len(pr))
        check('예정사항 2건이어도 루틴 14 그대로', summary(pg)['total'] == 14, summary(pg))
        check('배지 남은 2건', plan_badge(pg)['text'] == '남은 2건', plan_badge(pg))

        # 체크
        pg.click(f'#planList .todo[data-id="{pr[0]["id"]}"] .check')
        pg.wait_for_timeout(280)
        pr = plan_rows(pg)
        check('예정사항 체크 → done', pr[0]['done'] and pr[0]['aria'] == 'true', pr[0])
        check('체크한 예정사항은 내일 버튼 숨김', not pr[0]['laterVisible'] and pr[1]['laterVisible'], pr)
        check('예정사항 체크해도 루틴 완료수 2 그대로', summary(pg)['done'] == 2 and summary(pg)['total'] == 14, summary(pg))
        check('예정사항 체크 저장', stored(pg)['days'][tk]['plans'][0]['done'] is True, stored(pg)['days'][tk]['plans'])
        check('배지 남은 1건', plan_badge(pg)['text'] == '남은 1건', plan_badge(pg))

        # 모두 완료 → 배지 '모두 완료', 점 회색
        pg.click(f'#planList .todo[data-id="{pr[1]["id"]}"] .check')
        pg.wait_for_timeout(280)
        check('예정사항 모두 완료 배지', plan_badge(pg)['text'] == '모두 완료', plan_badge(pg))
        c = day_cell(pg, tk)
        check('모두 끝난 날 점은 회색', c['dot']['bg'] == 'rgb(201, 208, 216)', c['dot'])
        check('예정 완료는 달력 색·루틴 %에 영향 없음',
              'lv1' in c['cls'] and summary(pg)['done'] == 2 and summary(pg)['total'] == 14, (c['cls'], summary(pg)))

        # 내일로 미루기 (+ 되돌리기)
        pg.fill('#planInput', '우체국')
        pg.press('#planInput', 'Enter')
        pg.wait_for_timeout(240)
        pr = plan_rows(pg)
        check('세 번째 예정사항 추가', len(pr) == 3 and pr[-1]['name'] == '우체국', len(pr))
        pg.click(f'#planList .todo[data-id="{pr[-1]["id"]}"] [data-act="plan-later"]')
        pg.wait_for_timeout(320)
        nk = shift_key(pg, 1)
        check('내일로 미루면 오늘 목록에서 사라짐', [x['name'] for x in plan_rows(pg)] == ['병원 예약 10시', '은행 들르기'],
              [x['name'] for x in plan_rows(pg)])
        check('미루기 토스트', pg.is_visible('#toast') and '내일로 미뤘어요' in pg.inner_text('#toastText'),
              pg.inner_text('#toastText'))
        check('미루기 저장: 다음 날 plans', stored(pg)['days'][nk]['plans'][0]['name'] == '우체국',
              stored(pg)['days'].get(nk, {}).get('plans'))
        check('미루기 저장: 오늘 plans 2건', len(stored(pg)['days'][tk]['plans']) == 2, stored(pg)['days'][tk]['plans'])
        check('다음 날 달력에 예정 점', day_cell(pg, nk)['dot']['vis'] == 'visible', day_cell(pg, nk)['dot'])
        check('미루기는 루틴 개수에 영향 없음', summary(pg)['total'] == 14)
        pg.click('#toastBtn')
        pg.wait_for_timeout(320)
        check('미루기 되돌리기 → 오늘 3건 복원', len(plan_rows(pg)) == 3, len(plan_rows(pg)))
        check('미루기 되돌리기 → 다음 날 plans 없음', 'plans' not in stored(pg)['days'].get(nk, {}),
              stored(pg)['days'].get(nk))

        # 다시 미루고 새로고침 → 다음 날로 이동 유지
        pr = plan_rows(pg)
        pg.click(f'#planList .todo[data-id="{pr[-1]["id"]}"] [data-act="plan-later"]')
        pg.wait_for_timeout(300)
        reload(pg)
        check('미룬 뒤 새로고침: 오늘 2건', len(plan_rows(pg)) == 2, len(plan_rows(pg)))
        pg.click(f'.day[data-date="{nk}"]')
        pg.wait_for_timeout(260)
        check('내일 날짜에 미룬 예정사항 보임', [x['name'] for x in plan_rows(pg)] == ['우체국'],
              [x['name'] for x in plan_rows(pg)])
        check('내일 날짜 루틴은 기본 12개', len(rows(pg)) == 12 and summary(pg)['total'] == 12, summary(pg))
        check('내일 예정 배지 남은 1건', plan_badge(pg)['text'] == '남은 1건', plan_badge(pg))

        # 미래 날짜 예정사항: 그날에서 '내일' → date+1
        pg.fill('#planInput', '치과')
        pg.press('#planInput', 'Enter')
        pg.wait_for_timeout(240)
        pr = plan_rows(pg)
        pg.click(f'#planList .todo[data-id="{pr[-1]["id"]}"] [data-act="plan-later"]')
        pg.wait_for_timeout(300)
        check('미래 날짜에서 미루면 다음 날로', stored(pg)['days'][shift_key(pg, 2)]['plans'][0]['name'] == '치과',
              stored(pg)['days'].get(shift_key(pg, 2), {}).get('plans'))
        check('미래 날짜 미루기 토스트는 다음 날', '다음 날로 미뤘어요' in pg.inner_text('#toastText'), pg.inner_text('#toastText'))

        # 오늘로 돌아와 예정사항 삭제 + 되돌리기
        pg.click(f'.day[data-date="{tk}"]')
        pg.wait_for_timeout(260)
        before = [x['name'] for x in plan_rows(pg)]
        target = plan_rows(pg)[-1]
        pg.click(f'#planList .todo[data-id="{target["id"]}"] [data-act="plan-del"]')
        pg.wait_for_timeout(280)
        check('예정사항 ✕ 삭제', len(plan_rows(pg)) == 1 and plan_rows(pg)[0]['name'] != target['name'], len(plan_rows(pg)))
        check('삭제 토스트', '지웠어요' in pg.inner_text('#toastText'), pg.inner_text('#toastText'))
        check('삭제 저장', len(stored(pg)['days'][tk]['plans']) == 1, stored(pg)['days'][tk]['plans'])
        pg.click('#toastBtn')
        pg.wait_for_timeout(300)
        check('삭제 되돌리기 복원', [x['name'] for x in plan_rows(pg)] == before, [x['name'] for x in plan_rows(pg)])

        # 예정사항 접기/펴기
        f = fold(pg, 'plan')
        check('예정사항 기본 펼침', not f['collapsed'] and f['bodyVisible'], f)
        badge_before = plan_badge(pg)['text']
        pg.click('#planFold')
        pg.wait_for_timeout(220)
        f = fold(pg, 'plan')
        check('예정사항 접힘', f['collapsed'] and f['expanded'] == 'false' and not f['bodyVisible'], f)
        check('접혀도 배지 보임', plan_badge(pg)['visible'] and plan_badge(pg)['text'] == badge_before,
              (plan_badge(pg), badge_before))
        check('예정사항 접힘 저장', (ui_store(pg) or {}).get('planCollapsed') is True, ui_store(pg))
        reload(pg)
        check('새로고침 후 예정사항 접힘 유지', fold(pg, 'plan')['collapsed'] and not fold(pg, 'plan')['bodyVisible'])
        check('예정사항 접힌 채 데이터 유지', len(stored(pg)['days'][tk]['plans']) == 2)
        pg.click('#planHead')
        pg.wait_for_timeout(220)
        check('예정사항 헤더 클릭 → 펼침', not fold(pg, 'plan')['collapsed'] and len(plan_rows(pg)) == 2, len(plan_rows(pg)))
        reload(pg)
        check('새로고침 후 예정사항 펼침 유지', not fold(pg, 'plan')['collapsed'])

        # 두 카드 동시에 접기
        pg.click('#routineFold')
        pg.click('#planFold')
        pg.wait_for_timeout(260)
        check('두 카드 함께 접힘', fold(pg, 'routine')['collapsed'] and fold(pg, 'plan')['collapsed'])
        check('두 카드 모두 접혀도 숫자/배지 보임',
              pg.is_visible('#doneCount') and plan_badge(pg)['visible'])
        h_cal = pg.eval_on_selector('.calendar-card', 'e => e.getBoundingClientRect().height')
        check('접힌 두 카드가 한 화면에', h_cal > 200 and pg.evaluate("""() => {
          const r = document.querySelector('#routineCard').getBoundingClientRect();
          const p = document.querySelector('#planCard').getBoundingClientRect();
          return r.height < 110 && p.height < 90;
        }"""))
        pg.screenshot(path=os.path.join(REPO_SHOTS, '05_collapsed_390.png'))
        reload(pg)
        check('두 카드 접힘 새로고침 유지', fold(pg, 'routine')['collapsed'] and fold(pg, 'plan')['collapsed'])
        pg.click('#routineFold')
        pg.click('#planFold')
        pg.wait_for_timeout(240)

        # 전부 완료 → 100% 진파랑 + ✓
        check_all(pg)
        s = summary(pg)
        check('전부 완료 14 / 14', s['done'] == 14 and s['total'] == 14, s)
        check('완료 축하 메시지', '모두 끝냈어요' in s['msg'], s['msg'])
        check('진행바 100%', s['barW'] in ('100%', '100.0%'), s['barW'])
        c = day_cell(pg, tk)
        check('오늘 칸 lv3(진파랑)', 'lv3' in c['cls'] and c['bg'] == 'rgb(49, 130, 246)', c)
        check('lv3 체크 표시 ✓', c['mark'] == '✓', c['mark'])
        check('lv3 날에도 예정 점 보임', c['dot']['vis'] == 'visible', c['dot'])

        # 50% 단계 (14개 중 6개만 남기고 해제 → 8/14 = 57%)
        for i in range(8, 14):
            pg.click(f'#todoList .todo:nth-child({i + 1}) .check')
            pg.wait_for_timeout(35)
        pg.wait_for_timeout(260)
        c = day_cell(pg, tk)
        s = summary(pg)
        check('50% 칸 lv2(중간 파랑)', 'lv2' in c['cls'] and c['bg'] == 'rgb(185, 213, 251)', c)
        check('50% 요약 메시지', ('6개 남았어요' in s['msg']) and s['done'] == 8, s)

        # 지우기(✕) + 되돌리기 (루틴 그날 추가)
        last = rows(pg)[-1]
        pg.click(f'#todoList .todo[data-id="{last["id"]}"] .todo-del')
        pg.wait_for_timeout(280)
        r6 = rows(pg)
        check('추가 항목 ✕ 지우기', len(r6) == 13 and all(x['name'] != last['name'] for x in r6), len(r6))
        check('지운 항목 저장 반영', len(stored(pg)['days'][tk]['extra']) == 1, stored(pg)['days'][tk].get('extra'))
        check('지우기 토스트', pg.is_visible('#toast') and '지웠어요' in pg.inner_text('#toastText'), pg.inner_text('#toastText'))
        check('지운 뒤 요약 총 13', summary(pg)['total'] == 13, summary(pg))
        pg.click('#toastBtn')
        pg.wait_for_timeout(300)
        check('되돌리기 복원 14개', len(rows(pg)) == 14 and rows(pg)[-1]['name'] == last['name'], len(rows(pg)))

        # 다시 지우고 새로고침 → 13개 유지
        pg.click(f'#todoList .todo[data-id="{last["id"]}"] .todo-del')
        pg.wait_for_timeout(300)
        reload(pg)
        check('지운 채로 새로고침 13개', len(rows(pg)) == 13, len(rows(pg)))
        check('예정사항은 그대로 2건', len(plan_rows(pg)) == 2, len(plan_rows(pg)))

        # 항목 편집
        pg.click('#editBtn')
        pg.wait_for_timeout(320)
        check('편집 시트 열림', pg.is_visible('#sheetBackdrop') and pg.is_visible('#sheetTitle'))
        check('편집 행 12개', pg.eval_on_selector_all('#editList .edit-row', 'e => e.length') == 12)
        pg.fill('#addInput', '테스트 항목')
        pg.click('#addBtn')
        pg.wait_for_timeout(260)
        check('항목 추가 13개', pg.eval_on_selector_all('#editList .edit-row', 'e => e.length') == 13)
        check('추가 항목 목록 반영', rows(pg)[12]['name'] == '테스트 항목' and rows(pg)[12]['extra'] is False,
              rows(pg)[12])
        check('총 개수 14 반영 (13+1)', summary(pg)['total'] == 14, summary(pg))

        pg.fill('#editList .edit-row:nth-child(1) .edit-name', '성경문제 3장')
        pg.wait_for_timeout(180)
        check('이름 수정 반영', rows(pg)[0]['name'] == '성경문제 3장', rows(pg)[0]['name'])

        second = rows(pg)[1]['name']
        pg.click('#editList .edit-row:nth-child(2) [data-act="up"]')
        pg.wait_for_timeout(220)
        check('순서 위로 이동', rows(pg)[0]['name'] == second and rows(pg)[1]['name'] == '성경문제 3장',
              [x['name'] for x in rows(pg)[:3]])
        pg.click('#editList .edit-row:nth-child(1) [data-act="down"]')
        pg.wait_for_timeout(220)
        check('순서 아래로 이동(원복)', rows(pg)[0]['name'] == '성경문제 3장', rows(pg)[0]['name'])

        pg.click('#editList .edit-row:nth-child(13) [data-act="del"]')
        pg.wait_for_timeout(280)
        check('항목 삭제 12개', pg.eval_on_selector_all('#editList .edit-row', 'e => e.length') == 12)
        check('삭제 토스트', pg.is_visible('#toast') and '삭제' in pg.inner_text('#toastText'), pg.inner_text('#toastText'))
        check('삭제 후 총 13으로 복귀', summary(pg)['total'] == 13, summary(pg))
        pg.click('#toastBtn')
        pg.wait_for_timeout(280)
        check('되돌리기 복원 13개', pg.eval_on_selector_all('#editList .edit-row', 'e => e.length') == 13)

        pg.click('#editList .edit-row:nth-child(13) [data-act="del"]')
        pg.wait_for_timeout(240)
        pg.click('#sheetClose')
        pg.wait_for_timeout(280)
        check('시트 닫힘', not pg.is_visible('#sheetBackdrop'))
        check('닫은 뒤 총 13 (12+1)', summary(pg)['total'] == 13, summary(pg))

        # 백업 내보내기
        pg.click('#editBtn')
        pg.wait_for_timeout(240)
        with pg.expect_download(timeout=4000) as dl:
            pg.click('#exportBtn')
        d = dl.value
        check('JSON 내보내기 파일', d.suggested_filename.startswith('daily-todo-backup-') and d.suggested_filename.endswith('.json'),
              d.suggested_filename)
        path = d.path()
        data = json.load(open(path))
        check('백업 version 3', data.get('version') == 3, data.get('version'))
        check('백업에 plans 포함', len(data['days'][tk]['plans']) == 2, data['days'][tk].get('plans'))

        pg.click('#sheetClose')
        pg.wait_for_timeout(240)
        last2 = rows(pg)[-1]
        pg.click(f'#todoList .todo[data-id="{last2["id"]}"] .todo-del')
        pg.wait_for_timeout(240)
        pg.click('#editBtn')
        pg.wait_for_timeout(240)
        pg.once('dialog', lambda dlg: dlg.accept())
        pg.set_input_files('#importFile', path)
        pg.wait_for_timeout(400)
        check('JSON 불러오기로 추가 항목 복원', len(rows(pg)) == 13 and rows(pg)[-1]['name'] == last2['name'], len(rows(pg)))
        check('JSON 불러오기로 예정사항 복원', len(plan_rows(pg)) == 2, len(plan_rows(pg)))
        pg.click('#sheetClose')
        pg.wait_for_timeout(240)

        # 가로 넘침 (모바일) — 긴 예정사항 이름
        pg.fill('#planInput', '가나다라마바사아자차카타파하 아주 긴 예정사항 제목 테스트')
        pg.press('#planInput', 'Enter')
        pg.wait_for_timeout(260)
        check('긴 예정사항도 넘침 0', overflow(pg) == 0, overflow(pg))
        check('긴 예정사항은 두 줄로', plan_rows(pg)[-1]['height'] > 40, plan_rows(pg)[-1]['height'])
        pg.click(f'#planList .todo[data-id="{plan_rows(pg)[-1]["id"]}"] [data-act="plan-del"]')
        pg.wait_for_timeout(300)

        check('390 가로 넘침 0', overflow(pg) == 0, overflow(pg))

        # 월 이동
        title0 = pg.inner_text('#calTitle')
        pg.click('#prevMonth')
        pg.wait_for_timeout(160)
        title1 = pg.inner_text('#calTitle')
        check('이전 달 이동', title1 != title0 and '10월' in title1, (title0, title1))
        pg.click('#nextMonth')
        pg.wait_for_timeout(140)
        check('다음 달 복귀', pg.inner_text('#calTitle') == title0, pg.inner_text('#calTitle'))
        pg.click('#prevMonth')
        pg.click('#todayBtn')
        pg.wait_for_timeout(220)
        check('오늘 버튼 → 이번 달·오늘 선택',
              pg.inner_text('#calTitle') == title0 and pg.get_attribute('.day.sel', 'data-date') == tk)

        # 01 홈 스크린샷: 달력(곳곳에 예정 점) + 접힌 루틴 + 예정사항 카드
        fresh(pg)
        tk = today_key(pg)
        for n in (1, 4, 11):
            pg.click(f'#todoList .todo:nth-child({n}) .check')
            pg.wait_for_timeout(40)
        pg.fill('#quickInput', '약국 들르기')
        pg.press('#quickInput', 'Enter')
        pg.wait_for_timeout(180)
        pg.fill('#quickInput', '세탁소에 맡기기')
        pg.press('#quickInput', 'Enter')
        pg.wait_for_timeout(180)
        pg.click('#todoList .todo:nth-child(13) .check')
        pg.wait_for_timeout(260)
        pg.fill('#planInput', '병원 예약 10시')
        pg.press('#planInput', 'Enter')
        pg.wait_for_timeout(180)
        pg.fill('#planInput', '은행 들르기')
        pg.press('#planInput', 'Enter')
        pg.wait_for_timeout(180)
        pg.fill('#planInput', '저녁 약속')
        pg.press('#planInput', 'Enter')
        pg.wait_for_timeout(200)
        pg.click('#planList .todo:nth-child(1) .check')
        pg.wait_for_timeout(180)
        pg.click('#planList .todo:nth-child(2) .check')
        pg.wait_for_timeout(220)
        # 미래 날짜 예정사항(달력 점 확인용)
        pg.click(f'.day[data-date="{future_key(pg, 3)}"]')
        pg.wait_for_timeout(200)
        pg.fill('#planInput', '치과 예약')
        pg.press('#planInput', 'Enter')
        pg.wait_for_timeout(200)
        pg.click(f'.day[data-date="{tk}"]')
        pg.wait_for_timeout(220)
        pg.click('#routineFold')
        pg.wait_for_timeout(300)
        check('01 스크린샷 상태 4 / 14', summary(pg)['done'] == 4 and summary(pg)['total'] == 14, summary(pg))
        check('01 루틴 접힘', fold(pg, 'routine')['collapsed'])
        check('01 예정사항 3건', len(plan_rows(pg)) == 3, len(plan_rows(pg)))
        check('01 미래 날짜 점', day_cell(pg, future_key(pg, 3))['dot']['vis'] == 'visible',
              day_cell(pg, future_key(pg, 3))['dot'])
        pg.evaluate('window.scrollTo(0, 0)')
        pg.wait_for_timeout(300)
        check('01 세 카드가 한 화면에', pg.evaluate("""() => {
          const cal = document.querySelector('.calendar-card').getBoundingClientRect();
          const plan = document.querySelector('#planCard').getBoundingClientRect();
          return plan.bottom <= window.innerHeight && cal.top >= 0;
        }"""))
        pg.screenshot(path=os.path.join(SHOTS, '01_home_390.png'))
        pg.screenshot(path=os.path.join(REPO_SHOTS, '01_home_390.png'))

        # 02 완료 스크린샷: 루틴 펼쳐 전부 체크 + 예정사항(2/3 완료)
        pg.click('#routineFold')
        pg.wait_for_timeout(260)
        check_all(pg)
        pg.wait_for_timeout(340)
        check('02 스크린샷 상태 14 / 14', summary(pg)['done'] == 14 and summary(pg)['total'] == 14, summary(pg))
        check('02 예정사항은 따로 2/3', plan_badge(pg)['text'] == '남은 1건', plan_badge(pg))
        pg.evaluate("""() => {
          const r = document.querySelector('#planCard').getBoundingClientRect();
          window.scrollBy(0, r.bottom - window.innerHeight + 16);
        }""")
        pg.wait_for_timeout(320)
        pg.screenshot(path=os.path.join(SHOTS, '02_checked_390.png'))
        pg.screenshot(path=os.path.join(REPO_SHOTS, '02_checked_390.png'))
        pg.evaluate('window.scrollTo(0, 0)')
        pg.wait_for_timeout(220)

        # 예전 데이터(항목별 메모, plans 없음) 호환
        legacy = {
            'v': 1,
            'items': [{'id': 'd%d' % (i + 1), 'name': n} for i, n in enumerate(DEFAULT_NAMES)],
            'days': {
                tk: {
                    'done': {'d1': True, 'd4': True},
                    'memo': {'d1': '시편 23편 1-6', 'd4': '창세기 1-3장'}
                }
            }
        }
        pg.evaluate("(v) => localStorage.setItem('daily-todo-v1', v)", json.dumps(legacy, ensure_ascii=False))
        reload(pg)
        rl = rows(pg)
        check('예전 데이터 → 기본 12개', len(rl) == 12, len(rl))
        check('예전 데이터 → 메모칸 없이 표시', pg.eval_on_selector_all('#todoList .todo-main input', 'e => e.length') == 0)
        check('예전 데이터 → 체크 2개 유지', summary(pg)['done'] == 2 and summary(pg)['total'] == 12, summary(pg))
        check('예전 데이터 → 예정사항 없음', len(plan_rows(pg)) == 0 and '아직 예정사항이 없어요' in pg.inner_text('#planList'))
        kept = stored(pg)['days'][tk]
        check('예전 메모 데이터 보존', kept.get('memo', {}).get('d1') == '시편 23편 1-6', kept.get('memo'))
        check('예전 데이터 총 12(메모는 개수에 미포함)', summary(pg)['total'] == 12, summary(pg))

        pg.fill('#quickInput', '약속')
        pg.press('#quickInput', 'Enter')
        pg.wait_for_timeout(240)
        after = stored(pg)['days'][tk]
        check('추가 후에도 예전 메모 보존', after.get('memo', {}).get('d4') == '창세기 1-3장', after.get('memo'))
        check('예전 데이터 위에 추가 → 13', summary(pg)['total'] == 13, summary(pg))

        # 예정사항이 든 v3 데이터 보존(불러오기 정규화)
        v3 = {
            'v': 3,
            'items': [{'id': 'd%d' % (i + 1), 'name': n} for i, n in enumerate(DEFAULT_NAMES)],
            'days': {tk: {'done': {}, 'extra': [], 'memo': {},
                          'plans': [{'id': 'p1', 'name': '보존 확인', 'done': True},
                                    {'id': 'p2', 'name': '남은 일', 'done': False}]}}
        }
        pg.evaluate("(v) => localStorage.setItem('daily-todo-v1', v)", json.dumps(v3, ensure_ascii=False))
        reload(pg)
        check('v3 plans 데이터 불러오기', len(plan_rows(pg)) == 2 and plan_rows(pg)[0]['done'] is True, plan_rows(pg))
        check('v3 plans 배지 남은 1건', plan_badge(pg)['text'] == '남은 1건', plan_badge(pg))
        check('v3 plans 달력 점', day_cell(pg, tk)['dot']['vis'] == 'visible')

        # 깨진 저장값은 기본값으로 복구
        pg.evaluate("localStorage.setItem('daily-todo-v1', '{broken')")
        reload(pg)
        check('깨진 저장값 → 기본 12개', len(rows(pg)) == 12 and summary(pg)['done'] == 0, len(rows(pg)))
        check('깨진 저장값 → 예정사항 빈 상태', len(plan_rows(pg)) == 0)

        check('모바일 콘솔 오류 0', len(pg.errors) == 0, pg.errors)
        ctx.close()

        # ── PC 1280×800 ────────────────────────────────────────
        ctx2, pg2 = new_page(browser, 1280, 800, mobile=False)
        fresh(pg2)
        check('PC 12개', len(rows(pg2)) == 12)
        check('PC 가로 넘침 0', overflow(pg2) == 0, overflow(pg2))
        box = pg2.evaluate("""() => {
          const r = document.querySelector('.app').getBoundingClientRect();
          return { w: r.width, left: r.left, right: r.right, vw: window.innerWidth };
        }""")
        check('PC 가운데 정렬 560px', 540 <= box['w'] <= 561 and abs(box['left'] - (box['vw'] - box['right'])) < 2, box)
        pg2.click('#todoList .todo:nth-child(2) .check')
        pg2.wait_for_timeout(300)
        check('PC 체크 동작', summary(pg2)['done'] == 1)
        pg2.fill('#quickInput', 'PC 에서 추가')
        pg2.press('#quickInput', 'Enter')
        pg2.wait_for_timeout(260)
        check('PC 자유 추가 동작', len(rows(pg2)) == 13 and summary(pg2)['total'] == 13, summary(pg2))
        pg2.fill('#planInput', 'PC 예정사항')
        pg2.press('#planInput', 'Enter')
        pg2.wait_for_timeout(240)
        check('PC 예정사항 추가', len(plan_rows(pg2)) == 1 and plan_badge(pg2)['text'] == '남은 1건', plan_rows(pg2))
        check('PC 예정 dot', day_cell(pg2, today_key(pg2))['dot']['vis'] == 'visible')
        check('PC 추가 후 넘침 0', overflow(pg2) == 0, overflow(pg2))
        pg2.click('#routineFold')
        pg2.wait_for_timeout(200)
        check('PC 루틴 접기', fold(pg2, 'routine')['collapsed'] and pg2.is_visible('#doneCount'))
        pg2.click('#routineFold')
        pg2.wait_for_timeout(200)
        pg2.screenshot(path=os.path.join(REPO_SHOTS, '03_home_1280.png'))
        pg2.click('#editBtn')
        pg2.wait_for_timeout(320)
        check('PC 편집 시트', pg2.is_visible('#sheetTitle'))
        pg2.screenshot(path=os.path.join(REPO_SHOTS, '04_edit_1280.png'))
        pg2.click('#sheetClose')
        pg2.wait_for_timeout(200)
        check('PC 콘솔 오류 0', len(pg2.errors) == 0, pg2.errors)
        ctx2.close()

        browser.close()

    print()
    print('PASS %d / %d' % (len(PASSES), len(PASSES) + len(FAILS)))
    if FAILS:
        print('실패:')
        for f in FAILS:
            print(' - ' + f)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
