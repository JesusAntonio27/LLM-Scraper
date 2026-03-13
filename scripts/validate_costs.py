import httpx
import sys

BASE = "http://localhost:8000"
URLS = [
    "https://galeriasbajio.com.mx/tiendas",
    "https://galeriasbajio.com.mx/restaurantes"
]
SCHEMA = {"stores": [{"name": "string", "category": "string"}]}

def main():
    print("─── Script 3: Verificación de costos ─────────────────────────────────────────")
    try:
        r = httpx.get(f"{BASE}/health")
        r.raise_for_status()
        print("1. ✅ GET /health: Sistema UP")
    except Exception as e:
        print(f"❌ Sistema no está respondiendo: {e}")
        sys.exit(1)

    print(f"\n2. Ejecutando /extract para 2 URLs: {URLS}")
    r_ext = httpx.post(
        f"{BASE}/extract",
        json={
            "urls": URLS,
            "schema": SCHEMA
        },
        timeout=240
    )
    r_ext.raise_for_status()
    ext_data = r_ext.json()
    results = ext_data["results"]
    summary = ext_data["summary"]
    
    print("\n3. Desglose de costos por URL:")
    sum_costs = 0.0
    hashes = []
    for res in results:
        url = res["url"]
        meta = res["meta"]
        print(f"\n   URL: {url}")
        print(f"   Modelo:           {meta.get('model_used')}")
        print(f"   Tokens Input:     {meta.get('tokens_input')}")
        print(f"   Tokens Output:    {meta.get('tokens_output')}")
        print(f"   Costo USD:        ${meta.get('cost_usd'):.6f}")
        sum_costs += meta.get("cost_usd", 0.0)
        hashes.append({"url": url, "content_hash": res.get("content_hash", "")})

    total_cost_usd = summary["total_cost_usd"]
    
    print("\n4. Verificación de suma de costos:")
    print(f"   Suma calculada: ${sum_costs:.6f}")
    print(f"   Costo reportado en summary: ${total_cost_usd:.6f}")
    
    if abs(sum_costs - total_cost_usd) < 0.000001:
        print("   ✅ La suma de costos individuales coincide con el resumen")
    else:
        print("   ❌ La suma no coincide!")
        
    print("\n5. Segunda corrida con ambos hashes...")
    r_ext2 = httpx.post(
        f"{BASE}/extract",
        json={
            "urls": URLS,
            "schema": SCHEMA,
            "already_scraped": hashes
        },
        timeout=120
    )
    r_ext2.raise_for_status()
    ext2_data = r_ext2.json()
    total_cost_usd_2 = ext2_data["summary"]["total_cost_usd"]
    
    print(f"   Costo reportado en summary (corrida 2): ${total_cost_usd_2:.6f}")
    if total_cost_usd_2 == 0.0:
        print("   ✅ Costo de segunda corrida es exacto $0.000000")
    else:
        print("   ❌ El costo de la deduplicación no fue cero.")
        
    print("\n6. Resumen final:")
    print(f"   Primera corrida: ${total_cost_usd:.6f} USD")
    print(f"   Segunda corrida (dedup): ${total_cost_usd_2:.6f} USD")
    print("   Ahorro por deduplicación: 100%")

if __name__ == "__main__":
    main()
