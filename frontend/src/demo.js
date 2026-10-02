// Fixtures deliberadamente sintéticos: no son predicciones ni evaluaciones reales.
export const places = [
  { id: 'sol', name: 'Puerta del Sol', area: 'Sol · Distrito Centro', region: 'centro', lat: 40.4169, lon: -3.7035, kind: 'Plaza urbana', features: ['Plaza', 'Reloj', 'Edificio histórico'], terms: ['reloj', 'oso', 'sol', 'kilometro'], score: 0.87, graph: 0.79, color: '#bc8872', visual: 'clock', evidence: ['Plaza abierta y espacio peatonal', 'Reloj en el edificio de la escena'], unknown: 'La orientación de «a mi derecha» sigue sin conocerse.' },
  { id: 'mayor', name: 'Plaza Mayor', area: 'Palacio · Distrito Centro', region: 'centro', lat: 40.4154, lon: -3.7074, kind: 'Plaza porticada', features: ['Plaza', 'Soportales', 'Estatua'], terms: ['soportal', 'portic', 'estatua', 'roj', 'mayor'], score: 0.81, graph: 0.89, color: '#b67563', visual: 'arches', evidence: ['Edificios rodeando una plaza', 'Soportales y estatua en la escena'], unknown: 'Los detalles de la fachada no se han verificado con fotografías.' },
  { id: 'villa', name: 'Plaza de la Villa', area: 'Palacio · Distrito Centro', region: 'centro', lat: 40.4154, lon: -3.7108, kind: 'Conjunto histórico', features: ['Plaza', 'Torre', 'Ladrillo'], terms: ['torre', 'ladrillo', 'villa', 'historic'], score: 0.73, graph: 0.83, color: '#caa788', visual: 'tower', evidence: ['Entorno de plaza con arquitectura histórica', 'Torre en la escena ilustrativa'], unknown: 'La visibilidad desde la posición del usuario no está comprobada.' },
  { id: 'oriente', name: 'Plaza de Oriente', area: 'Palacio · Distrito Centro', region: 'centro', lat: 40.4183, lon: -3.7122, kind: 'Jardín urbano', features: ['Jardín', 'Palacio', 'Estatua'], terms: ['palacio', 'jardin', 'oriente'], score: 0.69, graph: 0.74, color: '#b9a68b', visual: 'arches', evidence: ['Espacio ajardinado junto a un palacio', 'Estatuas como pista de la escena'], unknown: 'No hay imágenes reales asociadas a este ejemplo.' },
  { id: 'retiro', name: 'Estanque del Retiro', area: 'Jerónimos · Retiro', region: 'retiro', lat: 40.4173, lon: -3.6835, kind: 'Parque y estanque', features: ['Parque', 'Estanque', 'Monumento'], terms: ['parque', 'estanque', 'barca', 'retiro', 'agua'], score: 0.91, graph: 0.84, color: '#9eaf8d', visual: 'park', evidence: ['Estanque y zona verde', 'Monumento al fondo de la escena'], unknown: 'No se conoce el lado del estanque desde el que mira el usuario.' },
  { id: 'olavide', name: 'Plaza de Olavide', area: 'Trafalgar · Chamberí', region: 'chamberi', lat: 40.4327, lon: -3.7015, kind: 'Plaza de barrio', features: ['Plaza', 'Árboles', 'Terrazas'], terms: ['terraza', 'arbol', 'olavide', 'chamberi'], score: 0.83, graph: 0.87, color: '#bb977d', visual: 'park', evidence: ['Plaza con árboles', 'Terrazas en el escenario de ejemplo'], unknown: 'La distribución actual de las terrazas no está verificada.' },
];
export const examples = [
  { label: 'Una plaza con reloj', region: 'centro', text: 'Estoy en una plaza peatonal bastante amplia. Veo un edificio de color claro con un reloj en lo alto y muchas calles que salen de la plaza.' },
  { label: 'Soportales y una estatua', region: 'centro', text: 'Estoy en una plaza rodeada de edificios rojizos con soportales. En el centro hay una estatua de una persona a caballo.' },
  { label: 'Un estanque en el parque', region: 'retiro', text: 'Estoy en un parque y delante de mí hay un estanque con barcas. Al otro lado veo un monumento grande rodeado de columnas.' },
];
export const normalize = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
export function simulateSearch(text, region, model, topK = 3) {
  const query = normalize(text);
  const pool = places.filter(p => region === 'madrid' || p.region === region);
  const known = /plaza|reloj|torre|iglesia|parque|estanque|edificio|soportal|estatua|palacio|jardin|terraza|arbol|barca|monumento/.test(query);
  if (!known) return [];
  return pool.map(p => ({ ...p, value: Math.min(0.98, (model === 'gotpr' ? p.graph : p.score) + (p.terms.some(t => query.includes(t)) ? 0.09 : -0.12)) }))
    .sort((a, b) => b.value - a.value).slice(0, topK);
}
export function extractClues(text) {
  const query = normalize(text);
  return [['plaza', 'Plaza'], ['reloj', 'Reloj'], ['torre', 'Torre'], ['iglesia', 'Iglesia'], ['parque', 'Parque'], ['estanque', 'Estanque'], ['soportal', 'Soportales'], ['estatua', 'Estatua'], ['edificio', 'Edificio'], ['roj', 'Fachada rojiza'], ['derecha', 'A la derecha · orientación pendiente']].filter(([term]) => query.includes(term)).map(([, label]) => label);
}
export const regionNames = { madrid: 'Madrid', centro: 'Distrito Centro', retiro: 'Retiro', chamberi: 'Chamberí' };
