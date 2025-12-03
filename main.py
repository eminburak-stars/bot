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
    page_title="BAUN-MYO-AI Asistan", 
    page_icon="indir.jpeg", 
    layout="centered",
    initial_sidebar_state="auto"
)

# --- TASARIM (CSS) ---
custom_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

.block-container {
    padding-top: 2rem !important;
    padding-bottom: 2rem !important;
}

[data-testid="stSidebarCollapsedControl"] {
    border: none !important;
    background-color: transparent !important;
    color: #31333F !important;
}
[data-testid="stSidebarCollapsedControl"]:hover {
    background-color: #f0f2f6 !important;
    border: none !important;
}

section[data-testid="stSidebar"] {
    background-color: #f0f2f6 !important;
}

.stButton button {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    background-color: transparent;
}
</style>
"""
st.markdown(custom_style, unsafe_allow_html=True)

# --- 2. OKUL BİLGİLERİ VE FİLTRE KURALLARI ---
okul_bilgileri = """
Sen Balıkesir Üniversitesi Meslek Yüksekokulu (BAUN MYO) asistanısın.
İsmin BAUN Asistan.

TEMEL PRENSİPLER:
1. Ciddi, sade ve net cevaplar ver.
2. ASLA emoji kullanma.
3. Samimi ol ama resmiyeti koru.

İNTERNET VE ARAMA KURALLARI (ÇOK KRİTİK):
1. HEDEF SİTE: Aramalarında ve cevaplarında SADECE "balikesirmyo.balikesir.edu.tr" adresini kaynak al. Başka hiçbir siteye bakma.

2. İZİNLİ KONULAR (SADECE BUNLARA CEVAP VER):
   Asistan olarak sadece aşağıdaki 3 ana başlık hakkında bilgi toplayabilir ve sunabilirsin. Bunların dışındaki konuları (Duyurular, Yemekhane, Etkinlikler vb.) görmezden gel.
   
   A) KADRO: 
      - Akademik ve idari personel bilgileri.
      
   B) HAKKIMIZDA:
      - Okulun genel tanıtımı, tarihçesi ve yönetim bilgileri.
      
   C) BÖLÜMLER (EN ÖNEMLİ KISIM):
      - Bölümleri listelerken mutlaka altındaki PROGRAMLARI da belirt.
      - Bir bölüm hakkında bilgi verirken mutlaka o bölümün MİSYON ve VİZYON bilgilerini bul ve söyle.
      - Programların içeriği ve amacı hakkında bilgi ver.

3. YASAKLI KONULAR:
   - "Duyurular", "Haberler", "Yemek Listesi", "Sınav Takvimi" gibi konulara BAKMA. Kullanıcı sorsa bile "Ben sadece Kadro, Hakkımızda ve Bölümler hakkında bilgi verebilirim, diğer konulara yetkim yok." de.

4. ARAMA TAKTİĞİ:
   - Google araması yaparken, aradığın konunun yanına mutlaka "site:balikesirmyo.balikesir.edu.tr" ekle.
   - Bölüm arıyorsan örneğin şöyle ara: "Bilgisayar Teknolojileri Bölümü misyon vizyon site:balikesirmyo.balikesir.edu.tr"

5. KAYNAK GÖSTER:
   - Cevabının sonuna mutlaka bilgiyi bulduğun sayfanın linkini ekle.
"""

# --- 3. MODELİ BAŞLAT ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("API Key bulunamadı.")
    st.stop()

try:
    genai.configure(api_key=api_key)
    
    # Google Arama yetkisi
    tools_list = [
        {"google_search": {}} 
    ]
    
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        tools=tools_list,
        system_instruction=okul_bilgileri
    )
except Exception as e:
    st.error(f"Bağlantı hatası: {e}")
    st.stop()

# --- 4. GEÇMİŞ YÖNETİMİ ---
HISTORY_FILE = "sohbet_gecmisi.json"

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
    r = sr.Recognizer()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_audio:
        tmp_audio.write(audio_bytes)
        tmp_audio_path = tmp_audio.name

    try:
        with sr.AudioFile(tmp_audio_path) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="tr-TR")
            return text
    except:
        return None
    finally:
        if os.path.exists(tmp_audio_path):
            os.unlink(tmp_audio_path)

def yazidan_sese(text):
    try:
        tts = gTTS(text=text, lang='tr')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
    except:
        return None

# --- SESSION ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []

# --- 6. YAN MENÜ ---
with st.sidebar:
    st.subheader("Menü")
    uploaded_file = st.file_uploader("Görsel Ekle", type=["jpg", "png", "jpeg"])
    current_image = None
    if uploaded_file:
        try:
            current_image = Image.open(uploaded_file)
            st.image(current_image, caption='Görsel Hazır', use_container_width=True)
        except:
            st.error("Görsel yüklenemedi")

    st.text("")
    ses_aktif = st.toggle("Sesli Yanıt", value=False)
    st.text("")

    if st.button("Yeni Sohbet", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    
    st.subheader("Geçmiş")
    for chat in reversed(load_history()):
        raw_title = chat.get("title", "Sohbet")
        btn_text = raw_title[:20] + "..." if len(raw_title) > 20 else raw_title
        if st.button(btn_text, key=chat["id"], use_container_width=True):
            st.session_state.session_id = chat["id"]
            st.session_state.messages = chat["messages"]
            st.rerun()
            
    if st.button("Geçmişi Temizle"):
        if os.path.exists(HISTORY_FILE): os.remove(HISTORY_FILE)
        st.session_state.messages = []
        st.rerun()

# --- 7. ANA EKRAN ---
st.header("BAUN-MYO-AI Asistan")
st.caption("MYO'nun Görsel, Sesli ve Metinsel Yapay Zekası")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("image"):
            try:
                img = base64_to_image(message["image"])
                if img: st.image(img, width=300)
            except: pass

# --- 8. GİRİŞ ---
audio_value = None
if ses_aktif:
    st.write("Mikrofon:")
    audio_value = st.audio_input("Konuş")

st.markdown(
    """
    <div style='text-align: center; color: gray; font-size: 12px; margin-bottom: 5px;'>
    💡 <b>İpucu:</b> "Bilgisayar bölümü misyonu nedir?", "Akademik kadroda kimler var?" diyebilirsin.
    </div>
    """, 
    unsafe_allow_html=True
)

text_input = st.chat_input("Mesajınızı yazın...")

prompt = None
if ses_aktif and audio_value:
    with st.spinner("Dinliyorum..."):
        prompt = sesten_yaziya(audio_value.read())
        if not prompt:
            st.warning("Anlaşılamadı.")
elif text_input:
    prompt = text_input

# --- 9. CEVAP ---
if prompt:
    saved_image_base64 = None
    saved_image_for_api = None
    if current_image:
        saved_image_base64 = image_to_base64(current_image)
        saved_image_for_api = current_image.copy()
    
    with st.chat_message("user"):
        st.markdown(prompt)
        if saved_image_for_api:
            st.image(saved_image_for_api, width=300)
    
    st.session_state.messages.append({
        "role": "user", 
        "content": prompt,
        "image": saved_image_base64
    })

    try:
        with st.spinner('...'):
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
        
        with st.chat_message("assistant"):
            st.markdown(bot_reply)
            if ses_aktif:
                audio_file = yazidan_sese(bot_reply)
                if audio_file:
                    st.audio(audio_file, format='audio/mp3', autoplay=True)

        st.session_state.messages.append({
            "role": "assistant", 
            "content": bot_reply,
            "image": None
        })
        
        current_history = load_history()
        chat_exists = False
        for chat in current_history:
            if chat["id"] == st.session_state.session_id:
                chat["messages"] = st.session_state.messages
                chat_exists = True
                break
        
        if not chat_exists:
            title = prompt[:20] + "..." if len(prompt) > 20 else prompt
            new_data = {
                "id": st.session_state.session_id, 
                "title": title, 
                "timestamp": str(datetime.now()), 
                "messages": st.session_state.messages
            }
            current_history.append(new_data)
        save_history(current_history)

    except Exception as e:
        st.error(f"Hata: {e}")