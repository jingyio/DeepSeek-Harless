"""GeneLoop default entry; preserve explicit legacy file RSI experiments."""
from pathlib import Path
import importlib.util,sys
HERE=Path(__file__).resolve().parent
def load(name):
 spec=importlib.util.spec_from_file_location('sss_'+name.replace('-','_'),HERE/(name+'.py'))
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
legacy=load('harness-web-legacy');geneloop=load('harness-geneloop')
def __getattr__(name):return getattr(geneloop,name) if hasattr(geneloop,name) else getattr(legacy,name)
def prepare(args,*rest):
 return (legacy if args.scenario=='file-management' or hasattr(args,'files_dir') or hasattr(args,'papers_dir') else geneloop).prepare(args,*rest)
def main():
 use_legacy=any(v in sys.argv for v in ('--files-dir','--papers-dir','--rsi-config','file-management'))
 if '--geneloop' in sys.argv:sys.argv.remove('--geneloop');use_legacy=False
 (legacy if use_legacy else geneloop).main()
if __name__=='__main__':main()
