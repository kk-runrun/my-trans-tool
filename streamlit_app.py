import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
import bcrypt
from openai import OpenAI
import csv
from datetime import datetime
import pandas as pd

# 引入后端的逻辑模块
from backend import FileParser, SimpleRAG, AIAgent

# ==========================================
# 0. 全局配置 & 工具函数
# ==========================================
ALLOWED_USERS_WHITELIST = ["admin", "manager_li", "translator_01", "dev_test"]

def log_usage(username, action, details=""):
    """记录用户行为到 CSV 文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("usage_log.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, username, action, details])

# ==========================================
# 1. 核心应用逻辑
# ==========================================
st.set_page_config(layout="wide", page_title="AI 批量翻译工作台")

def main_app():
    if "tasks" not in st.session_state:
        st.session_state.tasks = {} 
    if "rag_system" not in st.session_state:
        st.session_state.rag_system = None
    if "processing" not in st.session_state:
        st.session_state.processing = False

    FIXED_API_KEY = "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" 
    FIXED_BASE_URL = "http://gptapi.kuajingvs.com:7999/v1s" 
    FIXED_MODEL_NAME = "gpt-4o" 

    try:
        client = OpenAI(
            api_key=FIXED_API_KEY, 
            base_url=FIXED_BASE_URL,
            timeout=60.0 
        )
        agent = AIAgent(client, model_name=FIXED_MODEL_NAME)
    except Exception as e:
        st.error(f"❌ 系统配置错误: {e}")
        st.stop()

    # --- C. 侧边栏 ---
    with st.sidebar:
        st.title("⚙️ 设置与输入")
        st.info(f"当前用户: {st.session_state.get('name', 'Unknown')}")
        st.caption(f"当前模型: {FIXED_MODEL_NAME}")
        
        # 1. 知识库上传
        kb_files = st.file_uploader("上传知识库 (RAG)", accept_multiple_files=True)
        if kb_files and st.button("建立索引"):
            rag = SimpleRAG(client)
            rag.ingest(kb_files)
            st.session_state.rag_system = rag
            st.success("知识库建立完成")

        # 2. 待翻译文件上传
        target_files = st.file_uploader("待翻译文件", accept_multiple_files=True)
        
        # 3. 开始按钮
        if target_files and st.button("🚀 开始"):
            current_user = st.session_state.get('username', 'Unknown')
            log_usage(current_user, "START_TASK", f"提交了 {len(target_files)} 个文件")
            
            for f in target_files:
                if f.name not in st.session_state.tasks:
                    content = FileParser.extract_text(f) 
                    content = FileParser.optimize_text(content)
                    st.session_state.tasks[f.name] = {
                        "status": "翻译中", 
                        "raw": content, 
                        "chunks": [content],
                        "translated_chunks": [],
                        "result": None,
                        "api_log": []
                    }
            st.session_state.processing = True
            st.rerun()

        # --- 管理员后台监控 ---
        if st.session_state.get('username') == 'admin':
            st.markdown("---")
            st.subheader("🕵️ 管理员后台")
            if st.checkbox("查看行为日志"):
                try:
                    df_log = pd.read_csv("usage_log.csv", names=["Time", "User", "Action", "Details"])
                    st.dataframe(df_log)
                except FileNotFoundError:
                    st.info("暂无日志记录")

    # --- D. 主界面逻辑 ---
    st.title("🏭 智能翻译工作台")
    
    if st.session_state.get("processing"):
        for name, task in st.session_state.tasks.items():
            if task['status'] == "翻译中":
                # 调用 agent
                res = agent.run_translation(task['chunks'][0], "", "翻译它")
                task['result'] = res
                task['status'] = "已完成"
        st.session_state.processing = False
        st.rerun()

    # --- E. 结果展示与下载区 (已恢复) ---
    if st.session_state.tasks:
        st.markdown("---")
        selected_file = st.selectbox("📂 选择文件查看结果:", list(st.session_state.tasks.keys()))
        task = st.session_state.tasks[selected_file]
        
        c1, c2 = st.columns(2)
        
        with c1: 
            st.subheader("🇨🇳 原文 (中文)")
            st.text_area("Raw Text", task['raw'], height=500, disabled=True)
            
        with c2: 
            st.subheader("🇺🇸 译文 (英文) & 下载")
            
            if task['status'] == "翻译中":
                st.info("⏳ 正在努力翻译中...")
                
            elif task['result']:
                res = task['result']
                if "error" in res:
                    st.error(f"翻译出错: {res['error']}")
                    st.caption("建议：出错咯。")
                else:
                    v1_text = res.get('v1', '')
                    v2_text = res.get('v2', '')
                    
                    tab1, tab2 = st.tabs(["📝 精准直译", "✨ 地道流畅"])
                    
                    with tab1:
                        st.text_area("精准版", v1_text, height=350)
                        if v1_text:
                            st.download_button("📥 下载 Word", FileParser.generate_word(v1_text), f"{selected_file}_precise.docx")
                            st.download_button("📥 下载 TXT", v1_text, f"{selected_file}_precise.txt")

                    with tab2:
                        st.text_area("流畅版", v2_text, height=350)
                        if v2_text:
                            st.success("👇 推荐下载")
                            st.download_button("📥 下载 Word", FileParser.generate_word(v2_text), f"{selected_file}_fluent.docx")
                            st.download_button("📥 下载 TXT", v2_text, f"{selected_file}_fluent.txt")
            else:
                st.warning("等待处理...")
    else:
        st.info("👈 请在左侧上传文件并点击“🚀 开始”")

# ==========================================
# 2. 门卫逻辑
# ==========================================
if __name__ == "__main__":
    with open('config.yaml', encoding='utf-8') as file:
        config = yaml.load(file, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days']
    )

    authenticator.login(location='main')
    
    authentication_status = st.session_state.get('authentication_status')
    name = st.session_state.get('name')
    username = st.session_state.get('username')

    if authentication_status:
        authenticator.logout('退出登录', 'sidebar')
        st.session_state['name'] = name
        st.session_state['username'] = username
        
        if "has_logged_in" not in st.session_state:
            log_usage(username, "LOGIN", "用户登录成功")
            st.session_state["has_logged_in"] = True
            
        main_app()

    elif authentication_status is False:
        st.error('用户名或密码错误')

    elif authentication_status is None:
        st.warning('请登录以继续使用')
        st.markdown("---")
        with st.expander("📝 新用户注册"):
            new_user = st.text_input("用户名 (ID)")
            new_name = st.text_input("昵称")
            new_pass = st.text_input("密码", type="password")
            new_pass2 = st.text_input("确认密码", type="password")
            
            if st.button("提交注册"):
                if new_user not in ALLOWED_USERS_WHITELIST:
                    st.error("🚫 用户无权限")
                elif new_user in config['credentials']['usernames']:
                    st.warning("⚠️ 用户已存在")
                elif new_pass != new_pass2:
                    st.error("❌ 密码不一致")
                else:
                    try:
                        b_password = new_pass.encode('utf-8')
                        salt = bcrypt.gensalt()
                        hashed_pass = bcrypt.hashpw(b_password, salt).decode('ascii')
                        
                        config['credentials']['usernames'][new_user] = {
                            "name": new_name,
                            "password": hashed_pass
                        }
                        with open('config.yaml', 'w', encoding='utf-8') as file:
                            yaml.dump(config, file, default_flow_style=False)
                        st.success(f"✅ 注册成功！")
                    except Exception as e:
                        st.error(f"注册失败: {e}")
