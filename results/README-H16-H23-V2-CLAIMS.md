# Claims aprobados H16/H23 v2

El conjunto humano congelado contiene 29 claims aprobados para el protocolo v2.
La exportación recibida se conserva fuera de Git bajo `results/generated/` y se
importó mediante validación estricta y copia histórica.

Omisiones conocidas del extractor, no añadidas para evitar cambiar el conjunto
ya revisado:

- H16: atributo `gold` de las paredes.
- H16: `religious figures` como objeto o conjunto visible.

Estas omisiones limitan cobertura semántica, pero no invalidan los 29 claims
aprobados. Una futura versión del extractor deberá crear claims nuevos y migrar
solo decisiones semánticamente equivalentes de forma auditable.
