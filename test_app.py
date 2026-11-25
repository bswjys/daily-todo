"""데일리 투두 — Playwright 검증 (390×844 모바일 / 1280×800 PC)

    LD_LIBRARY_PATH=/workspace/.browserlibs/lib python3 test_app.py

검증
- 12개 기본 항목 순서, 날짜 선택/전환, 날짜별 체크·메모 독립 저장, 새로고침 유지
- 완료율 요약·달력 색상 단계(1~49 / 50~99 / 100%)
- 항목 추가·이름 수정·순서 이동·삭제(되돌리기)
- 월 이동·오늘 버튼, 콘솔 오류 0, 가로 넘침 0
- 대표 스크린샷 downloads/daily_todo/
"""
import functools
import http.server
import json
import os
import socketserver
import threading
import time

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
    return pg.evaluate("""() => Array.from(document.querySelectorAll('#todoList .todo')).map(li => ({
      id: li.dataset.id,
      name: li.querySelector('.todo-name').textContent,
      done: li.classList.contains('done'),
      aria: li.querySelector('.check').getAttribute('aria-checked'),
      memo: li.querySelector('.memo').value
    }))""")


def day_cell(pg, key):
    return pg.evaluate("""(k) => {
      const b = document.querySelector(`.day[data-date="${k}"]`);
      if (!b) return null;
      const cs = getComputedStyle(b);
      return { cls: b.className, bg: cs.backgroundColor, color: cs.color, num: b.querySelector('.num').textContent,
               mark: b.querySelector('.mark').textContent };
    }""", key)


def summary(pg):
    return pg.evaluate("""() => ({
      date: document.querySelector('#summaryDate').textContent,
      done: Number(document.querySelector('#doneCount').textContent),
      total: Number(document.querySelector('#totalCount').textContent),
      msg: document.querySelector('#summaryMsg').textContent,
      barW: document.querySelector('#barFill').style.width
    })""")


def overflow(pg):
    return pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")


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

        r = rows(pg)
        check('기본 항목 12개', len(r) == 12, len(r))
        check('항목 순서 일치', [x['name'] for x in r] == DEFAULT_NAMES, [x['name'] for x in r])
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

        # 메모
        pg.fill('.todo:nth-child(1) .memo', '시편 23편')
        pg.fill('.todo:nth-child(2) .memo', '조직신학 1장')
        pg.wait_for_timeout(120)
        stored = json.loads(pg.evaluate("localStorage.getItem('daily-todo-v1')"))
        check('localStorage 자동 저장', stored['days'][tk]['memo'][r[0]['id']] == '시편 23편', stored['days'][tk])

        # 새로고침 유지
        pg.reload(wait_until='networkidle')
        pg.wait_for_timeout(280)
        r2 = rows(pg)
        check('새로고침 후 체크 유지', r2[0]['done'] is True, r2[0])
        check('새로고침 후 메모 유지', r2[0]['memo'] == '시편 23편' and r2[1]['memo'] == '조직신학 1장', r2[:2])
        check('새로고침 후 요약 유지', summary(pg)['done'] == 1)

        # 다른 날짜(어제)로 이동 → 독립
        yk = pg.evaluate("""() => {
          const d = new Date(); d.setDate(d.getDate()-1);
          const p = n => String(n).padStart(2,'0');
          return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`;
        }""")
        pg.click(f'.day[data-date="{yk}"]')
        pg.wait_for_timeout(220)
        r3 = rows(pg)
        check('다른 날짜는 빈 상태', all(not x['done'] and x['memo'] == '' for x in r3), r3[:2])
        check('어제 라벨', summary(pg)['date'] == '어제', summary(pg)['date'])
        pg.click('.todo:nth-child(5) .check')
        pg.fill('.todo:nth-child(5) .memo', 'DAY 12')
        pg.wait_for_timeout(200)
        check('어제 1 / 12', summary(pg)['done'] == 1)

        # 오늘로 복귀 → 오늘 상태 그대로
        pg.click(f'.day[data-date="{tk}"]')
        pg.wait_for_timeout(200)
        r4 = rows(pg)
        check('오늘 복귀 시 체크 유지', r4[0]['done'] and r4[4]['done'] is False, r4[0])
        check('오늘 복귀 시 메모 유지', r4[0]['memo'] == '시편 23편', r4[0]['memo'])
        check('오늘 복귀 요약 1 / 12', summary(pg)['done'] == 1)

        # 어제 다시 → 유지
        pg.click(f'.day[data-date="{yk}"]')
        pg.wait_for_timeout(200)
        check('어제 기록 유지', rows(pg)[4]['done'] and rows(pg)[4]['memo'] == 'DAY 12', rows(pg)[4])
        pg.click(f'.day[data-date="{tk}"]')
        pg.wait_for_timeout(150)

        # 전부 체크 → 100% 진파랑 + ✓
        for i in range(12):
            if not rows(pg)[i]['done']:
                pg.click(f'.todo:nth-child({i+1}) .check')
                pg.wait_for_timeout(40)
        pg.wait_for_timeout(300)
        s = summary(pg)
        check('전부 완료 12 / 12', s['done'] == 12, s)
        check('완료 축하 메시지', '모두 끝냈어요' in s['msg'], s['msg'])
        check('진행바 100%', s['barW'] in ('100%', '100.0%'), s['barW'])
        c = day_cell(pg, tk)
        check('오늘 칸 lv3(진파랑)', 'lv3' in c['cls'] and c['bg'] == 'rgb(49, 130, 246)', c)
        check('lv3 체크 표시 ✓', c['mark'] == '✓', c['mark'])

        # 스크린샷 (완료 상태 = 02)
        pg.evaluate('window.scrollTo(0, 0)')
        pg.wait_for_timeout(200)
        pg.screenshot(path=os.path.join(SHOTS, '02_checked_390.png'))
        pg.screenshot(path=os.path.join(REPO_SHOTS, '02_checked_390.png'))

        # 50% 단계
        for i in range(6):
            pg.click(f'.todo:nth-child({i+1}) .check')
            pg.wait_for_timeout(35)
        pg.wait_for_timeout(250)
        c = day_cell(pg, tk)
        check('50% 칸 lv2(중간 파랑)', 'lv2' in c['cls'] and c['bg'] == 'rgb(185, 213, 251)', c)
        check('50% 요약 메시지', '6개 남았어요' in summary(pg)['msg'], summary(pg)['msg'])

        # 가로 넘침 (모바일)
        check('390 가로 넘침 0', overflow(pg) == 0, overflow(pg))

        # 월 이동
        title0 = pg.inner_text('#calTitle')
        pg.click('#prevMonth')
        pg.wait_for_timeout(150)
        title1 = pg.inner_text('#calTitle')
        check('이전 달 이동', title1 != title0 and '10월' in title1, (title0, title1))
        pg.click('#nextMonth')
        pg.wait_for_timeout(120)
        check('다음 달 복귀', pg.inner_text('#calTitle') == title0, pg.inner_text('#calTitle'))
        pg.click('#prevMonth')
        pg.click('#todayBtn')
        pg.wait_for_timeout(200)
        check('오늘 버튼 → 이번 달·오늘 선택',
              pg.inner_text('#calTitle') == title0 and pg.get_attribute('.day.sel', 'data-date') == tk)

        # 항목 편집: 추가
        pg.click('#editBtn')
        pg.wait_for_timeout(300)
        check('편집 시트 열림', pg.is_visible('#sheetBackdrop') and pg.is_visible('#sheetTitle'))
        check('편집 행 12개', pg.eval_on_selector_all('#editList .edit-row', 'e => e.length') == 12)
        pg.fill('#addInput', '테스트 항목')
        pg.click('#addBtn')
        pg.wait_for_timeout(250)
        check('항목 추가 13개', pg.eval_on_selector_all('#editList .edit-row', 'e => e.length') == 13)
        check('추가 항목 목록 반영', rows(pg)[-1]['name'] == '테스트 항목', rows(pg)[-1])
        check('총 개수 13 반영', summary(pg)['total'] == 13, summary(pg))

        # 이름 수정
        pg.fill('#editList .edit-row:nth-child(1) .edit-name', '성경문제 3장')
        pg.wait_for_timeout(180)
        check('이름 수정 반영', rows(pg)[0]['name'] == '성경문제 3장', rows(pg)[0]['name'])

        # 순서 이동 (2번을 위로)
        second = rows(pg)[1]['name']
        pg.click('#editList .edit-row:nth-child(2) [data-act="up"]')
        pg.wait_for_timeout(200)
        check('순서 위로 이동', rows(pg)[0]['name'] == second and rows(pg)[1]['name'] == '성경문제 3장',
              [x['name'] for x in rows(pg)[:3]])
        pg.click('#editList .edit-row:nth-child(1) [data-act="down"]')
        pg.wait_for_timeout(200)
        check('순서 아래로 이동(원복)', rows(pg)[0]['name'] == '성경문제 3장', rows(pg)[0]['name'])

        # 삭제 + 되돌리기
        pg.click('#editList .edit-row:nth-child(13) [data-act="del"]')
        pg.wait_for_timeout(250)
        check('항목 삭제 12개', pg.eval_on_selector_all('#editList .edit-row', 'e => e.length') == 12)
        check('삭제 토스트', pg.is_visible('#toast') and '삭제' in pg.inner_text('#toastText'), pg.inner_text('#toastText'))
        pg.click('#toastBtn')
        pg.wait_for_timeout(250)
        check('되돌리기 복원', pg.eval_on_selector_all('#editList .edit-row', 'e => e.length') == 13)

        # 다시 삭제 후 시트 닫기 → 총 12
        pg.click('#editList .edit-row:nth-child(13) [data-act="del"]')
        pg.wait_for_timeout(200)
        pg.click('#sheetClose')
        pg.wait_for_timeout(250)
        check('시트 닫힘', not pg.is_visible('#sheetBackdrop'))
        check('닫은 뒤 12개', summary(pg)['total'] == 12, summary(pg))

        # 백업 내보내기 (다운로드 이벤트)
        pg.click('#editBtn')
        pg.wait_for_timeout(200)
        with pg.expect_download(timeout=4000) as dl:
            pg.click('#exportBtn')
        d = dl.value
        check('JSON 내보내기 파일', d.suggested_filename.startswith('daily-todo-backup-') and d.suggested_filename.endswith('.json'),
              d.suggested_filename)
        path = d.path()
        data = json.load(open(path))
        check('백업에 items/days 포함', len(data['items']) == 12 and tk in data['days'], list(data.keys()))

        # 불러오기: 파일 내용으로 복원
        pg.fill('.todo:nth-child(3) .memo', '임시 메모')
        pg.wait_for_timeout(150)
        pg.once('dialog', lambda dlg: dlg.accept())
        pg.set_input_files('#importFile', path)
        pg.wait_for_timeout(400)
        check('JSON 불러오기 후 값 복원', rows(pg)[2]['memo'] == '', rows(pg)[2]['memo'])
        check('불러오기 후 체크 유지', rows(pg)[0]['memo'] == '시편 23편', rows(pg)[0]['memo'])
        pg.click('#sheetClose')
        pg.wait_for_timeout(250)

        # 01 홈 스크린샷용: 메모 몇 개 + 3개 체크 상태
        fresh(pg)
        pg.fill('.todo:nth-child(1) .memo', '시편 23편 1-6')
        pg.fill('.todo:nth-child(4) .memo', '창세기 1-3장')
        pg.fill('.todo:nth-child(5) .memo', 'UNIT 7 단어')
        pg.fill('.todo:nth-child(11) .memo', '10층 3회')
        pg.click('.todo:nth-child(1) .check')
        pg.click('.todo:nth-child(4) .check')
        pg.click('.todo:nth-child(11) .check')
        pg.wait_for_timeout(420)
        check('홈 스크린샷 상태 3 / 12', summary(pg)['done'] == 3, summary(pg))
        pg.evaluate('window.scrollTo(0, 0)')
        pg.wait_for_timeout(250)
        pg.screenshot(path=os.path.join(SHOTS, '01_home_390.png'))
        pg.screenshot(path=os.path.join(REPO_SHOTS, '01_home_390.png'))

        # 깨진 저장값은 기본값으로 복구
        pg.evaluate("localStorage.setItem('daily-todo-v1', '{broken')")
        pg.reload(wait_until='networkidle')
        pg.wait_for_timeout(280)
        check('깨진 저장값 → 기본 12개', len(rows(pg)) == 12 and summary(pg)['done'] == 0, len(rows(pg)))

        check('모바일 콘솔 오류 0', len(pg.errors) == 0, pg.errors)
        ctx.close()

        # ── PC 1280×800 ────────────────────────────────────────
        ctx2, pg2 = new_page(browser, 1280, 800, mobile=False)
        fresh(pg2)
        tk2 = today_key(pg2)
        check('PC 390 아님 · 12개', len(rows(pg2)) == 12)
        check('PC 가로 넘침 0', overflow(pg2) == 0, overflow(pg2))
        box = pg2.evaluate("""() => {
          const r = document.querySelector('.app').getBoundingClientRect();
          return { w: r.width, left: r.left, right: r.right, vw: window.innerWidth };
        }""")
        check('PC 가운데 정렬 560px', 540 <= box['w'] <= 561 and abs(box['left'] - (box['vw'] - box['right'])) < 2, box)
        pg2.click('.todo:nth-child(2) .check')
        pg2.wait_for_timeout(300)
        check('PC 체크 동작', summary(pg2)['done'] == 1)
        pg2.screenshot(path=os.path.join(REPO_SHOTS, '03_home_1280.png'))
        pg2.click('#editBtn')
        pg2.wait_for_timeout(300)
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
