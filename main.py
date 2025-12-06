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
import edge_tts

# --- 1. SAYFA AYARLARI ---
st.set_page_config(
    page_title="BAUN-MYO Asistan", 
    page_icon="🎓",  
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- 2. TASARIM (CSS) ---
custom_style = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
html, body, [class*="css"] {font-family: 'Inter', sans-serif;}
footer {visibility: hidden;}
header {background-color: transparent !important;}
.stApp {background-color: #0e1117;}
section[data-testid="stSidebar"] {background-color: #161b22 !important; border-right: 1px solid #30363d;}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {color: #c9d1d9 !important;}
.stButton button {border: 1px solid #30363d; border-radius: 8px; background-color: #21262d; color: #c9d1d9; transition: all 0.3s ease;}
.stButton button:hover {background-color: #30363d; border-color: #8b949e; color: white;}
[data-testid="stChatMessage"]:nth-of-type(odd) {background-color: #21262d; border: 1px solid #30363d; border-radius: 0px 20px 20px 20px; padding: 15px; margin-bottom: 10px;}
[data-testid="stChatMessage"]:nth-of-type(even) {background-color: #1f6feb; color: white; border-radius: 20px 0px 20px 20px; padding: 15px; margin-bottom: 10px; border: none;}
[data-testid="stChatMessage"]:nth-of-type(even) * {color: white !important;}
.stChatInputContainer textarea {background-color: #161b22; color: white; border: 1px solid #30363d; border-radius: 12px;}
</style>
"""
st.markdown(custom_style, unsafe_allow_html=True)

# --- 3. KLASÖR VE TEMİZLİK ---
SESSION_FOLDER = "sessions"
if not os.path.exists(SESSION_FOLDER):
    os.makedirs(SESSION_FOLDER)

def temizlik_yap(dakika=60):
    su_an = time.time()
    try:
        for dosya in os.listdir(SESSION_FOLDER):
            if dosya.endswith(".json"):
                dosya_yolu = os.path.join(SESSION_FOLDER, dosya)
                if (su_an - os.path.getmtime(dosya_yolu)) > (dakika * 60):
                    try: os.remove(dosya_yolu)
                    except: pass
    except: pass

temizlik_yap(dakika=60)

# --- 4. SESSION STATE ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "voice_text" not in st.session_state:
    st.session_state.voice_text = None

if "process_audio" not in st.session_state:
    st.session_state.process_audio = False

# İşte burası düzeldi, tek başına bir satır oldu:
USER_HISTORY_FILE = os.path.join(SESSION_FOLDER, f"history_{st.session_state.session_id}.json")

# --- 5. API ---
def bilgi_bankasini_oku():
    try:
        if os.path.exists("bilgi.txt"):
            with open("bilgi.txt", "r", encoding="utf-8") as f:
                return f.read()
    except: pass
    return "Sen bir yapay zeka asistanısın."

okul_bilgisi = bilgi_bankasini_oku()

system_instruction = f"""
{okul_bilgisi}

EKSTRA GÖREV (GÖRSEL OLUŞTURMA):
Eğer kullanıcı senden açıkça bir görsel, resim, fotoğraf veya çizim oluşturmanı isterse, normal bir cevap verme.
Bunun yerine, cevabının başına tam olarak şu etiketi koy: `[GORSEL_OLUSTUR]`
Bu etiketin hemen ardından, kullanıcının istediği görseli detaylı bir şekilde tarif eden İNGİLİZCE bir prompt yaz.
Örnek: `[GORSEL_OLUSTUR] A photorealistic image of Balikesir University campus.`
"""

try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name='gemini-2.0-flash', system_instruction=system_instruction)
    imagen_model = genai.GenerativeModel("imagen-3.0-generate-001")
except Exception as e:
    st.error(f"API Hatası (Secrets kontrol et): {e}")
    st.stop()

# --- 6. YARDIMCI FONKSİYONLAR ---
def load_history():
    if not os.path.exists(USER_HISTORY_FILE): return []
    try:
        with open(USER_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
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

# --- SES MOTORU (ORİJİNAL HALİ) ---
async def edge_tts_generate(text, voice):
    """Sesi asenkron olarak oluşturur (Microsoft Neural Voice)"""
    communicate = edge_tts.Communicate(text, voice)
    mp3_fp = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_fp.write(chunk["data"])
    mp3_fp.seek(0)
    return mp3_fp

def metni_sese_cevir_bytes(text, voice_id="tr-TR-AhmetNeural"):
    """
    Streamlit (senkron) içinden Async fonksiyonu çalıştırır.
    RAM üzerinde sesi oluşturur, diske yazmaz.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_fp = loop.run_until_complete(edge_tts_generate(text, voice_id))
        loop.close()
        return audio_fp
    except Exception as e:
        st.error(f"Ses Hatası: {e}")
        return None

# --- SES İŞLEME (INPUT) ---
def sesten_yaziya(audio_bytes):
    try:
        transcription_model = genai.GenerativeModel("gemini-2.0-flash")
        response = transcription_model.generate_content([
            "Bu ses kaydını dinle ve Türkçe olarak yazıya dök. Sadece söylenen metni ver.",
            {"mime_type": "audio/webm", "data": audio_bytes} 
        ])
        return response.text.strip()
    except Exception as e:
        return None

def gorsel_olustur(prompt_text):
    try:
        result = imagen_model.generate_images(
            prompt=prompt_text,
            number_of_images=1,
            aspect_ratio="1:1",
            safety_filter_level="block_few",
            person_generation="allow_adult"
        )
        if result and result.images:
             image_data = result.images[0].image_bytes
             img = Image.open(io.BytesIO(image_data))
             return img, None
        else:
             return None, "Model görsel üretemedi."
    except Exception as e:
        return None, str(e)

# --- 7. SIDEBAR ---
with st.sidebar:
    st.title("BAUN MYO")
    st.markdown("---")
    
    uploaded_file = st.file_uploader("Görsel Yükle", type=["jpg", "png", "jpeg"])
    current_image = None
    if uploaded_file:
        try:
            current_image = Image.open(uploaded_file)
            st.success("✅ Görsel yüklendi.")
            st.image(current_image, use_container_width=True)
        except: pass
            
    st.markdown("---")
    ses_aktif = st.toggle("🎤 Sesli Yanıt", value=False)

    # --- SES SEÇİMİ ---
    if ses_aktif:
        voice_choice = st.radio("Ses Tonu", ["Erkek (Ahmet)", "Kadın (Emel)"], index=0)
        # Microsoft Edge Ses Kodları
        voice_id = "tr-TR-AhmetNeural" if "Ahmet" in voice_choice else "tr-TR-EmelNeural"
    else:
        voice_id = "tr-TR-AhmetNeural"
    
    st.markdown("---")
    if st.button("Yeni Sohbet", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_chat_id = str(uuid.uuid4())
        st.session_state.voice_text = None
        st.session_state.process_audio = False
        st.rerun()
        
    st.markdown("### Geçmiş")
    for chat in reversed(load_history()):
        title = chat.get("title", "Sohbet")
        if st.button(f"💬 {title[:15]}..", key=chat["id"], use_container_width=True):
            st.session_state.messages = chat["messages"]
            st.session_state.current_chat_id = chat["id"]
            st.session_state.voice_text = None
            st.rerun()
            
    st.markdown("---")
    if st.button("Temizle", type="primary", use_container_width=True):
        if os.path.exists(USER_HISTORY_FILE): os.remove(USER_HISTORY_FILE)
        st.session_state.messages = []
        st.rerun()

# --- 8. ANA EKRAN ---
st.markdown("<h1 style='text-align: center; color: white;'>BAUN-MYO AI Asistan</h1>", unsafe_allow_html=True)

# Mesajları Göster
for i, message in enumerate(st.session_state.messages):
    avatar = "👤" if message["role"] == "user" else "🤖"
    with st.chat_message(message["role"], avatar=avatar):
        if message.get("image_bytes"):
            try:
                st.image(message["image_bytes"], width=300)
            except: pass
        
        st.markdown(message["content"])

        # Ses varsa Streamlit Player ile oynat
        if message.get("audio_bytes"):
            st.audio(message["audio_bytes"], format="audio/mpeg")

# --- 9. SES GİRİŞİ ---
prompt = None

if ses_aktif:
    st.markdown("---")
    audio_val = st.audio_input("🎙️ Ses Kaydet")
    
    if audio_val:
         if "last_audio_id" not in st.session_state or st.session_state.last_audio_id != audio_val.name:
             st.session_state.process_audio = True
             st.session_state.last_audio_id = audio_val.name

    if st.session_state.process_audio and audio_val:
        with st.spinner("Ses işleniyor..."):
            audio_bytes = audio_val.read()
            res = sesten_yaziya(audio_bytes)
            if res:
                st.session_state.voice_text = res
                prompt = res
            else:
                st.error("Ses anlaşılamadı.")
        st.session_state.process_audio = False

text_input = st.chat_input("Mesaj...")
if text_input:
    prompt = text_input
    st.session_state.voice_text = None

# --- 10. CEVAP ÜRETME ---
if prompt:
    user_img_bytes = None
    if current_image:
        user_img_bytes = image_to_bytes(current_image)
    
    st.session_state.messages.append({
        "role": "user", 
        "content": prompt, 
        "image_bytes": user_img_bytes
    })
    
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)
        if user_img_bytes: st.image(user_img_bytes, width=300)

    try:
        with st.spinner('Yazıyor...'):
            history_formatted = []
            for m in st.session_state.messages[:-1]:
                history_formatted.append({
                    "role": "user" if m["role"] == "user" else "model",
                    "parts": [m["content"] if m["content"] else "..."]
                })
            
            chat = model.start_chat(history=history_formatted)
            
            if current_image:
                response = chat.send_message([prompt, current_image])
            else:
                response = chat.send_message(prompt)
            
            bot_text = response.text

        final_text = bot_text
        gen_img_bytes = None
        voice_data = None

        if bot_text.strip().startswith("[GORSEL_OLUSTUR]"):
            img_prompt = bot_text.replace("[GORSEL_OLUSTUR]", "").strip()
            with st.spinner('Görsel çiziliyor...'):
                img_obj, err = gorsel_olustur(img_prompt)
                if img_obj:
                    gen_img_bytes = image_to_bytes(img_obj)
                    final_text = ""
                    with st.chat_message("assistant", avatar="🤖"):
                        st.image(img_obj, caption="AI Görseli")
                else:
                    final_text = f"Hata: {err}"
                    with st.chat_message("assistant", avatar="🤖"):
                        st.error(final_text)
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(final_text)
                
                # --- YENİ SES OLUŞTURMA KISMI (EDGE TTS) ---
                if ses_aktif and final_text:
                    try:
                        # Seçilen ses tonuna göre oluştur (voice_id)
                        audio_bio = metni_sese_cevir_bytes(final_text, voice_id)
                        if audio_bio:
                            st.audio(audio_bio, format="audio/mpeg")
                            voice_data = audio_bio.getvalue() 
                    except Exception as e:
                        st.warning(f"Ses hatası: {e}")

        st.session_state.messages.append({
            "role": "assistant", 
            "content": final_text, 
            "image_bytes": gen_img_bytes,
            "audio_bytes": voice_data
        })
        
        hist = load_history()
        chat_id = st.session_state.current_chat_id
        
        simple_msgs = []
        for m in st.session_state.messages:
            simple_msgs.append({"role": m["role"], "content": m["content"]})
            
        found = False
        for c in hist:
            if c["id"] == chat_id:
                c["messages"] = simple_msgs
                found = True
                break
        if not found:
            hist.append({"id": chat_id, "title": prompt[:20], "messages": simple_msgs})
        save_history(hist)

    except Exception as e:
        st.error(f"Bir hata oluştu: {e}")