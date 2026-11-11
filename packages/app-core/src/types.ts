export type Point = readonly [number, number];
export type Units = "m" | "cm" | "mm" | "ft" | "in";
export type OpeningKind = "door" | "window";

export interface Opening { readonly id: string; readonly kind: OpeningKind; readonly offset: number; readonly width: number; readonly height: number; readonly sill: number }
export interface Wall {
  readonly id: string; readonly level_id: string; readonly start: Point; readonly end: Point;
  readonly thickness: number; readonly height: number; readonly material: string;
  readonly properties: Readonly<Record<string, unknown>>; readonly openings: readonly Opening[];
}
export interface Level { readonly id: string; readonly name: string; readonly elevation: number; readonly height: number }
export interface Room { readonly id: string; readonly name: string; readonly level_id: string; readonly boundary: readonly Point[]; readonly target_area: number | null }
export interface Project { readonly name: string; readonly units: Units; readonly levels: readonly Level[]; readonly walls: readonly Wall[]; readonly rooms: readonly Room[] }

export interface ApiState { readonly revision: number; readonly project: Project; readonly label: string | null; readonly result: Readonly<Record<string, unknown>> | null }
export interface MeshElement {
  readonly id: string; readonly type: "wall" | "opening"; readonly level_id: string;
  readonly wall_id: string | null; readonly kind: OpeningKind | null;
  readonly positions: readonly number[]; readonly indices: readonly number[];
}
export interface MeshData { readonly revision: number; readonly units: string; readonly elements: readonly MeshElement[] }
export interface ToolInfo { readonly name: string; readonly write: boolean; readonly required: readonly string[]; readonly optional: readonly string[] }
