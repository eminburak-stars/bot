import sqlite3
import bcrypt

# Veritabanı bağlantısı (yoksa oluşturur)
conn = sqlite3.connect('sohbetler.db')
cursor = conn.cursor()

# Tabloları oluştur
print("📦 Tablolar oluşturuluyor...")

# 1. Users tablosu
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kullanici_adi TEXT UNIQUE NOT NULL,
        sifre_hash TEXT NOT NULL,
        olusturma_tarihi DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')

# 2. Sohbetler tablosu
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

# 3. Mesajlar tablosu
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
print("✅ Tablolar başarıyla oluşturuldu!")

# Test: Bir kullanıcı ekleyelim
print("\n👤 Test kullanıcısı oluşturuluyor...")
test_kullanici = "ahmet"
test_sifre = "12345"

# Şifreyi hash'le
sifre_hash = bcrypt.hashpw(test_sifre.encode('utf-8'), bcrypt.gensalt())

try:
    cursor.execute(
        "INSERT INTO users (kullanici_adi, sifre_hash) VALUES (?, ?)",
        (test_kullanici, sifre_hash)
    )
    conn.commit()
    print(f"✅ Kullanıcı '{test_kullanici}' oluşturuldu!")
except sqlite3.IntegrityError:
    print(f"⚠️ Kullanıcı '{test_kullanici}' zaten var!")

# Test: Şifre kontrolü
print("\n🔐 Şifre kontrolü yapılıyor...")
cursor.execute("SELECT sifre_hash FROM users WHERE kullanici_adi = ?", (test_kullanici,))
result = cursor.fetchone()

if result:
    db_hash = result[0]
    if bcrypt.checkpw(test_sifre.encode('utf-8'), db_hash):
        print("✅ Şifre doğru!")
    else:
        print("❌ Şifre yanlış!")

# Veritabanındaki kullanıcıları listele
print("\n📋 Kayıtlı kullanıcılar:")
cursor.execute("SELECT id, kullanici_adi, olusturma_tarihi FROM users")
users = cursor.fetchall()
for user in users:
    print(f"  - ID: {user[0]}, Kullanıcı: {user[1]}, Tarih: {user[2]}")

conn.close()
print("\n🎉 Test tamamlandı!")