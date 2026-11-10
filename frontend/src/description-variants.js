export function validateDescriptionVariantManifest(manifest){
  if(manifest?.contract_version!=='description-length-experiments-v1'||manifest.variant_count!==24||manifest.condition_count!==48||!Array.isArray(manifest.scope_query_ids)||!Array.isArray(manifest.variants))throw new TypeError('Manifest de longitudes incompatible.');
  return manifest;
}
export const getDescriptionVariant=(manifest,queryId,length)=>manifest?.variants?.find(row=>row.source_query_id===queryId&&row.length===length)||null;
export function experimentalSessionId(queryId,length){
  if(!/^H(?:26|27|28|29|31|33|36|37)$/.test(queryId)||!['short','medium','long'].includes(length))throw new TypeError('Variante experimental inválida.');
  return `X-${queryId}-${length}`;
}
