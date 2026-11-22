/** Abre un SSE efímero; la inferencia sigue usando el POST síncrono existente. */
export function openProgressStream(queryId, {
  baseUrl = '/api/v1',
  onEvent = () => {},
  onDisconnect = () => {},
  EventSourceImpl = globalThis.EventSource,
  connectTimeoutMs = 800,
} = {}) {
  let source = null;
  let timeout = null;
  let opened = false;
  let settled = false;
  let resolveReady;
  const ready = new Promise(resolve => { resolveReady = resolve; });
  const settleReady = value => {
    if (settled) return;
    settled = true;
    clearTimeout(timeout);
    resolveReady(value);
  };
  const close = () => {
    clearTimeout(timeout);
    source?.close();
    source = null;
    settleReady(false);
  };

  if (typeof EventSourceImpl !== 'function') {
    settleReady(false);
    onDisconnect(new Error('EventSource no está disponible en este navegador.'));
    return { ready, close };
  }

  const base = String(baseUrl || '/api/v1').replace(/\/$/, '');
  try {
    source = new EventSourceImpl(`${base}/progress/${encodeURIComponent(queryId)}`);
  } catch (error) {
    settleReady(false);
    onDisconnect(error);
    return { ready, close };
  }

  source.onopen = () => {
    opened = true;
    settleReady(true);
  };
  source.onmessage = message => {
    let event;
    try {
      event = JSON.parse(message.data);
    } catch (error) {
      onDisconnect(error);
      close();
      return;
    }
    onEvent(event);
    if (event.event_type === 'pipeline' && ['completed', 'failed'].includes(event.state)) close();
  };
  source.onerror = error => {
    onDisconnect(error);
    close();
  };
  timeout = setTimeout(() => {
    if (opened) return;
    onDisconnect(new Error('No se pudo abrir el canal SSE de progreso.'));
    close();
  }, connectTimeoutMs);

  return { ready, close };
}
