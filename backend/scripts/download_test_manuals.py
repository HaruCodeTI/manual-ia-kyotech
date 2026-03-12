"""
Download manuais técnicos públicos da Xerox e Ricoh para uso como dados de teste.

Uso:
    python scripts/download_test_manuals.py

Os PDFs são salvos em scripts/manuals/
"""
import os
import sys
import urllib.request
import ssl

MANUALS = [
    {
        "filename": "xerox-altalink-c80xx-user-guide.pdf",
        "url": "https://download.support.xerox.com/pub/docs/ALC80XX/userdocs/any-os/en_GB/AltaLink_C80XX_mfp_ug_en-US.pdf",
        "equipment": "Xerox AltaLink C8030/C8045/C8055/C8070",
        "doc_type": "manual",
    },
    {
        "filename": "xerox-versalink-c405-user-guide.pdf",
        "url": "https://download.support.xerox.com/pub/docs/VLC405/userdocs/any-os/en_GB/VersaLink_C405_mfp_ug_en-US.pdf",
        "equipment": "Xerox VersaLink C405",
        "doc_type": "manual",
    },
    {
        "filename": "xerox-versalink-c7000-user-guide.pdf",
        "url": "http://download.support.xerox.com/pub/docs/VLC7000/userdocs/any-os/en_GB/VersaLink_C7000_sfp_ug_en-us.pdf",
        "equipment": "Xerox VersaLink C7000",
        "doc_type": "manual",
    },
    {
        "filename": "xerox-workcentre-6515-user-guide.pdf",
        "url": "https://download.support.xerox.com/pub/docs/WC6515/userdocs/any-os/en_GB/WorkCentre_6515_mfp_ug_en-us.pdf",
        "equipment": "Xerox WorkCentre 6515",
        "doc_type": "manual",
    },
    {
        "filename": "xerox-altalink-b8100-c8100-admin-guide.pdf",
        "url": "https://download.support.xerox.com/pub/docs/ALB81XX/userdocs/any-os/en_GB/Xerox_AltaLink_B8100_C8100_AltaLink_B8200_C8200_series_mfp_sag_en-US.pdf",
        "equipment": "Xerox AltaLink B8100/C8100 Series",
        "doc_type": "manual",
    },
    {
        "filename": "xerox-workcentre-5325-admin-guide.pdf",
        "url": "https://download.support.xerox.com/pub/docs/WC53XX/userdocs/any-os/en_GB/WC53xx_sys_admin_guide_en.pdf",
        "equipment": "Xerox WorkCentre 5325/5330/5335",
        "doc_type": "manual",
    },
    {
        "filename": "xerox-versalink-b605-user-guide.pdf",
        "url": "https://download.support.xerox.com/pub/docs/VLB605_VLB615/userdocs/any-os/en_GB/VersaLink_B605_B615_mfp_ug_en-US.pdf",
        "equipment": "Xerox VersaLink B605/B615",
        "doc_type": "manual",
    },
    {
        "filename": "xerox-phaser-7800-user-guide.pdf",
        "url": "https://download.support.xerox.com/pub/docs/7800/userdocs/any-os/en/p7800_user_guide_en-us.pdf",
        "equipment": "Xerox Phaser 7800",
        "doc_type": "manual",
    },
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "manuals")


def download_manuals():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Some servers may have cert issues; use default context
    ctx = ssl.create_default_context()

    success = 0
    for i, manual in enumerate(MANUALS, 1):
        filepath = os.path.join(OUTPUT_DIR, manual["filename"])

        if os.path.exists(filepath):
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            print(f"  [{i}/{len(MANUALS)}] Já existe: {manual['filename']} ({size_mb:.1f} MB)")
            success += 1
            continue

        print(f"  [{i}/{len(MANUALS)}] Baixando: {manual['filename']}...")
        print(f"           URL: {manual['url']}")

        try:
            req = urllib.request.Request(
                manual["url"],
                headers={"User-Agent": "Mozilla/5.0 (compatible; KyotechAI/1.0)"},
            )
            with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
                data = resp.read()

            with open(filepath, "wb") as f:
                f.write(data)

            size_mb = len(data) / (1024 * 1024)
            print(f"           OK: {size_mb:.1f} MB")
            success += 1
        except Exception as e:
            print(f"           ERRO: {e}")

    print(f"\n  {success}/{len(MANUALS)} manuais baixados em {OUTPUT_DIR}")
    return success


if __name__ == "__main__":
    print("\n=== Download de Manuais Técnicos para Teste ===\n")
    download_manuals()
    print("\nPróximo passo: faça upload dos PDFs via interface em https://kyotech-ai.harucode.com.br")
    print("Ou use o script upload_test_manuals.py (quando disponível)\n")
