import csv
import io

class ResponseBuilder:
    """
    Consolidates processing results into a final response oriented to the client.
    Handles record flattening, CSV generation, and summary statistics.
    """

    @staticmethod
    def build(results: list[dict], schema: dict, include_csv: bool = False) -> dict:
        """
        Main method to build the final response object.
        Does not raise exceptions; returns common structure even if results are empty.
        """
        records = []
        
        # PASO 1 — Generar output.records
        for res in results:
            if res.get("status") == "extracted" and res.get("data"):
                data = res["data"]
                url = res.get("url")
                
                # Logic to find the "principal" list in the schema response
                found_list = False
                for val in data.values():
                    if isinstance(val, list):
                        for item in val:
                            if isinstance(item, dict):
                                # Flatten: Add source_url to each item in the list
                                record = item.copy()
                                record["source_url"] = url
                                records.append(record)
                        found_list = True
                        break # Only the first principal list
                
                if not found_list:
                    # Flat dict: data itself is the record
                    record = data.copy()
                    record["source_url"] = url
                    records.append(record)

        # PASO 2 — Generar output.csv (solo si include_csv=True)
        csv_content = None
        if include_csv and records:
            try:
                output = io.StringIO()
                # Use keys of the first record as headers
                writer = csv.DictWriter(output, fieldnames=records[0].keys())
                writer.writeheader()
                writer.writerows(records)
                csv_content = output.getvalue()
            except Exception:
                # Silently fail CSV generation to preserve the rest of the response
                csv_content = None

        # PASO 3 — Calcular summary
        summary = {
            "total":          len(results),
            "extracted":      0,
            "skipped":        0,
            "failed":         0,
            "total_tokens":   0,
            "total_cost_usd": 0.0,
            "total_ms":       0
        }

        for res in results:
            status = res.get("status")
            if status == "extracted":
                summary["extracted"] += 1
            elif status == "skipped":
                summary["skipped"] += 1
            elif status == "failed":
                summary["failed"] += 1
            
            meta = res.get("meta", {})
            # Use .get() with default 0 as per requirements
            tokens_in = meta.get("tokens_input", 0)
            tokens_out = meta.get("tokens_output", 0)
            cost = meta.get("cost_usd", 0.0)
            fetch_ms = meta.get("fetch_ms", 0)
            preprocess_ms = meta.get("preprocess_ms", 0)
            llm_ms = meta.get("llm_ms", 0)

            summary["total_tokens"] += (tokens_in + tokens_out)
            summary["total_cost_usd"] += cost
            summary["total_ms"] += (fetch_ms + preprocess_ms + llm_ms)

        # Round cost to 6 decimals as per requirements
        summary["total_cost_usd"] = round(summary["total_cost_usd"], 6)

        # PASO 4 — Nota especial para agentic
        if any(r.get("meta", {}).get("agentic") for r in results if r.get("meta")):
            summary_any: dict = summary  # type: ignore
            summary_any["cost_note"] = (
                "Costo incluye navegación agentic (Sonnet + múltiples "
                "iteraciones). Puede ser significativamente mayor que "
                "extracción directa."
            )

        # PASO 5 — Retornar el objeto final
        return {
            "results": results,
            "output": {
                "records":     records,
                "csv":         csv_content,
                "schema_used": schema
            },
            "summary": summary
        }
