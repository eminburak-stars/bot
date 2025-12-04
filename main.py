import streamlit as st
import google.generativeai as genai
import sqlite3
import bcrypt
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

# --- CSS ---
custom_style = """
<style>
footer {visibility: hidden;}
header {background-color: transparent !important;}
.block-container {padding-top: 3rem !important; padding-bottom: 2rem !important;}
section[data-testid="stSidebar"] {background-color: #19191a !important;}
[data-testid="stSidebarCollapsedControl"] {color: #19191a !important;}
.stButton button {border: 1px solid #e0e0e0; border-radius: 8px; background-color: transparent;}
</style>
"""
st.markdown(custom_style, unsafe_allow_html=True)

# --- 2. VERİTABANI FONKSİYONLARI ---
DB_FILE = "sohbetler.db"

def init_db():
    """Veritabanını başlat"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kullanici_adi TEXT UNIQUE NOT NULL,
            sifre_hash TEXT NOT NULL,
            olusturma_tarihi DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sohbetler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            baslik TEXT,
            olusturma_tarihi DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mesajlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sohbet_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            image_base64 TEXT,
            tarih DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sohbet_id) REFERENCES sohbetler(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def kayit_ol(kullanici_adi, sifre):
    """Yeni kullanıcı kaydı"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        sifre_hash = bcrypt.hashpw(sifre.encode('utf-8'), bcrypt.gensalt())
        cursor.execute(
            "INSERT INTO users (kullanici_adi, sifre_hash) VALUES (?, ?)",
            (kullanici_adi, sifre_hash)
        )
        
        conn.commit()
        conn.close()
        return True, "Kayıt başarılı!"
    except sqlite3.IntegrityError:
        return False, "Bu kullanıcı adı zaten var."
    except Exception as e:
        return False, f"Hata: {e}"

def giris_yap(kullanici_adi, sifre):
    """Kullanıcı girişi"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, sifre_hash FROM users WHERE kullanici_adi = ?",
            (kullanici_adi,)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            user_id, db_hash = result
            if bcrypt.checkpw(sifre.encode('utf-8'), db_hash):
                return True, user_id, "Giriş başarılı!"
            else:
                return False, None, "Şifre yanlış."
        else:
            return False, None, "Kullanıcı bulunamadı."
    except Exception as e:
        return False, None, f"Hata: {e}"

def sohbet_kaydet(user_id, session_id, baslik, mesajlar):
    """Sohbeti veritabanına kaydet"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Sohbet var mı kontrol et
        cursor.execute(
            "SELECT id FROM sohbetler WHERE session_id = ?",
            (session_id,)
        )
        result = cursor.fetchone()
        
        if result:
            sohbet_id = result[0]
            # Mevcut mesajları sil (güncellemek için)
            cursor.execute("DELETE FROM mesajlar WHERE sohbet_id = ?", (sohbet_id,))
        else:
            # Yeni sohbet oluştur
            cursor.execute(
                "INSERT INTO sohbetler (user_id, session_id, baslik) VALUES (?, ?, ?)",
                (user_id, session_id, baslik)
            )
            sohbet_id = cursor.lastrowid
        
        # Mesajları ekle
        for msg in mesajlar:
            cursor.execute(
                "INSERT INTO mesajlar (sohbet_id, role, content, image_base64) VALUES (?, ?, ?, ?)",
                (sohbet_id, msg["role"], msg["content"], msg.get("image"))
            )
        
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Kayıt hatası: {e}")

def sohbetleri_yukle(user_id):
    """Kullanıcının sohbetlerini yükle"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, session_id, baslik, olusturma_tarihi FROM sohbetler WHERE user_id = ? ORDER BY olusturma_tarihi DESC",
            (user_id,)
        )
        sohbetler = cursor.fetchall()
        conn.close()
        
        return sohbetler
    except:
        return []

def mesajlari_yukle(session_id):
    """Belirli bir sohbetin mesajlarını yükle"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id FROM sohbetler WHERE session_id = ?",
            (session_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            return []
        
        sohbet_id = result[0]
        cursor.execute(
            "SELECT role, content, image_base64 FROM mesajlar WHERE sohbet_id = ? ORDER BY tarih",
            (sohbet_id,)
        )
        mesajlar = cursor.fetchall()
        conn.close()
        
        return [{"role": m[0], "content": m[1], "image": m[2]} for m in mesajlar]
    except:
        return []

# --- 3. YARDIMCI FONKSİYONLAR ---
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

# --- 4. VERİTABANINI BAŞLAT ---
init_db()

# --- 5. SESSION STATE ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.kullanici_adi = None

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []

# --- 6. LOGİN/KAYDOL EKRANI ---
if not st.session_state.logged_in:
    st.title("🎓 BAUN-MYO-AI Asistan")
    st.caption("Giriş yapın ya da kayıt olun")
    
    tab1, tab2 = st.tabs(["Giriş Yap", "Kaydol"])
    
    with tab1:
        st.subheader("Giriş Yap")
        giris_kullanici = st.text_input("Kullanıcı Adı", key="giris_kullanici")
        giris_sifre = st.text_input("Şifre", type="password", key="giris_sifre")
        
        if st.button("Giriş Yap", use_container_width=True):
            if giris_kullanici and giris_sifre:
                basarili, user_id, mesaj = giris_yap(giris_kullanici, giris_sifre)
                if basarili:
                    st.session_state.logged_in = True
                    st.session_state.user_id = user_id
                    st.session_state.kullanici_adi = giris_kullanici
                    st.success(mesaj)
                    st.rerun()
                else:
                    st.error(mesaj)
            else:
                st.warning("Tüm alanları doldurun.")
    
    with tab2:
        st.subheader("Kaydol")
        kayit_kullanici = st.text_input("Kullanıcı Adı", key="kayit_kullanici")
        kayit_sifre = st.text_input("Şifre", type="password", key="kayit_sifre")
        kayit_sifre2 = st.text_input("Şifre Tekrar", type="password", key="kayit_sifre2")
        
        if st.button("Kaydol", use_container_width=True):
            if kayit_kullanici and kayit_sifre and kayit_sifre2:
                if kayit_sifre != kayit_sifre2:
                    st.error("Şifreler eşleşmiyor.")
                elif len(kayit_sifre) < 4:
                    st.error("Şifre en az 4 karakter olmalı.")
                else:
                    basarili, mesaj = kayit_ol(kayit_kullanici, kayit_sifre)
                    if basarili:
                        st.success(mesaj + " Şimdi giriş yapabilirsiniz.")
                    else:
                        st.error(mesaj)
            else:
                st.warning("Tüm alanları doldurun.")
    
    st.stop()

# --- 7. API AYARLARI ---
okul_bilgileri = """
Sen Balıkesir Üniversitesi Meslek Yüksekokulu (BAUN MYO) asistanısın.
İsmin BAUN Asistan.
Çok ciddi, sade ve net cevaplar ver.
Cevaplarında ASLA emoji kullanma.
Samimi ol ama cıvık olma. Sadece metin odaklı konuş.
Tasarımcı gibi düşün, minimalist cevaplar ver.
"""

try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        system_instruction=okul_bilgileri
    )
except Exception as e:
    st.error(f"API Hatası: {e}")
    st.stop()

# --- 8. YAN MENÜ ---
with st.sidebar:
    st.subheader(f"👤 {st.session_state.kullanici_adi}")
    
    if st.button("🚪 Çıkış Yap", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.kullanici_adi = None
        st.session_state.messages = []
        st.rerun()
    
    st.divider()
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
    sohbetler = sohbetleri_yukle(st.session_state.user_id)
    
    for sohbet in sohbetler:
        sohbet_id, session_id, baslik, tarih = sohbet
        btn_text = baslik[:20] + "..." if len(baslik) > 20 else baslik
        
        if st.button(btn_text, key=session_id, use_container_width=True):
            st.session_state.session_id = session_id
            st.session_state.messages = mesajlari_yukle(session_id)
            st.rerun()

# --- 9. ANA EKRAN ---
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

# --- 10. GİRİŞ ---
audio_value = None
if ses_aktif:
    st.write("Mikrofon:")
    audio_value = st.audio_input("Konuş")

text_input = st.chat_input("Mesajınızı yazın...")
prompt = None

if ses_aktif and audio_value:
    with st.spinner("Dinliyorum..."):
        prompt = sesten_yaziya(audio_value.read())
        if not prompt:
            st.warning("Anlaşılamadı.")
elif text_input:
    prompt = text_input

# --- 11. CEVAP ---
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
        
        # Sohbeti kaydet
        baslik = prompt[:20] + "..." if len(prompt) > 20 else prompt
        sohbet_kaydet(
            st.session_state.user_id,
            st.session_state.session_id,
            baslik,
            st.session_state.messages
        )
    
    except Exception as e:
        st.error(f"Hata: {e}")