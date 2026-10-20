"""Process-local bounded vectors; never caches task decisions or tool evidence."""
from collections import OrderedDict

class VectorCache:
    def __init__(self, capacity=256):
        if capacity<1:raise ValueError('positive capacity required')
        self.capacity=capacity;self.entries=OrderedDict();self.hits=0;self.misses=0

    def resolve(self,texts,encode):
        missing=list(dict.fromkeys(t for t in texts if t not in self.entries))
        self.hits+=len(texts)-len(missing);self.misses+=len(missing)
        vectors=encode(missing) if missing else []
        if len(vectors)!=len(missing):raise ValueError('embedding vector count mismatch')
        available=dict(zip(missing,vectors))
        results=[]
        for text in texts:
            vector=available[text] if text in available else self.entries[text]
            self.entries[text]=vector;self.entries.move_to_end(text);results.append(vector)
        while len(self.entries)>self.capacity:self.entries.popitem(last=False)
        return results
