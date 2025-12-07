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

def temizlik_yap(dakika=30):
    su_an = time.time()
    try:
        for dosya in os.listdir(SESSION_FOLDER):
            if dosya.endswith(".json"):
                dosya_yolu = os.path.join(SESSION_FOLDER, dosya)
                if (su_an - os.path.getmtime(dosya_yolu)) > (dakika * 60):
                    try: os.remove(dosya_yolu)
                    except: pass
    except: pass

temizlik_yap(dakika=30)

# --- 4. SESSION STATE ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "voice_text" not in st.session_state:
    st.session_state.voice_text = None

if "process_audio" not in st.session_state:
    st.session_state.process_audio = False

# --- YENİ EKLENEN KISIM: UPLOADER RESET İÇİN ANAHTAR ---
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = str(uuid.uuid4())

USER_HISTORY_FILE = os.path.join(SESSION_FOLDER, f"history_{st.session_state.session_id}.json")

# --- 5. API ---
def bilgi_bankasini_oku():
    dosya_yolu = "bilgi.txt"
    varsayilan = "Sen bir yapay zeka asistanısın."
    if os.path.exists(dosya_yolu):
        try:
            with open(dosya_yolu, "r", encoding="utf-8") as f:
                return f.read()
        except: return varsayilan
    return varsayilan

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
    model = genai.GenerativeModel(model_name='gemini-1.5-flash', system_instruction=system_instruction)
    imagen_model = genai.GenerativeModel("imagen-3.0-generate-001")
except Exception as e:
    st.error(f"API Hatası: {e}")
    st.stop()

# --- 6. YARDIMCI FONKSİYONLAR ---
def load_history():
    if not os.path.exists(USER_HISTORY_FILE):
        return []
    try:
        with open(USER_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

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

def bytes_to_base64_str(data_bytes):
    return base64.b64encode(data_bytes).decode('utf-8')

def base64_str_to_bytes(data_str):
    return base64.b64decode(data_str.encode('utf-8'))

# --- SES İŞLEME ---
def sesten_yaziya(audio_bytes):
    try:
        transcription_model = genai.GenerativeModel("gemini-1.5-flash")
        response = transcription_model.generate_content([
            "Bu ses kaydını dinle ve Türkçe olarak yazıya dök. Sadece söylenen metni ver, yorum yapma.",
            {"mime_type": "audio/wav", "data": audio_bytes} 
        ])
        if response and response.text:
            return response.text.strip()
        else:
            return None
    except Exception as e:
        print(f"Ses transcribe hatası: {e}") 
        return None

def metni_sese_cevir_bytes(text):
    try:
        tts = gTTS(text=text, lang='tr', slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
    except: return None

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
    st.subheader("İşlemler")
    
    # --- DÜZELTME: key parametresi eklendi ---
    uploaded_file = st.file_uploader("Görsel Yükle", type=["jpg", "png", "jpeg"], key=st.session_state.uploader_key)
    current_image = None
    if uploaded_file:
        try:
            current_image = Image.open(uploaded_file)
            st.success("✅ Görsel yüklendi.")
            st.image(current_image, use_container_width=True)
        except: 
            st.error("❌ Görsel yüklenemedi")
            
    st.markdown("---")
    ses_aktif = st.toggle("🎤 Sesli Yanıt", value=False)
    
    if st.button("Yeni Sohbet", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_chat_id = str(uuid.uuid4())
        st.session_state.voice_text = None
        st.session_state.process_audio = False
        st.session_state.uploader_key = str(uuid.uuid4())
        st.rerun()
        
    st.markdown("### Geçmiş")
    for chat in reversed(load_history()):
        raw_title = chat.get("title", "Sohbet")
        display_title = (raw_title[:20] + '..') if len(raw_title) > 20 else raw_title
        if st.button(f"💬 {display_title}", key=chat["id"], use_container_width=True):
            st.session_state.messages = chat["messages"]
            st.session_state.current_chat_id = chat["id"]
            st.session_state.voice_text = None
            st.session_state.process_audio = False
            st.session_state.uploader_key = str(uuid.uuid4())
            st.rerun()
            
    st.markdown("---")
    if st.button("Temizle", type="primary", use_container_width=True):
        if os.path.exists(USER_HISTORY_FILE): os.remove(USER_HISTORY_FILE)
        st.session_state.messages = []
        st.session_state.voice_text = None
        st.session_state.process_audio = False
        st.session_state.uploader_key = str(uuid.uuid4())
        st.rerun()

# --- 8. ANA EKRAN ---
st.markdown("<h1 style='text-align: center; color: white;'>BAUN-MYO AI Asistan</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Balıkesir Meslek Yüksekokulu AI Asistan.</p>", unsafe_allow_html=True)

# Mesajları Göster
for message in st.session_state.messages:
    avatar_icon = "👤" if message["role"] == "user" else "🤖"
    with st.chat_message(message["role"], avatar=avatar_icon):
        if message.get("image"):
            try:
                img = base64_to_image(message["image"])
                if img: st.image(img, width=400, caption="Görsel")
            except: pass
        
        if message.get("content"):
             st.markdown(message["content"])

        if message.get("audio"):
            try:
                audio_bytes = base64_str_to_bytes(message["audio"])
                st.audio(audio_bytes, format='audio/mpeg')
            except: pass

# --- 9. SES GİRİŞİ ---
prompt = None

if ses_aktif:
    st.markdown("---")
    audio_value = st.audio_input("🎙️ Ses Kaydet", key="audio_recorder")
    
    if not audio_value:
        st.session_state.last_audio_id = None
        st.session_state.voice_text = None
    
    else:
        current_audio_id = f"{audio_value.name}_{audio_value.size}"
        
        if "last_audio_id" not in st.session_state or st.session_state.last_audio_id != current_audio_id:
            st.session_state.process_audio = True
            st.session_state.last_audio_id = current_audio_id
            st.session_state.voice_text = None 

    if st.session_state.get("process_audio", False) and audio_value:
        with st.spinner("🔄 Ses işleniyor..."):
            try:
                audio_value.seek(0)
                audio_bytes = audio_value.read()
                
                if audio_bytes:
                    result = sesten_yaziya(audio_bytes)
                    if result:
                        st.session_state.voice_text = result
                        prompt = result
                        st.session_state.process_audio = False
                        st.rerun()
                    else:
                        st.error("⚠️ Ses anlaşılamadı.")
                        st.session_state.process_audio = False
            except Exception as e:
                st.error(f"Hata: {e}")
                st.session_state.process_audio = False

if st.session_state.voice_text:
    prompt = st.session_state.voice_text

# Metin girişi
text_input = st.chat_input("Mesajınızı buraya yazın...")
if text_input:
    prompt = text_input
    st.session_state.voice_text = None

# --- 10. CEVAP ÜRETME ---
if prompt:
    saved_image_base64 = None
    saved_image_for_api = None
    if current_image:
        saved_image_base64 = image_to_base64(current_image)
        saved_image_for_api = current_image.copy()
    
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)
        if saved_image_for_api: st.image(saved_image_for_api, width=300)
    
    st.session_state.messages.append({
        "role": "user", "content": prompt, "image": saved_image_base64
    })

    try:
        with st.spinner('🤔 Asistan düşünüyor...'):
            chat_history_text = []
            for m in st.session_state.messages[:-1]:
                msg_content = m.get("content", "")
                if msg_content is None: msg_content = "..."
                chat_history_text.append({
                    "role": "user" if m["role"] == "user" else "model",
                    "parts": [msg_content]
                })
            
            chat_session = model.start_chat(history=chat_history_text)
            
            if saved_image_for_api:
                response = chat_session.send_message([prompt, saved_image_for_api])
            else:
                response = chat_session.send_message(prompt)
            
            bot_reply_text = response.text

        generated_image_base64 = None
        audio_base64 = None 
        final_content_text = bot_reply_text

        if bot_reply_text.strip().startswith("[GORSEL_OLUSTUR]"):
            imagen_prompt = bot_reply_text.replace("[GORSEL_OLUSTUR]", "").strip()
            
            with st.spinner('🎨 Görsel oluşturuluyor...'):
                generated_img, hata_mesaji = gorsel_olustur(imagen_prompt)
                
                if generated_img:
                    generated_image_base64 = image_to_base64(generated_img)
                    final_content_text = ""
                    with st.chat_message("assistant", avatar="🤖"):
                        st.image(generated_img, width=400, caption="Oluşturulan Görsel")
                else:
                    final_content_text = f"⚠️ Görsel oluşturulamadı: {hata_mesaji}"
                    with st.chat_message("assistant", avatar="🤖"):
                        st.error(final_content_text)
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(final_content_text)
                
                if ses_aktif and final_content_text:
                    sound_fp = metni_sese_cevir_bytes(final_content_text)
                    if sound_fp:
                        audio_bytes = sound_fp.read()
                        audio_base64 = bytes_to_base64_str(audio_bytes) 
                        st.download_button(
                            label="🔊 Yanıtı Sesli Dinle",
                            data=audio_bytes,
                            file_name="yanit.mp3",
                            mime="audio/mpeg",
                            use_container_width=True
                        )
                        st.audio(audio_bytes, format='audio/mpeg')

        st.session_state.messages.append({
            "role": "assistant", 
            "content": final_content_text, 
            "image": generated_image_base64,
            "audio": audio_base64
        })
        
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
            current_history.append({
                "id": cid, "title": title, "timestamp": str(datetime.now()), "messages": st.session_state.messages
            })
        
        save_history(current_history)

        # --- DÜZELTME BURADA: EĞER RESİM GÖNDERİLDİYSE RESETLE ---
        if saved_image_for_api:
            st.session_state.uploader_key = str(uuid.uuid4())
            st.rerun()

    except Exception as e:
        st.error(f"❌ Bir hata oluştu: {e}")