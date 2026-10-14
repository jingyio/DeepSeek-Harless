import {readFileSync} from 'node:fs';
import {baseProgram, certify, permits, validateProgram} from './guard.js';
try {
  const input = JSON.parse(readFileSync(0,'utf8'));
  console.log(JSON.stringify(input.action === 'evaluate'
    ? {allowed: input.facts.every((facts: any) => permits(validateProgram(input.program),facts))}
    : certify(input.action === 'default' ? baseProgram : input)));
}
catch(error) { console.log(JSON.stringify({accepted:false, error:String(error)})); process.exitCode=2; }
