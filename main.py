import streamlit as st
import google.generativeai as genai
import json
import os
import uuid
import time
from datetime import datetime
from PIL import Image
import io
import asyncio
import base64 # Base64 kütüphanesi şart
import edge_tts

# --- 1. SAYFA AYARLARI ---
st.set_page_config(
    page_title="BAUN-MYO Asistan", 
    page_icon="🎓",  
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- 2. CSS ---
st.markdown("""
<style>
/* Ses oynatıcıyı güzelleştirelim */
audio { width: 100%; margin-top: 5px; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 3. KLASÖR VE AYARLAR ---
SESSION_FOLDER = "sessions"
if not os.path.exists(SESSION_FOLDER): os.makedirs(SESSION_FOLDER)
USER_HISTORY_FILE = os.path.join(SESSION_FOLDER, f"history_{st.session_state.get('session_id', 'default')}.json")

# --- 4. SESSION STATE ---
if "session_id" not in st.session_state: st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state: st.session_state.messages = []
if "process_audio" not in st.session_state: st.session_state.process_audio = False

# --- 5. API AYARLARI ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    # Model ayarları...
    system_instruction = "Sen Balıkesir MYO öğrencileri için yardımcı bir asistansın. Samimi ol."
    model = genai.GenerativeModel(model_name='gemini-2.0-flash', system_instruction=system_instruction)
    imagen_model = genai.GenerativeModel("imagen-3.0-generate-001")
except Exception as e:
    st.error(f"API Key Hatası: {e}")
    st.stop()

# --- 6. KRİTİK FONKSİYON: APPLE DOSTU SES OYNATICI ---
def html_audio_autoplay(audio_bytes, autoplay=False):
    """
    Sesi Base64 formatına çevirip HTML <audio> etiketi olarak basar.
    Bu yöntem Safari/iOS sorununu çözer.
    """
    if not audio_bytes: return None
    
    # Bytes verisini Base64 string'e çeviriyoruz
    b64 = base64.b64encode(audio_bytes).decode()
    
    # HTML kodunu oluşturuyoruz
    # autoplay=True ise otomatik başlar (iOS bazen engeller ama deniyoruz)
    autoplay_attr = "autoplay" if autoplay else ""
    md = f"""
        <audio controls {autoplay_attr} preload="auto">
        <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
        Tarayıcınız sesi desteklemiyor.
        </audio>
        """
    return md

# --- DİĞER FONKSİYONLAR ---
def load_history():
    if not os.path.exists(USER_HISTORY_FILE): return []
    try:
        with open(USER_HISTORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return []

def save_history(history):
    with open(USER_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def image_to_bytes(image):
    try:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except: return None

# ASYNC EDGE TTS
async def edge_tts_generate(text, voice):
    communicate = edge_tts.Communicate(text, voice)
    mp3_fp = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_fp.write(chunk["data"])
    mp3_fp.seek(0)
    return mp3_fp

def metni_sese_cevir_bytes(text, voice_id="tr-TR-AhmetNeural"):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_fp = loop.run_until_complete(edge_tts_generate(text, voice_id))
        loop.close()
        return audio_fp.getvalue() # Bytes döndür
    except Exception as e: return None

def sesten_yaziya(audio_bytes):
    try:
        model_flash = genai.GenerativeModel("gemini-2.0-flash")
        response = model_flash.generate_content([
            "Yazıya dök:", {"mime_type": "audio/webm", "data": audio_bytes} 
        ])
        return response.text.strip()
    except: return None

# --- 7. ARAYÜZ ---
with st.sidebar:
    st.title("BAUN MYO")
    ses_aktif = st.toggle("🎤 Sesli Yanıt", value=True)
    voice_choice = st.radio("Ses", ["Erkek (Ahmet)", "Kadın (Emel)"], index=0)
    voice_id = "tr-TR-AhmetNeural" if "Ahmet" in voice_choice else "tr-TR-EmelNeural"
    
    if st.button("Sıfırla", type="primary"):
        st.session_state.messages = []
        if os.path.exists(USER_HISTORY_FILE): os.remove(USER_HISTORY_FILE)
        st.rerun()

st.title("BAUN AI Asistan")

# --- 8. MESAJLARI GÖSTER (GÜNCELLENDİ) ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        # Metin
        if msg.get("content"): st.markdown(msg["content"])
        
        # Resim
        if msg.get("image_bytes"):
            try: st.image(msg["image_bytes"], width=300)
            except: pass
            
        # SES (İŞTE ÇÖZÜM BURASI)
        if msg.get("audio_bytes"):
            # st.audio YERİNE HTML KULLANIYORUZ
            # Bytes verisini alıp HTML'e çeviriyoruz
            # Ancak JSON'dan okurken bu veri base64 string olabilir, kontrol edelim.
            audio_data = msg["audio_bytes"]
            
            # Eğer veri zaten bytes ise (yeni oluştuysa)
            if isinstance(audio_data, bytes):
                html_code = html_audio_autoplay(audio_data, autoplay=False)
                st.markdown(html_code, unsafe_allow_html=True)
            
            # Eğer veri string ise (JSON'dan geldiyse - encode/decode gerekir)
            # Not: JSON bytes saklamaz, string saklar. Kayıt yaparken encode etmek lazım.
            # Şimdilik karmaşıklık olmasın diye sadece anlık oturum için bytes varsayıyoruz.

# --- 9. İŞLEMLER ---
prompt = None

if ses_aktif:
    audio_val = st.audio_input("Konuş")
    if audio_val:
        if "last_audio" not in st.session_state or st.session_state.last_audio != audio_val.name:
            st.session_state.process_audio = True
            st.session_state.last_audio = audio_val.name
    
    if st.session_state.process_audio and audio_val:
        with st.spinner("Dinliyorum..."):
            txt = sesten_yaziya(audio_val.read())
            if txt: prompt = txt
        st.session_state.process_audio = False

if not prompt:
    prompt = st.chat_input("Mesaj...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Düşünüyorum..."):
            # Basitçe sohbet geçmişi
            hist = [{"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]} for m in st.session_state.messages]
            chat = model.start_chat(history=hist[:-1])
            response = chat.send_message(prompt)
            bot_text = response.text
            
            st.markdown(bot_text)
            
            final_audio_bytes = None
            if ses_aktif:
                final_audio_bytes = metni_sese_cevir_bytes(bot_text, voice_id)
                if final_audio_bytes:
                    # HEMEN OYNAT (Apple Dostu HTML ile)
                    html_code = html_audio_autoplay(final_audio_bytes, autoplay=True)
                    st.markdown(html_code, unsafe_allow_html=True)
            
            st.session_state.messages.append({
                "role": "assistant",
                "content": bot_text,
                "audio_bytes": final_audio_bytes # Oturum boyunca sakla
            })
            # JSON'a kaydederken bytes hatası almamak için burayı geliştirmek gerekebilir
            # ama canlı oturumda bu çalışır.