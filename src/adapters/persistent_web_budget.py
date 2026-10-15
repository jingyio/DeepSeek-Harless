"""Persist the existing whole-service State without resetting counters on restart."""
import threading
from pathlib import Path
from .deepseek_cost_gate import State
from src.motif_core.offline.experience_registry import read,durable
class PersistentState(State):
    def __init__(self,*,checkpoint,**kwargs):
        self.checkpoint_file=Path(checkpoint);super().__init__(**kwargs)
        if self.checkpoint_file.exists():
            s=read(self.checkpoint_file)
            if (s['cap_usd'],s['output_cap'],s['request_limit'])!=(self.cap_usd,self.output_cap,self.request_limit):raise ValueError('original service budget changed; use the original limits')
            self.request_count=s['request_count'];self.reserved_usd=s['reserved_usd'];self.pending={int(k):v for k,v in s['pending'].items()}
        self.checkpoint()
    def checkpoint(self):
        durable(self.checkpoint_file,{k:getattr(self,k) for k in ('cap_usd','output_cap','request_limit','request_count','reserved_usd','pending')})
