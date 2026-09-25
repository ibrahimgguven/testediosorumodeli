"""
Zorluk Seviyesi Adaptasyon Motoru
---------------------------------
Basit ama etkili bir "staircase" (merdiven) algoritması.
ELO'nun sadeleştirilmiş bir versiyonu gibi düşünülebilir.

Zorluk skalası: 1.0 (çok kolay) - 10.0 (çok zor)
"""

MIN_ZORLUK = 1.0
MAX_ZORLUK = 10.0


def yeni_zorluk_hesapla(
    mevcut_zorluk: float,
    dogru_mu: bool,
    cevap_suresi_saniye: float,
    ideal_sure_saniye: float = 15.0,
) -> float:
    """
    Cevabın doğruluğuna VE hızına göre zorluk günceller.
    - Doğru + hızlı  -> zorluk daha çok artar (öğrenci rahat)
    - Doğru + yavaş  -> zorluk az artar (zorlanmış olabilir)
    - Yanlış + hızlı -> zorluk daha çok azalır (rastgele tıklamış olabilir, temel eksik)
    - Yanlış + yavaş -> zorluk az azalır (düşünmüş ama bilememiş)
    """
    hiz_orani = cevap_suresi_saniye / ideal_sure_saniye  # <1 hızlı, >1 yavaş
    hiz_orani = max(0.3, min(hiz_orani, 3.0))  # aşırı uçları kırp

    if dogru_mu:
        temel_artis = 0.9
        # hızlıysa artışı büyüt, yavaşsa küçült
        carpan = max(0.4, 1.6 - hiz_orani * 0.6)
        delta = temel_artis * carpan
    else:
        temel_azalis = -0.9
        carpan = max(0.4, 1.6 - hiz_orani * 0.6)
        delta = temel_azalis * carpan

    yeni = mevcut_zorluk + delta
    return round(max(MIN_ZORLUK, min(MAX_ZORLUK, yeni)), 2)


def zorluk_etiketi(zorluk: float) -> str:
    """LLM prompt'unda kullanılacak insan-okunur seviye etiketi."""
    if zorluk < 3:
        return "çok kolay (temel kavrama düzeyi)"
    elif zorluk < 5:
        return "kolay"
    elif zorluk < 7:
        return "orta"
    elif zorluk < 9:
        return "zor (LGS'de ayırt edici sorular seviyesi)"
    else:
        return "çok zor (LGS'de en üst dilim / zeka gerektiren sorular)"
