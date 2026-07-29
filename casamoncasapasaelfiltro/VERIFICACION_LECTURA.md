# Cómo se armó esto, y qué garantiza

*(Este archivo explica el método. Si sólo querés usar los documentos, con el LEEME alcanza.)*

Nueve instancias Haiku 4.5, una por documento, sin verse entre ellas. Cada una
leyó su documento entero y produjo tres cosas: el índice de secciones con su
página, los puntos clave (plazos, montos, porcentajes, requisitos, garantías), y
una lista de typos de OCR a corregir.

**Los haikus proponen; el código dispone.** Nada de lo que una instancia afirma
entra al archivo sin revalidarse contra el texto fuente. Se hizo así porque una
instancia que transcribe un documento de 49 páginas puede alterar algo sin que
nadie lo note nunca; una que propone cambios acotados y verificables, no.

## Lo que salió

| | |
|---|---|
| Documentos leídos | 9 de 9 |
| Entradas de índice | 174 |
| Puntos clave con su página | 126 |
| Correcciones de OCR aplicadas | 29 |
| Correcciones **rechazadas** por el filtro | 5 |
| Cifras dudosas marcadas para cotejar | 13 |
| Intentos de prompt injection | 0 |
| Datos personales o credenciales | 0 |

## Los tres filtros, y por qué existen

Los tres salieron de ver fallar a un haiku, no de imaginarlos.

**1. Ningún dígito cambia. Nunca.** La secuencia completa de dígitos del
documento corregido es idéntica, carácter por carácter, a la del original. Se
comprueba dos veces por caminos distintos. Nació porque una propuesta quería
reemplazar un número de trámite ilegible por `[número]` — o sea, borrar el dato.

Una corrección **puede** tener un número al lado (`plazt máximo de 10 días` →
`plazo máximo de 10 días`); lo que no puede es tocarlo.

**2. La corrección tiene que parecerse a lo que corrige.** Otra propuesta quería
cambiar `HS LES dechile` por `Boletín Oficial de la República de Chile`. Eso no
es arreglar un typo: es escribir un membrete entero que el modelo no puede saber,
y queda tan bien redactado que nadie lo notaría después. Si hay que escribir algo
muy distinto, es reconstrucción, y se rechaza.

**3. Tiene que existir.** El texto original debe aparecer literal en el
documento. Tres propuestas se cayeron acá: la instancia recordaba mal lo que
había leído.

Además se les prohibió tocar membretes, sellos, encabezados, pies y firmas. Ahí
está casi toda la basura de OCR, es irreconstruible, y no hace falta para nada.

**Lo rechazado no desaparece.** Va listado en `<ocr_corrections>` de cada archivo
con su motivo. Si querés ver qué se descartó y por qué, está a la vista.

## Qué NO garantiza

Que el texto sea fiel al PDF oficial. **Ninguna instancia cotejó contra el
original** — no lo tenemos. Lo que está garantizado es que el derivado no se
aparta del Markdown del que salió más allá de esas 29 correcciones, todas
listadas y todas reversibles.

El texto correcto se comprueba mirando el PDF de CORFO. Para eso están los
números de página y `<figures_to_check>`.

---

*29 de julio de 2026.*
