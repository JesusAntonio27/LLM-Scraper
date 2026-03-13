import httpx
import sys

BASE = "http://localhost:8000"
URL = "https://www.cyberpuerta.mx/Computo-Hardware/Discos-Duros-SSDs/SSDs/"

def main():
    print("─── Script 2: E-commerce / Catálogo ──────────────────────────────────────────")
    try:
        r = httpx.get(f"{BASE}/health")
        r.raise_for_status()
        print("1. ✅ GET /health: Sistema UP")
    except Exception as e:
        print(f"❌ Sistema no está respondiendo: {e}")
        sys.exit(1)

    print(f"\n2. Ejecutando /extract/discover para {URL}...")
    r_disc = httpx.post(
        f"{BASE}/extract/discover",
        json={"url": URL, "hint": "catálogo de productos con nombre y precio"},
        timeout=120
    )
    r_disc.raise_for_status()
    disc_data = r_disc.json()
    schema = disc_data["suggested_schema"]
    model_used = disc_data["meta"]["model_used"]
    print(f"   Schema sugerido: {schema}")
    print(f"   Modelo usado en discover: {model_used}")

    print(f"\n3. Ejecutando /extract con schema descubierto...")
    r_ext = httpx.post(
        f"{BASE}/extract",
        json={
            "urls": [URL],
            "schema": schema,
            "output_hint": "catálogo de productos con nombre y precio"
        },
        timeout=180
    )
    r_ext.raise_for_status()
    ext_data = r_ext.json()
    summary = ext_data["summary"]
    records = ext_data["output"]["records"]
    content_hash = ext_data["results"][0].get("content_hash", "")
    
    print(f"   Total productos extraídos: {summary['extracted']}")
    print(f"   Costo: ${summary['total_cost_usd']:.6f} USD")
    print(f"   Tiempo: {summary['total_ms']} ms")
    print("\n   Primeros 5 registros:")
    for rec in records[:5]:
        print(f"   - {rec}")

    print(f"\n4. Segunda corrida con content_hash ({content_hash})...")
    r_ext2 = httpx.post(
        f"{BASE}/extract",
        json={
            "urls": [URL],
            "schema": schema,
            "already_scraped": [{"url": URL, "content_hash": content_hash}]
        },
        timeout=120
    )
    r_ext2.raise_for_status()
    ext2_data = r_ext2.json()
    status2 = ext2_data["results"][0]["status"]
    cost2 = ext2_data["summary"]["total_cost_usd"]
    
    print(f"   Status corrida 2: {status2}")
    print(f"   Costo corrida 2: ${cost2:.6f} USD")

    # Validación
    success = True
    reasons = []
    
    if len(records) == 0:
        success = False
        reasons.append("No se extrajeron registros")
        
    precio_con_formato = False
    falta_campo = False
    
    for rec in records:
        name = rec.get("name") or rec.get("nombre") or rec.get("title") or rec.get("product_name")
        price = rec.get("price") or rec.get("precio")
        
        if name is None or price is None:
            falta_campo = True
            
        if price is not None:
            price_str = str(price)
            if "$" in price_str or "," in price_str:
                precio_con_formato = True

    if falta_campo:
        success = False
        reasons.append("Registros sin campos equivalentes a nombre y precio")
    
    if precio_con_formato:
        success = False
        reasons.append("precios con formato (contienen '$' o comas)")
        
    print("\n---------------------------------------------------------")
    if success:
        print("✅ ECOMMERCE OK")
    else:
        print(f"❌ ECOMMERCE FALLO: {', '.join(reasons)}")

if __name__ == "__main__":
    main()
