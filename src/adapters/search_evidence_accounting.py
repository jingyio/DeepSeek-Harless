"""Opt-in experiment instrumentation around the unchanged admitted cost gate.

No queries, page bodies, keys or encrypted source contents enter the ledger.
The protected native request event can be joined by request_sha256 offline.
The private Handler seam belongs to this repository; it is not a Harness patch.
"""
import hashlib
import json


def search_response_trace(request: dict, answer: bytes) -> dict:
    trace = {'request_sha256': hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}
    try:
        blocks = json.loads(answer).get('content', [])
        results = [b for b in blocks if isinstance(b, dict) and b.get('type') == 'web_search_tool_result']
        items = [s for b in results for s in b.get('content', []) if isinstance(s, dict)]
        trace.update(server_tool_calls=sum(isinstance(b, dict) and b.get('type') == 'server_tool_use' for b in blocks),
                     result_blocks=len(results), source_items=len(items),
                     source_item_fields=sorted({k for s in items for k in s}),
                     text_citations=sum(len(b.get('citations') or []) for b in blocks if isinstance(b, dict) and b.get('type') == 'text'))
    except (ValueError, TypeError, AttributeError):
        trace['response_shape_known'] = False
    return trace


def instrument_search_server(server):
    """Add metadata to the existing settled row, leaving admission/fees intact."""
    base = server.RequestHandlerClass
    class TracedHandler(base):
        _search_trace = None
        def _call_upstream(self, body, method, **kwargs):
            self._search_trace = None
            result = super()._call_upstream(body, method, **kwargs)
            if self.path.startswith('/v1/search/'):
                try:self._search_trace = search_response_trace(json.loads(body), result[2])
                except (ValueError, TypeError):pass
            return result

        def _state(self):
            state = super()._state()
            handler = self
            class ObservedState:
                def __getattr__(self, key):return getattr(state, key)
                def log(self, row):
                    if row.get('kind') == 'web_search' and handler._search_trace is not None:
                        row = {**row, 'search_trace': handler._search_trace}
                    return state.log(row)
            return ObservedState()
    server.RequestHandlerClass = TracedHandler
    return server
