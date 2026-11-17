"""현장 안전수첩 AI 도우미 — Streamlit 앱.   실행: streamlit run app.py"""
import html

import streamlit as st

from src import config
from src.agent import SafetyAgent
from src.checklist import to_csv, to_html, to_markdown

st.set_page_config(page_title="현장 안전수첩 AI 도우미", page_icon="🦺", layout="wide")

# ───────────────────────── 스타일 (라이트/다크 공용: 고정 글자색은 색 배경 위에서만 사용) ─────────────────────────
CSS = """
<style>
.block-container{padding-top:2.2rem;max-width:1100px}
h1{font-size:clamp(1.5rem,4.5vw,2.1rem)!important;letter-spacing:-.02em}
/* 위험등급 카드 */
.risk-card{border-radius:14px;padding:16px 20px;color:#fff;margin:4px 0 12px;box-shadow:0 2px 8px rgba(0,0,0,.18)}
.risk-card .lv{font-size:.85rem;opacity:.92;font-weight:600;letter-spacing:.04em}
.risk-card .nm{font-size:clamp(1.25rem,5.2vw,1.75rem);font-weight:800;line-height:1.3;margin-top:2px}
.risk-card .cats{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}
.risk-card .cat{background:rgba(255,255,255,.22);border-radius:999px;padding:3px 11px;font-size:.85rem;font-weight:600}
.risk-HIGH{background:linear-gradient(135deg,#b71c1c,#e53935)}
.risk-CHECK{background:linear-gradient(135deg,#e65100,#fb8c00)}
.risk-NORMAL{background:linear-gradient(135deg,#1b5e20,#43a047)}
.risk-UNKNOWN{background:linear-gradient(135deg,#37474f,#78909c)}
/* 지금 해야 할 일 */
.todo{border:1px solid rgba(128,128,128,.35);border-left:6px solid #e53935;border-radius:12px;padding:10px 16px;margin:0 0 14px;background:rgba(128,128,128,.07)}
.todo.NORMAL{border-left-color:#43a047}.todo.CHECK{border-left-color:#fb8c00}.todo.UNKNOWN{border-left-color:#78909c}
.todo .t{font-weight:800;margin-bottom:4px}
.todo .r{display:flex;gap:10px;padding:3px 0;line-height:1.5;font-size:1rem}
.todo .k{flex:0 0 3.4em;font-weight:700;opacity:.75}
/* 근거 페이지 칩 */
.pg{display:inline-block;background:rgba(21,101,192,.14);color:#1565c0;border-radius:6px;padding:0 7px;margin-left:4px;font-size:.78rem;font-weight:700;white-space:nowrap}
@media (prefers-color-scheme:dark){.pg{color:#90caf9;background:rgba(144,202,249,.16)}}
/* 터치 영역 */
.stButton>button,.stDownloadButton>button{min-height:46px;font-weight:600;border-radius:10px}
[data-testid="stCheckbox"] label{padding:7px 0;align-items:flex-start}
[data-testid="stCheckbox"] label p{line-height:1.5;font-size:1rem}
button[data-baseweb="tab"]{font-weight:700;padding:10px 14px}
[data-testid="stExpander"] summary{padding:.7rem .9rem;font-weight:700}
.item-sec{font-weight:800;margin:.6rem 0 .2rem}
@media (max-width:640px){
  .block-container{padding:1.2rem .8rem 5rem}
  .todo .r{flex-direction:column;gap:0}.todo .k{flex:none}
  button[data-baseweb="tab"]{padding:10px 8px;font-size:.88rem}
}
</style>
"""

LEVEL_ICON = {"HIGH": "🔴 고위험", "CHECK": "🟠 확인 필요", "NORMAL": "🟢 일반", "UNKNOWN": "⚪ 확인 필요"}
EXAMPLES = [
    "내일 저장탱크 내부에서 산소절단 작업 예정",
    "밀폐공간 들어가기 전에 뭘 해야 돼?",
    "4m 비계 해체",
    "카고크레인 인양",
    "지붕 강판 교체 작업",
    "지게차로 자재 운반",
]
SCR_PRIORITY = [4, 5, 3, 7, 8, 9, 1, 2, 6]


@st.cache_resource(show_spinner="수첩 데이터와 검색 인덱스를 불러오는 중… (최초 1회, 모델 다운로드로 1~2분 걸릴 수 있습니다)")
def get_agent():
    return SafetyAgent()


def chips(pages):
    if not pages:
        return "<span class='pg'>근거 확인 필요</span>"
    return "".join(f"<span class='pg'>p.{p}</span>" for p in pages)


def md_chips(pages):
    """st.markdown 안에서 쓰는 페이지 칩(HTML)."""
    return chips(pages)


def todo_lines(res):
    """'지금 해야 할 일' 3줄: 허가 / 배치 / 핵심."""
    if res["risk"]["level"] == "UNKNOWN":
        return [("안내", "작업 장소·방법·높이·사용 장비를 구체적으로 다시 입력해 주세요", []),
                ("확인", "안전작업허가 대상 여부는 관리감독자에게 확인하세요", [56])]
    permits = res["permits"]
    permit = html.escape(permits[0]["item"]) if permits else "안전작업허가 대상 여부 확인"
    if len(permits) > 1:
        permit += f" 외 {len(permits) - 1}건"
    roles = " · ".join(r["role"] for r in res["roles"]) or "해당 없음"
    scr = sorted(res.get("scr", []), key=lambda s: SCR_PRIORITY.index(s["no"]) if s["no"] in SCR_PRIORITY else 99)
    core = " · ".join(f"{s['no']}.{s['name']}" for s in scr[:3]) or "보호구 착용 · 허가 이행"
    return [("허가", permit, permits[0]["pages"] if permits else []),
            ("배치", html.escape(roles), res["roles"][0]["pages"] if res["roles"] else []),
            ("핵심", html.escape(core), scr[0]["pages"] if scr else [])]


def render_risk(res):
    risk = res["risk"]
    if risk["level"] == "UNKNOWN" and res.get("intent") == "qa":
        # 작업 입력이 아닌 순수 질문: 위험등급 대신 수첩 원문 안내
        st.markdown("<div class='risk-card risk-UNKNOWN'><div class='lv'>📖 수첩 Q&A</div>"
                    "<div class='nm'>질문과 관련된 수첩 내용입니다</div></div>", unsafe_allow_html=True)
        return
    cats = "".join(f"<span class='cat'>{html.escape(c['name'])}{'' if c['status'] == '해당' else ' (확인)'}</span>"
                   for c in risk["categories"])
    st.markdown(
        f"<div class='risk-card risk-{risk['level']}'><div class='lv'>{LEVEL_ICON.get(risk['level'], '')}</div>"
        f"<div class='nm'>{html.escape(risk['label'])}</div>"
        f"{f'<div class=cats>{cats}</div>' if cats else ''}</div>",
        unsafe_allow_html=True,
    )
    rows = "".join(f"<div class='r'><span class='k'>{k}</span><span>{v} {chips(p) if p else ''}</span></div>"
                   for k, v, p in todo_lines(res))
    st.markdown(f"<div class='todo {risk['level']}'><div class='t'>📌 지금 해야 할 일</div>{rows}</div>",
                unsafe_allow_html=True)


def group_rank(name: str) -> int:
    """핵심(공통·10대 수칙) 먼저, 장비 점검은 뒤."""
    if name.startswith("공통: TBM"):
        return 0
    if name.startswith("10대"):
        return 1
    if name.startswith("공통"):
        return 2
    return 3


def render_result(res: dict, user_text: str, key: str):
    risk = res["risk"]
    render_risk(res)
    for w in res.get("warnings", []):
        st.warning(w, icon="⚠️")
    if res.get("answer"):
        st.markdown(res["answer"])

    t1, t2, t3 = st.tabs(["📋 절차", "✅ 체크리스트", "📖 근거"])

    with t1:
        if risk["categories"]:
            st.markdown("<div class='item-sec'>고위험 분류표 대조 결과 <span class='pg'>p.59</span></div>", unsafe_allow_html=True)
            for c in risk["categories"]:
                mark = "🔴" if c["status"] == "해당" else "🟠"
                st.markdown(f"{mark} **{c['name']}** · {c['status']} — {html.escape(c['reason'])} {md_chips(c.get('pages', []))}",
                            unsafe_allow_html=True)
        for n in risk.get("notes", []):
            st.info(n)
        if res["permits"]:
            st.markdown("<div class='item-sec'>필요한 허가·절차</div>", unsafe_allow_html=True)
            for p in res["permits"]:
                st.markdown(f"- **{html.escape(p['item'])}** — {html.escape(p.get('detail', ''))} {md_chips(p.get('pages', []))}",
                            unsafe_allow_html=True)
        if res["roles"]:
            st.markdown("<div class='item-sec'>배치해야 하는 인원</div>", unsafe_allow_html=True)
            for p in res["roles"]:
                st.markdown(f"- **{html.escape(p['role'])}** — {html.escape(p.get('detail', ''))} {md_chips(p.get('pages', []))}",
                            unsafe_allow_html=True)

    with t2:
        groups = sorted(res["tbm"], key=lambda g: group_rank(g["group"]))
        total = sum(len(g["items"]) for g in groups)
        prog = st.empty()
        st.caption("핵심 항목부터 확인하세요. 장비·작업 점검은 아래 접힌 그룹에서 펼칩니다. (체크 상태는 화면에서만 유지)")
        done = 0
        for gi, g in enumerate(groups):
            opened = group_rank(g["group"]) <= 1 or gi == 0
            gcount = len(g["items"])
            with st.expander(f"{g['group']}  ·  {gcount}", expanded=opened):
                for ii, it in enumerate(g["items"]):
                    pgs = " ".join(f"`p.{p}`" for p in it.get("pages", [])) or "`근거 확인 필요`"
                    if st.checkbox(f"{it['text']}  {pgs}", key=f"{key}-{gi}-{ii}"):
                        done += 1
        prog.progress(done / total if total else 0.0, text=f"진행률 {done} / {total} 항목 확인")
        c1, c2, c3 = st.columns(3)
        c1.download_button("⬇ Markdown", to_markdown(res, user_text), file_name="TBM_체크리스트.md",
                           key=f"{key}-md", use_container_width=True)
        c2.download_button("⬇ CSV(엑셀)", to_csv(res), file_name="TBM_체크리스트.csv", mime="text/csv",
                           key=f"{key}-csv", use_container_width=True)
        c3.download_button("⬇ 인쇄용 HTML", to_html(res, user_text), file_name="TBM_체크리스트.html",
                           mime="text/html", key=f"{key}-html", use_container_width=True)

    with t3:
        st.info("표·그림은 텍스트로 추출되어 **순서가 뒤섞여 보일 수 있습니다.** 세부 내용은 E-Book 원본 쪽에서 확인하세요.")
        for s in res["sources"]:
            with st.expander(f"p.{s['page']}  ·  {s['breadcrumb']}"):
                st.code(s["text"], language=None, wrap_lines=True)
        st.link_button("📖 안전수첩 E-Book 열기", config.EBOOK_URL, use_container_width=True)

    st.caption(res["disclaimer"])


def qr_svg(data: str) -> str:
    """문자열을 QR 코드 SVG 문자열로 변환."""
    import io
    import segno
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=8, border=2, xmldecl=False, svgns=True)
    return buf.getvalue().decode("utf-8")


def default_app_url() -> str:
    """현재 접속 중인 주소를 추정 (실패 시 로컬 주소)."""
    try:
        u = st.context.url
        if u:
            return u
    except Exception:
        pass
    return "http://localhost:8501"


@st.dialog("📱 QR 코드", width="large")
def show_qr():
    st.caption("휴대폰 카메라로 스캔하면 바로 열립니다. TBM 시간에 화면을 띄워 작업자에게 공유하세요.")
    app_url = st.session_state.get("app_url") or default_app_url()
    if "localhost" in app_url or "127.0.0.1" in app_url:
        st.warning("localhost 주소는 다른 기기에서 열리지 않습니다. 배포 URL 또는 사내망 IP로 바꿔 주세요.", icon="⚠️")
    c1, c2 = st.columns(2)
    for col, title, url in ((c1, "🦺 AI 도우미 앱", app_url), (c2, "📖 안전수첩 E-Book", config.EBOOK_URL)):
        with col:
            st.markdown(f"**{title}**")
            st.markdown(f"<div style='background:#fff;padding:8px;border-radius:8px;max-width:320px'>{qr_svg(url)}</div>",
                        unsafe_allow_html=True)
            st.caption(url)


# ───────────────────────── 화면 ─────────────────────────
st.markdown(CSS, unsafe_allow_html=True)
if "app_url" not in st.session_state:
    st.session_state["app_url"] = default_app_url()

head_l, head_r = st.columns([5, 1.4], vertical_alignment="center")
with head_l:
    st.title("🦺 현장 안전수첩 AI 도우미", anchor=False)
    st.caption("오늘 할 작업을 입력하면 현대제철 안전수첩(수급업체, 2026)에서 **위험등급 · 필수 허가/조치 · TBM 체크리스트**를 근거 페이지와 함께 보여줍니다.")
with head_r:
    st.markdown(f"<div style='background:#fff;padding:6px;border-radius:8px;max-width:150px;margin-left:auto'>"
                f"{qr_svg(st.session_state['app_url'])}</div>", unsafe_allow_html=True)
    st.caption("📱 스캔하여 앱 열기")
    with st.popover("주소 변경", use_container_width=True):
        new_url = st.text_input("앱 주소", value=st.session_state["app_url"],
                                help="현장 휴대폰에서 접속할 배포 URL 또는 사내망 IP")
        if new_url.strip() and new_url.strip() != st.session_state["app_url"]:
            st.session_state["app_url"] = new_url.strip()
            st.rerun()

agent = get_agent()

with st.sidebar:
    st.subheader("상태", anchor=False)
    st.caption("수첩 원문 기반 · 검색: BM25 + " + ("ChromaDB 임베딩 (하이브리드)" if agent.ret.vec_ok else "ChromaDB 사용 불가 → BM25 단독"))
    st.subheader("예시 입력", anchor=False)
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True, key="ex-" + ex):
            st.session_state["pending"] = ex
    if st.button("📱 QR 코드 보기", use_container_width=True):
        show_qr()
    if st.button("🗑 대화 지우기", use_container_width=True):
        st.session_state["messages"] = []
        st.rerun()
    st.divider()
    st.caption("⚠️ 본 도구는 수첩의 일부 자료를 근거로 한 보조 도구이며 법적·공식 판단을 대체하지 않습니다. "
               "세부사항은 관련 지침과 현장 관리감독자에게 확인하세요.")

if "messages" not in st.session_state:
    st.session_state["messages"] = []

# ── 작업 사항 입력칸 (화면 상단)
st.markdown("<div class='item-sec'>✏️ 오늘 작업 내용을 입력하세요</div>", unsafe_allow_html=True)
with st.form("work_form", clear_on_submit=True):
    typed = st.text_area(
        "작업 사항",
        placeholder="예) 내일 저장탱크 내부에서 산소절단 작업 예정  (작업 장소·방법·높이·사용 장비를 함께 적으면 더 정확합니다)",
        height=110, max_chars=1000, label_visibility="collapsed",
    )
    submitted = st.form_submit_button("🔍 안전 기준 찾기", use_container_width=True, type="primary")
    st.caption("Ctrl + Enter 로도 제출할 수 있습니다.")

user_text = st.session_state.pop("pending", None)
if submitted:
    if (typed or "").strip():
        user_text = typed.strip()
    else:
        st.warning("작업 내용을 입력해 주세요.", icon="✏️")

# ── 처리
if user_text:
    history = [m["content"] for m in st.session_state["messages"] if m["role"] == "user"]
    with st.spinner("수첩에서 기준을 찾고 있습니다…"):
        result = agent.run(user_text, history)
    st.session_state["messages"] += [{"role": "user", "content": user_text},
                                     {"role": "assistant", "result": result, "query": user_text}]

# ── 예시 (결과가 없을 때만)
if not st.session_state["messages"]:
    st.markdown("<div class='item-sec'>이렇게 입력해 보세요</div>", unsafe_allow_html=True)
    cols = st.columns(2)
    for i, ex in enumerate(EXAMPLES[:4]):
        if cols[i % 2].button(ex, key=f"home-{i}", use_container_width=True):
            st.session_state["pending"] = ex
            st.rerun()

# ── 결과 (최신 입력이 맨 위)
msgs = st.session_state["messages"]
for pi in range(len(msgs) // 2 - 1, -1, -1):
    u, a = msgs[2 * pi], msgs[2 * pi + 1]
    with st.chat_message("user"):
        st.markdown(u["content"])
    with st.chat_message("assistant"):
        render_result(a["result"], a["query"], key=f"h{2 * pi + 1}")
