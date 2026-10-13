# 客服话术助手(优化版)
# 相比原版的改动:
#   1) 提示词升级成 6 条"输出契约"(含情绪处理、红线、具体到位的行动指引)
#   2) 按渠道 / 语气 / 回复长度生成,电话场景不再出现"亲"
#   3) 常见场景一键填充,不用手打客户问题
#   4) 产品资料改为每个会话独立保存,不再共用 knowledge.txt,避免多人串资料
#   5) 新增"内部提示"(依据 / 风险 / 该核实什么)和"换个说法"
import io
import streamlit as st
from openai import OpenAI
from pypdf import PdfReader

st.set_page_config(page_title="客服话术助手", page_icon="💬")

try:
    密钥 = st.secrets["DEEPSEEK_KEY"]
except Exception:
    st.error("还没配置 DEEPSEEK_KEY:请在 .streamlit/secrets.toml 里加上再打开。")
    st.stop()

client = OpenAI(api_key=密钥, base_url="https://api.deepseek.com")

内部标记 = "【内部提示】"

# 常见场景:点一下就填进去,不用手打
场景列表 = [
    ("问价格 / 优惠", "这个多少钱?有点贵,能便宜点吗?"),
    ("问交期 / 发货", "现在下单什么时候能发?我着急用。"),
    ("问库存 / 规格", "这个有货吗?都有哪些规格?"),
    ("催物流", "都三天了怎么还没到?我要退了。"),
    ("退换货", "收到的不合适,能退吗?怎么退?"),
    ("投诉 / 情绪激动", "你们这什么质量?我要投诉!"),
    ("差评挽回", "已经给你们差评了,太失望了。"),
    ("要发票 / 售后", "能开发票吗?保修多久?"),
]

渠道语气 = {
    "微信 / 私聊": "像熟人微信聊天:句子短,少客套,不用「亲」。",
    "淘宝 / 电商": "可以用「亲」:清楚利落,带一点促销感。",
    "抖音 / 短视频": "口语化、有网感、节奏快,少用书面词。",
    "电话 / 语音": "适合念出来的口语:句子短,不用表情,不用书面词。",
}

语气说明 = {
    "亲切随和": "像朋友一样,轻松、有温度",
    "专业稳妥": "专业、稳重、让人放心",
    "正式客气": "正式、礼貌、用词规范",
}

长度说明 = {
    "一句话就行": "尽量一句话说清,不超过 30 字。",
    "两三句(推荐)": "控制在 2-3 句、60 字以内。",
    "可以详细一点": "可以展开,但不要超过 4 句。",
}

# ============ 左边栏:资料管理 + 话术设置 ============
if "资料" not in st.session_state:
    st.session_state.资料 = ""
    st.session_state.资料名 = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
if "换说法" not in st.session_state:
    st.session_state.换说法 = ""

with st.sidebar:
    st.header("📁 产品资料")
    上传 = st.file_uploader("上传产品资料(txt / pdf)", type=["txt", "pdf"])
    if 上传 is not None:
        if 上传.name.endswith(".pdf"):
            读取器 = PdfReader(io.BytesIO(上传.read()))
            内容 = "\n".join(页.extract_text() or "" for 页 in 读取器.pages)
        else:
            内容 = 上传.read().decode("utf-8", errors="ignore")
        st.session_state.资料 = 内容.strip()
        st.session_state.资料名 = 上传.name
        st.success(f"已更新:{上传.name}({len(st.session_state.资料)} 字)")

    if st.session_state.资料名:
        st.caption(f"当前资料:{st.session_state.资料名}")
        if len(st.session_state.资料) > 8000:
            st.warning("资料有点长,重点容易被忽略。建议只留客户最常问的那几页。")
        if st.button("清除这份资料"):
            st.session_state.资料 = ""
            st.session_state.资料名 = ""
            st.rerun()

    st.divider()
    st.subheader("⚙️ 话术设置")
    渠道 = st.selectbox("客户从哪儿来", list(渠道语气.keys()))
    语气 = st.selectbox("语气", list(语气说明.keys()), index=1)
    长度 = st.selectbox("回复长度", list(长度说明.keys()), index=1)
    带表情 = st.checkbox("允许用表情", value=True)
    要内部提示 = st.checkbox("顺便告诉我这么说的理由", value=True)

    st.divider()
    if st.button("🗑️ 清空对话"):
        st.session_state.messages = []
        st.session_state.换说法 = ""
        st.rerun()

资料 = st.session_state.资料 or "(还没上传资料,请先在左边上传产品资料)"

表情说明 = (
    "可以在结尾放 1 个合适的表情,不要连着放好几个。"
    if 带表情
    else "不要使用任何表情符号。"
)

内部提示说明 = (
    f"""
【内部提示】
在给客户的回复之后换行,输出"{内部标记}",再用 1-2 句大白话说明:这句话依据了资料里的哪一点、哪里可能有风险、建议客服自己再核实什么。没把握就写"需要人工确认"。
"""
    if 要内部提示
    else f"""
【内部提示】
在给客户的回复之后换行,输出"{内部标记}",后面只写"无"。
"""
)

系统提示 = f"""你是一名做了 10 年的资深客服。你唯一的任务:把客户发来的话,变成能直接复制发给客户的回复。

【第一规则 · 输出什么】
只输出"可以原样发给客户"的话。不要写"可以这样回复""建议您先说"这类说明,不要自我介绍,不要输出思考过程。标点和称呼要像真人在手机上打字,不要公文腔。

【第二规则 · 只说资料里有的事】
只依据下面的【产品资料】回答。资料里没有的,以及价格、交期、库存、退换货政策这类会变的,一律不要编,统一回复:"亲,这个我跟技术/仓库确认一下,稍后回复您~"不要把"根据资料"这类内部说法发给客户。

【第三规则 · 先接情绪,再给方案】
客户生气、着急、失望时:第一句先接住情绪(道歉或共情),第二句给方案,最后一句给明确的下一步。任何时候都不要和客户争辩,不要说"这不是我们的问题""是您自己没看清"。

【第四规则 · 说清楚,别凑字数】
{长度说明[长度]}
需要客户配合的,把动作讲清楚:点哪里、发什么、等多久。时间不要用"尽快",要给具体预期;确实给不了,就说清楚什么时候能回复。

【第五规则 · 红线】
不承诺绝对结果(最好、绝对、100% 这类说法),不替公司答应赔偿、退款、免单、延长保修。遇到法律、医疗、安全、隐私、人身伤害相关的问题,不要自己判断,只回复会立刻转交专人处理。

【第六规则 · 说话风格】
语气:{语气说明[语气]}。
渠道:{渠道}。{渠道语气[渠道]}
{表情说明}

{内部提示说明}

【产品资料】
{资料}
"""

# ============ 界面 ============
st.title("💬 客服话术助手")
st.caption("把客户的问题粘进来,直接给你能发出去的话,还能看到为什么这么说")

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m["role"] == "assistant":
            st.code(m["content"], language=None)
            if m.get("内部"):
                with st.expander("🧠 内部提示(不要发给客户)"):
                    st.write(m["内部"])
        else:
            st.write(m["content"])

问题 = st.chat_input("把客户的问题粘贴进来,按回车")

with st.expander("⚡ 常见场景 · 点一下就填好", expanded=not st.session_state.messages):
    每行 = 4
    for 行号 in range(0, len(场景列表), 每行):
        列 = st.columns(每行)
        for i, (名称, 模板) in enumerate(场景列表[行号:行号 + 每行]):
            if 列[i].button(名称, use_container_width=True, key=f"场景_{名称}"):
                st.session_state.messages.append({"role": "user", "content": 模板})
                st.rerun()

if 问题:
    st.session_state.messages.append({"role": "user", "content": 问题})
    st.rerun()

# ============ 生成回复 ============
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    消息 = [{"role": "system", "content": 系统提示}]
    if st.session_state.换说法:
        消息.append({"role": "system", "content": st.session_state.换说法})
    消息 += [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]

    try:
        回复 = client.chat.completions.create(
            model="deepseek-chat",
            messages=消息,
            temperature=0.7,
            max_tokens=600,
        )
        全文 = (回复.choices[0].message.content or "").strip()
    except Exception as e:
        print("出错了:", e)
        st.warning("出了点小问题,请再点一次「换个说法」重试~")
        全文 = ""

    if 全文:
        if 内部标记 in 全文:
            回答, _, 内部 = 全文.partition(内部标记)
            回答, 内部 = 回答.strip(), 内部.strip()
        else:
            回答, 内部 = 全文, ""

        with st.chat_message("assistant"):
            st.code(回答, language=None)
            if 内部 and 内部 != "无":
                with st.expander("🧠 内部提示(不要发给客户)", expanded=True):
                    st.write(内部)

        st.session_state.换说法 = ""
        st.session_state.messages.append({"role": "assistant", "content": 回答, "内部": 内部})

# ============ 不满意就换一版 ============
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    if st.button("🔄 换个说法"):
        上次 = st.session_state.messages[-1]["content"]
        st.session_state.换说法 = (
            f"同一句客户的话你已经答过一次。上次你的回复是:「{上次}」。"
            "这次换一个完全不同的角度和措辞,信息量保持一致,不要和上次重复。"
        )
        st.session_state.messages.pop()
        st.rerun()