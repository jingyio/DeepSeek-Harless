/** Trusted scene deployment into the existing per-account bwrap; no auth changes. */
import { readdirSync, realpathSync, statSync, existsSync, lstatSync, readlinkSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join, relative, dirname, basename, isAbsolute, sep, resolve, posix } from 'node:path';
import {pptMasterInstallation} from '../src/adapters/geneloop_skill_installation.mjs';

const inside = (base, value) => value === base || (!relative(base, value).startsWith('..') && !isAbsolute(relative(base, value)));
function fixedPath(value, kind, label) {
  if (typeof value !== 'string' || !isAbsolute(value) || realpathSync(value) !== resolve(value) || lstatSync(value).isSymbolicLink() ||
      !(kind === 'file' ? statSync(value).isFile() : statSync(value).isDirectory()) || dirname(value) === value)
    throw Error('Member ' + label + ' must be a fixed installation without redirected paths');
  return realpathSync(value);
}
function containedInstallation(root) {
  // Distribution soname/documentation links may stay inside the read-only
  // installation; never follow a package link into an owner's home or secrets.
  const check = directory => {
    for (const entry of readdirSync(directory, {withFileTypes:true})) {
      const path=join(directory,entry.name);
      if (entry.isSymbolicLink()) {
        if (!inside(root,realpathSync(path))) throw Error('Member PDF parser link escapes its installation');
      } else if (entry.isDirectory()) check(path);
    }
  };
  check(root);
}
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
  const mappings = ['src', 'scripts', 'scenarios', 'benchmarks', 'motif-libraries'].filter(name=>existsSync(join(root,name))).map(name => {
    const source = realpathSync(join(root, name));
    if (!inside(root, source)) throw Error('Member code directory escapes the project');
    return { source, target: '/app/' + name };
  });
  const mounts = [...mappings, ...pythonRoots.map(source => ({ source, target: source }))];
  const skill=pptMasterInstallation(deployment.pptMasterRoot,root);
  if(skill){mounts.push(skill);mappings.push(skill);}
  if(policy.scenes.some(s=>!s.unavailable_reason&&s.ppt_execution_strategy==='ppt_master')&&!skill)
    throw Error('PPT scene requires a pinned ppt-master installation');
  // Only the explicit public config files in memberProductProfile are mounted.
  // Translate their certification locks without mounting the whole config directory.
  mappings.push({source:join(root,'config'),target:'/app/config'});
  const renderer=deployment.rendererRoot ? realpathSync(deployment.rendererRoot) : null;
  const fonts=deployment.fontRoot ? realpathSync(deployment.fontRoot) : null;
  const pdf=deployment.pdfToolchainRoot ? fixedPath(deployment.pdfToolchainRoot,'directory','PDF parser') : null;
  const antiword=deployment.antiwordRoot ? fixedPath(deployment.antiwordRoot,'directory','Word parser') : null;
  const attachmentEnvironment={};
  if(deployment.pdfOcrRoot){
    const ocr=fixedPath(deployment.pdfOcrRoot,'directory','PDF OCR');
    const languages=fixedPath(join(ocr,'tessdata'),'directory','PDF OCR languages');
    const manifest=JSON.parse(readFileSync(join(root,'config/pdf-ocr-assets.json'),'utf8'));
    if(readdirSync(ocr).some(name=>name!=='tessdata')||readdirSync(languages).some(name=>!Object.hasOwn(manifest.files,name)))
      throw Error('Member PDF OCR must contain only pinned public languages');
    for(const [name,digest] of Object.entries(manifest.files)){
      const path=fixedPath(join(languages,name),'file','PDF OCR language');
      if(createHash('sha256').update(readFileSync(path)).digest('hex')!==digest)throw Error('Member PDF OCR language hash mismatch');
    }
    mounts.push({source:ocr,target:'/opt/geneloop/pdf-ocr'});
    mappings.push({source:ocr,target:'/opt/geneloop/pdf-ocr'});
    attachmentEnvironment.GENELOOP_PDF_OCR_ROOT='/opt/geneloop/pdf-ocr';
  }
  if(pdf){
    if(pdf==='/' || !['pdfinfo','pdftotext'].every(name=>existsSync(join(pdf,'bin',name))) ||
       !existsSync(join(pdf,'lib/x86_64-linux-gnu')) ||
       readdirSync(pdf).some(name=>!['bin','lib','share','include'].includes(name)))
      throw Error('Member PDF parser must be a fixed Poppler installation');
    for(const name of ['pdfinfo','pdftotext'])fixedPath(join(pdf,'bin',name),'file','PDF parser executable');
    fixedPath(join(pdf,'lib/x86_64-linux-gnu'),'directory','PDF parser libraries');
    containedInstallation(pdf);
    // Existing bound literature presets still use the old absolute path.
    mounts.push({source:pdf,target:pdf});
    mounts.push({source:pdf,target:'/opt/harless/pdf'});
    mappings.push({source:pdf,target:'/opt/harless/pdf'});
    attachmentEnvironment.HARLESS_PDF_TOOLCHAIN_ROOT='/opt/harless/pdf';
  }
  let antiwordBinary,antiwordMappings;
  if(antiword){
    antiwordBinary=fixedPath(join(antiword,'usr/bin/antiword'),'file','Word parser executable');
    antiwordMappings=fixedPath(join(antiword,'usr/share/antiword'),'directory','Word parser mappings');
    fixedPath(join(antiwordMappings,'UTF-8.txt'),'file','Word UTF-8 mapping');
    if(readdirSync(antiwordMappings,{withFileTypes:true}).some(item=>!item.isFile() || item.isSymbolicLink() || item.name.startsWith('.')))
      throw Error('Member Word parser mappings must contain only fixed public resource files');
    const binaryTarget='/opt/harless/antiword/bin/antiword',mappingsTarget='/opt/harless/antiword/share/antiword';
    mounts.push({source:antiwordBinary,target:binaryTarget},{source:antiwordMappings,target:mappingsTarget});
    mappings.push({source:antiwordBinary,target:binaryTarget},{source:antiwordMappings,target:mappingsTarget});
    Object.assign(attachmentEnvironment,{HARLESS_ANTIWORD_BIN:binaryTarget,ANTIWORDHOME:mappingsTarget});
  }
  if(renderer){
    if(!existsSync(join(renderer,'program/soffice.bin')) || !existsSync(join(renderer,'share')))
      throw Error('Member renderer must be a LibreOffice installation');
    mounts.push({source:renderer,target:renderer});
  }
  if(fonts){
    const names=new Set(['fonts-static.conf','NotoSansCJKsc-Regular.otf','LICENSE.txt','wqy-microhei.ttc','WQY-COPYRIGHT.txt']);
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
    if(lstatSync(pptModules).isSymbolicLink()){
      // A release path may itself be a symlink to the real dependency store.
      // Mounting only realpath leaves the first hop dangling inside bwrap.
      const link=readlinkSync(pptModules);
      const target=isAbsolute(link)?resolve(link):posix.resolve('/app/scenarios/research_ppt',link.split(sep).join('/'));
      if(target!==source)mounts.push({source,target});
    }
  }
  if (deployment.libraryRoot) {
    const source = realpathSync(deployment.libraryRoot);
    if(source==='/')throw Error('Invalid member runtime library root');
    // Deploy only sanitized runtime artifacts; never mount historical raw traces or inputs.
    const allowed = new Set(['online-manifest.json','library.json','tool-schemas.json','task.json','certification.json','tool-schema-variants.json']);
    let count=0;
    const check = path => { for (const item of readdirSync(path, { withFileTypes: true })) {
      if(++count>128)throw Error('Member runtime library is too large');
      if (item.isSymbolicLink()) throw Error('Member library symlink rejected');
      const p=join(path,item.name);
      if (item.isDirectory()) check(p);
      else if (!item.isFile() || !allowed.has(item.name) || statSync(p).size>4000000) throw Error('Member library includes non-runtime private evidence');
    } };
    check(source); mounts.push({ source, target: '/app/private-motif-library' });
    mappings.unshift({ source, target: '/app/private-motif-library' });
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
    if (!['ppt','workspace','files','literature','data-report'].includes(scene.adapter) || Object.keys(scene.environment_references ?? {}).length)
      throw Error('Member scene requires a local Session adapter without inherited credentials');
    const rows = structuredClone(scene.mcp_rows);
    if (!Array.isArray(rows) || !rows.length) throw Error('Member scene has no MCP deployment');
    for (const row of rows) {
      const cfg=row.config;
      if (row.name !== '@deepseek-ai/dsh-mcp-client' || cfg?.transport !== 'stdio' || cfg.cwd !== root ||
          !['ppt','ppt_master','workspace','paper_checks','paper_trace_rsi','data_analysis','research_report','file_management','literature_web'].includes(cfg.serverName) ||
          !(cfg.command === 'node' || cfg.command === deployment.pythonExecutable || realpathSync(cfg.command) === binary) ||
          !Array.isArray(cfg.args) || !cfg.args.length || !inside(join(root,'scenarios'), cfg.args[cfg.args[0]==='--experimental-strip-types'?1:0]))
        throw Error('Member MCP deployment is outside approved scene code');
      if(scene.adapter==='files' && (cfg.serverName!=='file_management' || cfg.args.length!==1 ||
          cfg.args[0]!==join(root,'scenarios/file-management/plan_tools.py') ||
          cfg.env?.FM_WEB_WORKSPACE!=='__HARLESS_SESSION_WORKSPACE__' ||
          cfg.env?.FM_TASK_FILE!=='__HARLESS_SESSION_WORKSPACE__/file-task.json' ||
          cfg.env?.FM_OUTPUT!=='__HARLESS_SESSION_WORKSPACE__/file-results' ||
          Object.keys(cfg.env).length!==3))
        throw Error('Member Files MCP must use the server-bound task workspace');
      if(scene.id==='paper-proofreading' && cfg.serverName==='paper_checks' &&
         (cfg.args.length !== (paperRenderer ? 3 : 2) ||
          (paperRenderer && (scene.paper_renderer_root!==paperRenderer || cfg.args[2]!==paperRenderer))))
        throw Error('Member paper renderer is outside approved deployment');
      if(scene.adapter==='literature' && (cfg.serverName!=='literature_web' || cfg.args.length!==1 ||
          cfg.args[0]!==join(root,'scenarios/literature-notes/session_tools.py') ||
          cfg.env?.SSS_PDF_WEB_TASK!=='__HARLESS_SESSION_WORKSPACE__/literature'))
        throw Error('Member literature MCP must use uploaded Session sources');
      if(scene.adapter==='data-report' && (cfg.serverName!=='research_report' || cfg.args.length!==1 ||
          cfg.args[0]!==join(root,'scenarios/data_analysis/report_session.py') || cfg.env?.HARLESS_REPORT_WORKSPACE!=='__HARLESS_SESSION_WORKSPACE__'))
        throw Error('Member data report requires the registered Session adapter');
      cfg.command=cfg.command === 'node' ? 'node' : executable;
      cfg.cwd='/app'; cfg.args=cfg.args.map(translate);
      const env=cfg.env ?? {};
      const parserEnv=['HARLESS_PDF_TOOLCHAIN_ROOT','HARLESS_ANTIWORD_BIN','ANTIWORDHOME','GENELOOP_PDF_OCR_ROOT'];
      const permittedEnv=scene.adapter==='data-report'?['HARLESS_REPORT_WORKSPACE','HARLESS_PRIVATE_ROOT','HARLESS_REPORT_FONT',...parserEnv]:scene.adapter==='literature' ? ['SSS_PDF_WEB_TASK','PATH','LD_LIBRARY_PATH'] :
        scene.adapter==='files' ? ['FM_WEB_WORKSPACE','FM_TASK_FILE','FM_OUTPUT'] :
        cfg.serverName==='paper_checks'?['HARLESS_REPORT_FONT',...parserEnv]:
        cfg.serverName==='paper_trace_rsi'?['HARLESS_PRIVATE_ROOT']:
        cfg.serverName==='ppt_master'?['GENELOOP_PPT_MASTER_ROOT','PYTHONDONTWRITEBYTECODE',...parserEnv]:
        ['SSS_PPT_JOB','SSS_PPT_DELIVERY_PYTHON','PATH','FONTCONFIG_FILE','FONTCONFIG_PATH','HARLESS_PRIVATE_ROOT',...parserEnv];
      if (Object.keys(env).some(k=>!permittedEnv.includes(k)))
        throw Error('Member scene environment contains unapproved authority');
      if(cfg.serverName==='ppt_master' && (!skill || cfg.args.length!==2 ||
          cfg.args[0]!=='/app/scenarios/ppt_master/server.py' || cfg.args[1]!=='__HARLESS_SESSION_WORKSPACE__/inputs' || env.GENELOOP_PPT_MASTER_ROOT!==skill.source))
        throw Error('Member ppt-master requires the exact pinned deployment');
      if(scene.adapter==='data-report'||scene.adapter==='ppt'||cfg.serverName==='paper_checks'){
        if(env.GENELOOP_PDF_OCR_ROOT && env.GENELOOP_PDF_OCR_ROOT!==deployment.pdfOcrRoot)
          throw Error('Member PDF OCR requires the matching fixed installation');
        if(('HARLESS_PDF_TOOLCHAIN_ROOT' in env || scene.pdf_toolchain_root!==undefined) &&
            (!pdf || scene.pdf_toolchain_root!==pdf || env.HARLESS_PDF_TOOLCHAIN_ROOT!==pdf))
          throw Error('Member report PDF parser requires the matching fixed installation');
        if(('HARLESS_ANTIWORD_BIN' in env || 'ANTIWORDHOME' in env || scene.antiword_root!==undefined) &&
            (!antiword || scene.antiword_root!==antiword || env.HARLESS_ANTIWORD_BIN!==antiwordBinary || env.ANTIWORDHOME!==antiwordMappings))
          throw Error('Member report Word parser requires the matching fixed installation');
      }
      if((scene.adapter==='data-report'||cfg.serverName==='paper_checks') && ('HARLESS_REPORT_FONT' in env || scene.report_font_sha256!==undefined)){
        const font=fonts && join(fonts,'wqy-microhei.ttc');
        if(!font || env.HARLESS_REPORT_FONT!==font || !existsSync(font) ||
           !/^[a-f0-9]{64}$/.test(scene.report_font_sha256 ?? '') ||
           createHash('sha256').update(readFileSync(font)).digest('hex')!==scene.report_font_sha256)
          throw Error('Member report font requires the matching fixed public font and SHA-256');
      }
      if(scene.adapter==='literature'){
        if((env.PATH || env.LD_LIBRARY_PATH) && (!pdf || scene.pdf_toolchain_root!==pdf ||
            env.PATH!==join(pdf,'bin')+':/usr/bin:/bin' || env.LD_LIBRARY_PATH!==join(pdf,'lib/x86_64-linux-gnu')))
          throw Error('Member literature parser environment requires the matching installation');
      }else if((env.PATH && (!renderer || scene.renderer_root!==renderer)) ||
         (env.FONTCONFIG_FILE && (!fonts || env.FONTCONFIG_FILE!==join(fonts,'fonts-static.conf') || env.FONTCONFIG_PATH!==fonts)))
        throw Error('Member renderer/font environment requires explicit matching installations');
      cfg.env=Object.fromEntries(Object.entries(env).map(([k,v])=>[k,k==='SSS_PPT_DELIVERY_PYTHON'?executable:translate(v)]));
      if(env.HARLESS_PRIVATE_ROOT){
        if(env.HARLESS_PRIVATE_ROOT!==policy.output)throw Error('Member private root must be the server-owned task output');
        cfg.env.HARLESS_PRIVATE_ROOT='/app/.local/web';
      }
      if(cfg.env.PATH && scene.adapter!=='literature')cfg.env.PATH=join(renderer,'program')+':/opt/node/bin:/usr/bin:/bin';
    }
    const next={...structuredClone(scene),mcp_rows:rows};
    if(next.pdf_toolchain_root)next.pdf_toolchain_root=translate(next.pdf_toolchain_root);
    if(next.antiword_root)next.antiword_root='/opt/harless/antiword';
    for(const key of ['manifest','task','tool_schemas','certification_path','runtime_library']) if(next[key]) {
      if(!inside(join(root,'motif-libraries'),next[key]) && (!deployment.libraryRoot || !inside(realpathSync(deployment.libraryRoot),next[key])))
        throw Error('Member Motif library is outside sanitized runtime artifacts');
      next[key]=translate(next[key]);
    }
    if(next.certified_code_locks)next.certified_code_locks=Object.fromEntries(Object.entries(next.certified_code_locks).map(([path,sha])=>[translate(path),sha]));
    return next;
  });
  // Native skill and filesystem adapters execute inside the account namespace.
  // Derive their public resource paths from these verified mounts, independently
  // of the host paths retained by the gateway's command broker.
  const native_resources={projectRoot:'/app',...(skill?{pptMasterRoot:skill.target}:{}),
    ...(renderer?{rendererRoot:renderer}:{}),...(fonts?{fontRoot:fonts}:{})};
  return {scenes,mounts,native_resources,allowed_tools:[...new Set(scenes.filter(s=>!s.unavailable_reason).flatMap(s=>s.allowed_tools))],
    output:'/app/.local/web',python:executable,attachmentEnvironment};
}
