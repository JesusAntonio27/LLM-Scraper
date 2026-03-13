import httpx
import sys
import time
import csv
import copy

BASE = "http://localhost:8000"

PLAZAS = [
    {
        "nombre": "Forum Culiacán",
        "url": "https://www.forumculiacan.mx/directorio/directorio"
    },
    {
        "nombre": "Ceiba Culiacán",
        "url": "https://ceibaculiacan.com/directorio/"
    },
    {
        "nombre": "Plaza Sendero Culiacán",
        "url": "https://plazasendero.com.mx/plaza/culiacan/"
    },
    {
        "nombre": "Mítikah Mall",
        "url": "https://mitikah.com.mx/centrocomercial/directorio/"
    },
    {
        "nombre": "Plaza Satélite",
        "url": "https://plazasatelite.com.mx/directorio/"
    },
    {
        "nombre": "Galerías Insurgentes",
        "url": "https://www.galerias.com/galeriasinsurgentes"
    },
    {
        "nombre": "Antara Fashion Hall",
        "url": "https://www.antara.com.mx/directorio"
    },
    {
        "nombre": "Liverpool Perisur",
        "url": "https://www.liverpool.com.mx/tiendas/perisur"
    },
    {
        "nombre": "Pabellón Polanco",
        "url": "https://www.pabellonpolanco.com.mx/"
    }
]

DEFAULT_SCHEMA = {
    "stores": [{
        "plaza": "string",
        "ubicacion": "string | null",
        "nombre": "string"
    }]
}

def check_health() -> bool:
    try:
        r = httpx.get(f"{BASE}/health", timeout=10)
        r.raise_for_status()
        body = r.json()
        if body.get("status") == "ok":
            return True
        else:
            print(f"❌ /health indica estado degradado: {body}")
            return False
    except Exception as e:
        print(f"❌ Error conectando a /health: {e}")
        return False

def discover_schema(plaza: dict) -> dict:
    nombre = plaza["nombre"]
    url = plaza["url"]
    hint = f"directorio de tiendas de la plaza {nombre}. Necesito: nombre de tienda, ubicación dentro de la plaza (piso o local), y nombre de la plaza."
    
    print("  → Discover...")
    try:
        r = httpx.post(
            f"{BASE}/extract/discover",
            json={"url": url, "hint": hint},
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        
        # Validar si el schema descubierto tiene los 3 campos exactos requeridos
        schema = data.get("suggested_schema", {})
        if "stores" in schema and isinstance(schema["stores"], list) and len(schema["stores"]) > 0:
            store_schema = schema["stores"][0]
            if "plaza" in store_schema and "ubicacion" in store_schema and "nombre" in store_schema:
                # Retornaremos el exacto requerido para asegurar conformidad
                pass
            
        return DEFAULT_SCHEMA
    except Exception as e:
        print(f"  ⚠️  Fallo Discover ({e}), usando schema por defecto...")
        return DEFAULT_SCHEMA

def extract_with_retry(plaza: dict, schema: dict, max_intentos: int = 3) -> dict:
    nombre = plaza["nombre"]
    url = plaza["url"]
    hint = f"directorio de tiendas de la plaza {nombre}. Necesito: nombre de tienda, ubicación dentro de la plaza (piso o local), y nombre de la plaza. Si el sitio es Next.js busca en __NEXT_DATA__."
    
    best_result = {
        "records": [],
        "intentos": 0,
        "cost_usd": 0.0,
        "ms": 0
    }
    
    current_cost_usd = 0.0
    current_ms = 0
    
    for intento in range(1, max_intentos + 1):
        if intento == 1:
            print(f"  → Extrayendo tiendas (intento {intento}/{max_intentos})...")
            payload = {
                "urls": [url],
                "schema": schema,
                "output_hint": hint,
                "llm_options": {
                    "agentic": False
                }
            }
        else:
            print(f"  ⚠️  {nombre} intento {intento - 1}: {len(best_result['records'])} tiendas — reintentando...")
            time.sleep(2)
            payload = {
                "urls": [url],
                "schema": schema,
                "output_hint": hint,
                "llm_options": {
                    "model": "sonnet", # Forzar modelo más capaz en reintentos
                    "agentic": True
                }
            }
            
        try:
            r = httpx.post(
                f"{BASE}/extract",
                json=payload,
                timeout=120
            )
            r.raise_for_status()
            data = r.json()
            
            summary = data.get("summary", {})
            results = data.get("results", [])
            output = data.get("output", {})
            records = output.get("records", [])
            
            cost_usd = summary.get("total_cost_usd", 0.0)
            ms = summary.get("total_ms", 0)
            
            current_cost_usd += cost_usd
            current_ms += ms
            
            status = "failed"
            if len(results) > 0:
                status = results[0].get("status", "failed")
                
            num_tiendas = len(records)
            prev_num_tiendas = len(best_result["records"])
            
            # Guardamos el resultado si extrajo más tiendas que cualquier intento previo
            if num_tiendas > prev_num_tiendas:
                 best_result["records"] = copy.deepcopy(records)
                 
            # Actualizamos también si fue el primer intento, aunque sean 0, para tener algo de base, o conservamos el que extrajo más
            if intento == 1 and num_tiendas == 0:
                best_result["records"] = []
                
            best_result["intentos"] = intento
            best_result["cost_usd"] = current_cost_usd
            best_result["ms"] = current_ms
            
            # Condiciones para reintentar
            if status == "failed" or num_tiendas == 0 or num_tiendas <= prev_num_tiendas:
                if intento < max_intentos:
                    continue # Siguiente intento
                else:
                    break # Se acabaron los intentos
            else:
                 # El intento N extrajo más tiendas y no falló, pero podríamos evaluar si superó el '0', en ese caso se podría considerar reintentar buscando más, pero la regla dice que si el intento N retornó MÁS tiendas, evaluamos...
                 # De acuerdo con "El reintento se dispara por: 0 tiendas, status failed, O menos tiendas que intento anterior", aquí retornaríamos a menos que queramos intentar por defecto los 3 (pero usualmente se detiene en éxito).
                 # Como dice "Si el reintento retorna MÁS tiendas que el intento anterior ... Si el reintento retorna MENOS o IGUAL ... Después de agotar los 3 intentos", la regla "Reintentar si N retornó MENOS tiendas" se cumple en el if anterior (num_tiendas <= prev_num_tiendas). Si es más, se detiene, a menos que sea 0.
                 break
            
        except Exception as e:
            if intento < max_intentos:
                 continue
            else:
                 break

    print(f"  → {len(best_result['records'])} tiendas extraídas ✅")
    return best_result

def save_csv(all_records: list, filepath: str) -> None:
    # Escribir con utf-8-sig para soporte en Excel
    with open(filepath, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=',')
        
        # Escribir encabezados en orden exacto
        writer.writerow(["plaza", "ubicacion", "nombre"])
        
        for record in all_records:
            plaza = record.get("plaza", "")
            ubicacion = record.get("ubicacion", "")
            if ubicacion is None:
                ubicacion = ""
            nombre = record.get("nombre", "")
            
            writer.writerow([plaza, ubicacion, nombre])

def main() -> None:
    print(f"🔍 Iniciando extracción de directorios — {len(PLAZAS)} plazas")
    print("📡 Verificando sistema...")
    
    if not check_health():
        sys.exit(1)
        
    all_records = []
    total_cost = 0.0
    total_ms = 0
    plaza_stats = []
    
    for plaza in PLAZAS:
        print("─────────────────────────────────────")
        print(f"🏬 Procesando: {plaza['nombre']}")
        
        schema = discover_schema(plaza)
        
        result = extract_with_retry(plaza, schema)
        
        records = result["records"]
        all_records.extend(records)
        
        total_cost += result["cost_usd"]
        total_ms += result["ms"]
        
        print(f"  ✅ {plaza['nombre']}: {len(records)} tiendas | ${result['cost_usd']:.6f} USD | {result['ms']/1000.0:.2f}s")
        
        plaza_stats.append({
            "nombre": plaza["nombre"],
            "count": len(records)
        })

    csv_path = "scripts/resultados_plazas.csv"
    save_csv(all_records, csv_path)
    
    print("─────────────────────────────────────")
    print("📊 RESUMEN FINAL")
    for stat in plaza_stats:
        print(f"  {stat['nombre']}:    {stat['count']} tiendas")
    print(f"  Total:             {len(all_records)} tiendas")
    print(f"  Costo total:       ${total_cost:.6f} USD")
    print(f"  Tiempo total:      {total_ms/1000.0:.2f}s")
    print(f"  💾 Guardado en: {csv_path}")

if __name__ == "__main__":
    main()
