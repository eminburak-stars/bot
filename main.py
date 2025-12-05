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
from gtts import gTTS 

# --- 1. SAYFA AYARLARI ---
st.set_page_config(
    page_title="BAUN-MYO Asistan", 
    page_icon="🎓",  
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- 2. TASARIM (CSS) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
html, body, [class*="css"] {font-family: 'Inter', sans-serif;}
footer {visibility: hidden;}
header {background-color: transparent !important;}
.stApp {background-color: #0e1117;}
[data-testid="stSidebar"] {background-color: #161b22 !important;}
/* Ses oynatıcı için özel stil */
audio { width: 100%; margin-top: 10px; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 3. KLASÖR VE DOSYA AYARLARI ---
SESSION_FOLDER = "sessions"
if not os.path.exists(SESSION_FOLDER): os.makedirs(SESSION_FOLDER)
USER_HISTORY_FILE = os.path.join(SESSION_FOLDER, "chat_history_v2.json") # Dosya adını değiştirdim çakışma olmasın

# --- 4. SESSION STATE ---
if "messages" not in st.session_state: st.session_state.messages = []
if "session_id" not in st.session_state: st.session_state.session_id = str(uuid.uuid4())
if "process_audio" not in st.session_state: st.session_state.process_audio = False

# --- 5. API AYARLARI ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    system_instruction = "Sen Balıkesir MYO öğrencileri için yardımcı bir asistansın. Samimi ol. Görsel istenirse [GORSEL_OLUSTUR] etiketi kullan."
    model = genai.GenerativeModel(model_name='gemini-2.0-flash', system_instruction=system_instruction)
    imagen_model = genai.GenerativeModel("imagen-3.0-generate-001")
except Exception as e:
    st.error(f"API Key Hatası: {e}")
    st.stop()

# --- 6. KRİTİK FONKSİYON: SAFARİ DOSTU SES OYNATICI ---
# İşte büyü burada kral. st.audio yerine bunu kullanacağız.
def apple_dostu_oynatici(audio_b64, autoplay=False):
    """
    Sesi Streamlit bileşeni olarak değil, saf HTML5 audio etiketi olarak basar.
    Bu yöntem Apple/Safari'deki MIME type ve Range Request sorunlarını aşar.
    """
    if not audio_b64: return ""
    
    autoplay_attr = "autoplay" if autoplay else ""
    
    # HTML bloğu oluşturuyoruz. 
    # data:audio/mp3;base64,... diyerek sesi direkt kodun içine gömüyoruz.
    audio_html = f"""
    <audio controls {autoplay_attr} style="width: 100%;">
        <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
        Tarayıcınız ses elementini desteklemiyor.
    </audio>
    """
    return audio_html

# --- DİĞER YARDIMCI FONKSİYONLAR ---
def metni_sese_cevir_b64(text):
    try:
        tts = gTTS(text=text, lang='tr', slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        # Bytes'ı Base64 string'e çeviriyoruz
        return base64.b64encode(fp.read()).decode()
    except: return None

def sesten_metne(audio_bytes):
    try:
        model_flash = genai.GenerativeModel("gemini-2.0-flash")
        response = model_flash.generate_content([
            "Sesi yazıya dök.", {"mime_type": "audio/webm", "data": audio_bytes}
        ])
        return response.text.strip()
    except: return None

def gorsel_olustur(prompt):
    try:
        res = imagen_model.generate_images(prompt=prompt, number_of_images=1)
        if res and res.images:
            return Image.open(io.BytesIO(res.images[0].image_bytes)), None
        return None, "Resim hatası."
    except Exception as e: return None, str(e)

# --- 7. GEÇMİŞ YÖNETİMİ ---
def save_chat():
    with open(USER_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(st.session_state.messages, f, ensure_ascii=False)

def load_chat():
    if os.path.exists(USER_HISTORY_FILE):
        try:
            with open(USER_HISTORY_FILE, "r", encoding="utf-8") as f:
                st.session_state.messages = json.load(f)
        except: st.session_state.messages = []

if "loaded" not in st.session_state:
    load_chat()
    st.session_state.loaded = True

# --- 8. SIDEBAR ---
with st.sidebar:
    st.title("Ayarlar")
    ses_aktif = st.toggle("🎤 Sesli Yanıt Modu", value=True)
    if st.button("Sohbeti Sıfırla", type="primary"):
        st.session_state.messages = []
        if os.path.exists(USER_HISTORY_FILE): os.remove(USER_HISTORY_FILE)
        st.rerun()

# --- 9. ANA EKRAN ---
st.title("BAUN-MYO Asistan")

# Mesajları Listeleme
for msg in st.session_state.messages:
    avatar = "👤" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        # İçerik
        if msg.get("content"): st.markdown(msg["content"])
        
        # Resim
        if msg.get("image"):
            try:
                img_bytes = base64.b64decode(msg["image"])
                st.image(Image.open(io.BytesIO(img_bytes)), width=300)
            except: pass

        # SES (HTML Injection Yöntemi)
        if msg.get("audio_data"):
            # st.audio YERİNE HTML KULLANIYORUZ
            html_code = apple_dostu_oynatici(msg["audio_data"], autoplay=False)
            st.markdown(html_code, unsafe_allow_html=True)

# --- 10. GİRİŞ İŞLEMLERİ ---
prompt = None
if ses_aktif:
    audio_val = st.audio_input("Konuş")
    if audio_val:
        if "last_audio" not in st.session_state or st.session_state.last_audio != audio_val.name:
            st.session_state.process_audio = True
            st.session_state.last_audio = audio_val.name
            with st.spinner("Dinliyorum..."):
                txt = sesten_metne(audio_val.read())
                if txt: prompt = txt
            st.session_state.process_audio = False

if prompt is None:
    prompt = st.chat_input("Yaz...")

# --- 11. YANIT ÜRETME ---
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Düşünüyorum..."):
            # API Çağrısı
            gemini_history = [{"role": "user" if m["role"] == "user" else "model", "parts": [m.get("content","")]} for m in st.session_state.messages[:-1]]
            chat = model.start_chat(history=gemini_history)
            resp = chat.send_message(prompt)
            bot_text = resp.text
            
            final_img_b64 = None
            final_audio_b64 = None
            
            # Görsel mi?
            if "[GORSEL_OLUSTUR]" in bot_text:
                prompt_img = bot_text.replace("[GORSEL_OLUSTUR]", "").strip()
                img, err = gorsel_olustur(prompt_img)
                if img:
                    st.image(img)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    final_img_b64 = base64.b64encode(buf.getvalue()).decode()
                    bot_text = "Görsel hazır."
                else: st.error(err)
            else:
                st.markdown(bot_text)
                
                # Ses Oluşturma
                if ses_aktif:
                    # Sesi oluşturup Base64 string yapıyoruz
                    final_audio_b64 = metni_sese_cevir_b64(bot_text)
                    
                    if final_audio_b64:
                        # O anlık oynatmak için HTML basıyoruz (Autoplay açık)
                        html_code = apple_dostu_oynatici(final_audio_b64, autoplay=True)
                        st.markdown(html_code, unsafe_allow_html=True)

            # Kayıt
            st.session_state.messages.append({
                "role": "assistant",
                "content": bot_text,
                "image": final_img_b64,
                "audio_data": final_audio_b64 
            })
            save_chat()