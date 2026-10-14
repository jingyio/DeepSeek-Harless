/** Trusted scene deployment into the existing per-account bwrap; no auth changes. */
import { readdirSync, realpathSync, statSync, existsSync } from 'node:fs';
import { join, relative, dirname, basename, isAbsolute, sep } from 'node:path';

const inside = (base, value) => value === base || (!relative(base, value).startsWith('..') && !isAbsolute(relative(base, value)));
export function memberSceneDeployment(policy, deployment) {
  if (!deployment) return null; // Legacy explicit chat-only deployment remains supported.
  const root = realpathSync(deployment.projectRoot);
  if (root === '/' || !Array.isArray(policy.scenes) || !Array.isArray(deployment.pythonRoots) || !deployment.pythonRoots.length)
    throw Error('Invalid member scene deployment');
  const pythonRoots = deployment.pythonRoots.map(path => {
    const p = realpathSync(path);
    if (!isAbsolute(p) || p === '/' || !statSync(p).isDirectory() || /\/(?:\.ssh|credentials|secrets)(?:\/|$)/.test(p))
      throw Error('Invalid member Python dependency root');
    const children=readdirSync(p);
    if(children.some(name=>['.env','.credentials.yaml','accounts.json','.ssh'].includes(name)) ||
       !(children.includes('pyvenv.cfg') || (children.includes('bin') && children.includes('lib') &&
          readdirSync(join(p,'lib')).some(name=>/^python\d+\.\d+$/.test(name)))))
      throw Error('Member Python mount must be an installation, not a user or project directory');
    return p;
  });
  const executable = join(realpathSync(dirname(deployment.pythonExecutable)), basename(deployment.pythonExecutable));
  const binary = realpathSync(executable);
  if (!pythonRoots.some(p => inside(p, binary)) || !pythonRoots.some(p=>inside(p,executable)) || !statSync(binary).isFile())
    throw Error('Member Python executable is outside mounted dependencies');
  const mappings = ['src', 'scripts', 'scenarios'].map(name => {
    const source = realpathSync(join(root, name));
    if (!inside(root, source)) throw Error('Member code directory escapes the project');
    return { source, target: '/app/' + name };
  });
  const mounts = [...mappings, ...pythonRoots.map(source => ({ source, target: source }))];
  const renderer=deployment.rendererRoot ? realpathSync(deployment.rendererRoot) : null;
  const fonts=deployment.fontRoot ? realpathSync(deployment.fontRoot) : null;
  if(renderer){
    if(!existsSync(join(renderer,'program/soffice.bin')) || !existsSync(join(renderer,'share')))
      throw Error('Member renderer must be a LibreOffice installation');
    mounts.push({source:renderer,target:renderer});
  }
  if(fonts){
    const names=new Set(['fonts-static.conf','NotoSansCJKsc-Regular.otf','LICENSE.txt']);
    if(!existsSync(join(fonts,'NotoSansCJKsc-Regular.otf')) || readdirSync(fonts,{withFileTypes:true}).some(f=>!f.isFile() || !names.has(f.name)))
      throw Error('Member fonts must contain only fixed public font resources');
    mounts.push({source:fonts,target:fonts});
  }
  const paperRenderer=deployment.paperRendererRoot ? realpathSync(deployment.paperRendererRoot) : null;
  if(paperRenderer){
    const same=(path,names)=>new Set(readdirSync(path)).size===names.length &&
      readdirSync(path).every(name=>names.includes(name));
    if(!same(paperRenderer,['deployment.json','review.json','package']) ||
       !same(join(paperRenderer,'package'),['manifest.json','generated-original.py','generated-bound.py','font.ttf','input-schema.json']))
      throw Error('Member paper renderer must contain only reviewed deployment files');
    mounts.push({source:paperRenderer,target:'/app/paper-renderer'});
    mappings.push({source:paperRenderer,target:'/app/paper-renderer'});
  }
  const pptModules=join(root,'scenarios/research_ppt/node_modules');
  if(existsSync(pptModules)){
    const source=realpathSync(pptModules);
    if(basename(source)!=='node_modules')throw Error('PPT dependencies must be an installed node_modules directory');
    // Preserve the target of an installation symlink without exposing its parent checkout.
    mounts.push({source,target:source});
  }
  if (deployment.libraryRoot) {
    const source = realpathSync(deployment.libraryRoot);
    if(source==='/')throw Error('Invalid member runtime library root');
    // Deploy only sanitized runtime artifacts; never mount historical raw traces or inputs.
    const allowed = new Set(['online-manifest.json','library.json','tool-schemas.json','task.json','certification.json']);
    let count=0;
    const check = path => { for (const item of readdirSync(path, { withFileTypes: true })) {
      if(++count>128)throw Error('Member runtime library is too large');
      if (item.isSymbolicLink()) throw Error('Member library symlink rejected');
      const p=join(path,item.name);
      if (item.isDirectory()) check(p);
      else if (!item.isFile() || !allowed.has(item.name) || statSync(p).size>4000000) throw Error('Member library includes non-runtime private evidence');
    } };
    check(source); mounts.push({ source, target: '/app/motif-libraries' });
    mappings.push({ source, target: '/app/motif-libraries' });
  }
  const translate = value => {
    if (typeof value !== 'string') return value;
    if (value === root) return '/app';
    for (const {source,target} of mappings) if (inside(source, value))
      return target + value.slice(source.length).split(sep).join('/');
    return value;
  };
  const scenes = policy.scenes.map(scene => {
    if (scene.unavailable_reason) return structuredClone(scene);
    if (!['ppt','workspace','files'].includes(scene.adapter) || Object.keys(scene.environment_references ?? {}).length)
      throw Error('Member scene requires a local Session adapter without inherited credentials');
    const rows = structuredClone(scene.mcp_rows);
    if (!Array.isArray(rows) || !rows.length) throw Error('Member scene has no MCP deployment');
    for (const row of rows) {
      const cfg=row.config;
      if (row.name !== '@deepseek-ai/dsh-mcp-client' || cfg?.transport !== 'stdio' || cfg.cwd !== root ||
          !['ppt','workspace','paper_checks','data_analysis','file_management'].includes(cfg.serverName) ||
          !(cfg.command === 'node' || cfg.command === deployment.pythonExecutable || realpathSync(cfg.command) === binary) ||
          !Array.isArray(cfg.args) || !cfg.args.length || !inside(join(root,'scenarios'), cfg.args[0]))
        throw Error('Member MCP deployment is outside approved scene code');
      if(scene.adapter==='files' && (cfg.serverName!=='file_management' || cfg.args.length!==1 ||
          cfg.args[0]!==join(root,'scenarios/file-management/plan_tools.py') ||
          cfg.env?.FM_WEB_WORKSPACE!=='__HARLESS_SESSION_WORKSPACE__' ||
          cfg.env?.FM_TASK_FILE!=='__HARLESS_SESSION_WORKSPACE__/file-task.json' ||
          cfg.env?.FM_OUTPUT!=='__HARLESS_SESSION_WORKSPACE__/file-results' ||
          Object.keys(cfg.env).length!==3))
        throw Error('Member Files MCP must use the server-bound task workspace');
      if(scene.id==='paper-proofreading' &&
         (cfg.args.length !== (paperRenderer ? 3 : 2) ||
          (paperRenderer && (scene.paper_renderer_root!==paperRenderer || cfg.args[2]!==paperRenderer))))
        throw Error('Member paper renderer is outside approved deployment');
      cfg.command=cfg.command === 'node' ? 'node' : executable;
      cfg.cwd='/app'; cfg.args=cfg.args.map(translate);
      const env=cfg.env ?? {};
      const permittedEnv=scene.adapter==='files' ? ['FM_WEB_WORKSPACE','FM_TASK_FILE','FM_OUTPUT'] :
        ['SSS_PPT_JOB','SSS_PPT_DELIVERY_PYTHON','PATH','FONTCONFIG_FILE','FONTCONFIG_PATH'];
      if (Object.keys(env).some(k=>!permittedEnv.includes(k)))
        throw Error('Member scene environment contains unapproved authority');
      if((env.PATH && (!renderer || scene.renderer_root!==renderer)) ||
         (env.FONTCONFIG_FILE && (!fonts || env.FONTCONFIG_FILE!==join(fonts,'fonts-static.conf') || env.FONTCONFIG_PATH!==fonts)))
        throw Error('Member renderer/font environment requires explicit matching installations');
      cfg.env=Object.fromEntries(Object.entries(env).map(([k,v])=>[k,k==='SSS_PPT_DELIVERY_PYTHON'?executable:translate(v)]));
      if(cfg.env.PATH)cfg.env.PATH=join(renderer,'program')+':/opt/node/bin:/usr/bin:/bin';
    }
    const next={...structuredClone(scene),mcp_rows:rows};
    for(const key of ['manifest','task','tool_schemas','certification_path']) if(next[key]) {
      if(!deployment.libraryRoot || !inside(realpathSync(deployment.libraryRoot),next[key]))
        throw Error('Member Motif library is outside sanitized runtime artifacts');
      next[key]=translate(next[key]);
    }
    if(next.certified_code_locks)next.certified_code_locks=Object.fromEntries(Object.entries(next.certified_code_locks).map(([path,sha])=>[translate(path),sha]));
    return next;
  });
  return {scenes,mounts,allowed_tools:[...new Set(scenes.filter(s=>!s.unavailable_reason).flatMap(s=>s.allowed_tools))],
    output:'/app/.local/web',python:executable};
}
