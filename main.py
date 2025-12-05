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
from pydub import AudioSegment 

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

/* Ses Oynatıcı Stilleri */
.audio-player {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 12px;
    padding: 15px;
    margin: 10px 0;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
}
.audio-player audio {
    width: 100%;
    border-radius: 8px;
    margin-bottom: 10px;
}
.play-button {
    background: white;
    color: #667eea;
    border: none;
    padding: 12px 24px;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s;
    font-size: 16px;
    width: 100%;
}
.play-button:hover {
    transform: scale(1.05);
    box-shadow: 0 6px 12px rgba(0,0,0,0.2);
}
.download-link {
    display: inline-block;
    padding: 10px 20px;
    background: rgba(255,255,255,0.2);
    color: white;
    text-decoration: none;
    border-radius: 8px;
    margin-top: 8px;
    font-weight: 600;
    transition: all 0.3s;
}
.download-link:hover {
    background: rgba(255,255,255,0.3);
}
</style>
"""
st.markdown(custom_style, unsafe_allow_html=True)

# --- 3. KLASÖR VE TEMİZLİK ---
SESSION_FOLDER = "sessions"
AUDIO_FOLDER = "audio_files"

for folder in [SESSION_FOLDER, AUDIO_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

def temizlik_yap(dakika=30):
    su_an = time.time()
    try:
        for dosya in os.listdir(AUDIO_FOLDER):
            if dosya.endswith(".mp3"):
                dosya_yolu = os.path.join(AUDIO_FOLDER, dosya)
                if (su_an - os.path.getmtime(dosya_yolu)) > (dakika * 60):
                    try: os.remove(dosya_yolu)
                    except: pass
        
        for dosya in os.listdir(SESSION_FOLDER):
            if dosya.endswith(".json"):
                dosya_yolu = os.path.join(SESSION_FOLDER, dosya)
                if (su_an - os.path.getmtime(dosya_yolu)) > (dakika * 60):
                    try: os.remove(dosya_yolu)
                    except: pass
    except: pass

temizlik_yap(dakika=30)

# --- 4. SESSION ID ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

USER_HISTORY_FILE = os.path.join(SESSION_FOLDER, f"history_{st.session_state.session_id}.json")

# --- 5. API VE BİLGİ BANKASI ---
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
    model = genai.GenerativeModel(model_name='gemini-2.0-flash', system_instruction=system_instruction)
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

# --- SES GİRİŞİ ---
def sesten_yaziya(audio_bytes):
    r = sr.Recognizer()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp_input:
        tmp_input.write(audio_bytes)
        tmp_input_path = tmp_input.name
    
    tmp_wav_path = tmp_input_path.replace(".webm", ".wav")

    try:
        audio = AudioSegment.from_file(tmp_input_path) 
        audio.export(tmp_wav_path, format="wav")
        
        with sr.AudioFile(tmp_wav_path) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="tr-TR")
            return text
            
    except Exception as e:
        print(f"Ses İşleme Hatası: {e}") 
        return None
        
    finally:
        if os.path.exists(tmp_input_path): os.unlink(tmp_input_path)
        if os.path.exists(tmp_wav_path): os.unlink(tmp_wav_path)

# --- SES ÇIKIŞI (ULTIMATE ÇÖZÜM) ---
def text_to_audio_base64(text):
    """Base64 formatında ses döndürür (iPhone uyumlu)"""
    try:
        tts = gTTS(text=text, lang='tr', slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return base64.b64encode(fp.read()).decode()
    except Exception as e:
        print(f"Ses oluşturma hatası: {e}")
        return None

def render_audio_player(audio_base64):
    """iPhone Safari uyumlu gelişmiş ses oynatıcı"""
    audio_id = f"audio_{uuid.uuid4().hex[:8]}"
    
    html = f"""
    <div class="audio-player">
        <audio id="{audio_id}" preload="auto">
            <source src="data:audio/mpeg;base64,{audio_base64}" type="audio/mpeg">
        </audio>
        
        <button class="play-button" onclick="playAudio_{audio_id}()">
            ▶️ Sesi Oynat
        </button>
        
        <a href="data:audio/mpeg;base64,{audio_base64}" 
           download="yanit.mp3" 
           class="download-link">
            📥 İndir (iPhone için)
        </a>
        
        <script>
        function playAudio_{audio_id}() {{
            var audio = document.getElementById('{audio_id}');
            if (audio.paused) {{
                audio.play().then(() => {{
                    console.log('Ses oynatılıyor');
                }}).catch(e => {{
                    console.error('Oynatma hatası:', e);
                    alert('Ses oynatılamadı. Lütfen indirme linkini kullanın.');
                }});
            }} else {{
                audio.pause();
            }}
        }}
        </script>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# GÖRSEL OLUŞTURMA
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
if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.title("BAUN MYO")
    st.markdown("---")
    st.subheader("İşlemler")
    
    uploaded_file = st.file_uploader("Görsel Yükle", type=["jpg", "png", "jpeg"])
    current_image = None
    if uploaded_file:
        try:
            current_image = Image.open(uploaded_file)
            st.success("Görsel yüklendi.")
            st.image(current_image, use_container_width=True)
        except: st.error("Hata")
            
    st.markdown("---")
    ses_aktif = st.toggle("🎤 Sesli Yanıt", value=False)
    
    if st.button("Yeni Sohbet", use_container_width=True):
        st.session_state.messages = []
        st.session_state.current_chat_id = str(uuid.uuid4())
        st.rerun()
        
    st.markdown("### Geçmiş")
    for chat in reversed(load_history()):
        raw_title = chat.get("title", "Sohbet")
        display_title = (raw_title[:20] + '..') if len(raw_title) > 20 else raw_title
        if st.button(f"💬 {display_title}", key=chat["id"], use_container_width=True):
            st.session_state.messages = chat["messages"]
            st.session_state.current_chat_id = chat["id"]
            st.rerun()
            
    st.markdown("---")
    if st.button("Temizle", type="primary", use_container_width=True):
        if os.path.exists(USER_HISTORY_FILE): os.remove(USER_HISTORY_FILE)
        st.session_state.messages = []
        st.rerun()

# --- 8. ANA EKRAN ---
st.markdown("<h1 style='text-align: center; color: white;'>BAUN-MYO AI Asistan</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Balıkesir Meslek Yüksekokulu AI Asistan.</p>", unsafe_allow_html=True)

# Mesajları Ekrana Bas
for message in st.session_state.messages:
    avatar_icon = "👤" if message["role"] == "user" else "🤖"
    with st.chat_message(message["role"], avatar=avatar_icon):
        if message.get("image"):
            try:
                img = base64_to_image(message["image"])
                if img: st.image(img, width=400, caption="Görsel")
            except: pass
        
        if message.get("content") and not message.get("image"):
             st.markdown(message["content"])

# --- 9. GİRİŞ ALANI ---
audio_value = None
if ses_aktif:
    st.write("🎙️ **Mikrofon:**")
    audio_value = st.audio_input("Konuş")

text_input = st.chat_input("Mesajınızı buraya yazın...")
prompt = None

if ses_aktif and audio_value:
    with st.spinner("Sesiniz işleniyor..."):
        prompt = sesten_yaziya(audio_value.read())
        if not prompt: st.warning("Ses anlaşılamadı.")
elif text_input:
    prompt = text_input

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
        with st.spinner('Asistan düşünüyor...'):
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
        final_content_text = bot_reply_text
        hata_mesaji = None

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
                
                # --- ULTIMATE SES ÇÖZÜMÜ (IPHONE UYUMLU) ---
                if ses_aktif and final_content_text.strip():
                    with st.spinner("🔊 Ses hazırlanıyor..."):
                        audio_base64 = text_to_audio_base64(final_content_text)
                    
                    if audio_base64:
                        # Özel oynatıcı render et
                        render_audio_player(audio_base64)
                        
                        # Ek bilgi
                        st.info("💡 **iPhone kullanıcıları:** 'Sesi Oynat' butonu çalışmazsa '📥 İndir' linkine tıklayın")
                    else:
                        st.error("⚠️ Ses oluşturulamadı")

        st.session_state.messages.append({
            "role": "assistant", "content": final_content_text, "image": generated_image_base64
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

    except Exception as e:
        st.error(f"Bir hata oluştu: {e}")