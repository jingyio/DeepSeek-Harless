/** Keep the browser command picker in Harness's native client plugin graph. */
import {name, inject, apply as applyMain} from '../dsh_web_tasks.ts';
import {installFileScene} from '../harless_file_scene.ts';
export {name, inject};
export function apply(ctx) {
  applyMain(ctx);
  installFileScene(ctx);
}
