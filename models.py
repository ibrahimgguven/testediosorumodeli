"""
LGS Bomba Oyunu - Veri Modelleri
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal

Ders = Literal["Matematik", "Türkçe", "Fen Bilimleri", "T.C. İnkılap Tarihi", "Din Kültürü", "İngilizce"]


class SessionStartRequest(BaseModel):
    ogrenci_id: str
    dersler: list[Ders] = Field(default_factory=lambda: [
        "Matematik", "Türkçe", "Fen Bilimleri",
        "T.C. İnkılap Tarihi", "Din Kültürü", "İngilizce"
    ])
    baslangic_zorluk: float = 5.0  # 1-10 arası


class SessionStartResponse(BaseModel):
    session_id: str
    ilk_soru: "Soru"


class Soru(BaseModel):
    soru_id: str
    ders: str
    konu: str
    zorluk: float
    soru_metni: str
    secenekler: dict[str, str]  # {"A": "...", "B": "...", "C": "...", "D": "..."}
    # Not: dogru_cevap ve cozum_aciklamasi istemciye (mobil app) GÖNDERİLMEZ.
    # Sadece backend'de saklanır; hile/kopya önlemi için.


class AnswerRequest(BaseModel):
    session_id: str
    soru_id: str
    verilen_cevap: str  # "A", "B", "C" veya "D"
    cevap_suresi_saniye: float


class AnswerResponse(BaseModel):
    dogru_mu: bool
    dogru_cevap: str
    cozum_aciklamasi: str
    yeni_zorluk: float
    bomba_patladi: bool  # süre doldu/yanlış limit aşıldıysa
    sonraki_soru: Optional[Soru] = None


class SessionEndResponse(BaseModel):
    toplam_soru: int
    dogru_sayisi: int
    yanlis_sayisi: int
    son_zorluk: float
    ders_bazli_ozet: dict[str, dict]
