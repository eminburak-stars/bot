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

# --- 1. SAYFA AYARLARI ---
st.set_page_config(
    page_title="BAUN-MYO Asistan", 
    page_icon="🎓",  
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- 2. CSS STİL ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
html, body, [class*="css"] {font-family: 'Inter', sans-serif;}
.stApp {background-color: #0e1117;}
[data-testid="stSidebar"] {background-color: #161b22 !important;}
[data-testid="stChatMessage"]:nth-of-type(odd) {background-color: #21262d; border-radius: 20px; padding: 15px;}
[data-testid="stChatMessage"]:nth-of-type(even) {background-color: #1f6feb; color: white; border-radius: 20px; padding: 15px;}
</style>
""", unsafe_allow_html=True)

# --- 3. API AYARLARI ---
try:
    # API KEY'i st.secrets'tan alıyoruz
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    
    # Bilgi bankasını oku
    try:
        with open("bilgi.txt", "r", encoding="utf-8") as f:
            okul_bilgisi = f.read()
    except:
        okul_bilgisi = "Sen Balıkesir MYO asistanısın."

    system_instruction = f"""
    {okul_bilgisi}
    EKSTRA: Eğer görsel istenirse cevabın başına [GORSEL_OLUSTUR] yaz ve İngilizce prompt ekle.
    """
    
    model = genai.GenerativeModel(model_name='gemini-2.0-flash', system_instruction=system_instruction)
    imagen_model = genai.GenerativeModel("imagen-3.0-generate-001")

except Exception as e:
    st.error(f"❌ API Başlatma Hatası: {e}")
    st.stop()

# --- 4. SESSION YÖNETİMİ ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# --- 5. FONKSİYONLAR ---
def image_to_base64(image):
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def base64_to_image(base64_str):
    if base64_str: return Image.open(io.BytesIO(base64.b64decode(base64_str)))
    return None

def gorsel_olustur(prompt):
    try:
        result = imagen_model.generate_images(prompt=prompt, number_of_images=1, aspect_ratio="1:1")
        if result.images:
            img_data = result.images[0].image_bytes
            return Image.open(io.BytesIO(img_data)), None
    except Exception as e:
        return None, str(e)
    return None, "Bilinmeyen hata"

# --- 6. ARAYÜZ ---
with st.sidebar:
    st.title("BAUN MYO")
    uploaded_file = st.file_uploader("Resim Yükle", type=["jpg", "png"])
    if st.button("Sohbeti Temizle", type="primary"):
        st.session_state.messages = []
        st.rerun()

st.markdown("<h3 style='text-align: center;'>BAUN-MYO AI Asistan 🤖</h3>", unsafe_allow_html=True)

# Geçmiş mesajları yazdır
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("image"):
            st.image(base64_to_image(msg["image"]), width=300)
        if msg.get("content"):
            st.write(msg["content"])

# --- 7. GİRİŞ ALANI (SES + METİN) ---
prompt = None
audio_bytes = None

# Ses Girişi (Streamlit Native)
audio_input = st.audio_input("🎙️ Sesli sor (iPhone Uyumlu)")

if audio_input:
    audio_bytes = audio_input.read()
    # Sesi direkt işleyelim (Buttonsuz)
    # Ses geldiği an prompt olarak kabul ediyoruz ama text'e çevirmeden modele atacağız.
    # Ancak önce kullanıcı arayüzünde ne görünecek?
    prompt = "🎤 [Sesli Mesaj]" 

# Metin Girişi
text_input = st.chat_input("Mesaj yaz...")
if text_input:
    prompt = text_input
    audio_bytes = None # Metin yazıldıysa sesi yoksay

# --- 8. İŞLEME ---
if prompt:
    # 1. Kullanıcı mesajını ekrana bas
    with st.chat_message("user"):
        st.write(prompt)
        if uploaded_file:
            st.image(uploaded_file, width=200)
    
    # Mesajı geçmişe ekle
    user_msg_obj = {"role": "user", "content": prompt}
    if uploaded_file:
        img_temp = Image.open(uploaded_file)
        user_msg_obj["image"] = image_to_base64(img_temp)
    st.session_state.messages.append(user_msg_obj)

    # 2. Cevap Üretme
    with st.chat_message("assistant"):
        with st.spinner("Düşünüyorum..."):
            try:
                # Geçmişi hazırla
                history_for_gemini = []
                for m in st.session_state.messages[:-1]: # Son mesajı hariç tut, onu aşağıda özel ekleyeceğiz
                    role = "user" if m["role"] == "user" else "model"
                    parts = [m["content"]]
                    # Geçmişteki resimleri history'e eklemek karmaşık olabilir, şimdilik text gidiyor
                    history_for_gemini.append({"role": role, "parts": parts})
                
                chat = model.start_chat(history=history_for_gemini)
                
                # İÇERİK LİSTESİ OLUŞTUR
                content_to_send = []
                
                # A) Metin varsa ekle
                if text_input:
                    content_to_send.append(text_input)
                
                # B) Ses varsa ekle (DİKKAT: En kritik yer burası)
                if audio_bytes:
                    content_to_send.append("Bu ses kaydına cevap ver:")
                    # Streamlit audio_input genelde 'audio/wav' döner.
                    content_to_send.append({"mime_type": "audio/wav", "data": audio_bytes})
                
                # C) Resim varsa ekle
                if uploaded_file:
                    img_pil = Image.open(uploaded_file)
                    content_to_send.append(img_pil)

                # Modele Gönder
                response = chat.send_message(content_to_send)
                bot_text = response.text

                # Görsel oluşturma kontrolü
                if "[GORSEL_OLUSTUR]" in bot_text:
                    prompt_img = bot_text.replace("[GORSEL_OLUSTUR]", "").strip()
                    generated_img, err = gorsel_olustur(prompt_img)
                    if generated_img:
                        st.image(generated_img, caption="Oluşturulan Görsel")
                        st.session_state.messages.append({"role": "assistant", "content": "Görsel oluşturdum.", "image": image_to_base64(generated_img)})
                    else:
                        st.error(f"Görsel hatası: {err}")
                else:
                    st.write(bot_text)
                    st.session_state.messages.append({"role": "assistant", "content": bot_text})

            except Exception as e:
                st.error(f"❌ HATA DETAYI: {e}")
                st.info("Eğer '400 Bad Request' alıyorsan, ses formatı desteklenmiyor olabilir.")