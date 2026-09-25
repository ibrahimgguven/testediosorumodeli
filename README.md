# LGS Bomba Oyunu — Soru Üretim API'si

LLM (Groq — **ücretsiz**) ile anlık, zorluk-seviyesine-uyumlu LGS sorusu üreten backend.
Bomba oyununuzun mobil uygulamasına (Flutter, React Native, native Android/iOS — fark etmez,
sadece HTTP istekleri atacak) direkt bağlanabilir.

## Neden gecikme sorun olmayacak?

LLM çağrısı 1-3 saniye sürebilir. Kullanıcı bombayı beklerken bunu hissetmesin diye
backend **her zaman 3 soruyu önceden üretip hazırda bekletir (prefetch queue)**.
Kullanıcı bir soruyu cevapladığı an, bir sonraki soru zaten hazır olduğu için anında gelir;
LLM aynı anda arka planda 4. soruyu üretmeye başlar. Detaylar `main.py` içindeki
`_queue_doldur` fonksiyonunda.

## Kurulum (yerel test için)

```bash
cd lgs_bomba_api
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# .env dosyasını açıp GROQ_API_KEY değerini kendi ücretsiz key'inizle doldurun
# (key almak için: https://console.groq.com -> ücretsiz kayıt -> API Keys)

export $(cat .env | xargs)    # .env'i ortam değişkeni olarak yükle (Linux/Mac)
uvicorn main:app --reload --port 8000
```

Servis ayağa kalktığında: `http://localhost:8000` — API dökümantasyonu (Swagger)
otomatik olarak `http://localhost:8000/docs` adresinde açılır, orada tüm endpoint'leri
tarayıcıdan deneyebilirsiniz.

## Endpoint'ler

| Method | Yol | Açıklama |
|---|---|---|
| POST | `/session/start` | Oyunu başlatır, ilk soruyu döner |
| POST | `/answer` | Cevabı değerlendirir, sonraki soruyu döner |
| GET | `/session/{id}/summary` | Oturum özetini (skor, ders bazlı istatistik) döner |
| DELETE | `/session/{id}` | Oturumu kapatır |

### Örnek akış (curl ile test)

```bash
# 1) Oturumu başlat
curl -X POST http://localhost:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{"ogrenci_id": "ogrenci_123", "baslangic_zorluk": 5}'

# Cevap örneği:
# {
#   "session_id": "a1b2c3...",
#   "ilk_soru": {
#     "soru_id": "...",
#     "ders": "Matematik",
#     "konu": "Üslü Sayılar",
#     "zorluk": 5.0,
#     "soru_metni": "...",
#     "secenekler": {"A": "...", "B": "...", "C": "...", "D": "..."}
#   }
# }

# 2) Cevap gönder
curl -X POST http://localhost:8000/answer \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3...",
    "soru_id": "...",
    "verilen_cevap": "C",
    "cevap_suresi_saniye": 8.5
  }'
```

## Mobil taraftan bağlanma (örnek)

Uygulamanız Flutter/React Native/native fark etmeksizin, sadece bu iki isteği atar:

```javascript
// React Native / JS örneği
const baseUrl = "https://sizin-sunucunuz.com"; // deploy ettikten sonraki adres

async function oyunuBaslat(ogrenciId) {
  const res = await fetch(`${baseUrl}/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ogrenci_id: ogrenciId }),
  });
  return res.json(); // { session_id, ilk_soru }
}

async function cevapGonder(sessionId, soruId, cevap, sureSaniye) {
  const res = await fetch(`${baseUrl}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      soru_id: soruId,
      verilen_cevap: cevap,
      cevap_suresi_saniye: sureSaniye,
    }),
  });
  return res.json(); // { dogru_mu, dogru_cevap, cozum_aciklamasi, bomba_patladi, sonraki_soru, ... }
}
```

## Ücretsiz tutmak için notlar

- **Groq ücretsiz katmanı**: dakika/gün başına istek limiti var (hesabınızdan kontrol edin).
  Kullanıcı sayınız büyüdükçe bu limitlere takılabilirsiniz.
- **Hosting**: Bu FastAPI servisini Render.com, Railway.app veya Fly.io gibi platformların
  ücretsiz katmanlarında barındırabilirsiniz (küçük/orta trafik için yeterli).
- **Maliyeti daha da düşürmek isterseniz**: Üretilen kaliteli soruları basit bir
  veritabanına (SQLite/Postgres) kaydedip zamanla "önce bankadan dene, yoksa LLM'den üret"
  hibrit moduna geçebilirsiniz — bu hem hızı arttırır hem LLM çağrı sayısını azaltır.

## Prodüksiyon için yapılması önerilenler

1. **Redis'e geçiş**: Şu an session'lar RAM'de (`SESSIONS` dict). Sunucu yeniden başlarsa
   veya birden fazla instance çalışırsa veri kaybolur/tutarsız olur. Redis ile session
   state paylaşımlı ve kalıcı hale gelir.
2. **Rate limiting**: Kötüye kullanımı önlemek için `slowapi` gibi bir kütüphaneyle
   IP/kullanıcı bazlı limit koyun.
3. **Kalite kontrol**: `llm_service.py` içindeki `soru_dogrula` fonksiyonunu devreye alarak
   matematik sorularında LLM'in kendi cevabını ikinci kez doğrulatabilirsiniz (maliyeti
   ikiye katlar ama yanlış "doğru cevap" riskini ciddi azaltır).
4. **HTTPS + Auth**: Mobil app ile backend arasına JWT token / API key doğrulaması ekleyin.
