import streamlit as st
import google.generativeai as genai
import os
import uuid
import io
import base64
from PIL import Image
from gtts import gTTS # Sadece bunu kullanacağız, macera yok.

# --- 1. AYARLAR ---
st.set_page_config(
    page_title="BAUN-MYO Asistan", 
    page_icon="🎓",  
    layout="centered",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
audio { width: 100%; height: 54px; margin-top: 10px; border-radius: 12px; }
.stChatInputContainer textarea {border-radius: 12px;}
</style>
""", unsafe_allow_html=True)

# --- 2. SESSION STATE ---
if "messages" not in st.session_state: st.session_state.messages = []
if "session_id" not in st.session_state: st.session_state.session_id = str(uuid.uuid4())
if "process_audio" not in st.session_state: st.session_state.process_audio = False

# --- 3. API BAĞLANTISI ---
try:
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
    else:
        st.error("🚨 HATA: Secrets içinde API Key yok!")
        st.stop()
        
    genai.configure(api_key=api_key)
    # Model Ayarları
    model = genai.GenerativeModel('gemini-2.0-flash', system_instruction="Sen Balıkesir MYO asistanısın. Samimi ol.")
    imagen_model = genai.GenerativeModel("imagen-3.0-generate-001")
except Exception as e:
    st.error(f"Bağlantı Hatası: {e}")
    st.stop()

# --- 4. FONKSİYONLAR (GARANTİ VERSİYON) ---

# A) Ses Oynatıcı (Boş veri kontrolü ekledim)
def safe_audio_player(audio_bytes, key_id):
    if not audio_bytes or len(audio_bytes) < 100:
        return ""
    
    try:
        b64 = base64.b64encode(audio_bytes).decode()
        # Key ekleyerek her player'ın benzersiz olmasını sağlıyoruz
        return f"""
        <audio id="audio_{key_id}" controls preload="auto">
            <source src="data:audio/mpeg;base64,{b64}" type="audio/mpeg">
        </audio>
        """
    except:
        return ""

# B) Sadece gTTS (En Sorunsuzu)
def metni_sese_cevir(text):
    try:
        # Google Translate TTS (En güvenilir yöntem)
        tts = gTTS(text=text, lang='tr')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp.read()
    except Exception as e:
        st.error(f"Ses oluşturma hatası: {e}")
        return None

# C) Sesten Yazıya (Gemini)
def sesten_yaziya(audio_bytes):
    try:
        m = genai.GenerativeModel("gemini-2.0-flash")
        res = m.generate_content(["Yazıya dök:", {"mime_type": "audio/webm", "data": audio_bytes}])
        return res.text.strip()
    except: return None

# D) Resim Çizme
def gorsel_olustur(prompt):
    try:
        res = imagen_model.generate_images(prompt=prompt, number_of_images=1)
        if res and res.images:
            return Image.open(io.BytesIO(res.images[0].image_bytes)), None
        return None, "Servis meşgul."
    except Exception as e: return None, str(e)

# Görüntü Yardımcıları
def image_to_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def base64_to_image(b64_str):
    return Image.open(io.BytesIO(base64.b64decode(b64_str)))

# --- 5. SIDEBAR ---
with st.sidebar:
    st.title("Ayarlar")
    uploaded_file = st.file_uploader("Resim Yükle", type=["jpg", "png"])
    current_image = None
    if uploaded_file:
        current_image = Image.open(uploaded_file)
        st.image(current_image, caption="Yüklendi")

    st.markdown("---")
    ses_aktif = st.toggle("🎤 Sesli Yanıt", value=True)
    
    if st.button("Temizle", type="primary"):
        st.session_state.messages = []
        st.rerun()

# --- 6. AKIŞ ---
st.title("BAUN AI Asistan")

# Mesajları Göster
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg.get("content"): st.markdown(msg["content"])
        
        if msg.get("image_data"):
            try: st.image(base64_to_image(msg["image_data"]), width=300)
            except: pass
            
        if msg.get("audio_data"):
            # Player kodunu buraya basıyoruz
            st.markdown(safe_audio_player(msg["audio_data"], i), unsafe_allow_html=True)

# Girdi Alanı
prompt = None

# Sesli Giriş (Streamlit 1.39+)
if ses_aktif:
    try:
        audio_val = st.audio_input("Konuş")
        if audio_val:
            if "last_audio" not in st.session_state or st.session_state.last_audio != audio_val.name:
                st.session_state.process_audio = True
                st.session_state.last_audio = audio_val.name
        
        if st.session_state.process_audio and audio_val:
            with st.spinner("Ses işleniyor..."):
                prompt = sesten_yaziya(audio_val.read())
            st.session_state.process_audio = False
    except: pass

if not prompt:
    prompt = st.chat_input("Mesaj yaz...")

if prompt:
    user_img_b64 = image_to_base64(current_image) if current_image else None
    st.session_state.messages.append({"role": "user", "content": prompt, "image_data": user_img_b64})
    
    with st.chat_message("user"):
        st.write(prompt)
        if current_image: st.image(current_image, width=300)
        
    with st.chat_message("assistant"):
        with st.spinner("..."):
            try:
                # API Çağrısı
                hist = [{"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]} 
                        for m in st.session_state.messages if m.get("content")]
                
                chat = model.start_chat(history=hist[:-1])
                response = chat.send_message([prompt, current_image] if current_image else prompt)
                bot_text = response.text
                
                final_img = None
                final_audio = None # Bytes olarak saklayacağız
                
                # Görsel İsteği Var mı?
                if "[GORSEL_OLUSTUR]" in bot_text:
                    p = bot_text.replace("[GORSEL_OLUSTUR]", "").strip()
                    img, err = gorsel_olustur(p)
                    if img:
                        st.image(img)
                        final_img = image_to_base64(img)
                        bot_text = "Görsel oluşturuldu."
                    else: st.error(err)
                else:
                    st.markdown(bot_text)
                    if ses_aktif:
                        # GÜVENLİ SES OLUŞTURMA
                        audio_bytes = metni_sese_cevir(bot_text)
                        
                        if audio_bytes and len(audio_bytes) > 0:
                            # Player'ı hemen göster
                            # Debug için boyutunu yazdırıyorum, çalışınca kaldırırsın
                            # st.caption(f"Ses verisi: {len(audio_bytes)} bytes") 
                            st.markdown(safe_audio_player(audio_bytes, 999), unsafe_allow_html=True)
                            final_audio = audio_bytes
                        else:
                            st.warning("Ses verisi oluşturulamadı (0 byte).")

                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": bot_text, 
                    "image_data": final_img, 
                    "audio_data": final_audio
                })
            except Exception as e:
                st.error(f"Hata: {e}")