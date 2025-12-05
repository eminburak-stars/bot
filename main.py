import streamlit as st
import google.generativeai as genai
import os
import uuid
import io
import asyncio
import base64
import edge_tts
from PIL import Image

# --- 1. AYARLAR ---
st.set_page_config(
    page_title="BAUN-MYO Asistan", 
    page_icon="🎓",  
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- 2. CSS (PLAY TUŞUNU BÜYÜTELİM) ---
st.markdown("""
<style>
/* Mobilde rahat basılsın diye oynatıcıyı büyütüyoruz */
audio { 
    width: 100%; 
    height: 50px; 
    margin-top: 10px; 
    border-radius: 25px; 
    background-color: #f1f3f4; 
}
</style>
""", unsafe_allow_html=True)

# --- 3. SESSION STATE ---
if "messages" not in st.session_state: st.session_state.messages = []
if "session_id" not in st.session_state: st.session_state.session_id = str(uuid.uuid4())
if "process_audio" not in st.session_state: st.session_state.process_audio = False

# --- 4. API AYARLARI ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    st.error("API Key Hatası!")
    st.stop()

# --- 5. APPLE DOSTU PLAYER (OTOMATİK OYNATMA YOK!) ---
def apple_safe_player(audio_bytes):
    """
    Otomatik oynatmayı (autoplay) kapattık.
    Apple sadece kullanıcı tıklarsa ses çalar.
    """
    if not audio_bytes: return ""
    
    # Bytes -> Base64 dönüşümü
    if isinstance(audio_bytes, bytes):
        b64 = base64.b64encode(audio_bytes).decode()
    else:
        b64 = audio_bytes
        
    # ÖNEMLİ: autoplay yok! preload="auto" var.
    return f"""
    <audio controls preload="auto">
        <source src="data:audio/mpeg;base64,{b64}" type="audio/mpeg">
        Tarayıcınız bu sesi desteklemiyor.
    </audio>
    """

# --- 6. TTS MOTORU ---
async def edge_tts_generate(text, voice):
    communicate = edge_tts.Communicate(text, voice)
    mp3_fp = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_fp.write(chunk["data"])
    mp3_fp.seek(0)
    return mp3_fp.getvalue()

def metni_sese_cevir(text, voice_id="tr-TR-AhmetNeural"):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio = loop.run_until_complete(edge_tts_generate(text, voice_id))
        loop.close()
        return audio
    except: return None

# --- 7. SES GİRİŞİ ---
def sesten_yaziya(audio_bytes):
    try:
        model_flash = genai.GenerativeModel("gemini-2.0-flash")
        response = model_flash.generate_content([
            "Yazıya dök:", {"mime_type": "audio/webm", "data": audio_bytes} 
        ])
        return response.text.strip()
    except: return None

# --- 8. ARAYÜZ ---
st.title("BAUN AI (iOS Uyumlu)")
with st.sidebar:
    ses_aktif = st.toggle("🎤 Ses Modu", value=True)
    if st.button("Sıfırla"):
        st.session_state.messages = []
        st.rerun()

# --- 9. MESAJLARI GÖSTER ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        
        # Eğer ses verisi varsa player'ı koy
        if msg.get("audio_data"):
            st.markdown(apple_safe_player(msg["audio_data"]), unsafe_allow_html=True)

# --- 10. İŞLEM ---
prompt = None
if ses_aktif:
    val = st.audio_input("Konuş")
    if val and (not st.session_state.process_audio):
        st.session_state.process_audio = True
        with st.spinner("Dinleniyor..."):
            res = sesten_yaziya(val.read())
            if res: prompt = res
        st.session_state.process_audio = False

if not prompt:
    prompt = st.chat_input("Yaz...")

if prompt:
    # Kullanıcı mesajı
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    
    # Asistan Cevabı
    with st.chat_message("assistant"):
        with st.spinner("Cevap hazırlanıyor..."):
            chat = model.start_chat()
            response = chat.send_message(prompt)
            text = response.text
            st.write(text)
            
            final_audio = None
            if ses_aktif:
                # Sesi oluştur
                audio_bytes = metni_sese_cevir(text)
                if audio_bytes:
                    # Player'ı ekrana bas (Tıklaman lazım!)
                    st.markdown(apple_safe_player(audio_bytes), unsafe_allow_html=True)
                    final_audio = base64.b64encode(audio_bytes).decode()
            
            st.session_state.messages.append({
                "role": "assistant",
                "content": text,
                "audio_data": final_audio
            })