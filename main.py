import streamlit as st
import google.generativeai as genai
import json
import os
import uuid
import time
from PIL import Image
import io
import asyncio
import base64
import edge_tts

# --- 1. AYARLAR ---
st.set_page_config(
    page_title="BAUN-MYO Asistan", 
    page_icon="🎓",  
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- 2. CSS (Tasarım) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
html, body, [class*="css"] {font-family: 'Inter', sans-serif;}
.stChatInputContainer textarea {border-radius: 12px;}
/* Ses oynatıcı stili */
audio { width: 100%; margin-top: 5px; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 3. DOSYA VE GEÇMİŞ YÖNETİMİ ---
SESSION_FOLDER = "sessions"
if not os.path.exists(SESSION_FOLDER): os.makedirs(SESSION_FOLDER)
USER_HISTORY_FILE = os.path.join(SESSION_FOLDER, f"history_{st.session_state.get('session_id', 'default')}.json")

if "session_id" not in st.session_state: st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state: st.session_state.messages = []
if "process_audio" not in st.session_state: st.session_state.process_audio = False

# --- 4. API BAĞLANTISI ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    system_instruction = """
    Sen Balıkesir MYO öğrencileri için yardımcı bir asistansın. Samimi, "kral, hacı" gibi hitapları dozunda kullanabilirsin.
    Görsel istenirse cevabın başına [GORSEL_OLUSTUR] yazıp İngilizce prompt ekle.
    """
    model = genai.GenerativeModel(model_name='gemini-2.0-flash', system_instruction=system_instruction)
    imagen_model = genai.GenerativeModel("imagen-3.0-generate-001")
except Exception as e:
    st.error(f"API Hatası: {e}")
    st.stop()

# --- 5. ÖZEL FONKSİYONLAR (APPLE DOSTU) ---

def html_audio_autoplay(audio_data, autoplay=False):
    """
    Sesi (Bytes veya Base64 String) alır, HTML Audio player olarak sayfaya gömer.
    Safari/iOS uyumludur.
    """
    if not audio_data: return ""
    
    # Veri zaten base64 string mi yoksa bytes mı?
    if isinstance(audio_data, bytes):
        b64_str = base64.b64encode(audio_data).decode()
    else:
        b64_str = audio_data # Zaten string gelmiştir

    autoplay_attr = "autoplay" if autoplay else ""
    return f"""
    <audio controls {autoplay_attr} preload="auto">
        <source src="data:audio/mp3;base64,{b64_str}" type="audio/mp3">
        Tarayıcınız sesi desteklemiyor.
    </audio>
    """

async def edge_tts_generate(text, voice):
    """Edge TTS ile yüksek kaliteli ses üretir"""
    communicate = edge_tts.Communicate(text, voice)
    mp3_fp = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_fp.write(chunk["data"])
    mp3_fp.seek(0)
    return mp3_fp.getvalue()

def metni_sese_cevir_bytes(text, voice_id):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_bytes = loop.run_until_complete(edge_tts_generate(text, voice_id))
        loop.close()
        return audio_bytes
    except: return None

def sesten_yaziya(audio_bytes):
    try:
        m = genai.GenerativeModel("gemini-2.0-flash")
        res = m.generate_content(["Yazıya dök:", {"mime_type": "audio/webm", "data": audio_bytes}])
        return res.text.strip()
    except: return None

def gorsel_olustur(prompt):
    try:
        res = imagen_model.generate_images(prompt=prompt, number_of_images=1)
        if res and res.images:
            return Image.open(io.BytesIO(res.images[0].image_bytes)), None
        return None, "Görsel oluşturulamadı."
    except Exception as e: return None, str(e)

# Görüntü İşleme Yardımcıları
def image_to_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def base64_to_image(b64_str):
    return Image.open(io.BytesIO(base64.b64decode(b64_str)))

# --- 6. GEÇMİŞ YÖNETİMİ (JSON) ---
def save_chat():
    # JSON'a kaydederken binary verileri (bytes) kaydemeyiz, o yüzden her şey string olmalı
    # Bu kod çalışırken session_state'de bytes tutuyoruz, ama dosyaya yazarken dikkatli olmalıyız.
    # Şimdilik basitlik adına sadece session_state'i dosyaya dökmüyoruz, 
    # oturum bazlı çalışıyoruz. Eğer dosya kaydı çok şartsa bytes->base64 dönüşümü yapılmalı.
    pass 

# --- 7. SIDEBAR ---
with st.sidebar:
    st.title("Ayarlar")
    
    # Görsel Yükleme
    uploaded_file = st.file_uploader("Resim Yükle", type=["jpg", "png", "jpeg"])
    current_image = None
    if uploaded_file:
        current_image = Image.open(uploaded_file)
        st.image(current_image, caption="Yüklendi")

    st.markdown("---")
    ses_aktif = st.toggle("🎤 Sesli Yanıt", value=True)
    voice_choice = st.radio("Ses Tonu", ["Erkek (Ahmet)", "Kadın (Emel)"], index=0)
    voice_id = "tr-TR-AhmetNeural" if "Ahmet" in voice_choice else "tr-TR-EmelNeural"
    
    if st.button("Sohbeti Temizle", type="primary"):
        st.session_state.messages = []
        st.rerun()

# --- 8. ANA EKRAN ---
st.title("BAUN AI Asistan")

# Mesajları Döngüyle Göster
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        # 1. Metin
        if msg.get("content"): 
            st.markdown(msg["content"])
        
        # 2. Resim (Kullanıcı yüklediyse veya AI çizdiyse)
        if msg.get("image_data"):
            # Veri base64 string ise resme çevir
            try: st.image(base64_to_image(msg["image_data"]), width=300)
            except: pass

        # 3. SES (APPLE FIX)
        if msg.get("audio_data"):
            # HTML kodu oluştur ve bas
            html_code = html_audio_autoplay(msg["audio_data"], autoplay=False)
            st.markdown(html_code, unsafe_allow_html=True)

# --- 9. INPUT ALANI ---
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
    prompt = st.chat_input("Mesaj yaz...")

# --- 10. CEVAP MANTIĞI ---
if prompt:
    # Kullanıcı Mesajını Ekle
    user_img_b64 = None
    if current_image:
        user_img_b64 = image_to_base64(current_image)

    st.session_state.messages.append({
        "role": "user", 
        "content": prompt, 
        "image_data": user_img_b64
    })
    
    with st.chat_message("user"):
        st.write(prompt)
        if current_image: st.image(current_image, width=300)

    # Asistan Cevabı
    with st.chat_message("assistant"):
        with st.spinner("Düşünüyorum..."):
            # Geçmişi Gemini formatına çevir
            gemini_hist = []
            for m in st.session_state.messages:
                # Sadece metin içeriğini geçmişe veriyoruz, resimler karmaşa yaratmasın
                if m.get("content"):
                    gemini_hist.append({"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]})

            chat = model.start_chat(history=gemini_hist[:-1])
            
            # Eğer resim varsa resimli sor
            if current_image:
                response = chat.send_message([prompt, current_image])
            else:
                response = chat.send_message(prompt)
            
            bot_text = response.text
            final_img_b64 = None
            final_audio_b64 = None

            # [GORSEL_OLUSTUR] Kontrolü
            if "[GORSEL_OLUSTUR]" in bot_text:
                img_prompt = bot_text.replace("[GORSEL_OLUSTUR]", "").strip()
                img_obj, err = gorsel_olustur(img_prompt)
                if img_obj:
                    st.image(img_obj)
                    final_img_b64 = image_to_base64(img_obj)
                    bot_text = "İstediğin görseli oluşturdum kral."
                else:
                    st.error(err)
            else:
                st.markdown(bot_text)
                
                # SES OLUŞTURMA (Eğer ses açıksa)
                if ses_aktif:
                    audio_bytes = metni_sese_cevir_bytes(bot_text, voice_id)
                    if audio_bytes:
                        # Base64'e çevirip saklayalım (JSON uyumluluğu için)
                        final_audio_b64 = base64.b64encode(audio_bytes).decode()
                        
                        # HEMEN OYNAT (Autoplay True)
                        html_code = html_audio_autoplay(final_audio_b64, autoplay=True)
                        st.markdown(html_code, unsafe_allow_html=True)

            # Cevabı Kaydet
            st.session_state.messages.append({
                "role": "assistant",
                "content": bot_text,
                "image_data": final_img_b64,
                "audio_data": final_audio_b64 # String olarak saklıyoruz
            })