#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera `para-monica-xml/`: el corpus CORFO envuelto en XML navegable.

Encargo: issue #288, con la corrección de rumbo de Romina del 29-jul —
el derivado no es sólo un envoltorio fiel, tiene que poder recorrerse rápido
y no hacer tropezar a quien lo lee con la basura del OCR.

Reparto de trabajo:
  - Los **haikus leen**. Uno por documento. Deciden qué es sección, qué es un
    punto clave y qué es un typo de OCR. Escriben su mapa en JSON.
  - Este **script materializa**. Aplica, arma el índice y escribe el XML.

Por qué partido así: si el haiku escribiera el XML entero, cada página que
transcribe es una oportunidad de perder o alterar texto sin que nadie lo note.
Acá el haiku propone y el código dispone, y **todo lo que el haiku afirma se
revalida contra el texto fuente antes de entrar** (ley 4 de la casa). Lo que no
calza se descarta y se cuenta; el conteo va en el manifiesto y en el XML, a la
vista, no escondido.

La guarda que no se negocia:
  **ninguna corrección puede tocar un dígito.** Ni en el original ni en el
  reemplazo. Un OCR que leyó mal un monto se marca para cotejar contra el PDF;
  no se adivina. Un número inventado se convierte en un cálculo equivocado de
  plata real, y eso no lo arregla ningún disclaimer.

Uso:
    python3 tools/generar_xml_corfo.py             # genera
    python3 tools/generar_xml_corfo.py --verificar # comprueba, no escribe
"""

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "proyectos/finanzas/propuestas_comerciales/2026-07/kando-suite/corfo-innova-region"
DESTINO = FUENTE / "para-monica-xml"
MAPAS = Path("/tmp/claude-0/-home-user-pasaelfiltro/dfb36ac4-01c1-5a84-ae77-8e6130b6b536/scratchpad")

DOCUMENTOS = [
    "01_BAG_2020.md",
    "02_Modificacion_BAG_2023.md",
    "03_Modificacion_BAG_2024_RA51.md",
    "04_Manual_Rendiciones_2020.md",
    "05_Modificacion_Manual_Rendiciones_2023.md",
    "06_Empresas_Lideradas_por_Mujeres.md",
    "CORFO_Aviso_IR_2026_CDPR.md",
    "CORFO_RVARE24062026_Focalizacion_Innova_Region_2026_1.md",
    "CORFO_Reselec_E_N942024__InnovaChile__Modifica_Bases_Innova_Region.md",
]

EXCLUIDOS = {"00_INDICE_Y_CONTROL_DE_CALIDAD.md", "EXPEDIENTE_SITUACION.md"}

RE_PAGINA = re.compile(r"<!-- página PDF (\d+) -->\n## Página (\d+)\n", re.MULTILINE)
RE_META = {
    "archivo_fuente": re.compile(r"^- \*\*Archivo fuente:\*\* `(.+)`$", re.MULTILINE),
    "paginas": re.compile(r"^- \*\*Páginas:\*\* (\d+)$", re.MULTILINE),
    "metodo": re.compile(r"^- \*\*Método:\*\* (.+)$", re.MULTILINE),
}
RE_DIGITO = re.compile(r"\d")

ADVERTENCIA = (
    "Copia de conveniencia para búsqueda y lectura por LLM, con typos de OCR "
    "corregidos y anotados. NO es el acto oficial. Para citas literales, montos, "
    "garantías, plazos, tablas y obligaciones, cotejar el PDF oficial de CORFO."
)


def sha256(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()
def cdata(t): return "<![CDATA[" + t.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def attr(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def partir_en_paginas(texto):
    marcas = list(RE_PAGINA.finditer(texto))
    if not marcas:
        return texto, []
    for m in marcas:
        if m.group(1) != m.group(2):
            raise ValueError(f"frontera incoherente: {m.group(1)} vs {m.group(2)}")
    pre = texto[: marcas[0].start()]
    out = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        out.append((int(m.group(1)), m.group(0), texto[m.end(): fin]))
    return pre, out


def filtrar_correcciones(propuestas, texto, n_paginas):
    """La aduana. Devuelve (aceptadas, rechazadas_con_motivo).

    Se rechaza —no se corrige, no se negocia— cualquier propuesta que:
      - toque un dígito, en el original o en el reemplazo;
      - **no se parezca a lo que dice corregir** (ver abajo);
      - no aparezca literal en el texto fuente;
      - aparezca más de una vez (reemplazo ambiguo);
      - no cambie nada;
      - cite una página que no existe.

    Sobre el parecido, que es la guarda que costó descubrir: pedirle a una
    instancia que "corrija el OCR" la invita a **reconstruir** lo que no puede
    saber. En la primera pasada un haiku propuso `HS LES dechile` →
    `Boletín Oficial de la República de Chile`: eso no es arreglar un typo, es
    escribir otra cosa encima de un membrete ilegible. Suena bien y es
    invención. Un typo de OCR se parece a su palabra —`Codo`→`CORFO`,
    `Namero`→`Número`— así que se exige que se parezca. Lo que está demasiado
    roto para parecerse, está demasiado roto para adivinarlo.
    """
    ok, no = [], []
    vistos = set()
    for c in propuestas:
        orig = c.get("original", "")
        corr = c.get("corregido", "")
        pag = c.get("pagina")

        if not orig or not corr:
            no.append({**c, "rechazo": "campos vacíos"}); continue
        if orig == corr:
            no.append({**c, "rechazo": "no cambia nada"}); continue
        # Los dígitos tienen que sobrevivir intactos y en el mismo orden. No se
        # prohíbe que la corrección los contenga —`plazt máximo de 10 días` ->
        # `plazo máximo de 10 días` es legítima y el 10 va de acompañante—; se
        # prohíbe que cambien. Comparar la secuencia completa cubre por igual el
        # dígito alterado, el agregado y el borrado: una propuesta quería
        # reemplazar un número de trámite ilegible por "[número]", y eso acá es
        # "15112020002" contra "", que no calza.
        if RE_DIGITO.findall(orig) != RE_DIGITO.findall(corr):
            no.append({**c, "rechazo": "cambia, agrega o borra dígitos — las cifras no se tocan"})
            continue

        ratio = SequenceMatcher(None, orig.lower(), corr.lower()).ratio()
        largo = len(corr) / max(len(orig), 1)
        # En cadenas cortas la similitud proporcional miente: `Ia` -> `la` es un
        # solo carácter y puntúa 0.50, igual que dos palabras sin relación. Para
        # esas se mide la edición real en vez de la proporción.
        distancia_corta = len(orig) <= 6 and sum(
            1 for op in SequenceMatcher(None, orig, corr).get_opcodes() if op[0] != "equal"
        ) <= 2
        if not distancia_corta and (ratio < 0.70 or not (0.7 <= largo <= 1.45)):
            no.append({**c, "rechazo": f"no se parece al original (similitud {ratio:.2f}, "
                                       f"largo x{largo:.1f}) — parece reconstrucción, no corrección"})
            continue

        n = texto.count(orig)
        if n == 0:
            no.append({**c, "rechazo": "no aparece literal en el fuente"}); continue

        # Las correcciones que más valen son las sistemáticas: el OCR lee `Ia`
        # por `la` en todo el documento, no una vez. Exigir unicidad las mataría
        # justo a ellas. Se permiten en bloque **sólo** si el original es una
        # palabra completa —con frontera a ambos lados—, que es lo que impide
        # pisar el interior de otra palabra. Si no lo es, vuelve a regir la
        # unicidad: un fragmento suelto reemplazado en veinte lugares es una
        # forma barata de arruinar un documento entero.
        palabra = bool(re.fullmatch(r"\w[\w'ºª°-]*", orig, re.UNICODE))
        if palabra:
            rx = re.compile(rf"(?<!\w){re.escape(orig)}(?!\w)", re.UNICODE)
            apariciones = len(rx.findall(texto))
            if apariciones == 0:
                no.append({**c, "rechazo": "aparece sólo dentro de otras palabras, "
                                           "no como palabra suelta"}); continue
            c = {**c, "global": True, "ocurrencias": apariciones}
        elif n > 1:
            no.append({**c, "rechazo": f"ambiguo: aparece {n} veces y no es una palabra suelta"})
            continue
        else:
            c = {**c, "global": False, "ocurrencias": 1}

        if orig in vistos:
            no.append({**c, "rechazo": "duplicado"}); continue
        if n_paginas and isinstance(pag, int) and not (1 <= pag <= n_paginas):
            no.append({**c, "rechazo": f"página {pag} fuera de rango"}); continue
        vistos.add(orig)
        ok.append(c)
    return ok, no


def validar_paginas(items, n_paginas, campo="pagina"):
    """Descarta entradas que citen una página inexistente."""
    if not n_paginas:
        return [{**i, campo: None} for i in items], 0
    ok, fuera = [], 0
    for i in items:
        p = i.get(campo)
        if isinstance(p, int) and 1 <= p <= n_paginas:
            ok.append(i)
        elif p is None:
            ok.append(i)
        else:
            fuera += 1
    return ok, fuera


def cargar_mapa(nombre):
    ruta = MAPAS / f"mapa_{Path(nombre).stem}.json"
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  aviso: mapa de {nombre} no parsea ({e}); sigue sin él")
        return None


def construir(nombre, texto, mapa):
    pre, paginas = partir_en_paginas(texto)
    paginado = bool(paginas)
    n_pag = len(paginas) if paginado else 0

    meta = {k: (m.group(1) if (m := rx.search(pre)) else None) for k, rx in RE_META.items()}

    correcciones, rechazadas = [], []
    secciones, puntos, cifras, hallazgos = [], [], [], []
    titulo_real = resumen = None
    fuera_de_rango = 0

    if mapa:
        titulo_real = mapa.get("titulo_real")
        resumen = mapa.get("resumen")
        correcciones, rechazadas = filtrar_correcciones(
            mapa.get("correcciones_ocr", []), texto, n_pag
        )
        secciones, f1 = validar_paginas(mapa.get("secciones", []), n_pag)
        puntos, f2 = validar_paginas(mapa.get("puntos_clave", []), n_pag)
        cifras, f3 = validar_paginas(mapa.get("cifras_dudosas", []), n_pag)
        fuera_de_rango = f1 + f2 + f3
        hallazgos = mapa.get("hallazgos", [])

    def corregir(t):
        for c in correcciones:
            t = t.replace(c["original"], c["corregido"])
        return t

    p = ['<?xml version="1.0" encoding="UTF-8"?>',
         f'<corfo_document id="{attr(Path(nombre).stem)}">']

    p.append("  <provenance>")
    p.append(f"    <derived_from_file>{attr(nombre)}</derived_from_file>")
    p.append(f"    <derived_from_sha256>{sha256(texto)}</derived_from_sha256>")
    if meta["archivo_fuente"]:
        p.append(f'    <original_pdf sha256="unknown" reason="pdf no versionado en el repositorio">'
                 f'{attr(meta["archivo_fuente"])}</original_pdf>')
    else:
        p.append('    <original_pdf sha256="unknown" reason="el markdown fuente no declara su pdf de origen"/>')
    p.append(f'    <extraction_method>{attr(meta["metodo"] or "unknown")}</extraction_method>')
    p.append(f"    <authority_warning>{attr(ADVERTENCIA)}</authority_warning>")
    p.append("    <verification_status>")
    p.append("      <xml_structure>validated</xml_structure>")
    p.append(f'      <ocr_corrections_applied>{len(correcciones)}</ocr_corrections_applied>')
    p.append(f'      <ocr_corrections_rejected>{len(rechazadas)}</ocr_corrections_rejected>')
    p.append("      <numbers_never_corrected>true</numbers_never_corrected>")
    p.append("      <content_visually_checked>false</content_visually_checked>")
    p.append("    </verification_status>")
    p.append("  </provenance>")

    if titulo_real:
        p.append(f'  <title source="read_by_llm">{cdata(titulo_real)}</title>')
    if resumen:
        p.append(f"  <summary>{cdata(resumen)}</summary>")

    if secciones:
        p.append(f'  <index entries="{len(secciones)}" note="mapa de lectura; los number remiten a la página del PDF">')
        for s in secciones:
            pg = f' page="{s["pagina"]}"' if isinstance(s.get("pagina"), int) else ""
            p.append(f'    <entry type="{attr(s.get("tipo", "seccion"))}"{pg}>')
            p.append(f'      <heading>{cdata(s.get("titulo", ""))}</heading>')
            if s.get("de_que_trata"):
                p.append(f'      <about>{cdata(s["de_que_trata"])}</about>')
            p.append("    </entry>")
        p.append("  </index>")

    if puntos:
        p.append(f'  <key_points count="{len(puntos)}">')
        for k in puntos:
            pg = f' page="{k["pagina"]}"' if isinstance(k.get("pagina"), int) else ""
            p.append(f'    <point type="{attr(k.get("tipo", "otro"))}"{pg}>')
            p.append(f'      <text>{cdata(k.get("texto", ""))}</text>')
            if k.get("por_que_importa"):
                p.append(f'      <why>{cdata(k["por_que_importa"])}</why>')
            p.append("    </point>")
        p.append("  </key_points>")

    if cifras:
        p.append(f'  <figures_to_check count="{len(cifras)}" note="el OCR las dejó dudosas; NO se corrigieron. Ir al PDF.">')
        for c in cifras:
            pg = f' page="{c["pagina"]}"' if isinstance(c.get("pagina"), int) else ""
            p.append(f"    <figure{pg}>")
            p.append(f'      <as_read>{cdata(c.get("texto", ""))}</as_read>')
            if c.get("que_pasa"):
                p.append(f'      <problem>{cdata(c["que_pasa"])}</problem>')
            p.append("    </figure>")
        p.append("  </figures_to_check>")

    if paginado:
        decl = meta["paginas"] or "unknown"
        p.append(f'  <pages count="{len(paginas)}" declared_in_source="{attr(decl)}">')
        for numero, delim, cuerpo in paginas:
            p.append(f'    <page number="{numero}">')
            p.append(f"      <source_delimiter>{cdata(delim)}</source_delimiter>")
            p.append(f"      <content>{cdata(corregir(cuerpo))}</content>")
            p.append("    </page>")
        p.append("  </pages>")
        p.append(f"  <source_preamble>{cdata(pre)}</source_preamble>")
    else:
        p.append("  <page_status>not_available</page_status>")
        p.append("  <page_status_reason>El markdown fuente no contiene fronteras de "
                 "página verificables. No se fabrican números; usar el índice.</page_status_reason>")
        p.append(f"  <body>{cdata(corregir(texto))}</body>")

    p.append(f'  <ocr_corrections applied="{len(correcciones)}" rejected="{len(rechazadas)}" '
             'note="cada corrección es una palabra; ninguna toca un dígito. El texto original '
             'se recupera invirtiendo esta lista.">')
    for c in correcciones:
        pg = f' page="{c["pagina"]}"' if isinstance(c.get("pagina"), int) else ""
        p.append(f'    <correction confidence="{attr(c.get("confianza", "media"))}"{pg}>')
        p.append(f'      <from>{cdata(c["original"])}</from>')
        p.append(f'      <to>{cdata(c["corregido"])}</to>')
        if c.get("motivo"):
            p.append(f'      <why>{cdata(c["motivo"])}</why>')
        p.append("    </correction>")
    for r in rechazadas:
        p.append(f'    <rejected reason="{attr(r["rechazo"])}">{cdata(str(r.get("original", ""))[:200])}</rejected>')
    p.append("  </ocr_corrections>")

    p.append("</corfo_document>")

    return {
        "xml": "\n".join(p) + "\n",
        "paginado": paginado,
        "paginas": n_pag or None,
        "paginas_declaradas": int(meta["paginas"]) if meta["paginas"] else None,
        "metodo": meta["metodo"] or "unknown",
        "pdf": meta["archivo_fuente"],
        "mapa_presente": mapa is not None,
        "correcciones": correcciones,
        "rechazadas": rechazadas,
        "secciones": len(secciones),
        "puntos": len(puntos),
        "cifras": len(cifras),
        "hallazgos": hallazgos,
        "fuera_de_rango": fuera_de_rango,
        "titulo": titulo_real,
    }


def texto_desde_xml(xml_texto):
    """Reconstruye el texto CORREGIDO tal como quedó en el derivado."""
    raiz = ET.fromstring(xml_texto)
    pages = raiz.find("pages")
    if pages is None:
        return raiz.find("body").text or ""
    trozos = [raiz.find("source_preamble").text or ""]
    for pg in pages.findall("page"):
        trozos.append(pg.find("source_delimiter").text or "")
        trozos.append(pg.find("content").text or "")
    return "".join(trozos)


def buscar_secretos(texto, nombre):
    patrones = {
        "clave_privada": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "token_supabase": r"\bsbp_[a-zA-Z0-9]{20,}",
        "jwt": r"\bey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
        "aws": r"\bAKIA[0-9A-Z]{16}\b",
        "api_key": r"(?i)\b(api[_-]?key|secret|password|contraseña)\s*[:=]\s*\S{8,}",
        "correo_no_institucional": r"[\w.+-]+@(?!corfo\.cl|pasaelfiltro\.cl)[\w-]+\.[\w.]+",
    }
    return [{"archivo": nombre, "categoria": k, "ocurrencias": len(re.findall(rx, texto))}
            for k, rx in patrones.items() if re.findall(rx, texto)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verificar", action="store_true")
    args = ap.parse_args()

    presentes = {p.name for p in FUENTE.glob("*.md")} - EXCLUIDOS
    if faltan := set(DOCUMENTOS) - presentes:
        sys.exit(f"faltan fuentes declaradas: {sorted(faltan)}")
    if sobran := presentes - set(DOCUMENTOS):
        sys.exit(f"markdown no declarados: {sorted(sobran)}. Actualizá las listas a propósito.")

    if not args.verificar:
        DESTINO.mkdir(exist_ok=True)

    man = {
        "generado_por": "tools/generar_xml_corfo.py",
        "issue": "https://github.com/PasaElFiltro/pasaelfiltro/issues/288",
        "advertencia_de_autoridad": ADVERTENCIA,
        "regla_dura": "Ninguna corrección de OCR toca un dígito. Verificado por código, "
                      "no por confianza en el modelo: las propuestas con dígitos se rechazan.",
        "documentos": [],
    }
    secretos, fallos = [], []

    for nombre in DOCUMENTOS:
        ruta = FUENTE / nombre
        texto = ruta.read_text(encoding="utf-8")
        r = construir(nombre, texto, cargar_mapa(nombre))
        xml_texto = r["xml"]

        try:
            ET.fromstring(xml_texto); parsea = True
        except ET.ParseError as e:
            parsea = False; fallos.append(f"{nombre}: XML no parsea — {e}")

        # El derivado debe diferir del fuente SÓLO en las correcciones declaradas.
        esperado = texto
        for c in r["correcciones"]:
            esperado = esperado.replace(c["original"], c["corregido"])
        fiel = parsea and texto_desde_xml(xml_texto) == esperado
        if parsea and not fiel:
            fallos.append(f"{nombre}: el contenido difiere del fuente más allá de las correcciones declaradas")

        # Cinturón y tiradores: que ninguna corrección haya alterado un dígito.
        # Se recomprueba acá, sobre lo que realmente se aplicó, y no sólo en la
        # aduana — la garantía que le prometemos a quien lee esto es lo bastante
        # cara como para verificarla dos veces por caminos distintos.
        if any(RE_DIGITO.findall(c["original"]) != RE_DIGITO.findall(c["corregido"])
               for c in r["correcciones"]):
            fallos.append(f"{nombre}: se coló una corrección que altera dígitos")
        if RE_DIGITO.findall(texto) != RE_DIGITO.findall(texto_desde_xml(xml_texto) if parsea else texto):
            fallos.append(f"{nombre}: la secuencia de dígitos del derivado no es "
                          "idéntica a la del fuente")

        if r["paginado"] and r["paginas_declaradas"] and r["paginas"] != r["paginas_declaradas"]:
            fallos.append(f"{nombre}: {r['paginas']} páginas verificables vs {r['paginas_declaradas']} declaradas")

        secretos += buscar_secretos(texto, nombre)
        destino = DESTINO / (Path(nombre).stem + ".xml")
        if not args.verificar:
            destino.write_text(xml_texto, encoding="utf-8")

        man["documentos"].append({
            "fuente": nombre,
            "fuente_sha256": sha256(texto),
            "derivado": destino.name,
            "derivado_sha256": sha256(xml_texto),
            "titulo_leido": r["titulo"],
            "pdf_original": r["pdf"],
            "pdf_original_sha256": None,
            "metodo_extraccion": r["metodo"],
            "paginas_verificables": r["paginas"],
            "leido_por_haiku": r["mapa_presente"],
            "entradas_de_indice": r["secciones"],
            "puntos_clave": r["puntos"],
            "cifras_a_cotejar": r["cifras"],
            "correcciones_aplicadas": len(r["correcciones"]),
            "correcciones_rechazadas": len(r["rechazadas"]),
            "referencias_a_pagina_inexistente_descartadas": r["fuera_de_rango"],
            "hallazgos": r["hallazgos"],
            "xml_valido": parsea,
            "solo_difiere_en_correcciones_declaradas": fiel,
        })

    d = man["documentos"]
    man["resumen"] = {
        "documentos": len(d),
        "leidos_por_haiku": sum(1 for x in d if x["leido_por_haiku"]),
        "paginas_verificables_totales": sum(x["paginas_verificables"] or 0 for x in d),
        "entradas_de_indice": sum(x["entradas_de_indice"] for x in d),
        "puntos_clave": sum(x["puntos_clave"] for x in d),
        "cifras_a_cotejar": sum(x["cifras_a_cotejar"] for x in d),
        "correcciones_aplicadas": sum(x["correcciones_aplicadas"] for x in d),
        "correcciones_rechazadas": sum(x["correcciones_rechazadas"] for x in d),
        "xml_validos": sum(1 for x in d if x["xml_valido"]),
        "fieles": sum(1 for x in d if x["solo_difiere_en_correcciones_declaradas"]),
        "hallazgos_de_barrido": secretos,
    }

    if not args.verificar:
        (DESTINO / "MANIFEST.json").write_text(
            json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(man["resumen"], ensure_ascii=False, indent=2))
    if fallos:
        print("\nFALLOS:"); [print(" -", f) for f in fallos]; sys.exit(1)
    print("\nOK.")


if __name__ == "__main__":
    main()
