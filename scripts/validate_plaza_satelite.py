import asyncio
import csv
import json
import os
import sys

sys.path.append(os.getcwd())

from httpx import AsyncClient, ASGITransport
from app.main import app

def print_separator():
    print("─────────────────────────────────────────────────")

async def run_validation():
    print("🏬 Procesando: Plaza Satélite")
    
    csv_path = "scripts/resultados_plazas.csv"
    
    # Check if CSV exists to know if we need header
    file_exists = os.path.isfile(csv_path)
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # PASO 1: Health
        health_res = await client.get("/health")
        if health_res.status_code == 200:
            health_data = health_res.json()
            if health_data.get("status") == "degraded":
                print("Error: API health is degraded. Stopping.")
                return
        
        # PASO 2: Discover
        print("  → Discover...")
        discover_req = {
            "url": "https://www.plazasatelite.com.mx/tiendas/",
            "hint": "directorio de tiendas de Plaza Satélite en CDMX, México",
            "fetch_options": {
                "render_js": True,
                "geo_location": "Mexico",
                "timeout": 45,
                "browser_instructions": [
                    {"type": "scroll_to_bottom"},
                    {"type": "wait", "wait_time_s": 2},
                    {"type": "scroll_to_bottom"},
                    {"type": "wait", "wait_time_s": 1}
                ]
            }
        }
        
        disc_res = await client.post("/extract/discover", json=discover_req)
        disc_data = disc_res.json()
        
        schema = disc_data.get("suggested_schema")
        if not schema or not disc_data.get("confidence"):
            schema = {
                "stores": [{
                    "plaza": "string",
                    "ubicacion": "string | null",
                    "nombre": "string"
                }]
            }
            
        # PASO 3: Extract Intento 1
        print("  → Extrayendo tiendas (intento 1/3)...")
        extract_req = {
            "urls": ["https://www.plazasatelite.com.mx/tiendas/"],
            "schema": schema,
            "output_hint": "directorio de tiendas de Plaza Satélite en CDMX México.\n              El nombre de la plaza es Plaza Satélite.\n              Los nombres de tiendas pueden estar en texto, en links o en\n              nombres de archivo de logos. Nunca inventes nombres — usa null\n              si no encuentras el nombre real de una tienda.",
            "fetch_options": discover_req["fetch_options"]
        }
        
        ext_res = await client.post("/extract", json=extract_req)
        ext_data = ext_res.json()
        
        records = ext_data.get("records", [])
        total_cost = ext_data.get("summary", {}).get("total_cost_usd", 0.0)
        
        # Intento 2
        if not records:
            print("  → Extrayendo tiendas (intento 2/3)...")
            extract_req["fetch_options"]["browser_instructions"] = [
                {"type": "scroll_to_bottom"},
                {"type": "wait", "wait_time_s": 2},
                {"type": "scroll_to_bottom"},
                {"type": "wait", "wait_time_s": 1},
                {"type": "wait", "wait_time_s": 3},
                {"type": "scroll_to_bottom"},
                {"type": "wait", "wait_time_s": 2}
            ]
            extract_req["llm_options"] = {"model": "sonnet"}
            
            ext_res = await client.post("/extract", json=extract_req)
            ext_data = ext_res.json()
            records = ext_data.get("records", [])
            total_cost += ext_data.get("summary", {}).get("total_cost_usd", 0.0)
            
        # Intento 3 - Preprocess
        if not records:
            print("  → Extrayendo tiendas (intento 3/3)...")
            prep_req = {
                "url": "https://www.plazasatelite.com.mx/tiendas/",
                "fetch_options": extract_req["fetch_options"]
            }
            prep_res = await client.post("/preprocess", json=prep_req)
            prep_data = prep_res.json()
            
            print_separator()
            print("  ❌ Plaza Satélite: 0 tiendas — ver diagnóstico abajo")
            print(f"original_size_kb: {prep_data.get('original_size_kb')}")
            print(f"processed_size_kb: {prep_data.get('processed_size_kb')}")
            print(f"strategy_used: {prep_data.get('strategy_used')}")
            print("--- Primeros 500 caracteres del markdown ---")
            print(prep_data.get("markdown", "")[:500])
            return

        # Success - write to CSV
        # Formatear "plaza" a "Plaza Satélite" y extraer campos
        formatted_records = []
        for r in records:
            # Depending on the schema, find the name and location
            # If the schema was hardcoded, keys are plaza, ubicacion, nombre
            nombre = r.get("nombre") or r.get("name") or r.get("store_name") or r.get("tienda")
            ubicacion = r.get("ubicacion") or r.get("location") or r.get("local")
            
            if nombre:
                formatted_records.append({
                    "plaza": "Plaza Satélite",
                    "ubicacion": ubicacion,
                    "nombre": nombre
                })
        
        if formatted_records:
            with open(csv_path, mode="a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["plaza", "ubicacion", "nombre"])
                if not file_exists:
                    writer.writeheader()
                writer.writerows(formatted_records)
                
            # Count total lines in CSV
            with open(csv_path, mode="r", encoding="utf-8") as f:
                total_lineas = sum(1 for line in f)
                
            print_separator()
            print(f"  ✅ Plaza Satélite: {len(formatted_records)} tiendas agregadas al CSV")
            print("  💾 scripts/resultados_plazas.csv actualizado")
            print(f"  📊 Total en archivo: {total_lineas - 1} tiendas de todas las plazas")
            print(f"  💰 Costo: ${total_cost:.6f} USD")
        else:
            print_separator()
            print("  ❌ Plaza Satélite: No se pudieron formatear los registros extraídos.")

if __name__ == "__main__":
    asyncio.run(run_validation())
