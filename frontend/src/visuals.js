export function icon(name, size = 20) {
  const paths = {
    compass: '<path d="m16.5 7.5-3 6-6 3 3-6 6-3Z"/><circle cx="12" cy="12" r="9"/>',
    pin: '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    layers: '<path d="m12 3 10 6-10 6L2 9l10-6Zm-9 11 9 5 9-5M3 18l9 5 9-5"/>',
    compare: '<path d="M8 3v18M16 3v18M3 7h10m-3-3 3 3-3 3m11 7H11m3-3-3 3 3 3"/>',
    history: '<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7m2-5v6l4 2"/>',
    settings: '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2" fill="currentColor"/><circle cx="16" cy="12" r="2" fill="currentColor"/><circle cx="10" cy="18" r="2" fill="currentColor"/>',
    chevron: '<path d="m9 5 7 7-7 7"/>',
    down: '<path d="m6 9 6 6 6-6"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
    spark: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',
    close: '<path d="m6 6 12 12M6 18 18 6"/>',
    download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>', minus: '<path d="M5 12h14"/>',
    target: '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 1v4m0 14v4M1 12h4m14 0h4"/>',
    chat: '<path d="M21 11a9 9 0 0 1-9 9H4l-3 2 2-7a9 9 0 1 1 18-4Z"/><path d="M7 9h10M7 13h6"/>',
    eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
    copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M15 8V3H3v13h5"/>',
    book: '<path d="M3 4h6l3 3 3-3h6v15h-6l-3 2-3-2H3V4Zm9 3v14"/>',
  };
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.pin}</svg>`;
}
export function scene(place, suffix = '') {
  const windows = Array.from({ length: 12 }, (_, i) => `<rect x="${34 + (i % 6) * 42}" y="${91 + Math.floor(i / 6) * 34}" width="13" height="20" rx="1" fill="#4c615d" opacity=".72"/>`).join('');
  const arches = Array.from({ length: 7 }, (_, i) => `<path d="M${22 + i * 42} 199v-29a12 12 0 0 1 24 0v29" fill="#52645c"/>`).join('');
  const trees = '<g fill="#819a70"><circle cx="39" cy="151" r="35"/><circle cx="267" cy="145" r="44"/></g><path d="M39 160v57m228-67v67" stroke="#6d7960" stroke-width="6"/>';
  return `<svg class="scene" viewBox="0 0 320 240" role="img" aria-label="Ilustración de ${place.name}"><defs><linearGradient id="sky-${place.id}-${suffix}" x2="0" y2="1"><stop stop-color="#c6d9d5"/><stop offset="1" stop-color="#eef0df"/></linearGradient></defs><rect width="320" height="240" fill="url(#sky-${place.id}-${suffix})"/><circle cx="257" cy="45" r="22" fill="#fff8dc" opacity=".8"/><path d="M0 187h320v53H0Z" fill="#d5cfba"/><path d="m0 240 100-43m220 43-100-43M0 221h320" stroke="#b5b49f" opacity=".5"/><path d="M17 76h284v123H17Z" fill="${place.color}"/><path d="m9 76 19-18h261l20 18Z" fill="#65746c"/>${windows}${arches}${place.visual === 'clock' ? '<path d="M135 63V31h50v32" fill="#d7bea0"/><path d="m130 32 30-18 30 18Z" fill="#64716b"/><circle cx="160" cy="46" r="11" fill="#faf5df" stroke="#686c60"/><path d="M160 39v7l5 3" stroke="#596259" fill="none"/>' : ''}${place.visual === 'tower' ? '<path d="M221 199V41h51v158" fill="#b79473"/><path d="m215 41 31-31 32 31Z" fill="#66736b"/><path d="M235 68h22v27h-22Z" fill="#52645c"/>' : ''}${place.visual === 'park' ? trees + '<ellipse cx="165" cy="222" rx="87" ry="16" fill="#8eb6b2"/>' : '<path d="M150 230v-19h20v19m-15-19v-15h10v15" fill="#77847a"/>'}<g fill="#485b55"><circle cx="73" cy="213" r="3"/><path d="M73 216v13m-3-7h6" stroke="#485b55"/><circle cx="250" cy="211" r="3"/><path d="M250 214v12m-3-7h6" stroke="#485b55"/></g></svg>`;
}

export function mapArtwork() {
  let blocks = '';
  for (let row = 0; row < 13; row++) for (let col = 0; col < 17; col++) {
    const x = col * 62 + 6 + (row % 2) * 10, y = row * 54 + 8;
    const shade = ['#dfdfd2', '#e3e3d9', '#dedfd5', '#e7e5d9'][(row * 3 + col) % 4];
    blocks += `<rect x="${x}" y="${y}" width="${40 + (col % 3) * 4}" height="${32 + (row % 3) * 3}" rx="4" fill="${shade}" stroke="#d6d8cd" stroke-width=".7"/>`;
  }
  const roads = ['M-30 162C180 143 240 234 435 185S710 161 1040 90', 'M290-30C284 114 373 228 425 330S490 493 549 760', 'M-20 477C233 510 300 355 489 387S756 352 1040 399', 'M585-20C554 124 637 260 700 330S738 555 838 740', 'M-20 315C134 286 267 306 395 279S744 249 1050 232', 'M137-30C182 98 132 286 178 414S280 593 231 740', 'M-20 627C149 576 263 630 431 564S788 511 1060 547'];
  return `<svg viewBox="0 0 1050 720" preserveAspectRatio="none" class="city-map" aria-hidden="true"><rect width="1050" height="720" fill="#efefe7"/>${blocks}<path d="M791 292 1015 277 1030 626 839 646 776 495Z" fill="#d3dfbf" stroke="#c5d4b0"/><path d="M821 316 989 304m-156 35 156-11m-147 36 147-11m-137 41 137-16M871 304l23 301m40-307 12 301" stroke="#edf0d9" stroke-width="7"/><rect x="893" y="388" width="55" height="115" rx="5" fill="#b4d1cd" transform="rotate(-5 920 430)"/><path d="M37 237 118 224 129 365 48 379Z" fill="#d4dfc2"/>${roads.map(d => `<path d="${d}" fill="none" stroke="#d2d4c9" stroke-width="18"/><path d="${d}" fill="none" stroke="#fffef5" stroke-width="14"/>`).join('')}<path d="m349 402 73-25 34 32-85 35Z" fill="#e5decd" stroke="#cdcbb9"/><ellipse cx="483" cy="350" rx="51" ry="21" fill="#e5decd" transform="rotate(-12 483 350)"/><g fill="#919b91" font-family="Arial,sans-serif" font-size="13" letter-spacing="3"><text x="390" y="125">MALASAÑA</text><text x="647" y="145">CHUECA</text><text x="259" y="307">PALACIO</text><text x="442" y="315">SOL</text><text x="573" y="460">LAS LETRAS</text><text x="407" y="600">LAVAPIÉS</text><text x="121" y="529">LA LATINA</text><text x="837" y="570" fill="#849574">EL RETIRO</text><text x="466" y="31">CHAMBERÍ</text></g><g fill="#a1a499" font-family="Arial,sans-serif" font-size="10"><text x="456" y="187" transform="rotate(-5 456 187)">Gran Vía</text><text x="593" y="266">Calle de Alcalá</text><text x="277" y="394" transform="rotate(-21 277 394)">Calle Mayor</text><text x="735" y="440" transform="rotate(73 735 440)">Paseo del Prado</text><text x="318" y="250" transform="rotate(60 318 250)">Calle de San Bernardo</text></g><g fill="#90a888" opacity=".7">${Array.from({ length: 25 }, (_, i) => `<circle cx="${799 + (i % 5) * 44}" cy="${323 + Math.floor(i / 5) * 65}" r="5"/>`).join('')}</g></svg>`;
}
