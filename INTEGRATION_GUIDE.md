# 🛠 LGS Bomba Oyunu — Backend Entegrasyon & Kurulum Rehberi

Bu belge, **LGS Bomba Oyunu Soru Üretim ve Oyun Motoru API'sinin** kurulması, çalıştırılması ve mevcut altyapınıza entegre edilmesi için hazırlanmıştır.

---

## 📂 1. Dizin Yapısının İncelemesi

Proje aşağıdaki modüllerden oluşmaktadır:

```text
lgs_bomba_api/
├── main.py             # FastAPI HTTP endpoint'leri ve asenkron queue yönetimi
├── llm_service.py      # Groq LLM API entegrasyonu & JSON parser
├── models.py           # Pydantic veri modelleri ve request/response şemaları
├── difficulty.py       # ELO tabanlı dinamik zorluk uyarlama algoritması
├── requirements.txt    # Python paket bağımlılıkları
├── .env                # Ortam değişkenleri ve API Key'ler
├── README.md           # Genel bilgilendirme ve cURL örnekleri
└── INTEGRATION_GUIDE.md# Bu entegrasyon kılavuzu
```

---

## ⚙️ 2. Kurulum ve Ortam Hazırlığı (Sırayla Yapılacaklar)

### Adım 2.1: Python Sanal Ortamı Oluşturma ve Bağımlılıkları Yükleme
Projenin dizinine geçip aşağıdaki komutları sırasıyla çalıştırın:

```bash
# 1. Sanal ortam oluşturun (Python 3.10+ önerilir)
python3 -m venv venv

# 2. Sanal ortamı aktif edin
# Linux/macOS:
source venv/bin/activate
# Windows:
# venv\Scripts\activate

# 3. Gerekli kütüphaneleri yükleyin
pip install -r requirements.txt
```

### Adım 2.2: Ortam Değişkenlerinin (`.env`) Yapılandırılması
Proje dizinindeki `.env` dosyasını kontrol edin veya yoksa oluşturun:

```env
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
```
> **Not:** Ücretsiz Groq API Key tanımlanmıştır. İhtiyaç durumunda `https://console.groq.com` adresinden yeni bir anahtar alınabilir.

---

## 🚀 3. Servisi Çalıştırma ve Test Etme

### Adım 3.1: Servisi Başlatma
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Adım 3.2: Sağlık Kontrolü (Healthcheck)
Servisin çalıştığını doğrulamak için terminalden veya tarayıcıdan kontrol edin:
```bash
curl http://localhost:8000/
```
**Beklenen Yanıt:**
```json
{"status": "ok", "servis": "LGS Bomba Oyunu API"}
```

### Adım 3.3: Interactive API Dokümantasyonu (Swagger)
Tarayıcıdan `http://localhost:8000/docs` adresine giderek tüm endpoint'leri canlı olarak test edebilirsiniz.

---

## 🔌 4. Mevcut Backend Mimarisine Entegrasyon Yöntemleri

Backend ekibi ihtiyacına göre iki farklı entegrasyon yolundan birini seçebilir:

### Yöntem A: Bağımsız Microservice Olarak Çalıştırma (Önerilen)
- Bu servisi Docker container'ı veya ayrı bir port (`8000`) üzerinde mikroservis olarak çalıştırın.
- Mobil uygulama veya ana backend'iniz doğrudan bu servisin endpoint'lerine istek atar.

### Yöntem B: Mevcut FastAPI / Python Projesine Modül Olarak Dahil Etme
- Eğer ana backend'iniz de Python / FastAPI ise; `llm_service.py`, `difficulty.py` ve `models.py` dosyalarını ana projenize kopyalayıp `main.py` içindeki endpoint'leri kendi `APIRouter` yapınıza dahil edebilirsiniz.

---

## 📱 5. Mobil Uygulama & Backend İstek Akışı (API Contract)

### 1️⃣ Oyun Başlangıcı
- **Endpoint:** `POST /session/start`
- **Request Body:**
  ```json
  {
    "ogrenci_id": "ogrenci_123",
    "dersler": ["Matematik", "Türkçe", "Fen Bilimleri"],
    "baslangic_zorluk": 5.0
  }
  ```
- **Response:**
  ```json
  {
    "session_id": "c9622de3-9315-44d7-b11c-636453236b78",
    "ilk_soru": {
      "soru_id": "8813d843-64b5-4ba5-aed9-64aacadaca09",
      "ders": "Matematik",
      "konu": "Denklemler",
      "zorluk": 5.0,
      "soru_metni": "2x - 5 = 15 ise x kaçtır?",
      "secenekler": { "A": "10", "B": "8", "C": "12", "D": "5" }
    }
  }
  ```

### 2️⃣ Cevap Gönderme ve Sonraki Soruyu Alma
- **Endpoint:** `POST /answer`
- **Request Body:**
  ```json
  {
    "session_id": "c9622de3-9315-44d7-b11c-636453236b78",
    "soru_id": "8813d843-64b5-4ba5-aed9-64aacadaca09",
    "verilen_cevap": "A",
    "cevap_suresi_saniye": 8.5
  }
  ```
- **Response:**
  ```json
  {
    "dogru_mu": true,
    "dogru_cevap": "A",
    "cozum_aciklamasi": "2x = 20 => x = 10 bulunur.",
    "yeni_zorluk": 5.85,
    "bomba_patladi": false,
    "sonraki_soru": {
      "soru_id": "9924e954-75c6-5cb6-bfe0-747553247c10",
      "ders": "Türkçe",
      "konu": "Paragrafta Anlam",
      "zorluk": 5.85,
      "soru_metni": "...",
      "secenekler": { "A": "...", "B": "...", "C": "...", "D": "..." }
    }
  }
  ```

### 3️⃣ Oyun Sonu ve İstatistik Özeti
- **Endpoint:** `GET /session/{session_id}/summary`
- **Response:**
  ```json
  {
    "toplam_soru": 5,
    "dogru_sayisi": 4,
    "yanlis_sayisi": 1,
    "son_zorluk": 6.2,
    "ders_bazli_ozet": {
      "Matematik": { "soru": 3, "dogru": 2 },
      "Türkçe": { "soru": 2, "dogru": 2 }
    }
  }
  ```

---

## 🔒 6. Prodüksiyon Yayını İpuçları (Production Readiness)

1. **Redis Entegrasyonu (Çoklu Worker/Node için):**
   - Şu an session state'leri RAM üzerinde `SESSIONS` sözlüğünde tutulmaktadır.
   - Sunucuda birden fazla Uvicorn worker'ı (`--workers 4`) veya Kubernetes kullanacaksanız `SESSIONS` yapısını Redis'e yönlendirmeniz önerilir.
2. **Güvenlik (Authentication & CORS):**
   - `main.py` içinde CORS `allow_origins=["*"]` varsayılandır. Prodüksiyonda uygulamanızın domain/scheme'i ile kısıtlayın.
   - Endpoint'lere JWT Bearer token doğrulaması ekleyebilirsiniz.
