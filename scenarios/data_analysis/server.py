"""Actual bounded CSV/TSV analysis; no arbitrary Python, shell or fabricated data."""
from pathlib import Path
import csv
import io
import math
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.adapters.session_files import SessionFiles
from mcp.server import MCPServer
from mcp.types import ToolAnnotations


class DatasetEvidence(SessionFiles):
    def dataset(self, source_id):
        name, data, version = self.pinned(source_id)
        suffix = Path(name).suffix.lower()
        if suffix not in ('.csv', '.tsv'): raise ValueError('csv_or_tsv_required')
        text = data.decode('utf-8-sig', errors='strict')
        reader = csv.reader(io.StringIO(text, newline=''), delimiter='\t' if suffix == '.tsv' else ',', strict=True)
        header = next(reader, [])
        if (not header or len(header) > 128 or len(set(header)) != len(header) or
                any(not x or len(x) > 256 for x in header)): raise ValueError('invalid_or_duplicate_columns')
        rows = []
        for row in reader:
            if len(row) != len(header): raise ValueError('ragged_dataset')
            if len(rows) >= 100000: raise ValueError('dataset_row_limit')
            rows.append(row)
        self.pinned(source_id)  # Recheck version after analysis preparation.
        return header, rows, version

    def summary(self, source_id):
        header, rows, version = self.dataset(source_id)
        columns = []
        for i, name in enumerate(header):
            cells = [r[i].strip() for r in rows]
            nonempty = [x for x in cells if x]
            numeric = []
            for x in nonempty:
                try: v = float(x)
                except ValueError: break
                if not math.isfinite(v): break
                numeric.append(v)
            is_numeric = bool(nonempty) and len(numeric) == len(nonempty)
            columns.append({'name': name, 'missing': len(cells) - len(nonempty),
                            'kind': 'finite_numeric' if is_numeric else 'text_or_nonfinite',
                            'unique_nonempty': len(set(nonempty)),
                            'numeric': {'count': len(numeric), 'mean': statistics.fmean(numeric),
                                        'median': statistics.median(numeric), 'min': min(numeric), 'max': max(numeric),
                                        'sample_stddev': statistics.stdev(numeric) if len(numeric) > 1 else None}
                            if is_numeric else None})
        self.pinned(source_id)
        return {'source_id': source_id, 'version_sha256': version, 'rows': len(rows), 'columns': columns,
                'coverage': 'descriptive_statistics_only_no_imputation_or_causal_claims'}

    def correlation(self, source_id, x, y):
        header, rows, version = self.dataset(source_id)
        if x == y or x not in header or y not in header: raise ValueError('two_distinct_columns_required')
        i, j = header.index(x), header.index(y)
        pairs = []
        for row in rows:
            if not row[i].strip() or not row[j].strip(): continue
            try: left, right = float(row[i]), float(row[j])
            except ValueError: raise ValueError('correlation_requires_numeric_columns') from None
            if not math.isfinite(left) or not math.isfinite(right): raise ValueError('nonfinite_data')
            pairs.append((left, right))
        if len(pairs) < 2: raise ValueError('insufficient_complete_pairs')
        a, b = zip(*pairs)
        # Normalize before summing to avoid overflow from large finite inputs.
        sa, sb = max(map(abs, a)), max(map(abs, b))
        if sa == 0 or sb == 0: raise ValueError('constant_column')
        a, b = [v / sa for v in a], [v / sb for v in b]
        ma, mb = statistics.fmean(a), statistics.fmean(b)
        aa, bb = sum((v-ma)**2 for v in a), sum((v-mb)**2 for v in b)
        if not aa or not bb: raise ValueError('constant_column')
        value = sum((u-ma)*(v-mb) for u,v in zip(a,b)) / math.sqrt(aa*bb)
        self.pinned(source_id)
        return {'source_id': source_id, 'version_sha256': version, 'x': x, 'y': y,
                'pearson_r': max(-1., min(1., value)), 'complete_pairs': len(pairs),
                'excluded_missing_pairs': len(rows)-len(pairs), 'causality_established': False}


def create_server(directory):
    files = DatasetEvidence(directory)
    server = MCPServer('Harless uploaded research data')
    annotation = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @server.tool(annotations=annotation)
    def list_inputs() -> dict:
        """List only this Session's uploaded CSV/TSV files and their exact SHA256."""
        return files.list_files()

    @server.tool(annotations=annotation)
    def pin_dataset(name: str, sha256: str) -> dict:
        """Pin one listed UTF-8 CSV/TSV version to a fresh Session-local source_id."""
        if Path(name).suffix.lower() not in ('.csv', '.tsv'): raise ValueError('csv_or_tsv_required')
        return files.pin(name, sha256)

    @server.tool(annotations=annotation)
    def read_pinned_dataset_summary(source_id: str) -> dict:
        """Read row counts, missingness, types and descriptive numeric statistics; recheck the pinned bytes."""
        return files.summary(source_id)

    @server.tool(annotations=annotation)
    def correlate_pinned_columns(source_id: str, x: str, y: str) -> dict:
        """Calculate Pearson r for two finite numeric columns using complete pairs, with exclusion counts; no causal claim."""
        return files.correlation(source_id, x, y)

    return server


if __name__ == '__main__': create_server(Path(sys.argv[1])).run(transport='stdio')
