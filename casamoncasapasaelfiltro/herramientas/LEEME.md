# Cómo se generaron los XML

`generar_xml_corfo.py` es el script que armó `documentos/`. Está acá para que se
vea el método, no para correrlo tal cual: necesita los Markdown fuente, que viven
en el repositorio de PasaElFiltro y no se copiaron acá.

Lo que hace, en corto:

1. Parte cada documento por sus fronteras de página, exigiendo que el comentario
   `<!-- página PDF N -->` y el encabezado `## Página N` digan el mismo número.
2. Toma el mapa que produjo un Haiku por documento (índice, puntos clave,
   correcciones de OCR) y **lo revalida entero contra el texto fuente** antes de
   aplicar nada.
3. Escribe el XML y el manifiesto con los SHA-256.

Los tres filtros que aplica a cada corrección propuesta están explicados en
`../VERIFICACION_LECTURA.md`. El más importante: la secuencia de dígitos del
documento corregido tiene que ser idéntica a la del original, comprobado por dos
caminos distintos. Ningún número se corrige nunca.
