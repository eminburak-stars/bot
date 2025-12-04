import streamlit as st
import google.generativeai as genai
import json
import os
import uuid
import time
from datetime import datetime
from PIL import Image
import io
import base64
import speech_recognition as sr
from gtts import gTTS
import tempfile

# --- 1. SAYFA AYARLARI ---
st.set_page_config(
    page_title="BAUN-MYO Asistan",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- 2. PROFESYONEL TASARIM (CSS) ---
custom_style = """
<style>
/* Fontu Google'dan çekelim (Inter Fontu) */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Gereksizleri Gizle */
footer {visibility: hidden;}
header {background-color: transparent !important;}

/* Ana Arka Plan */
.stApp {
    background-color: #0e1117;
}

/* Yan Menü (Sidebar) */
section[data-testid="stSidebar"] {
    background-color: #161b22 !important;
    border-right: 1px solid #30363d;
}

/* Yan Menü Başlıkları */
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    color: #c9d1d9 !important;
}

/* Butonlar */
.stButton button {
    border: 1px solid #30363d;
    border-radius: 8px;
    background-color: #21262d;
    color: #c9d1d9;
    transition: all 0.3s ease;
}
.stButton button:hover {
    background-color: #30363d;
    border-color: #8b949e;
    color: white;
}

/* --- CHAT BALONLARI TASARIMI --- */

/* Asistan Mesajı (Sol) */
[data-testid="stChatMessage"]:nth-of-type(odd) {
    background-color: #21262d; /* Koyu Gri */
    border: 1px solid #30363d;
    border-radius: 0px 20px 20px 20px;
    padding: 15px;
    margin-bottom: 10px;
}

/* Kullanıcı Mesajı (Sağ - Simüle) */
[data-testid="stChatMessage"]:nth-of-type(even) {
    background-color: #1f6feb; /* Güzel bir Mavi */
    color: white;
    border-radius: 20px 0px 20px 20px;
    padding: 15px;
    margin-bottom: 10px;
    border: none;
}

/* Kullanıcı mesajındaki metin rengini zorla beyaz yap */
[data-testid="stChatMessage"]:nth-of-type(even) * {
    color: white !important;
}

/* Mesaj Giriş Kutusu (Chat Input) */
.stChatInputContainer {
    padding-bottom: 20px;
}
.stChatInputContainer textarea {
    background-color: #161b22;
    color: white;
    border: 1px solid #30363d;
    border-radius: 12px;
}
.stChatInputContainer textarea:focus {
    border-color: #1f6feb;
    box-shadow: 0 0 0 1px #1f6feb;
}

</style>
"""
st.markdown(custom_style, unsafe_allow_html=True)

# --- 3. KLASÖR VE TEMİZLİK (Garbage Collector) ---
SESSION_FOLDER = "sessions"
if not os.path.exists(SESSION_FOLDER):
    os.makedirs(SESSION_FOLDER)

def temizlik_yap(dakika=30):
    su_an = time.time()
    try:
        for dosya in os.listdir(SESSION_FOLDER):
            if dosya.endswith(".json"):
                dosya_yolu = os.path.join(SESSION_FOLDER, dosya)
                dosya_zamani = os.path.getmtime(dosya_yolu)
                if (su_an - dosya_zamani) > (dakika * 60):
                    try:
                        os.remove(dosya_yolu)
                    except: pass
    except: pass

temizlik_yap(dakika=30)

# --- 4. SESSION ID ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

USER_HISTORY_FILE = os.path.join(SESSION_FOLDER, f"history_{st.session_state.session_id}.json")

# --- 5. API AYARLARI ---
okul_bilgileri = """
Sen Balıkesir Üniversitesi Meslek Yüksekokulu (BAUN MYO) asistanısın.
İsmin BAUN Asistan.
Çok ciddi, sade ve net cevaplar ver.
Cevaplarında ASLA emoji kullanma.
Samimi ol ama cıvık olma. Sadece metin odaklı konuş.
Tasarımcı gibi düşün, minimalist cevaplar ver.
"""

try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        system_instruction=okul_bilgileri
    )
except Exception as e:
    st.error(f"API Hatası: {e}")
    st.stop()

# --- 6. YARDIMCI FONKSİYONLAR ---
def load_history():
    if not os.path.exists(USER_HISTORY_FILE): return []
    try:
        with open(USER_HISTORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return []

def save_history(history):
    with open(USER_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def image_to_base64(image):
    try:
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    except: return None

def base64_to_image(base64_str):
    try:
        if base64_str: return Image.open(io.BytesIO(base64.b64decode(base64_str)))
    except: return None

def sesten_yaziya(audio_bytes):
    r = sr.Recognizer()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_audio:
        tmp_audio.write(audio_bytes)
        tmp_audio_path = tmp_audio.name
    try:
        with sr.AudioFile(tmp_audio_path) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="tr-TR")
            return text
    except: return None
    finally:
        if os.path.exists(tmp_audio_path): os.unlink(tmp_audio_path)

def yazidan_sese(text):
    try:
        tts = gTTS(text=text, lang='tr')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
    except: return None

# --- 7. SIDEBAR (YAN MENÜ) ---
if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.title("BAUN MYO")
    st.markdown("---")
    
    st.subheader("İşlemler")
    
    uploaded_file = st.file_uploader("Görsel Yükle", type=["jpg", "png", "jpeg"])
    current_image = None
    if uploaded_file:
        try:
            current_image = Image.open(uploaded_file)
            st.success("Görsel eklendi.")
            st.image(current_image, use_container_width=True)
        except: st.error("Hata")

    st.markdown("---")
    ses_aktif = st.toggle("Sesli Yanıt", value=False)
    
    if st.button("Yeni Sohbet", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_chat_id = str(uuid.uuid4())
        st.rerun()
    
    st.markdown("### Geçmiş Sohbetler")
    for chat in reversed(load_history()):
        raw_title = chat.get("title", "Sohbet")
        display_title = (raw_title[:22] + '..') if len(raw_title) > 22 else raw_title
        
        if st.button(f"{display_title}", key=chat["id"], use_container_width=True):
            st.session_state.messages = chat["messages"]
            st.session_state.current_chat_id = chat["id"]
            st.rerun()
            
    st.markdown("---")
    if st.button("Geçmişi Temizle", type="primary", use_container_width=True):
        if os.path.exists(USER_HISTORY_FILE): os.remove(USER_HISTORY_FILE)
        st.session_state.messages = []
        st.rerun()

# --- 8. ANA EKRAN ---
st.markdown("<h1 style='text-align: center; color: white;'>BAUN-MYO AI Asistan</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Size nasıl yardımcı olabilirim?</p>", unsafe_allow_html=True)

# Mesajları Döngüyle Yazdır
for message in st.session_state.messages:
    # Avatar kullanmıyoruz, Streamlit varsayılanı kullansın (Sade)
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("image"):
            try:
                img = base64_to_image(message["image"])
                if img: st.image(img, width=300)
            except: pass

# --- 9. GİRİŞ ALANI ---
audio_value = None
if ses_aktif:
    st.write("**Mikrofon:**")
    audio_value = st.audio_input("Konuş")

text_input = st.chat_input("Mesajınızı buraya yazın...") 
prompt = None

if ses_aktif and audio_value:
    with st.spinner("Sesiniz işleniyor..."):
        prompt = sesten_yaziya(audio_value.read())
        if not prompt: st.warning("Ses anlaşılamadı.")
elif text_input:
    prompt = text_input

# --- 10. CEVAP ÜRETME ---
if prompt:
    saved_image_base64 = None
    saved_image_for_api = None
    if current_image:
        saved_image_base64 = image_to_base64(current_image)
        saved_image_for_api = current_image.copy()
    
    # Kullanıcı mesajını hemen göster
    with st.chat_message("user"):
        st.markdown(prompt)
        if saved_image_for_api: st.image(saved_image_for_api, width=300)
    
    st.session_state.messages.append({
        "role": "user", "content": prompt, "image": saved_image_base64
    })

    try:
        with st.spinner('Asistan düşünüyor...'):
            chat_history_text = []
            for m in st.session_state.messages[:-1]:
                chat_history_text.append({
                    "role": "user" if m["role"] == "user" else "model", 
                    "parts": [m["content"]]
                })
            
            chat_session = model.start_chat(history=chat_history_text)
            
            if saved_image_for_api:
                response = chat_session.send_message([prompt, saved_image_for_api])
            else:
                response = chat_session.send_message(prompt)
            
            bot_reply = response.text
        
        # Bot cevabını göster
        with st.chat_message("assistant"):
            st.markdown(bot_reply)
            if ses_aktif:
                audio_file = yazidan_sese(bot_reply)
                if audio_file: st.audio(audio_file, format='audio/mp3', autoplay=True)

        st.session_state.messages.append({
            "role": "assistant", "content": bot_reply, "image": None
        })
        
        # --- KAYIT (SAVE) ---
        current_history = load_history()
        chat_exists = False
        
        if "current_chat_id" not in st.session_state:
            st.session_state.current_chat_id = str(uuid.uuid4())
            
        cid = st.session_state.current_chat_id

        for chat in current_history:
            if chat["id"] == cid:
                chat["messages"] = st.session_state.messages
                chat_exists = True
                break
        
        if not chat_exists:
            title = prompt[:30] + "..." if len(prompt) > 30 else prompt
            new_data = {
                "id": cid, 
                "title": title, 
                "timestamp": str(datetime.now()), 
                "messages": st.session_state.messages
            }
            current_history.append(new_data)
        
        save_history(current_history)

    except Exception as e:
        st.error(f"Bir hata oluştu: {e}")