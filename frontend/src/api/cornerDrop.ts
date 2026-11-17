import { buildUrl, request } from "./client";
export interface DropMethod { id: string; code: string; title: string; experimental: boolean; }
export interface ShapeMethod { id: string; label: string; family: string; extra_dynamic_runs: number; }
export interface DropSettings { available: boolean; reason: string | null; can_execute: boolean; methods: DropMethod[]; shape_methods?: ShapeMethod[]; presets: string[]; max_runtime_s: number; }
export interface ShapeRegion { tests:number; passed:number; worst_field_l2:number|null; worst_peak_rms_error:number|null; direction_agreement:number|null; recommended_in_region:boolean; }
export interface ShapeResult { scope:string; methods:string[]; baseline:Record<string,unknown>; summary?:Record<string,{label:string;regions:{small:ShapeRegion;extended:ShapeRegion};extra_calibration_drops:number}>; }
export interface LegacyResult { baseline: { peak_rms_mm: number }; methods: MethodResult[]; actual_drops: number; scope: string; }
export interface MethodResult { method: string; code?: string; status: string; error?: string; predicted_mm?: number; actual_mm?: number; improvement_fraction?: number; plastic_p95?: number; mass_ratio?: number; accepted?: boolean; holdout_spearman?: number | null; }
export interface DropRun {
  id: string; project_id: string; method: string; preset: string; created_at: number; alive: boolean;
  progress: { status: string; stage?: string; message?: string; error?: string; completed?: number; total?: number; };
  result: LegacyResult | ShapeResult | null;
}
const base = (project: string) => `/projects/${encodeURIComponent(project)}/corner-drop`;
export const cornerDrop = {
  settings: (p: string) => request<DropSettings>("GET", `${base(p)}/settings`),
  runs: (p: string) => request<DropRun[]>("GET", `${base(p)}/runs`),
  start: (p: string, method: string, preset: string) => request<DropRun>("POST", `${base(p)}/runs`, { body: { method, preset } }),
  cancel: (p: string, id: string) => request("POST", `${base(p)}/runs/${id}/cancel`),
  file: (p: string, id: string, name: string) => buildUrl(`${base(p)}/runs/${id}/files/${encodeURIComponent(name)}`),
};
