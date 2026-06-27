import { parsePGMAndYAML } from './mapImporter';

interface OccupancyGrid {
  header: {
    frame_id: string;
    stamp: { sec: number; nsec: number };
  };
  info: {
    map_load_time: { sec: number; nsec: number };
    resolution: number;
    width: number;
    height: number;
    origin: {
      position: { x: number; y: number; z: number };
      orientation: { x: number; y: number; z: number; w: number };
    };
  };
  data: number[] | Int8Array;
}

/**
 * Load a static map from a YAML descriptor and its referenced PGM image.
 *
 * @param yamlUrl  URL to the .yaml file (e.g. "/maps/707.yaml")
 * @returns        Parsed OccupancyGrid (frame_id = 'map')
 */
export async function loadStaticMap(yamlUrl: string): Promise<OccupancyGrid> {
  // 1. Fetch YAML
  const yamlResp = await fetch(yamlUrl);
  if (!yamlResp.ok) {
    throw new Error(`[StaticMapLoader] Failed to fetch YAML: ${yamlUrl} (${yamlResp.status})`);
  }
  const yamlText = await yamlResp.text();

  // 2. Resolve PGM path relative to YAML URL
  const yamlBase = yamlUrl.substring(0, yamlUrl.lastIndexOf('/') + 1);
  const imageMatch = yamlText.match(/^image:\s*(.+)$/m);
  if (!imageMatch) {
    throw new Error('[StaticMapLoader] No "image:" field found in YAML');
  }
  const imagePath = imageMatch[1]!.trim();
  const pgmUrl = imagePath.startsWith('./')
    ? yamlBase + imagePath.slice(2)
    : imagePath.startsWith('/')
      ? imagePath
      : yamlBase + imagePath;

  // 3. Fetch PGM
  const pgmResp = await fetch(pgmUrl);
  if (!pgmResp.ok) {
    throw new Error(`[StaticMapLoader] Failed to fetch PGM: ${pgmUrl} (${pgmResp.status})`);
  }
  const pgmBuffer = await pgmResp.arrayBuffer();

  // 4. Parse
  return parsePGMAndYAML(new Uint8Array(pgmBuffer), yamlText);
}
