/** Register Distil's recovery name in DSH for mixed recovery/research tool turns.
 *
 * Distil resolves a pure distil_expand turn internally. If an assistant also
 * calls a client tool, its proxy forwards the whole batch, so DSH must be able
 * to execute the same name against the per-run private restore store.
 */

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { defineTool } from '@deepseek-ai/dsh-tools';

const execFileAsync = promisify(execFile);
export const name = 'sss-distil-expand-bridge';
export const inject = ['tools'];

export function apply(ctx) {
  ctx.tools.register(defineTool({
    name: 'distil_expand',
    description: 'Recover the original text for a Distil context handle from this run\'s local store.',
    parameters: {
      handle: { type: 'string', required: true, description: 'Eight hexadecimal characters from handle=XXXXXXXX.' },
    },
    output: {
      schema: { type: 'object', additionalProperties: false,
        properties: { content: { type: 'string', required: true } } },
      render: (_args, value) => [{ type: 'text', text: value.content }],
    },
    async execute(args) {
      if (!/^[0-9a-f]{8}$/.test(args.handle)) throw new Error('Invalid Distil handle');
      if (!process.env.SSS_DISTIL_HOME || !process.env.SSS_MCP_PYTHON) {
        throw new Error('Distil recovery is unavailable in this session');
      }
      const code = 'from distil.mcp_server import load_restore; import sys; '
        + 'value=load_restore(sys.argv[1]); '
        + 'sys.exit(2) if value is None else sys.stdout.write(value)';
      try {
        const { stdout } = await execFileAsync(process.env.SSS_MCP_PYTHON,
          ['-c', code, args.handle], { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024,
            timeout: 10000, env: { ...process.env, DISTIL_HOME: process.env.SSS_DISTIL_HOME } });
        return { content: stdout };
      } catch {
        throw new Error('Original content is unavailable; reread the approved source');
      }
    },
  }));
}
