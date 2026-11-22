# Rediseño profesional MapLibre y DialogueVPR

## Skills y herramientas

Se consultó el directorio verificable `skills.sh`:

- `anthropics/skills/frontend-design`: 1,1 M instalaciones, repositorio Anthropic
  con 195 k estrellas y auditorías Trust Hub, Socket y Snyk aprobadas.
- `vercel-labs/agent-skills/web-design-guidelines`: 869 k instalaciones,
  repositorio Vercel con 34 k estrellas; Trust Hub/Snyk aprobados y advertencia
  Socket por descargar las guidelines actuales.
- `vercel-react-best-practices`: no aplicable porque el frontend es JavaScript
  vanilla/Vite, no React.

No se instalaron skills ni scripts remotos. Se aplicaron directamente sus pautas
revisadas: dirección visual deliberada, composición cartográfica, jerarquía,
accesibilidad, estados reales, reduced motion y responsive. Chromium/CDP y los
fixtures locales existentes sustituyen Playwright sin añadir dependencias.

## Sistema visual

- Mapa: 65–75 % de escritorio; medición Chromium final fake 70,9 %.
- Panel lateral: 350–410 px, scroll independiente y composer sticky.
- Paleta sobria verde/cartográfica, superficies blancas y sombras contenidas.
- Radios 7–20 px según jerarquía, tipografía Inter del proyecto y escalas
  compactas adecuadas para aplicación, no landing page.
- Ranking compacto horizontal de cinco columnas visibles y selección sincronizada.
- Móvil: mapa a viewport completo y panel como bottom sheet sobrepuesto.

## Modal de progreso

Se usa `<dialog>` nativo:

- focus trap e inert proporcionados por el navegador;
- Escape cancelado y sin cierre por backdrop;
- sin botón cancelar porque backend no ofrece cancelación segura;
- indicador indeterminado, nunca porcentajes ficticios;
- etapas Qwen, CrossText2Loc y persistencia basadas en eventos reales;
- cierre únicamente en `waiting_user`, `completed`, `failed` o `unknown` global;
- reconexión GET/SSE mantiene el modal mientras el estado siga running/pending;
- foco restaurado al control previo al cerrar.

## DialogueVPR

- Chat con preguntas y respuestas diferenciadas.
- Indicador pregunta N de 3 sin afirmar que siempre habrá tres.
- Textarea autoajustable.
- Enter envía; Shift+Enter inserta salto; composición IME respetada.
- Doble envío bloqueado por estado/modal e idempotencia.
- Borrador conservado ante reconciliación ambigua sin avance durable.
- Último ranking válido permanece ante fallos posteriores.

## Pruebas visuales

- [Estado inicial escritorio](screenshots/integrated-app-initial-desktop-v2.png).
- [Modal de progreso escritorio](screenshots/integrated-app-progress-modal-v2.png).
- [DialogueVPR móvil](screenshots/integrated-app-dialogue-mobile-v2.png).

Las capturas usan API fake identificada y no son resultados científicos. Chromium
validó modal/foco, proporción 70,9/29,1, mapa/panel móvil, composer y ausencia de
overflow. Este agente no puede revisar píxeles; queda recomendada revisión estética
humana desde Windows.
