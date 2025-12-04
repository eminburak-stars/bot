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

# --- 1. AYARLAR & CSS ---
st.set_page_config(
    page_title="BAUN-MYO-AI Asistan", 
    page_icon="indir.jpeg",  
    layout="centered",
    initial_sidebar_state="auto"
)

custom_style = """
<style>
footer {visibility: hidden;}
header {background-color: transparent !important;}
.block-container {padding-top: 3rem !important; padding-bottom: 2rem !important;}
section[data-testid="stSidebar"] {background-color: #19191a !important;}
[data-testid="stSidebarCollapsedControl"] {color: #19191a !important;}
.stButton button {border: 1px solid #e0e0e0; border-radius: 8px; background-color: transparent;}
</style>
"""
st.markdown(custom_style, unsafe_allow_html=True)

# --- 2. TEMİZLİKÇİ FONKSİYONU (Depo Şişmesin Diye) ---
def temizlik_yap(dakika=30):
    """
    Belirtilen süreden (dakika) daha eski olan sohbet dosyalarını siler.
    """
    su_an = time.time()
    klasor = "."  # Mevcut klasör
    
    try:
        for dosya in os.listdir(klasor):
            # Sadece bizim oluşturduğumuz json dosyalarına bak
            if dosya.startswith("sohbet_gecmisi_") and dosya.endswith(".json"):
                dosya_yolu = os.path.join(klasor, dosya)
                dosya_zamani = os.path.getmtime(dosya_yolu)
                
                # Süresi dolmuşsa sil
                if (su_an - dosya_zamani) > (dakika * 60):
                    try:
                        os.remove(dosya_yolu)
                    except:
                        pass
    except Exception as e:
        pass # Hata olursa akışı bozma, devam et

# Uygulama her tetiklendiğinde önden bir temizlik yapsın
temizlik_yap(dakika=30)

# --- 3. SESSION ID YÖNETİMİ ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# Her kullanıcıya özel dosya ismi
USER_HISTORY_FILE = f"sohbet_gecmisi_{st.session_state.session_id}.json"

# --- 4. API BAĞLANTISI ---
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

# --- 5. FONKSİYONLAR ---
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

# --- SESSION MESAJLARI ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 6. YAN MENÜ ---
with st.sidebar:
    st.subheader("Menü")
    uploaded_file = st.file_uploader("Görsel Ekle", type=["jpg", "png", "jpeg"])
    current_image = None
    if uploaded_file:
        try:
            current_image = Image.open(uploaded_file)
            st.image(current_image, caption='Görsel Hazır', use_container_width=True)
        except: st.error("Hata")

    st.text("")
    ses_aktif = st.toggle("Sesli Yanıt", value=False)
    st.text("")

    if st.button("Yeni Sohbet", use_container_width=True):
        st.session_state.messages = []
        # Yeni sohbet için yeni bir chat ID üretelim ki geçmişe ayrı kaydetsin
        st.session_state.current_chat_id = str(uuid.uuid4())
        st.rerun()
    
    st.subheader("Geçmiş")
    for chat in reversed(load_history()):
        raw_title = chat.get("title", "Sohbet")
        btn_text = raw_title[:20] + "..." if len(raw_title) > 20 else raw_title
        if st.button(btn_text, key=chat["id"], use_container_width=True):
            st.session_state.messages = chat["messages"]
            st.session_state.current_chat_id = chat["id"]
            st.rerun()
            
    if st.button("Geçmişi Temizle"):
        if os.path.exists(USER_HISTORY_FILE): os.remove(USER_HISTORY_FILE)
        st.session_state.messages = []
        st.rerun()

# --- 7. ANA EKRAN ---
st.header("BAUN-MYO-AI Asistan")
st.caption("MYO'nun Görsel, Sesli ve Metinsel Yapay Zekası")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("image"):
            try:
                img = base64_to_image(message["image"])
                if img: st.image(img, width=300)
            except: pass

# --- 8. GİRİŞ ALANI ---
audio_value = None
if ses_aktif:
    st.write("Mikrofon:")
    audio_value = st.audio_input("Konuş")

text_input = st.chat_input("Mesajınızı yazın...") 
prompt = None

if ses_aktif and audio_value:
    with st.spinner("Dinliyorum..."):
        prompt = sesten_yaziya(audio_value.read())
        if not prompt: st.warning("Anlaşılamadı.")
elif text_input:
    prompt = text_input

# --- 9. CEVAP ÜRETME ---
if prompt:
    saved_image_base64 = None
    saved_image_for_api = None
    if current_image:
        saved_image_base64 = image_to_base64(current_image)
        saved_image_for_api = current_image.copy()
    
    # Kullanıcı mesajını ekrana bas
    with st.chat_message("user"):
        st.markdown(prompt)
        if saved_image_for_api: st.image(saved_image_for_api, width=300)
    
    st.session_state.messages.append({
        "role": "user", "content": prompt, "image": saved_image_base64
    })

    try:
        with st.spinner('...'):
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
        
        # Asistan mesajını ekrana bas
        with st.chat_message("assistant"):
            st.markdown(bot_reply)
            if ses_aktif:
                audio_file = yazidan_sese(bot_reply)
                if audio_file: st.audio(audio_file, format='audio/mp3', autoplay=True)

        st.session_state.messages.append({
            "role": "assistant", "content": bot_reply, "image": None
        })
        
        # Dosyaya kaydet
        current_history = load_history()
        chat_exists = False
        
        # Eğer aktif bir chat ID yoksa oluştur
        if "current_chat_id" not in st.session_state:
            st.session_state.current_chat_id = str(uuid.uuid4())
            
        cid = st.session_state.current_chat_id

        for chat in current_history:
            if chat["id"] == cid:
                chat["messages"] = st.session_state.messages
                chat_exists = True
                break
        
        if not chat_exists:
            title = prompt[:20] + "..." if len(prompt) > 20 else prompt
            new_data = {
                "id": cid, 
                "title": title, 
                "timestamp": str(datetime.now()), 
                "messages": st.session_state.messages
            }
            current_history.append(new_data)
        
        save_history(current_history)

    except Exception as e:
        st.error(f"Hata: {e}")