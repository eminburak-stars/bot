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

# --- 2. CSS AYARLARI ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
html, body, [class*="css"] {font-family: 'Inter', sans-serif;}
footer {visibility: hidden;}
header {background-color: transparent !important;}
.stApp {background-color: #0e1117;}
[data-testid="stSidebar"] {background-color: #161b22 !important;}
.stChatMessage {border-radius: 10px; margin-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

# --- 3. KLASÖR VE AYARLAR ---
SESSION_FOLDER = "sessions"
if not os.path.exists(SESSION_FOLDER): os.makedirs(SESSION_FOLDER)
USER_HISTORY_FILE = os.path.join(SESSION_FOLDER, "chat_history.json")

# --- 4. SESSION STATE BAŞLATMA ---
if "messages" not in st.session_state: st.session_state.messages = []
if "session_id" not in st.session_state: st.session_state.session_id = str(uuid.uuid4())
if "process_audio" not in st.session_state: st.session_state.process_audio = False

# --- 5. API AYARLARI ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    # Sistem talimatı
    system_instruction = "Sen Balıkesir MYO öğrencileri için yardımcı bir asistansın. Samimi, yardımsever ol. Eğer görsel istenirse [GORSEL_OLUSTUR] etiketi kullan."
    model = genai.GenerativeModel(model_name='gemini-2.0-flash', system_instruction=system_instruction)
    imagen_model = genai.GenerativeModel("imagen-3.0-generate-001")
except Exception as e:
    st.error(f"API Key Hatası: {e}")
    st.stop()

# --- 6. KRİTİK FONKSİYONLAR (SES İÇİN) ---

def audio_bytes_to_b64(audio_bytes):
    """Ses verisini metne çevirir (JSON'a kaydetmek için)"""
    return base64.b64encode(audio_bytes).decode()

def b64_to_audio_bytes(b64_string):
    """Metni ses verisine çevirir (Oynatmak için)"""
    return base64.b64decode(b64_string)

def metni_sese_cevir_b64(text):
    """Metni okur, base64 string olarak döndürür"""
    try:
        tts = gTTS(text=text, lang='tr', slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return audio_bytes_to_b64(fp.read())
    except: return None

def sesten_metne(audio_bytes):
    """Gemini ile sesi yazıya döker"""
    try:
        model_flash = genai.GenerativeModel("gemini-2.0-flash")
        response = model_flash.generate_content([
            "Sesi tam olarak yazıya dök.",
            {"mime_type": "audio/webm", "data": audio_bytes}
        ])
        return response.text.strip()
    except: return None

def gorsel_olustur(prompt):
    """Resim oluşturur"""
    try:
        res = imagen_model.generate_images(prompt=prompt, number_of_images=1)
        if res and res.images:
            return Image.open(io.BytesIO(res.images[0].image_bytes)), None
        return None, "Resim oluşturulamadı."
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

# Uygulama açılışında geçmişi yükle (sadece bir kez)
if "loaded" not in st.session_state:
    load_chat()
    st.session_state.loaded = True

# --- 8. SIDEBAR ---
with st.sidebar:
    st.title("Ayarlar")
    ses_aktif = st.toggle("🎤 Sesli Yanıt Modu", value=True) # Varsayılan açık olsun
    
    if st.button("Temizle / Sıfırla", type="primary"):
        st.session_state.messages = []
        if os.path.exists(USER_HISTORY_FILE): os.remove(USER_HISTORY_FILE)
        st.rerun()

# --- 9. ANA EKRAN (GÖRÜNTÜLEME) ---
st.title("BAUN-MYO Asistan")

# Mesajları Ekrana Basma Döngüsü
# BURASI ÇOK ÖNEMLİ: 'ses_aktif' değişkenine bakmaksızın, ses verisi varsa oynatıcı koyuyoruz.
for i, msg in enumerate(st.session_state.messages):
    avatar = "👤" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        # 1. Metin
        if "content" in msg and msg["content"]:
            st.markdown(msg["content"])
        
        # 2. Resim (Base64'ten çöz)
        if "image" in msg and msg["image"]:
            try:
                img_bytes = base64.b64decode(msg["image"])
                st.image(Image.open(io.BytesIO(img_bytes)), width=300)
            except: pass

        # 3. SES (Base64'ten çöz ve oynat) - KRİTİK NOKTA
        if "audio_data" in msg and msg["audio_data"]:
            try:
                audio_bytes = b64_to_audio_bytes(msg["audio_data"])
                # Key eşsiz olmalı ki Streamlit karıştırmasın
                st.audio(audio_bytes, format="audio/mp3", start_time=0)
            except: pass

# --- 10. GİRİŞ ALANI (SES veya METİN) ---
prompt = None

# Ses Girişi
if ses_aktif:
    audio_val = st.audio_input("Konuşmak için bas")
    if audio_val:
        # Sadece yeni bir ses geldiğinde işle
        if "last_audio" not in st.session_state or st.session_state.last_audio != audio_val.name:
            st.session_state.process_audio = True
            st.session_state.last_audio = audio_val.name
            
            with st.spinner("Ses işleniyor..."):
                text_res = sesten_metne(audio_val.read())
                if text_res:
                    prompt = text_res
            st.session_state.process_audio = False

# Metin Girişi
if prompt is None:
    prompt = st.chat_input("Mesaj yaz...")

# --- 11. CEVAP ÜRETME ---
if prompt:
    # Kullanıcı mesajını ekle
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # Asistan cevabı
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Düşünüyorum..."):
            # Geçmişi formatla
            history_gemini = []
            for m in st.session_state.messages[:-1]:
                role = "user" if m["role"] == "user" else "model"
                history_gemini.append({"role": role, "parts": [m.get("content", "")]})
            
            chat = model.start_chat(history=history_gemini)
            response = chat.send_message(prompt)
            bot_text = response.text
            
            final_img_b64 = None
            final_audio_b64 = None
            
            # Görsel isteği kontrolü
            if "[GORSEL_OLUSTUR]" in bot_text:
                img_prompt = bot_text.replace("[GORSEL_OLUSTUR]", "").strip()
                img, err = gorsel_olustur(img_prompt)
                if img:
                    st.image(img, caption="Oluşturulan Görsel")
                    # Görseli base64 yapıp sakla
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    final_img_b64 = base64.b64encode(buf.getvalue()).decode()
                    bot_text = "Görsel oluşturuldu."
                else:
                    st.error(err)
            else:
                st.markdown(bot_text)
                
                # SES OLUŞTURMA (Eğer ses modu açıksa)
                if ses_aktif:
                    final_audio_b64 = metni_sese_cevir_b64(bot_text)
                    if final_audio_b64:
                        # Hemen oynat
                        st.audio(b64_to_audio_bytes(final_audio_b64), format="audio/mp3")

            # Mesajı oturuma kaydet (SES VERİSİ DAHİL)
            st.session_state.messages.append({
                "role": "assistant",
                "content": bot_text,
                "image": final_img_b64,
                "audio_data": final_audio_b64 # <--- İŞTE BURASI OLMADAN OLMAZ
            })
            
            save_chat() # Dosyaya yaz