"""
Upload dos manuais de teste para o Kyotech AI via API.

Uso:
    python scripts/upload_test_manuals.py --api-url https://kyotech-ai-backend-url --token SEU_JWT

O token JWT pode ser obtido no Clerk (dashboard ou via browser devtools).
"""
import argparse
import os
import sys

import httpx

MANUALS = [
    {
        "filename": "xerox-altalink-c80xx-user-guide.pdf",
        "equipment_key": "altalink-c80xx",
        "equipment_display_name": "Xerox AltaLink C8030/C8045/C8055/C8070",
        "doc_type": "manual",
        "published_date": "2024-01-15",
    },
    {
        "filename": "xerox-versalink-c405-user-guide.pdf",
        "equipment_key": "versalink-c405",
        "equipment_display_name": "Xerox VersaLink C405",
        "doc_type": "manual",
        "published_date": "2023-06-01",
    },
    {
        "filename": "xerox-versalink-c7000-user-guide.pdf",
        "equipment_key": "versalink-c7000",
        "equipment_display_name": "Xerox VersaLink C7000",
        "doc_type": "manual",
        "published_date": "2023-09-10",
    },
    {
        "filename": "xerox-workcentre-6515-user-guide.pdf",
        "equipment_key": "workcentre-6515",
        "equipment_display_name": "Xerox WorkCentre 6515",
        "doc_type": "manual",
        "published_date": "2023-03-20",
    },
    {
        "filename": "xerox-versalink-b605-user-guide.pdf",
        "equipment_key": "versalink-b605",
        "equipment_display_name": "Xerox VersaLink B605/B615",
        "doc_type": "manual",
        "published_date": "2024-02-01",
    },
]

MANUALS_DIR = os.path.join(os.path.dirname(__file__), "manuals")


def upload_manual(client: httpx.Client, api_url: str, token: str, manual: dict) -> bool:
    filepath = os.path.join(MANUALS_DIR, manual["filename"])

    if not os.path.exists(filepath):
        print(f"  SKIP: {manual['filename']} não encontrado")
        return False

    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"  Uploading: {manual['filename']} ({size_mb:.1f} MB) -> {manual['equipment_key']}")

    with open(filepath, "rb") as f:
        resp = client.post(
            f"{api_url}/api/v1/upload/document",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (manual["filename"], f, "application/pdf")},
            data={
                "equipment_key": manual["equipment_key"],
                "doc_type": manual["doc_type"],
                "published_date": manual["published_date"],
                "equipment_display_name": manual["equipment_display_name"],
            },
            timeout=300,
        )

    if resp.status_code == 200:
        data = resp.json()
        print(f"  OK: {data.get('total_pages', '?')} pages, {data.get('total_chunks', '?')} chunks")
        if data.get("was_duplicate"):
            print(f"      (duplicado — já existia)")
        return True
    else:
        print(f"  ERRO ({resp.status_code}): {resp.text[:200]}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Upload manuais de teste para Kyotech AI")
    parser.add_argument("--api-url", required=True, help="URL base do backend (ex: https://kyotech-backend.xxx.azurecontainerapps.io)")
    parser.add_argument("--token", required=True, help="JWT token do Clerk (Bearer token)")
    parser.add_argument("--only", help="Upload apenas um arquivo específico (nome do arquivo)")
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")
    manuals = MANUALS

    if args.only:
        manuals = [m for m in MANUALS if args.only in m["filename"]]
        if not manuals:
            print(f"Nenhum manual encontrado com '{args.only}'")
            sys.exit(1)

    print(f"\n=== Upload de Manuais de Teste ===")
    print(f"API: {api_url}")
    print(f"Manuais: {len(manuals)}\n")

    with httpx.Client() as client:
        success = 0
        for i, manual in enumerate(manuals, 1):
            print(f"[{i}/{len(manuals)}]")
            if upload_manual(client, api_url, args.token, manual):
                success += 1
            print()

    print(f"Resultado: {success}/{len(manuals)} manuais enviados com sucesso\n")


if __name__ == "__main__":
    main()
