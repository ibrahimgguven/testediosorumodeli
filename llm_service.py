"""
LLM Soru Üretim Servisi
------------------------
Groq API kullanır (ücretsiz katman mevcut, çok düşük gecikme).
groq.com üzerinden ücretsiz API key alıp .env dosyasına eklemeniz yeterli.

İstenirse GROQ yerine başka bir OpenAI-uyumlu ücretsiz sağlayıcıya
(örn. Google AI Studio / Gemini ücretsiz katman) geçmek için sadece
BASE_URL, MODEL ve API_KEY değerlerini değiştirmeniz yeterli;
kodun geri kalanı OpenAI-uyumlu her servisle çalışır.
"""
import os
import json
import re
import uuid
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

from difficulty import zorluk_etiketi
from models import Soru

# --- Ücretsiz sağlayıcı ayarları (Groq) ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")  # Groq'ta hızlı ve güçlü model

def get_client() -> AsyncOpenAI:
    api_key = os.environ.get("GROQ_API_KEY", "") or GROQ_API_KEY
    if not api_key:
        raise ValueError("GROQ_API_KEY tanımlanmamış! Lütfen .env dosyanızı kontrol edin.")
    return AsyncOpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


SISTEM_PROMPTU = """Sen Türkiye'deki LGS (Liselere Geçiş Sınavı) sınavına hazırlanan
8. sınıf öğrencileri için soru hazırlayan uzman bir eğitmensin.

KURALLAR:
1. SADECE geçerli JSON döndür. Başka hiçbir açıklama, markdown işareti (```) veya ek metin ekleme.
2. Sorular MEB müfredatına ve LGS kazanımlarına birebir uygun olmalı.
3. Her soru 4 seçenekli (A, B, C, D) olmalı, tek doğru cevabı olmalı.
4. Zorluk seviyesine göre soru karmaşıklığını ayarla.
5. cozum_aciklamasi alanında doğru cevabın NEDEN doğru olduğunu adım adım, öğrenciye
   öğretici biçimde açıkla.
6. Sana verilen "tekrar sorulmasın" listesindeki konu/soru tiplerini tekrarlama.

JSON formatı tam olarak şöyle olmalı:
{
  "konu": "kısa konu başlığı",
  "soru_metni": "soru metni",
  "secenekler": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "dogru_cevap": "A",
  "cozum_aciklamasi": "adım adım çözüm"
}
"""


def _json_ayikla(metin: str) -> dict:
    """LLM cevabından güvenli bir şekilde JSON ayıklar ve ayrıştırır."""
    metin = metin.strip()
    metin = re.sub(r"^```(?:json)?\s*", "", metin, flags=re.MULTILINE)
    metin = re.sub(r"\s*```$", "", metin, flags=re.MULTILINE).strip()
    
    baslangic = metin.find("{")
    bitis = metin.rfind("}")
    if baslangic == -1 or bitis == -1:
        raise ValueError(f"LLM cevabında JSON bulunamadı: {metin[:200]}")
    
    json_str = metin[baslangic:bitis + 1]
    try:
        return json.loads(json_str, strict=False)
    except json.JSONDecodeError as e:
        try:
            json_str_clean = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
            return json.loads(json_str_clean, strict=False)
        except json.JSONDecodeError:
            raise ValueError(f"JSON ayrıştırma hatası: {e}\nMetin: {json_str[:300]}")


def _veri_normalize_et(veri: dict) -> dict:
    """LLM'den gelen JSON'daki anahtar isimlerini standartlaştırır."""
    anahtarlar = {str(k).lower(): v for k, v in veri.items()}
    
    konu = veri.get("konu") or anahtarlar.get("konu") or "Genel"
    soru_metni = (
        veri.get("soru_metni") or 
        anahtarlar.get("soru_metni") or 
        anahtarlar.get("soru") or 
        anahtarlar.get("sorumetni") or ""
    )
    secenekler_ham = (
        veri.get("secenekler") or 
        anahtarlar.get("secenekler") or 
        anahtarlar.get("options") or {}
    )
    secenekler = {str(k).upper(): str(v) for k, v in secenekler_ham.items()}
    
    dogru_cevap = (
        veri.get("dogru_cevap") or 
        anahtarlar.get("dogru_cevap") or 
        anahtarlar.get("dogrucevap") or 
        anahtarlar.get("cevap") or 
        "A"
    )
    dogru_cevap = str(dogru_cevap).strip().upper()[:1]
    
    cozum_aciklamasi = (
        veri.get("cozum_aciklamasi") or 
        anahtarlar.get("cozum_aciklamasi") or 
        anahtarlar.get("cozum") or 
        anahtarlar.get("aciklama") or ""
    )
    
    return {
        "konu": konu,
        "soru_metni": soru_metni,
        "secenekler": secenekler,
        "dogru_cevap": dogru_cevap,
        "cozum_aciklamasi": cozum_aciklamasi
    }


async def soru_uret(ders: str, zorluk: float, son_konular: list[str]) -> Soru:
    """
    Belirtilen ders ve zorluk seviyesinde LLM ile yeni bir LGS sorusu üretir.
    son_konular: Tekrarı önlemek için son üretilen konu başlıkları.
    """
    kullanici_promptu = f"""
Ders: {ders}
Zorluk seviyesi: {zorluk}/10 ({zorluk_etiketi(zorluk)})
Son sorulan konular (bunları TEKRARLAMA): {", ".join(son_konular) if son_konular else "yok"}

Yukarıdaki kurallara göre 1 adet yeni LGS sorusu üret.
"""

    client = get_client()
    yanit = await client.chat.completions.create(
        model=GROQ_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SISTEM_PROMPTU},
            {"role": "user", "content": kullanici_promptu},
        ],
        temperature=0.7,
        max_tokens=1500,
    )

    ham_metin = yanit.choices[0].message.content
    ham_veri = _json_ayikla(ham_metin)
    veri = _veri_normalize_et(ham_veri)

    return Soru(
        soru_id=str(uuid.uuid4()),
        ders=ders,
        konu=veri["konu"],
        zorluk=zorluk,
        soru_metni=veri["soru_metni"],
        secenekler=veri["secenekler"],
    ), veri["dogru_cevap"], veri["cozum_aciklamasi"]


async def soru_dogrula(soru_metni: str, secenekler: dict, iddia_edilen_cevap: str) -> bool:
    """
    OPSİYONEL kalite-kontrol katmanı: LLM'in verdiği 'doğru cevap'ı
    ikinci bir çağrıyla teyit eder. Matematik/mantık sorularında
    LLM hata yapabildiği için önerilir. Maliyeti ikiye katlar,
    isterseniz bu adımı atlayıp doğrudan güvenebilirsiniz.
    """
    dogrulama_promptu = f"""
Aşağıdaki çoktan seçmeli soruyu adım adım çöz ve SADECE doğru şıkkın harfini
(A, B, C veya D) tek karakter olarak döndür, başka hiçbir şey yazma.

Soru: {soru_metni}
A) {secenekler.get("A")}
B) {secenekler.get("B")}
C) {secenekler.get("C")}
D) {secenekler.get("D")}
"""
    client = get_client()
    yanit = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": dogrulama_promptu}],
        temperature=0,
        max_tokens=10,
    )
    tespit_edilen = yanit.choices[0].message.content.strip().upper()[:1]
    return tespit_edilen == iddia_edilen_cevap.upper()
