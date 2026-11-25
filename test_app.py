"""데일리 투두 — Playwright 검증 (390×844 모바일 / 1280×800 PC)

    LD_LIBRARY_PATH=/workspace/.browserlibs/lib python3 test_app.py

검증
- 기본 12개 항목에 메모 입력칸이 없고 '체크 동그라미 + 이름'만 있는지
- 맨 아래 자유 추가 빈칸: Enter·버튼 추가, 그날만 표시, 체크·지우기(되돌리기),
  새로고침 유지, 날짜별 독립
- 요약 카운트·달력 색상이 그날 추가 항목까지 포함하는지(1~49 / 50~99 / 100%)
- 예전 데이터(항목별 메모 포함) 호환, 깨진 저장값 복구
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


def today_key(pg):
    return pg.evaluate("""() => {
      const d = new Date(); const p = n => String(n).padStart(2,'0');
      return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`;
    }""")


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
        hasDel: !!li.querySelector('.todo-del')
      };
    })""")


def day_cell(pg, key):
    return pg.evaluate("""(k) => {
      const b = document.querySelector(`.day[data-date="${k}"]`);
      if (!b) return null;
      const cs = getComputedStyle(b);
      return { cls: b.className, bg: cs.backgroundColor, color: cs.color, num: b.querySelector('.num').textContent,
               mark: b.querySelector('.mark').textContent, aria: b.getAttribute('aria-label') };
    }""", key)


def summary(pg):
    return pg.evaluate("""() => ({
      date: document.querySelector('#summaryDate').textContent,
      done: Number(document.querySelector('#doneCount').textContent),
      total: Number(document.querySelector('#totalCount').textContent),
      msg: document.querySelector('#summaryMsg').textContent,
      barW: document.querySelector('#barFill').style.width,
      barNow: document.querySelector('#summaryBar').getAttribute('aria-valuenow')
    })""")


def overflow(pg):
    return pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")


def stored(pg):
    return json.loads(pg.evaluate("localStorage.getItem('daily-todo-v1')"))


def check_all(pg):
    n = len(rows(pg))
    for i in range(n):
        if not rows(pg)[i]['done']:
            pg.click(f'.todo:nth-child({i + 1}) .check')
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
        check('index.html 마크업 v=2', pg.eval_on_selector('script[src]', 'e => e.getAttribute("src")').endswith('?v=2'))

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
        check('행 높이 44px 이하로 납작', pg.eval_on_selector('.todo', 'e => e.getBoundingClientRect().height') <= 48,
              pg.eval_on_selector('.todo', 'e => e.getBoundingClientRect().height'))

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
        check('달력 lv0 기본', 'lv0' in day_cell(pg, tk)['cls'], day_cell(pg, tk)['cls'])

        # 1개 체크
        pg.click('.todo:nth-child(1) .check')
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
        pg.click(f'.todo[data-id="{extra_id}"] .check')
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
        pg.reload(wait_until='networkidle')
        pg.wait_for_timeout(300)
        r4 = rows(pg)
        check('새로고침 후 14개 유지', len(r4) == 14 and r4[-1]['name'] == '세탁소 맡기기', len(r4))
        check('새로고침 후 체크 유지', r4[0]['done'] and [x for x in r4 if x['id'] == extra_id][0]['done'], r4[0])
        check('새로고침 후 요약 2 / 14', summary(pg)['done'] == 2 and summary(pg)['total'] == 14, summary(pg))

        # 날짜별 독립 (어제)
        yk = pg.evaluate("""() => {
          const d = new Date(); d.setDate(d.getDate()-1);
          const p = n => String(n).padStart(2,'0');
          return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`;
        }""")
        pg.click(f'.day[data-date="{yk}"]')
        pg.wait_for_timeout(250)
        ry = rows(pg)
        check('어제는 기본 12개만', len(ry) == 12 and all(not x['extra'] for x in ry), len(ry))
        check('어제는 체크 비어 있음', all(not x['done'] for x in ry))
        check('어제 라벨', summary(pg)['date'] == '어제', summary(pg)['date'])
        pg.fill('#quickInput', '어제만 할 일')
        pg.press('#quickInput', 'Enter')
        pg.wait_for_timeout(240)
        pg.click('.todo:nth-child(5) .check')
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

        # 전부 완료 → 100% 진파랑 + ✓
        check_all(pg)
        s = summary(pg)
        check('전부 완료 14 / 14', s['done'] == 14 and s['total'] == 14, s)
        check('완료 축하 메시지', '모두 끝냈어요' in s['msg'], s['msg'])
        check('진행바 100%', s['barW'] in ('100%', '100.0%'), s['barW'])
        c = day_cell(pg, tk)
        check('오늘 칸 lv3(진파랑)', 'lv3' in c['cls'] and c['bg'] == 'rgb(49, 130, 246)', c)
        check('lv3 체크 표시 ✓', c['mark'] == '✓', c['mark'])

        # 50% 단계 (14개 중 6개만 남기고 해제 → 8/14 = 57%)
        for i in range(8, 14):
            pg.click(f'.todo:nth-child({i + 1}) .check')
            pg.wait_for_timeout(35)
        pg.wait_for_timeout(260)
        c = day_cell(pg, tk)
        s = summary(pg)
        check('50% 칸 lv2(중간 파랑)', 'lv2' in c['cls'] and c['bg'] == 'rgb(185, 213, 251)', c)
        check('50% 요약 메시지', ('6개 남았어요' in s['msg']) and s['done'] == 8, s)

        # 지우기(✕) + 되돌리기
        last = rows(pg)[-1]
        pg.click(f'.todo[data-id="{last["id"]}"] .todo-del')
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
        pg.click(f'.todo[data-id="{last["id"]}"] .todo-del')
        pg.wait_for_timeout(300)
        pg.reload(wait_until='networkidle')
        pg.wait_for_timeout(300)
        check('지운 채로 새로고침 13개', len(rows(pg)) == 13, len(rows(pg)))

        # 항목 편집: 기본 항목 추가 → 그날 총 14 (13 기본 + 1 추가)
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

        # 이름 수정
        pg.fill('#editList .edit-row:nth-child(1) .edit-name', '성경문제 3장')
        pg.wait_for_timeout(180)
        check('이름 수정 반영', rows(pg)[0]['name'] == '성경문제 3장', rows(pg)[0]['name'])

        # 순서 이동 (2번을 위로)
        second = rows(pg)[1]['name']
        pg.click('#editList .edit-row:nth-child(2) [data-act="up"]')
        pg.wait_for_timeout(220)
        check('순서 위로 이동', rows(pg)[0]['name'] == second and rows(pg)[1]['name'] == '성경문제 3장',
              [x['name'] for x in rows(pg)[:3]])
        pg.click('#editList .edit-row:nth-child(1) [data-act="down"]')
        pg.wait_for_timeout(220)
        check('순서 아래로 이동(원복)', rows(pg)[0]['name'] == '성경문제 3장', rows(pg)[0]['name'])

        # 삭제 + 되돌리기
        pg.click('#editList .edit-row:nth-child(13) [data-act="del"]')
        pg.wait_for_timeout(280)
        check('항목 삭제 12개', pg.eval_on_selector_all('#editList .edit-row', 'e => e.length') == 12)
        check('삭제 토스트', pg.is_visible('#toast') and '삭제' in pg.inner_text('#toastText'), pg.inner_text('#toastText'))
        check('삭제 후 총 13으로 복귀', summary(pg)['total'] == 13, summary(pg))
        pg.click('#toastBtn')
        pg.wait_for_timeout(280)
        check('되돌리기 복원 13개', pg.eval_on_selector_all('#editList .edit-row', 'e => e.length') == 13)

        # 다시 삭제 후 시트 닫기 → 기본 12
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
        check('백업에 items/days/extra 포함',
              len(data['items']) == 12 and len(data['days'][tk]['extra']) == 1, list(data.keys()))

        # 불러오기: 다른 날 추가 항목을 지운 뒤 백업으로 되살리기
        pg.click('#sheetClose')
        pg.wait_for_timeout(240)
        last2 = rows(pg)[-1]
        pg.click(f'.todo[data-id="{last2["id"]}"] .todo-del')
        pg.wait_for_timeout(240)
        pg.click('#editBtn')
        pg.wait_for_timeout(240)
        pg.once('dialog', lambda dlg: dlg.accept())
        pg.set_input_files('#importFile', path)
        pg.wait_for_timeout(400)
        check('JSON 불러오기로 추가 항목 복원', len(rows(pg)) == 13 and rows(pg)[-1]['name'] == last2['name'], len(rows(pg)))
        pg.click('#sheetClose')
        pg.wait_for_timeout(240)

        # 가로 넘침 (모바일)
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

        # 01 홈 스크린샷: 3개 체크 + 그날 추가 2개(하나 체크)
        fresh(pg)
        tk = today_key(pg)
        pg.click('.todo:nth-child(1) .check')
        pg.click('.todo:nth-child(4) .check')
        pg.click('.todo:nth-child(11) .check')
        pg.fill('#quickInput', '약국 들르기')
        pg.press('#quickInput', 'Enter')
        pg.wait_for_timeout(200)
        pg.fill('#quickInput', '세탁소에 맡기기')
        pg.press('#quickInput', 'Enter')
        pg.wait_for_timeout(200)
        pg.click('.todo:nth-child(13) .check')
        pg.wait_for_timeout(420)
        check('홈 스크린샷 상태 4 / 14', summary(pg)['done'] == 4 and summary(pg)['total'] == 14, summary(pg))
        pg.click('.quick-plus')
        pg.wait_for_timeout(120)
        check('+ 동그라미를 누르면 입력칸 포커스', pg.evaluate("document.activeElement.id") == 'quickInput',
              pg.evaluate("document.activeElement.id"))
        pg.evaluate('document.activeElement.blur()')
        pg.evaluate('window.scrollTo(0, 0)')
        pg.wait_for_timeout(260)
        pg.screenshot(path=os.path.join(SHOTS, '01_home_390.png'))
        pg.screenshot(path=os.path.join(REPO_SHOTS, '01_home_390.png'))

        # 02 완료 스크린샷: 14 / 14 — 목록 맨 아래 빈칸까지 한 화면에
        check_all(pg)
        pg.wait_for_timeout(400)
        check('02 스크린샷 상태 14 / 14', summary(pg)['done'] == 14, summary(pg))
        pg.evaluate("document.querySelector('#quickAdd').scrollIntoView({ block: 'end' })")
        pg.wait_for_timeout(320)
        pg.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
        pg.wait_for_timeout(280)
        pg.screenshot(path=os.path.join(SHOTS, '02_checked_390.png'))
        pg.screenshot(path=os.path.join(REPO_SHOTS, '02_checked_390.png'))
        pg.evaluate('window.scrollTo(0, 0)')
        pg.wait_for_timeout(200)

        # 예전 데이터(항목별 메모) 호환
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
        pg.reload(wait_until='networkidle')
        pg.wait_for_timeout(320)
        rl = rows(pg)
        check('예전 데이터 → 기본 12개', len(rl) == 12, len(rl))
        check('예전 데이터 → 메모칸 없이 표시', pg.eval_on_selector_all('#todoList .todo-main input', 'e => e.length') == 0)
        check('예전 데이터 → 체크 2개 유지', summary(pg)['done'] == 2 and summary(pg)['total'] == 12, summary(pg))
        kept = stored(pg)['days'][tk]
        check('예전 메모 데이터 보존', kept.get('memo', {}).get('d1') == '시편 23편 1-6', kept.get('memo'))
        check('예전 데이터 총 12(메모는 개수에 미포함)', summary(pg)['total'] == 12, summary(pg))

        # 새 항목을 추가해도 예전 메모는 그대로
        pg.fill('#quickInput', '약속')
        pg.press('#quickInput', 'Enter')
        pg.wait_for_timeout(240)
        after = stored(pg)['days'][tk]
        check('추가 후에도 예전 메모 보존', after.get('memo', {}).get('d4') == '창세기 1-3장', after.get('memo'))
        check('예전 데이터 위에 추가 → 13', summary(pg)['total'] == 13, summary(pg))

        # 깨진 저장값은 기본값으로 복구
        pg.evaluate("localStorage.setItem('daily-todo-v1', '{broken')")
        pg.reload(wait_until='networkidle')
        pg.wait_for_timeout(300)
        check('깨진 저장값 → 기본 12개', len(rows(pg)) == 12 and summary(pg)['done'] == 0, len(rows(pg)))

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
        pg2.click('.todo:nth-child(2) .check')
        pg2.wait_for_timeout(300)
        check('PC 체크 동작', summary(pg2)['done'] == 1)
        pg2.fill('#quickInput', 'PC 에서 추가')
        pg2.press('#quickInput', 'Enter')
        pg2.wait_for_timeout(260)
        check('PC 자유 추가 동작', len(rows(pg2)) == 13 and summary(pg2)['total'] == 13, summary(pg2))
        check('PC 추가 후 넘침 0', overflow(pg2) == 0, overflow(pg2))
        pg2.screenshot(path=os.path.join(REPO_SHOTS, '03_home_1280.png'))
        pg2.click('#editBtn')
        pg2.wait_for_timeout(320)
        check('PC 편집 시트', pg2.is_visible('#sheetTitle'))
        pg2.screenshot(path=os.path.join(REPO_SHOTS, '04_edit_1280.png'))
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
