/** Human controls; no Agent loop, file access or model calls. */
import type { ExecutionMode } from './web_task_request.ts';
export type Scene = {
  id: string; label: string; preset: string; allowed_tools: string[];
  config_sha256?: string; instructions?: string;
  manifest?: string; task?: string; certified_input_sha256?: string;
  embedding_endpoint?: string; embedding_model?: string;
  diagnostic?: boolean; tool_schemas?: string; certified_tool_schemas?: any[]; certified_tool_schemas_sha256?: string;
  scenario?: string; scenario_version?: number; instructions_sha256?: string;
  unavailable_reason?: string; adapter?: 'ppt' | 'workspace' | 'files' | 'literature' | 'data-report';
  mcp_rows?: any[]; environment_references?: Record<string, string>;
  rsi_unavailable_reason?: string; matching_policy?: 'structural_only'; binding_policy?: 'ppt_uploaded_sources_v1' | 'uploaded_source_handles_v1' | 'approved_uploaded_reads_v1';
  certification_path?: string; certification_sha256?: string; certified_code_locks?: Record<string,string>;
  certification_scope?: string; quality_cost_promoted?: boolean;
  output_unavailable_reason?: string; renderer_root?: string; font_root?: string; runtime_file_locks?: Record<string,string>;
  paper_renderer_root?: string;
  pdf_toolchain_root?: string;
  certified_tool_schema_variants?: any[][];
  runtime_kind?: 'ppt_read_v1' | 'data_receipts_v3' | 'paper_shadow_v1';
  runtime_library?: string; runtime_library_sha256?: string; runtime_mode?: string; runtime_manifest_digest?: string;
};
export type Selection = { scene: string; mode: ExecutionMode; rsi: boolean };
const shortcutNames: Record<string, string> = { ppt: 'ppt', 'paper-proofreading': 'paper',
  'research-data-analysis': 'data', 'new-scene': 'chat' };
export function sceneShortcut(scene: Scene): string { return shortcutNames[scene.id] ?? scene.id; }
/** Only a leading, complete scene token is a control; paths and prose stay text. */
export function parseSceneShortcut(text: string, scenes: readonly Scene[]) {
  const match = /^\s*\/([a-z][a-z0-9_-]*)(?=\s|$|[^\x00-\x7F])/i.exec(text);
  const scene = match && scenes.find(row => sceneShortcut(row) === match[1].toLowerCase());
  return scene ? { scene: scene.id, text: text.slice(match![0].length).trimStart() } : undefined;
}
export class SettingsError extends Error {
  code: string;
  constructor(code: string, message: string) { super(message); this.code = code; }
}
export function sceneCatalog(rows: unknown): Scene[] {
  if (!Array.isArray(rows) || !rows.length || rows.length > 32) throw new SettingsError('invalid_registry', '场景登记表为空或过大');
  const ids = new Set(), presets = new Set();
  return rows.map(row => {
    if (!row || typeof row !== 'object' || !/^[a-z][a-z0-9_-]{0,63}$/.test(row.id) || ids.has(row.id) ||
        typeof row.label !== 'string' || !row.label.trim() || row.label.length > 128 ||
        typeof row.preset !== 'string' || !/^sss-[a-z0-9_-]+$/.test(row.preset) || presets.has(row.preset) ||
        !Array.isArray(row.allowed_tools) ||
        row.allowed_tools.some((tool: unknown) => typeof tool !== 'string' || !/^mcp__[a-z0-9_]+__[a-zA-Z0-9_]+$/.test(tool as string)) ||
        new Set(row.allowed_tools).size !== row.allowed_tools.length ||
        (row.unavailable_reason !== undefined && !/^[a-z][a-z0-9_]{0,127}$/.test(row.unavailable_reason)) ||
        (row.adapter !== undefined && (!['ppt', 'workspace', 'files', 'literature', 'data-report'].includes(row.adapter) || !Array.isArray(row.mcp_rows))) ||
        (row.instructions !== undefined && (typeof row.instructions !== 'string' || row.instructions.length > 100000))) {
      throw new SettingsError('invalid_registry', '场景 ID、工具或 preset 无效');
    }
    ids.add(row.id); presets.add(row.preset); return Object.freeze({ ...structuredClone(row), allowed_tools: Object.freeze([...row.allowed_tools]) });
  });
}
export function initialSelection(scene: string, mode: ExecutionMode): Selection {
  return { scene, mode, rsi: true };
}
export function changeSelection(current: Selection, patch: unknown, scenes: readonly Scene[], unavailable: (scene: Scene) => string | null): Selection {
  if (!patch || typeof patch !== 'object' || Array.isArray(patch) ||
      Object.keys(patch).some(key => !['scene', 'mode', 'rsi'].includes(key))) throw new SettingsError('invalid_selection', '只支持场景、模式和 RSI 开关');
  const row = patch as Record<string, unknown>, next = { ...current };
  if (row.scene !== undefined) {
    if (typeof row.scene !== 'string' || !scenes.some(scene => scene.id === row.scene)) throw new SettingsError('scene_not_found', '场景未登记，请从列表选择');
    next.scene = row.scene;
  }
  if (row.mode !== undefined) {
    if (!['baseline', 'shadow', 'execute'].includes(row.mode as string)) throw new SettingsError('invalid_mode', '模式必须是 baseline、shadow 或 execute');
    next.mode = row.mode as ExecutionMode;
  }
  if (row.rsi !== undefined) {
    if (typeof row.rsi !== 'boolean') throw new SettingsError('invalid_rsi', 'RSI 开关必须是 on 或 off');
    next.rsi = row.rsi;
  }
  const scene = scenes.find(scene => scene.id === next.scene)!;
  if (next.rsi && next.mode === 'execute') {
    const reason = unavailable(scene);
    if (reason) throw new SettingsError('execute_unavailable', `该场景暂不能 Execute：${reason}。可选择 Shadow。`);
  }
  return next;
}
export type Command = { kind: 'panel'; section: 'all' | 'mode' | 'rsi' } | { kind: 'status' | 'list' } | { kind: 'change'; patch: Record<string, unknown> };
export function parseHarlessCommand(rawInput: string): Command {
  const words = rawInput.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return { kind: 'panel', section: 'all' };
  const [action, value] = words;
  if (words.length > 2) throw new SettingsError('invalid_command', '请使用 /harless <场景>、mode、rsi、list 或 status');
  if (action === 'mode' || action === 'rsi') {
    if (words.length === 1) return { kind: 'panel', section: action };
    if (action === 'rsi' && !['on', 'off'].includes(value)) throw new SettingsError('invalid_rsi', '用 /harless rsi on 或 off，或使用输入框旁的 GeneLoop 菜单');
    return { kind: 'change', patch: { [action]: action === 'rsi' ? value === 'on' : value === 'origin' ? 'baseline' : value } };
  }
  if (words.length !== 1) throw new SettingsError('invalid_command', '场景名不接受附加参数');
  if (action === 'list' || action === 'status') return { kind: action };
  if (action === 'off') throw new SettingsError('invalid_command', '请用 /harless rsi off');
  return { kind: 'change', patch: { scene: action } };
}
