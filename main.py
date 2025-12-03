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

# !!! BURAYA KENDİ KEY'İNİ YAZ KRAL !!!
# --- 3. MODELİ BAŞLAT ---
# API Key'i kodun içine YAZMA! st.secrets'tan çekiyoruz.
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except FileNotFoundError:
    st.error("❌ Hacı, .streamlit/secrets.toml dosyası yok ya da key eksik!")
    st.stop()

genai.configure(api_key=api_key)

try:
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        system_instruction=okul_bilgileri
    )
except Exception as e:
    st.error(f"Bağlantı hatası: {e}")
    st.stop()
okul_bilgileri = bilgileri_yukle()

# --- 3. MODELİ BAŞLAT ---
if "BURAYA" in GOOGLE_API_KEY or not GOOGLE_API_KEY or GOOGLE_API_KEY == "xxxxx":
    st.error("❌ Hacı API Key girmeyi unuttun kodun içine! Kodun 35. satırına bi el at.")
    st.stop()

try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        system_instruction=okul_bilgileri
    )
except Exception as e:
    st.error(f"Bağlantı hatası: {e}")
    st.stop()

# --- 4. GEÇMİŞ YÖNETİMİ ---
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
    """Mikrofondan gelen sesi yazıya çevirir"""
    r = sr.Recognizer()
    
    # Geçici dosya oluşturup sesi oraya yazıyoruz
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_audio:
        tmp_audio.write(audio_bytes)
        tmp_audio_path = tmp_audio.name

    try:
        with sr.AudioFile(tmp_audio_path) as source:
            audio_data = r.record(source)
            # Google Speech API (Türkçe)
            text = r.recognize_google(audio_data, language="tr-TR")
            return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError:
        return "Hata: Google Ses Servisine ulaşılamadı."
    finally:
        if os.path.exists(tmp_audio_path):
            os.unlink(tmp_audio_path) # Temizlik imandan gelir

def yazidan_sese(text):
    """Metni ses dosyasına çevirir"""
    try:
        tts = gTTS(text=text, lang='tr')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
    except Exception as e:
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

    # --- SESLİ SOHBET MODU ---
    # Bu tuş kapalıysa mikrofon görünmez, açıksa görünür ve asistan konuşur.
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

# Geçmiş mesajları yazdır
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("image"):
            try:
                img = base64_to_image(message["image"])
                if img: st.image(img, width=300)
            except: pass

# --- 8. GİRİŞ YÖNTEMLERİ ---

audio_value = None # Başlangıçta boş

# Sadece mod açıksa mikrofonu göster
if ses_aktif:
    st.write("🎙️ **Sesli Soru Sor:**")
    audio_value = st.audio_input("Mikrofonu kullanmak için tıkla")

# Yazı girişi her zaman var
text_input = st.chat_input("Sorunuzu yazın...")

prompt = None
is_audio_prompt = False

# Giriş kontrolü
if ses_aktif and audio_value: # Ses modu açık ve ses kaydı varsa
    with st.spinner("Sesin yazıya dökülüyor kral..."):
        # !!! KRİTİK NOKTA: .read() KULLANIYORUZ !!!
        prompt = sesten_yaziya(audio_value.read())
        
        if prompt:
            is_audio_prompt = True
        else:
            st.warning("Dediklerini tam anlayamadım, tekrar dene be gülüm.")

elif text_input: # Ses yoksa yazıya bak
    prompt = text_input

# --- 9. CEVAP ÜRETME VE KAYIT ---
if prompt:
    # Resmi kaydet (varsa)
    saved_image_base64 = None
    saved_image_for_api = None
    if current_image:
        try:
            saved_image_base64 = image_to_base64(current_image)
            saved_image_for_api = current_image.copy()
        except Exception as e:
            st.error(f"Resim hatası: {e}")
    
    # Kullanıcı mesajını ekrana bas
    with st.chat_message("user"):
        st.markdown(prompt)
        if saved_image_for_api:
            st.image(saved_image_for_api, width=300)
    
    # Geçmişe ekle
    st.session_state.messages.append({
        "role": "user", 
        "content": prompt,
        "image": saved_image_base64
    })

    try:
        with st.spinner('Yapay Zeka düşünüyor...'):
            # Chat geçmişini hazırla
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
        
        # Asistan cevabı
        with st.chat_message("assistant"):
            st.markdown(bot_reply)
            
            # Eğer mod açıksa sesli oku
            if ses_aktif:
                audio_file = yazidan_sese(bot_reply)
                if audio_file:
                    st.audio(audio_file, format='audio/mp3', autoplay=True)

        # Asistan mesajını kaydet
        st.session_state.messages.append({
            "role": "assistant", 
            "content": bot_reply,
            "image": None
        })
        
        # JSON'a kaydet
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