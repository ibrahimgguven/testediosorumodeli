"""
LGS Bomba Oyunu - Backend API
-------------------------------
Mobil uygulamanın bağlanacağı FastAPI servisi.

Akış:
1. Mobil app -> POST /session/start  -> session açılır, ilk soru + arkaplanda queue doldurulur
2. Mobil app -> POST /answer         -> cevap değerlendirilir, zorluk güncellenir,
                                          queue'dan hazır bekleyen SONRAKI soru anında döner
                                          (kullanıcı LLM'i beklemez, çünkü soru önceden üretilmişti)
3. Arka planda queue sürekli 3 soru dolu tutulacak şekilde beslenir.

Not: Bu örnek in-memory (RAM) session store kullanır -> basit / hızlı prototipleme için.
Prodüksiyonda Redis kullanmanızı öneririm (birden fazla sunucu instance'ı olduğunda
in-memory state paylaşılmaz).
"""
import asyncio
import uuid
from collections import deque
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import (
    SessionStartRequest, SessionStartResponse, Soru,
    AnswerRequest, AnswerResponse, SessionEndResponse,
)
from difficulty import yeni_zorluk_hesapla
from llm_service import soru_uret

app = FastAPI(title="LGS Bomba Oyunu API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # mobil app'ten gelen istekler için; prodüksiyonda kısıtlayın
    allow_methods=["*"],
    allow_headers=["*"],
)

QUEUE_HEDEF_BOYUT = 3  # her zaman en az bu kadar soru hazır bekletilsin

# --- In-memory session store ---
# session_id -> { ... state ... }
SESSIONS: dict[str, dict] = {}


def _yeni_session_state(ogrenci_id: str, dersler: list[str], zorluk: float) -> dict:
    return {
        "ogrenci_id": ogrenci_id,
        "dersler": dersler,
        "zorluk": zorluk,
        "queue": deque(),          # bekleyen (henüz gösterilmemiş) sorular: (Soru, dogru_cevap, cozum)
        "aktif_soru": None,        # şu an mobil app'e gösterilmiş olan soru: (Soru, dogru_cevap, cozum)
        "son_konular": [],         # tekrarı önlemek için
        "toplam_soru": 0,
        "dogru_sayisi": 0,
        "yanlis_sayisi": 0,
        "ders_istatistik": {d: {"soru": 0, "dogru": 0} for d in dersler},
        "doldurma_kilidi": asyncio.Lock(),
    }


async def _queue_doldur(session_id: str):
    """Queue hedef boyutun altına düşerse arka planda yeni soru(lar) üretir."""
    state = SESSIONS.get(session_id)
    if state is None:
        return
    async with state["doldurma_kilidi"]:
        while len(state["queue"]) < QUEUE_HEDEF_BOYUT:
            ders = _sirali_ders_sec(state)
            try:
                soru, dogru_cevap, cozum = await soru_uret(
                    ders=ders,
                    zorluk=state["zorluk"],
                    son_konular=state["son_konular"][-8:],
                )
            except Exception as e:
                # LLM çağrısı başarısız olursa sessizce dener, sonsuz döngüye girmesin diye kırıyoruz
                print(f"[UYARI] Soru üretimi başarısız: {e}")
                break
            state["queue"].append((soru, dogru_cevap, cozum))
            state["son_konular"].append(soru.konu)


def _sirali_ders_sec(state: dict) -> str:
    """Dersleri sırayla döndürerek dengeli dağılım sağlar (round-robin)."""
    dersler = state["dersler"]
    idx = state["toplam_soru"] % len(dersler)
    return dersler[idx]


@app.post("/session/start", response_model=SessionStartResponse)
async def session_start(req: SessionStartRequest):
    session_id = str(uuid.uuid4())
    state = _yeni_session_state(req.ogrenci_id, req.dersler, req.baslangic_zorluk)
    SESSIONS[session_id] = state

    # İlk soruyu doğrudan üretip anında dönüyoruz (~1-2 sn),
    # kalan queue arka planda asenkron olarak doldurulur.
    ders = _sirali_ders_sec(state)
    try:
        soru, dogru_cevap, cozum = await soru_uret(
            ders=ders,
            zorluk=state["zorluk"],
            son_konular=[],
        )
    except Exception as e:
        SESSIONS.pop(session_id, None)
        raise HTTPException(status_code=502, detail=f"Soru üretilemedi, LLM servisini kontrol edin: {e}")

    state["aktif_soru"] = (soru, dogru_cevap, cozum)
    state["son_konular"].append(soru.konu)

    # Kalan queue'yu arka planda doldur (Queue hedef boyutuna kadar)
    asyncio.create_task(_queue_doldur(session_id))

    return SessionStartResponse(session_id=session_id, ilk_soru=soru)


@app.post("/answer", response_model=AnswerResponse)
async def answer(req: AnswerRequest):
    state = SESSIONS.get(req.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session bulunamadı.")

    if state["aktif_soru"] is None or state["aktif_soru"][0].soru_id != req.soru_id:
        raise HTTPException(status_code=400, detail="Bu soru şu anda aktif değil.")

    soru, dogru_cevap, cozum = state["aktif_soru"]
    dogru_mu = req.verilen_cevap.strip().upper() == dogru_cevap.strip().upper()

    # --- istatistikleri güncelle ---
    state["toplam_soru"] += 1
    state["dogru_sayisi" if dogru_mu else "yanlis_sayisi"] += 1
    ders_ist = state["ders_istatistik"][soru.ders]
    ders_ist["soru"] += 1
    if dogru_mu:
        ders_ist["dogru"] += 1

    # --- zorluk güncelle ---
    state["zorluk"] = yeni_zorluk_hesapla(
        mevcut_zorluk=state["zorluk"],
        dogru_mu=dogru_mu,
        cevap_suresi_saniye=req.cevap_suresi_saniye,
    )

    # NOT: "bomba_patladi" mantığı oyun kurallarınıza göre burada özelleştirilebilir.
    # Örn: art arda 3 yanlış -> bomba patlar. Basit örnek:
    bomba_patladi = not dogru_mu  # örnek kural: 1 yanlış = bomba patlar (isteğe göre değiştirin)

    sonraki_soru = None
    if not bomba_patladi:
        if not state["queue"]:
            # Nadiren queue boş kalırsa (LLM yavaş kaldıysa) burada bekleriz.
            await _queue_doldur(req.session_id)
        if state["queue"]:
            sonraki = state["queue"].popleft()
            state["aktif_soru"] = sonraki
            sonraki_soru = sonraki[0]
            asyncio.create_task(_queue_doldur(req.session_id))  # queue'yu tekrar besle
        else:
            bomba_patladi = True  # soru üretilemediyse oyunu güvenli şekilde bitir

    return AnswerResponse(
        dogru_mu=dogru_mu,
        dogru_cevap=dogru_cevap,
        cozum_aciklamasi=cozum,
        yeni_zorluk=state["zorluk"],
        bomba_patladi=bomba_patladi,
        sonraki_soru=sonraki_soru,
    )


@app.get("/session/{session_id}/summary", response_model=SessionEndResponse)
async def session_summary(session_id: str):
    state = SESSIONS.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session bulunamadı.")
    return SessionEndResponse(
        toplam_soru=state["toplam_soru"],
        dogru_sayisi=state["dogru_sayisi"],
        yanlis_sayisi=state["yanlis_sayisi"],
        son_zorluk=state["zorluk"],
        ders_bazli_ozet=state["ders_istatistik"],
    )


@app.delete("/session/{session_id}")
async def session_end(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"ok": True}


@app.get("/")
async def health():
    return {"status": "ok", "servis": "LGS Bomba Oyunu API"}
