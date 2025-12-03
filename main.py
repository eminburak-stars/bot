import streamlit as st
import google.generativeai as genai
import json
import os
import uuid
from datetime import datetime
from PIL import Image
import io
import base64
import speech_recognition as sr
from gtts import gTTS
import tempfile

# --- 1. AYARLAR ---
st.set_page_config(
    page_title="BAUN-MYO AI Asistanı", 
    page_icon="🎓", 
    layout="centered",
    initial_sidebar_state="expanded"
)

# Gereksiz Streamlit yazılarını gizle
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display:none;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- 2. BİLGİLERİ DOSYADAN OKU (GARANTİ YÖNTEM) ---
import os

def bilgileri_yukle():
    try:
        # Kodun çalıştığı klasörü bul
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # bilgi.txt ile yolu birleştir
        file_path = os.path.join(current_dir, "bilgi.txt")
        
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Hata: bilgi.txt dosyası bulunamadı! Lütfen dosyayı GitHub'a yüklediğinden emin ol."

okul_bilgileri = bilgileri_yukle()

# --- 3. MODELİ BAŞLAT ---
# API Key'i secrets'tan çekiyoruz (Güvenlik için)
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    # Eğer secrets dosyası yoksa veya hata varsa buraya düşer
    st.error("❌ Hacı, .streamlit/secrets.toml dosyası yok veya API Key bulunamadı!")
    st.stop()

try:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        # Burada az önce tanımladığımız okul_bilgileri'ni kullanıyoruz
        system_instruction=okul_bilgileri
    )
except Exception as e:
    st.error(f"Bağlantı hatası: {e}")
    st.stop()

# --- 4. GEÇMİŞ YÖNETİMİ ---
HISTORY_FILE = "sohbet_gecmisi.json"

def load_history():
    if not os.path.exists(HISTORY_FILE): return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def image_to_base64(image):
    try:
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    except:
        return None

def base64_to_image(base64_str):
    try:
        if base64_str:
            return Image.open(io.BytesIO(base64.b64decode(base64_str)))
    except:
        return None

# --- 5. SES İŞLEMLERİ ---
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
    except:
        return None
    finally:
        if os.path.exists(tmp_audio_path):
            os.unlink(tmp_audio_path)

def yazidan_sese(text):
    try:
        tts = gTTS(text=text, lang='tr')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
    except:
        return None

# --- SESSION BAŞLATMA ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []

# --- 6. YAN MENÜ (SIDEBAR) ---
with st.sidebar:
    st.header("🗂️ BAUN-MYO AI")
    
    st.subheader("📷 Fotoğraf Yükle")
    uploaded_file = st.file_uploader("Bir resim seç...", type=["jpg", "png", "jpeg"])
    
    current_image = None
    if uploaded_file:
        try:
            current_image = Image.open(uploaded_file)
            st.image(current_image, caption='Analize Hazır', use_container_width=True)
            st.info("Resim yüklendi! Şimdi sorunu sor.")
        except Exception as e:
            st.error(f"Hata: {e}")

    st.divider()

    # SESLİ SOHBET MODU
    ses_aktif = st.toggle("🎙️ Sesli Sohbet Modu", value=False)

    st.divider()

    if st.button("➕ Yeni Sohbet", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    
    st.subheader("Geçmiş")
    for chat in reversed(load_history()):
        btn_text = chat.get("title", "Sohbet")
        if st.button(f"💬 {btn_text}", key=chat["id"], use_container_width=True):
            st.session_state.session_id = chat["id"]
            st.session_state.messages = chat["messages"]
            st.rerun()
            
    if st.button("🗑️ Hepsini Sil"):
        if os.path.exists(HISTORY_FILE): os.remove(HISTORY_FILE)
        st.session_state.messages = []
        st.rerun()

# --- 7. ANA EKRAN ---
st.title("🎓 BAUN-MYO AI Asistanı")
st.caption("Görsel, Metinsel ve Sesli Analiz Asistanı")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("image"):
            try:
                img = base64_to_image(message["image"])
                if img: st.image(img, width=300)
            except: pass

# --- 8. GİRİŞ YÖNTEMLERİ ---
audio_value = None
if ses_aktif:
    st.write("🎙️ **Sesli Soru Sor:**")
    audio_value = st.audio_input("Mikrofonu kullanmak için tıkla")

text_input = st.chat_input("Sorunuzu yazın...")

prompt = None
if ses_aktif and audio_value:
    with st.spinner("Sesin yazıya dökülüyor kral..."):
        prompt = sesten_yaziya(audio_value.read())
        if not prompt:
            st.warning("Dediklerini tam anlayamadım, tekrar dene be gülüm.")
elif text_input:
    prompt = text_input

# --- 9. CEVAP ÜRETME ---
if prompt:
    saved_image_base64 = None
    saved_image_for_api = None
    if current_image:
        saved_image_base64 = image_to_base64(current_image)
        saved_image_for_api = current_image.copy()
    
    with st.chat_message("user"):
        st.markdown(prompt)
        if saved_image_for_api:
            st.image(saved_image_for_api, width=300)
    
    st.session_state.messages.append({
        "role": "user", 
        "content": prompt,
        "image": saved_image_base64
    })

    try:
        with st.spinner('Yapay Zeka düşünüyor...'):
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
        
        with st.chat_message("assistant"):
            st.markdown(bot_reply)
            if ses_aktif:
                audio_file = yazidan_sese(bot_reply)
                if audio_file:
                    st.audio(audio_file, format='audio/mp3', autoplay=True)

        st.session_state.messages.append({
            "role": "assistant", 
            "content": bot_reply,
            "image": None
        })
        
        current_history = load_history()
        chat_exists = False
        for chat in current_history:
            if chat["id"] == st.session_state.session_id:
                chat["messages"] = st.session_state.messages
                chat_exists = True
                break
        
        if not chat_exists:
            title = prompt[:25] + "..." if len(prompt) > 25 else prompt
            new_data = {
                "id": st.session_state.session_id, 
                "title": title, 
                "timestamp": str(datetime.now()), 
                "messages": st.session_state.messages
            }
            current_history.append(new_data)
        save_history(current_history)

    except Exception as e:
        st.error(f"Bir sıkıntı çıktı kral: {e}")