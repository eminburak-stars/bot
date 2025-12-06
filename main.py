import streamlit as st
import google.generativeai as genai
import os
import uuid
import io
import asyncio
import base64
import edge_tts
from PIL import Image
from gtts import gTTS
import nest_asyncio

# --- KRİTİK YAMA: ASYNCIO DÖNGÜ HATASINI ÖNLER ---
try:
    nest_asyncio.apply()
except:
    pass

# --- 1. AYARLAR ---
st.set_page_config(
    page_title="BAUN-MYO Asistan", 
    page_icon="🎓",  
    layout="centered",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
audio { width: 100%; height: 45px; margin-top: 5px; border-radius: 20px; background-color: #f1f3f4; }
.stChatInputContainer textarea {border-radius: 12px;}
</style>
""", unsafe_allow_html=True)

# --- 2. SESSION STATE ---
if "messages" not in st.session_state: st.session_state.messages = []
if "session_id" not in st.session_state: st.session_state.session_id = str(uuid.uuid4())
if "process_audio" not in st.session_state: st.session_state.process_audio = False

# --- 3. API BAĞLANTISI (HATA YAKALAMALI) ---
try:
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
    else:
        st.error("🚨 HATA: Streamlit Secrets içinde 'GOOGLE_API_KEY' bulunamadı!")
        st.stop()
        
    genai.configure(api_key=api_key)
    system_instruction = "Sen Balıkesir MYO öğrencileri için yardımcı bir asistansın. Samimi ol. Görsel istenirse [GORSEL_OLUSTUR] etiketi kullan."
    model = genai.GenerativeModel(model_name='gemini-2.0-flash', system_instruction=system_instruction)
    imagen_model = genai.GenerativeModel("imagen-3.0-generate-001")
except Exception as e:
    st.error(f"🚨 API Bağlantı Hatası: {e}")
    st.stop()

# --- 4. FONKSİYONLAR ---

# A) Apple Dostu Player
def apple_safe_player(audio_data):
    if not audio_data: return ""
    b64 = base64.b64encode(audio_data).decode() if isinstance(audio_data, bytes) else audio_data
    return f"""
    <audio controls preload="auto">
        <source src="data:audio/mpeg;base64,{b64}" type="audio/mpeg">
        Ses desteklenmiyor.
    </audio>
    """

# B) HİBRİT SES MOTORU (EDGE TTS -> Hata Verirse -> gTTS)
async def edge_tts_generate(text, voice):
    communicate = edge_tts.Communicate(text, voice)
    mp3_fp = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_fp.write(chunk["data"])
    mp3_fp.seek(0)
    return mp3_fp.getvalue()

def metni_sese_cevir(text, voice_id):
    # 1. YÖNTEM: Kaliteli Ses (Edge TTS)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_bytes = loop.run_until_complete(edge_tts_generate(text, voice_id))
        loop.close()
        return audio_bytes
    except Exception as e:
        # Eğer Edge TTS hata verirse (async sorunu vs.) konsola yaz
        print(f"EdgeTTS Hatası: {e}")
        # 2. YÖNTEM: Yedek Ses (gTTS) - Asla yolda bırakmaz
        try:
            # st.warning("Kaliteli ses motoru hata verdi, yedek motora geçildi.")
            tts = gTTS(text=text, lang='tr')
            fp = io.BytesIO()
            tts.write_to_fp(fp)
            return fp.getvalue()
        except Exception as e2:
            st.error(f"Ses tamamen çöktü: {e2}")
            return None

# C) Sesten Yazıya
def sesten_yaziya(audio_bytes):
    try:
        m = genai.GenerativeModel("gemini-2.0-flash")
        res = m.generate_content(["Yazıya dök:", {"mime_type": "audio/webm", "data": audio_bytes}])
        return res.text.strip()
    except Exception as e:
        st.error(f"Ses tanıma hatası: {e}")
        return None

# D) Görsel
def gorsel_olustur(prompt):
    try:
        res = imagen_model.generate_images(prompt=prompt, number_of_images=1)
        if res and res.images:
            return Image.open(io.BytesIO(res.images[0].image_bytes)), None
        return None, "Servis yanıt vermedi."
    except Exception as e: return None, str(e)

def image_to_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def base64_to_image(b64_str):
    return Image.open(io.BytesIO(base64.b64decode(b64_str)))

# --- 5. ARAYÜZ ---
with st.sidebar:
    st.title("Ayarlar")
    uploaded_file = st.file_uploader("Görsel Yükle", type=["jpg", "png"])
    current_image = None
    if uploaded_file:
        current_image = Image.open(uploaded_file)
        st.image(current_image, caption="Analiz için hazır")

    st.markdown("---")
    ses_aktif = st.toggle("🎤 Sesli Yanıt", value=True)
    voice_choice = st.radio("Ses", ["Erkek (Ahmet)", "Kadın (Emel)"], index=0)
    voice_id = "tr-TR-AhmetNeural" if "Ahmet" in voice_choice else "tr-TR-EmelNeural"
    
    if st.button("Sıfırla", type="primary"):
        st.session_state.messages = []
        st.rerun()

# --- 6. AKIŞ ---
st.title("BAUN AI Asistan")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("content"): st.markdown(msg["content"])
        if msg.get("image_data"): 
            try: st.image(base64_to_image(msg["image_data"]), width=300)
            except: pass
        if msg.get("audio_data"):
            st.markdown(apple_safe_player(msg["audio_data"]), unsafe_allow_html=True)

prompt = None
if ses_aktif:
    # Streamlit 1.39+ özelliği
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
    except AttributeError:
        st.error("Streamlit versiyonu eski! requirements.txt içine 'streamlit>=1.39.0' yazmalısın.")

if not prompt:
    prompt = st.chat_input("Yaz...")

if prompt:
    user_img_b64 = image_to_base64(current_image) if current_image else None
    st.session_state.messages.append({"role": "user", "content": prompt, "image_data": user_img_b64})
    
    with st.chat_message("user"):
        st.write(prompt)
        if current_image: st.image(current_image, width=300)
        
    with st.chat_message("assistant"):
        with st.spinner("..."):
            try:
                # Geçmiş hazırlığı
                gemini_hist = [{"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]} 
                               for m in st.session_state.messages if m.get("content")]
                
                chat = model.start_chat(history=gemini_hist[:-1])
                response = chat.send_message([prompt, current_image] if current_image else prompt)
                bot_text = response.text
                
                final_img = None
                final_audio = None
                
                if "[GORSEL_OLUSTUR]" in bot_text:
                    p = bot_text.replace("[GORSEL_OLUSTUR]", "").strip()
                    img, err = gorsel_olustur(p)
                    if img:
                        st.image(img)
                        final_img = image_to_base64(img)
                        bot_text = "Görsel hazır."
                    else: st.error(err)
                else:
                    st.markdown(bot_text)
                    if ses_aktif:
                        # Ses oluştururken hata olursa program kırılmasın diye try-except içine aldık
                        # Ve yukarıda gTTS yedeği ekledik
                        audio_bytes = metni_sese_cevir(bot_text, voice_id)
                        if audio_bytes:
                            final_audio = base64.b64encode(audio_bytes).decode()
                            st.markdown(apple_safe_player(final_audio), unsafe_allow_html=True)
                
                st.session_state.messages.append({
                    "role": "assistant", "content": bot_text, 
                    "image_data": final_img, "audio_data": final_audio
                })
            except Exception as e:
                st.error(f"Beklenmedik Hata: {e}")