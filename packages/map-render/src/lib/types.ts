/** PoiPicker 的点位数据（与 deploy/seed/data/pois_*.yaml 行一一对应）。 */

export interface PoiPoint {
  name: string;
  category: string;
  floor: string; // B1 / F1 / F2
  x: number;
  y: number;
  hours: string; // "HH:MM-HH:MM"
  tags: string[];
  hot?: number;
  weight?: number;
}
