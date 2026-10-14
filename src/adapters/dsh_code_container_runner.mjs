/** Runs the actual upstream worker-thread backend inside an isolated container. */
import { createInterface } from 'node:readline';
import { Context } from '@deepseek-ai/cordis';
import { WorkerThreadCodeRuntime } from '@deepseek-ai/dsh-code-runtime-worker-thread';
const input = createInterface({ input: process.stdin }), waiting = new Map();
let sequence = 0, started = false;
const send = value => process.stdout.write(JSON.stringify(value) + '\n');
input.on('line', async text => {
  try {
    const message = JSON.parse(text);
    if (message.type === 'response') {
      const pending = waiting.get(message.id); if (!pending) return; waiting.delete(message.id);
      if (message.error) pending.reject(Error(message.error)); else pending.resolve(message.value);
      return;
    }
    if (message.type !== 'run' || started) throw Error('invalid or duplicate run'); started = true;
    const ctx = new Context();
    const runtime = new WorkerThreadCodeRuntime(ctx, { computeMs: 10000, maxWallMs: 60000,
      maxOutputBytes: 1048576, maxOldGenerationSizeMb: 128 });
    const bindings = message.bindings.map(namespace => ({ global: namespace.global,
      ...(namespace.errorClass ? {errorClass:namespace.errorClass}:{}),
      functions: Object.fromEntries(namespace.members.map(member => [member, args => new Promise((resolve,reject) => {
        const id = ++sequence; waiting.set(id,{resolve,reject}); send({type:'call',id,global:namespace.global,member,args});
      })])) }));
    const result = await runtime.run({ program: message.program, bindings });
    await runtime.teardown(); send({type:'done',result}); input.close(); process.exit(0);
  } catch (error) { send({type:'done',result:{error:{kind:'exception',message:String(error)},logs:[]}}); input.close();process.exit(0); }
});
