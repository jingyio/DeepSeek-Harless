"""Paper diagnostic MCP. All registered tools are genuinely read-only."""
from pathlib import Path
import json
import os
import sys
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from checks import PaperEvidence
from src.adapters.paper_query_recovery import validate_queries

def main():
    evidence = PaperEvidence(json.loads(Path(os.environ['SSS_PAPER_INPUTS']).read_text()), ROOT / '.local')
    server = MCPServer('SSS paper evidence')
    annotation = ToolAnnotations(readOnlyHint=True, destructiveHint=False)

    @server.tool(annotations=annotation)
    def pin_paper_sources(case_id: str) -> dict:
        """固定已授权论文的源码诊断视图及版本，返回只用于来源读取的 source_id。"""
        return evidence.pin(case_id, 'sources')

    @server.tool(annotations=annotation)
    def read_pinned_paper_sources(source_id: str) -> dict:
        """读取固定源码视图的活动引用/标签/浮动体诊断；不核验文献真实性。"""
        return evidence.read(source_id, 'sources')

    @server.tool(annotations=annotation)
    def pin_paper_build(case_id: str) -> dict:
        """固定已有编译日志和退出码记录及版本，返回 source_id；不执行编译或修复。"""
        return evidence.pin(case_id, 'build')

    @server.tool(annotations=annotation)
    def read_pinned_paper_build(source_id: str) -> dict:
        """读取固定编译视图的真实退出码和日志计数，缺失记录明确标为未知。"""
        return evidence.read(source_id, 'build')

    @server.tool(annotations=annotation)
    def pin_paper_pdf(case_id: str) -> dict:
        """固定已有 PDF 及版本，返回只用于元数据/字体检查的 source_id。"""
        return evidence.pin(case_id, 'pdf')

    @server.tool(annotations=annotation)
    def read_pinned_paper_pdf(source_id: str) -> dict:
        """读取固定 PDF 的页面数量和字体嵌入诊断；不执行视觉或会议合规判断。"""
        return evidence.read(source_id, 'pdf')

    # Existing six-tool experiments keep their schema/order unless explicitly enabled.
    if os.environ.get('SSS_PAPER_REFERENCE_RECORDS') == '1':
        @server.tool(annotations=annotation)
        def read_pinned_paper_references(source_id: str, keys: list[str]) -> dict:
            """批量读取已固定源码中指定引用键的完整 BibTeX、哈希、缺失及重复项；不判断真实性。"""
            return evidence.read_references(source_id, keys)

    if os.environ.get('SSS_PAPER_COMPOSITE_EVIDENCE') == '1':
        @server.tool(annotations=annotation)
        def collect_paper_citation_evidence(case_id: str) -> dict:
            """一次取得已登记稿件的活动引用诊断、全部原始BibTeX和批量arXiv元数据；保留来源版本与内部步骤。不执行科研判断、编译或写文件。"""
            return evidence.collect_citation_evidence(case_id)

    if os.environ.get('SSS_PAPER_CITATION_FLOW') == '1':
        @server.tool(annotations=annotation)
        def pin_paper_citations(case_id: str) -> dict:
            """固定已授权稿件的活动正文引用检查范围和源码版本，返回 source_id。"""
            return evidence.pin(case_id, 'sources')

        @server.tool(annotations=annotation)
        def read_pinned_paper_citations(source_id: str) -> dict:
            """检查活动正文引用对应，返回诊断及绑定真实 cited_keys 的 citation_id；不含 nocite。"""
            return evidence.inspect_citations(source_id)

        @server.tool(annotations=annotation)
        def read_pinned_citation_records(citation_id: str) -> dict:
            """读取 citation_id 绑定的全部正文引用原文/哈希/缺失/重复；不判断真实性或正式版本。"""
            return evidence.read_citation_records(citation_id)

        if os.environ.get('SSS_PAPER_ARXIV_BATCH') == '1':
            @server.tool(annotations=annotation)
            def fetch_pinned_cited_preprint_metadata(citation_id: str) -> dict:
                """批量获取该固定引用批次所有 arXiv 标识的官方 Atom 元数据；非正式版本/真实性判定。实际 HTTP 来源是 metadata.request_url，source_url 是论文记录定位页。"""
                return evidence.read_preprints(citation_id)

            if os.environ.get('SSS_PAPER_FORMAL_METADATA') == '1':
                @server.tool(annotations=annotation)
                def fetch_pinned_formal_reference_metadata(citation_id: str) -> dict:
                    """对固定批次的被引预印本，用原始/已取arXiv DOI或原始标题批量查询Crossref；返回原始著录候选及来源，不认证同一工作或替代版本。须先取得该批次arXiv元数据。"""
                    return evidence.read_formal_metadata(citation_id)

            if os.environ.get('SSS_PAPER_QUERY_RECOVERY'):
                path=Path(os.environ['SSS_PAPER_QUERY_RECOVERY']).resolve()
                if not path.is_relative_to((ROOT/'.local').resolve()) or path.stat().st_size>1000000:
                    raise ValueError('bounded private compiled query library required')
                library=json.loads(path.read_text());validate_queries(library)
                @server.tool(annotations=annotation)
                def recover_pinned_formal_reference_queries(citation_id: str) -> dict:
                    """按正常历史查询编译的受限协议，批量执行当前原始标题的完整词/已学前缀检索，供DOI查询失败或正式版本不明时恢复。仅Crossref/DBLP只读API，返回候选和来源；不确认同一工作或正式版本。"""
                    return evidence.recover_formal_queries(citation_id,library)

    server.run(transport='stdio')

if __name__ == '__main__': main()
